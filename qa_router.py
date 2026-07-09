"""
Spectraloop — QA Router
------------------------
Küratörlü bilgi tabanına dayalı deterministik cevap yönlendirici.

Yönlendirme sırası:
  1. KEYWORD: Sorgu normalize edilir; herhangi bir variant metni sorgu içinde
     geçiyorsa o cevap anında döndürülür. Embedding gerekmez.
  2. SEMANTIC: Sorgu embed edilir, tüm semantic variant'larla cosine similarity
     hesaplanır. En yüksek skor eşik >= 0.72 ise cevap döndürülür.
  3. FALLBACK: Her ikisi de eşleşmezse None döner; brain.py grounded Ollama'ya geçer.

Config: QA_CONFIG sözlüğünü değiştirerek model/eşik ayarlanabilir.
Loglama: Her sorgu (match_type, id, skor) logs/qa_misses.jsonl'e yazılır.
Singleton: get_router() ile modül genelinde tek örnek kullanılır.
"""

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import requests

# ── Config ────────────────────────────────────────────────────────────────────
QA_CONFIG: dict = {
    "embed_model": "nomic-embed-text",
    "chat_model":  "qwen2.5:3b",
    "threshold":   0.72,
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
    query: str,
    matched_id: Optional[str],
    score: float,
    matched: bool,
    match_type: str = "semantic",
) -> None:
    try:
        record = {
            "ts":         datetime.now().isoformat(timespec="seconds"),
            "query":      query,
            "matched":    matched,
            "match_type": match_type,
            "id":         matched_id,
            "score":      round(score, 4),
        }
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── Router Sınıfı ─────────────────────────────────────────────────────────────
class QARouter:
    """
    Kullanım (singleton tercih edilir):
        from qa_router import get_router
        answer, score = get_router().route("İtki sistemi nasıl çalışıyor?")
    """

    def __init__(self) -> None:
        # _entries: [{id, category, match_type, answer, tags, variants, vecs:[]}]
        self._entries:   list  = []
        self._ready:     bool  = False
        self._threshold: float = QA_CONFIG["threshold"]
        self._top_k:     int   = QA_CONFIG["top_k"]
        self._model:     str   = QA_CONFIG["embed_model"]
        self._lock = threading.Lock()
        # Arka planda başlat
        t = threading.Thread(target=self._load_safe, daemon=True, name="qa-router-load")
        t.start()

    # ── Yükleme ──────────────────────────────────────────────────────────────
    def _load_safe(self) -> None:
        try:
            self.load()
        except Exception as e:
            print(f"[QARouter] Yükleme hatası: {e}")

    def load(self) -> None:
        """
        qa_base.json'u okur.
        - keyword girişleri: vecs=[] (embedding yok, sadece metin eşleştirme)
        - semantic girişleri: tüm variant'lar embed edilir.
        Senkron; eval_qa.py tarafından doğrudan çağrılır.
        """
        with open(_QA_PATH, encoding="utf-8") as f:
            data: list[dict] = json.load(f)

        # match_type eksik girişlere varsayılan olarak "semantic" ata
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

            # Semantic: embed et
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
    def _keyword_match(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """
        (answer, matched_id) veya (None, None) döndürür.
        Sorgunun normalize edilmiş halinde herhangi bir keyword variant geçiyorsa eşleşir.
        """
        q_norm = _norm_kw(query)
        with self._lock:
            kw_entries = [e for e in self._entries if e.get("match_type") == "keyword"]
        for entry in kw_entries:
            for variant in entry.get("variants", []):
                if _norm_kw(variant) in q_norm:
                    return entry["answer"], entry["id"]
        return None, None

    # ── Semantic Eşleştirme ───────────────────────────────────────────────────
    def _semantic_match(
        self, query: str
    ) -> tuple[Optional[str], float, Optional[str]]:
        """(answer | None, best_score, best_id) döndürür."""
        if not self._ready:
            return None, 0.0, None
        try:
            q_vec = _embed(query, self._model)
        except Exception as e:
            print(f"[QARouter] Query embed hatası: {e}")
            return None, 0.0, None

        best_score  = 0.0
        best_answer = None
        best_id     = None

        with self._lock:
            sem_entries = [e for e in self._entries if e.get("match_type") != "keyword"]
        for entry in sem_entries:
            for vec in entry["vecs"]:
                score = _cosine(q_vec, vec)
                if score > best_score:
                    best_score  = score
                    best_answer = entry["answer"]
                    best_id     = entry["id"]

        if best_score >= self._threshold:
            return best_answer, best_score, best_id
        return None, best_score, best_id

    # ── Ana Route ─────────────────────────────────────────────────────────────
    def route(self, query: str) -> tuple[Optional[str], float]:
        """
        1. Keyword → 2. Semantic → None

        Döndürür: (answer | None, score)
          - keyword eşleşmesinde score=1.0
          - semantic eşleşmesinde cosine skoru
          - eşleşmede answer=None
        """
        # 1. Keyword
        kw_answer, kw_id = self._keyword_match(query)
        if kw_answer is not None:
            _log(query, kw_id, 1.0, True, "keyword")
            print(f"[QARouter] Keyword eşleşti: {kw_id}")
            return kw_answer, 1.0

        # 2. Semantic
        sem_answer, score, sem_id = self._semantic_match(query)
        matched = sem_answer is not None
        _log(query, sem_id, score, matched, "semantic")

        if matched:
            print(f"[QARouter] Semantic eşleşti: {sem_id} (skor={score:.3f})")
            return sem_answer, score

        print(f"[QARouter] Eşleşmedi (en iyi={sem_id}, skor={score:.3f}) → Ollama")
        return None, score

    def route_debug(
        self, query: str
    ) -> tuple[Optional[str], float, Optional[str], str]:
        """
        Eval için genişletilmiş route.

        Döndürür: (answer | None, score, matched_id | None, match_type)
        """
        # 1. Keyword
        kw_answer, kw_id = self._keyword_match(query)
        if kw_answer is not None:
            _log(query, kw_id, 1.0, True, "keyword")
            return kw_answer, 1.0, kw_id, "keyword"

        # 2. Semantic
        sem_answer, score, sem_id = self._semantic_match(query)
        matched = sem_answer is not None
        _log(query, sem_id, score, matched, "semantic")
        return sem_answer, score, sem_id, "semantic"

    # ── Grounding Metni ──────────────────────────────────────────────────────
    def grounding_text(self, query: Optional[str] = None) -> str:
        """
        Ollama system prompt'una enjekte edilecek fact bloğu.
        VIP/kişiye özel kategoriler hariç tutulur.
        query verilirse top_k en alakalı semantic giriş seçilir.
        """
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

    # ── Yardımcı ─────────────────────────────────────────────────────────────
    def get_by_id(self, qa_id: str) -> Optional[str]:
        """VIP tetikleme gibi operatör kullanımı için id'ye göre cevap döndürür."""
        with self._lock:
            for entry in self._entries:
                if entry["id"] == qa_id:
                    return entry["answer"]
        return None

    def vip_ids(self) -> list[str]:
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
    """
    Modül genelinde tek QARouter örneği döndürür.
    brain.py ve ui_server.py bu fonksiyonu çağırarak aynı instance'ı paylaşır.
    """
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = QARouter()
    return _router_instance
