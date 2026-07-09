"""
Spectraloop — QA Router
------------------------
Küratörlü bilgi tabanına dayalı deterministik cevap yönlendirici.

Yönlendirme sırası:
  1. KEYWORD  : Sorgu normalize edilir; herhangi bir variant metni sorgu içinde
                geçiyorsa o cevap anında döndürülür. Embedding gerekmez.
  2. SEMANTIC : Hibrit skor = W_SEM * cosine + W_LEX * lexical (RapidFuzz).
                Üç bantlı karar:
                  final >= T_HIGH              → answer
                  T_MED <= final < T_HIGH      → margin >= MARGIN_MIN → answer
                                                 margin <  MARGIN_MIN → confirm / repeat
                  final < T_MED               → llm (grounded Ollama fallback)
  3. FALLBACK : karar "llm" ise brain.py grounded Ollama'ya geçer.

Config  : spectra_config.py
Loglama : logs/qa_misses.jsonl — STT metadata, top1/top2 skor, karar dahil
Singleton: get_router() ile modül genelinde tek örnek kullanılır.
"""

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import numpy as np
import requests

import spectra_config as cfg

# ── RapidFuzz (opsiyonel; yoksa difflib fallback) ─────────────────────────────
try:
    from rapidfuzz.fuzz import token_set_ratio as _rf_tsr

    def _lexical(a: str, b: str) -> float:
        """RapidFuzz token_set_ratio → [0, 1]"""
        return _rf_tsr(a, b) / 100.0

except ImportError:
    import difflib

    def _lexical(a: str, b: str) -> float:  # type: ignore[misc]
        """difflib fallback — yükle: pip install rapidfuzz"""
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()

# ── Config ────────────────────────────────────────────────────────────────────
QA_CONFIG: dict = {
    "embed_model": "nomic-embed-text",
    "chat_model":  "qwen2.5:3b",
    "threshold":   cfg.T_HIGH,   # geriye dönük uyumluluk; asıl eşikler spectra_config'de
    "top_k":       3,
}

# ── Yollar ───────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).parent
_QA_PATH  = _BASE_DIR / "knowledge" / "qa_base.json"
_LOG_PATH = _BASE_DIR / "logs" / "qa_misses.jsonl"
_LOG_PATH.parent.mkdir(exist_ok=True)

_EMBED_URL = "http://localhost:11434/api/embeddings"

# Grounding'den hariç tutulacak kategori prefix'leri (kişiye özel / VIP)
_GROUNDING_SKIP_CATEGORIES = {"kisiye_ozel_vip", "kisiye_ozel_takim"}

# CONFIRM_MODE için okunabilir kategori isimleri
_CATEGORY_DISPLAY: Dict[str, str] = {
    "tanitim":           "Takım ve proje tanıtımı",
    "teknik_itki":       "İtki sistemi",
    "teknik_enerji":     "Enerji ve batarya sistemi",
    "teknik_fren":       "Fren sistemi",
    "teknik_kontrol":    "Kontrol sistemi",
    "teknik_detay":      "Teknik detaylar",
    "guvenlik":          "Güvenlik",
    "yarisma_vizyon":    "Yarışma ve vizyon",
    "etkilesim":         "Genel konuşma",
    "proje_detay":       "Proje detayları",
    "sohbet":            "Sohbet",
    "kisiye_ozel_vip":   "VIP protokol",
    "kisiye_ozel_takim": "Takım üyeleri",
}


# ── Normalizasyon ─────────────────────────────────────────────────────────────
def _norm_kw(s: str) -> str:
    """Keyword eşleştirmesi için: küçük harf, Türkçe → ASCII, noktalama → boşluk."""
    s = s.lower().strip()
    for tr, en in [
        ("ı", "i"), ("İ", "i"), ("ğ", "g"), ("Ğ", "g"),
        ("ş", "s"), ("Ş", "s"), ("ç", "c"), ("Ç", "c"),
        ("ö", "o"), ("Ö", "o"), ("ü", "u"), ("Ü", "u"),
    ]:
        s = s.replace(tr, en)
    return re.sub(r"[^\w\s]", " ", s)


# ── Embedding ─────────────────────────────────────────────────────────────────
def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 1e-9 else 0.0


def _embed(text: str, model: str) -> np.ndarray:
    resp = requests.post(
        _EMBED_URL,
        json={"model": model, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return np.array(resp.json()["embedding"], dtype=np.float32)


# ── Loglama ───────────────────────────────────────────────────────────────────
def _log(
    query:      str,
    matched_id: Optional[str],
    score:      float,
    matched:    bool,
    match_type: str = "semantic",
    *,
    stt_meta:   Optional[Dict[str, Any]] = None,
    decision:   str  = "answer",
    top1_id:    Optional[str]  = None,
    top2_id:    Optional[str]  = None,
    top1_score: float = 0.0,
    top2_score: float = 0.0,
) -> None:
    try:
        record: Dict[str, Any] = {
            "ts":         datetime.now().isoformat(timespec="seconds"),
            "query":      query,
            "matched":    matched,
            "match_type": match_type,
            "id":         matched_id,
            "score":      round(score, 4),
            "decision":   decision,
            "top1_id":    top1_id,
            "top1_score": round(top1_score, 4),
            "top2_id":    top2_id,
            "top2_score": round(top2_score, 4),
        }
        if stt_meta:
            record["stt"] = stt_meta
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── Router Sınıfı ─────────────────────────────────────────────────────────────
class QARouter:
    """
    Kullanım (singleton tercih edilir):
        from qa_router import get_router
        answer, decision, score, top1_id, top2_id = get_router().route_v2("İtki sistemi nasıl çalışıyor?")
    """

    def __init__(self) -> None:
        self._entries:   list  = []
        self._ready:     bool  = False
        self._top_k:     int   = QA_CONFIG["top_k"]
        self._model:     str   = QA_CONFIG["embed_model"]
        self._lock = threading.Lock()
        t = threading.Thread(target=self._load_safe, daemon=True, name="qa-router-load")
        t.start()

    # ── Yükleme ──────────────────────────────────────────────────────────────
    def _load_safe(self) -> None:
        try:
            self.load()
        except Exception as e:
            print(f"[QARouter] Yükleme hatası: {e}")

    def load(self) -> None:
        with open(_QA_PATH, encoding="utf-8") as f:
            data: list = json.load(f)
        for e in data:
            e.setdefault("match_type", "semantic")

        kw_count  = sum(1 for e in data if e["match_type"] == "keyword")
        sem_count = len(data) - kw_count
        print(f"[QARouter] {len(data)} giriş yükleniyor "
              f"({kw_count} keyword, {sem_count} semantic, model={self._model})...")

        entries = []
        for entry in data:
            if entry["match_type"] == "keyword":
                entries.append({**entry, "vecs": []})
                continue
            vecs = []
            for variant in entry.get("variants", []):
                try:
                    vecs.append(_embed(variant, self._model))
                except Exception as e:
                    print(f"[QARouter]   Embed hatası ({variant!r}): {e}")
            if vecs:
                entries.append({**entry, "vecs": vecs})
            else:
                print(f"[QARouter]   Giriş atlandı (embed yok): {entry.get('id')}")

        with self._lock:
            self._entries = entries
            self._ready   = True

        total_vecs = sum(len(e["vecs"]) for e in entries)
        print(f"[QARouter] Hazır — {len(entries)} giriş, {total_vecs} semantic vektör.")

    # ── Keyword Eşleştirme ────────────────────────────────────────────────────
    def _keyword_match(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """(answer, matched_id) veya (None, None)"""
        q_norm = _norm_kw(query)
        with self._lock:
            kw_entries = [e for e in self._entries if e.get("match_type") == "keyword"]
        for entry in kw_entries:
            for variant in entry.get("variants", []):
                if _norm_kw(variant) in q_norm:
                    return entry["answer"], entry["id"]
        return None, None

    # ── Hibrit Semantic Eşleştirme ────────────────────────────────────────────
    def _semantic_match_hybrid(
        self, query: str
    ) -> Tuple[float, Optional[str], Optional[str], Optional[str], float]:
        """
        Hibrit skor (cosine + lexical) ile top-2 eşleşme.

        Dönüş: (top1_score, top1_answer, top1_id, top2_id, top2_score)
        Eşik uygulamaz; karar route_v2()'ye bırakılır.
        """
        if not self._ready:
            return 0.0, None, None, None, 0.0
        try:
            q_vec = _embed(query, self._model)
        except Exception as e:
            print(f"[QARouter] Query embed hatası: {e}")
            return 0.0, None, None, None, 0.0

        with self._lock:
            sem_entries = [e for e in self._entries if e.get("match_type") != "keyword"]

        candidates = []
        for entry in sem_entries:
            if not entry["vecs"]:
                continue
            # Cosine: variant embedding'leri üzerinden max
            cos = max(_cosine(q_vec, v) for v in entry["vecs"])
            # Lexical: variant metinleri üzerinden max RapidFuzz skoru
            lex = max(_lexical(query, v) for v in entry.get("variants", [""]))
            # Hibrit final skor
            final = cfg.W_SEM * cos + cfg.W_LEX * lex
            candidates.append((final, entry))

        if not candidates:
            return 0.0, None, None, None, 0.0

        candidates.sort(key=lambda x: x[0], reverse=True)
        top1_score, top1_entry = candidates[0]
        top2_score = candidates[1][0] if len(candidates) > 1 else 0.0
        top2_id    = candidates[1][1]["id"] if len(candidates) > 1 else None

        return top1_score, top1_entry["answer"], top1_entry["id"], top2_id, top2_score

    # ── Üç Bantlı Karar: route_v2 ────────────────────────────────────────────
    def route_v2(
        self,
        query:    str,
        stt_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], str, float, Optional[str], Optional[str]]:
        """
        Ana yönlendirici — üç bantlı karar mantığı.

        Dönüş: (answer | None, decision, score, top1_id, top2_id)

        decision:
          "answer"  — eşleşme bulundu, cevabı döndür
          "confirm" — belirsiz; CONFIRM_MODE açıksa doğrulama sorusu sor
          "repeat"  — anlayamadım; "anlamadım" yanıtına git
          "llm"     — bilgi tabanı dışı; grounded Ollama fallback

        Karar tablosu:
          keyword eşleşmesi          → "answer"
          final >= T_HIGH            → "answer"
          T_MED <= final < T_HIGH
            margin >= MARGIN_MIN     → "answer"   (baskın eşleşme)
            margin <  MARGIN_MIN
              CONFIRM_MODE=True      → "confirm"
              CONFIRM_MODE=False     → "repeat"
          final < T_MED             → "llm"
        """
        # ── 1. Keyword ────────────────────────────────────────────────────────
        kw_answer, kw_id = self._keyword_match(query)
        if kw_answer is not None:
            _log(query, kw_id, 1.0, True, "keyword",
                 stt_meta=stt_meta, decision="answer",
                 top1_id=kw_id, top2_id=None, top1_score=1.0, top2_score=0.0)
            print(f"[QARouter] Keyword eşleşti: {kw_id}")
            return kw_answer, "answer", 1.0, kw_id, None

        # ── 2. Hibrit semantic ────────────────────────────────────────────────
        top1_score, top1_answer, top1_id, top2_id, top2_score = \
            self._semantic_match_hybrid(query)
        margin = top1_score - top2_score

        # ── 3. Üç bantlı karar ───────────────────────────────────────────────
        if top1_score >= cfg.T_HIGH:
            decision = "answer"
            answer   = top1_answer

        elif top1_score >= cfg.T_MED:
            if margin >= cfg.MARGIN_MIN:
                decision = "answer"
                answer   = top1_answer
            else:
                if cfg.CONFIRM_MODE and top1_id:
                    decision = "confirm"
                else:
                    decision = "repeat"
                answer = None

        else:
            decision = "llm"
            answer   = None

        matched = decision == "answer" and answer is not None
        _log(query, top1_id if matched else top1_id, top1_score, matched, "semantic",
             stt_meta=stt_meta, decision=decision,
             top1_id=top1_id, top2_id=top2_id,
             top1_score=top1_score, top2_score=top2_score)

        if matched:
            print(f"[QARouter] Semantic eşleşti: {top1_id} "
                  f"(skor={top1_score:.3f}, margin={margin:.3f})")
        else:
            print(f"[QARouter] Karar={decision} "
                  f"(top1={top1_id}, skor={top1_score:.3f}, margin={margin:.3f})")

        return answer, decision, top1_score, top1_id, top2_id

    # ── Geriye Dönük Uyumluluk ────────────────────────────────────────────────
    def route(
        self,
        query:    str,
        stt_meta: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], float]:
        """Eski arayüz — brain.py'nin mevcut çağrıları için korunur."""
        answer, decision, score, top1_id, _ = self.route_v2(query, stt_meta=stt_meta)
        return (answer if decision == "answer" else None), score

    # ── Eval / Debug ──────────────────────────────────────────────────────────
    def route_debug(
        self, query: str
    ) -> Tuple[Optional[str], float, Optional[str], str, str]:
        """
        Eval için genişletilmiş route.

        Dönüş: (answer | None, score, matched_id | None, match_type, decision)
        """
        kw_answer, kw_id = self._keyword_match(query)
        if kw_answer is not None:
            _log(query, kw_id, 1.0, True, "keyword",
                 decision="answer", top1_id=kw_id, top1_score=1.0)
            return kw_answer, 1.0, kw_id, "keyword", "answer"

        top1_score, top1_answer, top1_id, top2_id, top2_score = \
            self._semantic_match_hybrid(query)
        margin = top1_score - top2_score

        if top1_score >= cfg.T_HIGH:
            decision = "answer"
        elif top1_score >= cfg.T_MED:
            decision = "answer" if margin >= cfg.MARGIN_MIN else "repeat"
        else:
            decision = "llm"

        answer  = top1_answer if decision == "answer" else None
        matched = answer is not None
        _log(query, top1_id, top1_score, matched, "semantic",
             decision=decision, top1_id=top1_id, top2_id=top2_id,
             top1_score=top1_score, top2_score=top2_score)
        return answer, top1_score, top1_id, "semantic", decision

    # ── Grounding Metni ──────────────────────────────────────────────────────
    def grounding_text(self, query: Optional[str] = None) -> str:
        """Ollama system prompt'una enjekte edilecek fact bloğu."""
        with self._lock:
            eligible = [
                e for e in self._entries
                if e.get("category", "") not in _GROUNDING_SKIP_CATEGORIES
            ]
        if not eligible:
            return ""

        if query:
            try:
                q_vec = _embed(query, self._model)
                scored = []
                for entry in eligible:
                    if entry["vecs"]:
                        best = max(_cosine(q_vec, v) for v in entry["vecs"])
                    else:
                        best = 0.0
                    scored.append((best, entry))
                scored.sort(key=lambda x: x[0], reverse=True)
                selected = [e for _, e in scored[: self._top_k]]
            except Exception:
                selected = eligible
        else:
            selected = eligible

        lines = [
            "Aşağıdaki bilgiler doğruluk garantilidir.",
            "Yanıtlarını YALNIZCA bu bilgilere ve genel hyperloop bilgisine dayandır.",
            "Konu dışı sorularda nazikçe araca ve projeye yönlendir.",
            "",
        ]
        for e in selected:
            lines.append(f"[{e['id']}] {e['answer']}")
        lines += [
            "",
            "KURAL: Yukarıdaki bilgiler dışında bir şeyi bilmiyorsan "
            "'Bu konuda net bir bilgim yok' de; asla uydurma. "
            "Resmi Türkçe 'siz', kısa cümleler, emoji yok.",
        ]
        return "\n".join(lines)

    # ── Yardımcılar ──────────────────────────────────────────────────────────
    def get_by_id(self, qa_id: str) -> Optional[str]:
        """ID'ye göre cevap döndürür (VIP tetikleme ve CONFIRM_MODE için)."""
        with self._lock:
            for entry in self._entries:
                if entry["id"] == qa_id:
                    return entry["answer"]
        return None

    def get_display_name(self, qa_id: str) -> str:
        """CONFIRM_MODE doğrulama sorusu için okunabilir kategori ismi."""
        with self._lock:
            for entry in self._entries:
                if entry["id"] == qa_id:
                    cat = entry.get("category", "")
                    return _CATEGORY_DISPLAY.get(
                        cat,
                        entry.get("variants", [qa_id])[0],
                    )
        return qa_id

    def vip_ids(self) -> list:
        """Kategori kisiye_ozel_vip olan tüm id'leri listeler."""
        with self._lock:
            return [e["id"] for e in self._entries if e.get("category") == "kisiye_ozel_vip"]

    @property
    def is_ready(self) -> bool:
        return self._ready


# ── Modül Singleton ───────────────────────────────────────────────────────────
_router_instance: Optional[QARouter] = None
_router_lock = threading.Lock()


def get_router() -> QARouter:
    """Modül genelinde tek QARouter örneği döndürür."""
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = QARouter()
    return _router_instance
