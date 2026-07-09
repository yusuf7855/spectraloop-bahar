"""
Spectraloop — STT Güven Kapısı
-------------------------------
faster-whisper Segment nesnelerinden metadata okuyarak kalite kontrolü yapar.
Herhangi bir sinyal başarısız olursa routing devre dışı kalır ve
brain.stt_gate_failed() "anlamadım" yoluna yönlendirir.

Kullanım:
    gate = STTGate()
    passed, reason, meta = gate.check(segments)
"""

import re
from typing import List, Tuple, Dict, Any, Optional

import spectra_config as cfg


# ── Bilinen Whisper Hallucination Kalıpları ───────────────────────────────────
# Sessiz veya düşük kaliteli seste üretilen yaygın çıktılar.
# Liste normalize edilmiş (küçük harf, Türkçe→ASCII, noktalama yok).
_HALLUCINATION_BLOCKLIST: frozenset = frozenset({
    "tesekkur ederim",
    "tesekkurler",
    "altyazi",
    "altyazilar",
    "ceviriler",
    "ceviri",
    "devam ediyor",
    "www",
    "bu bir",
    "bu video",
    "izlediginiz icin tesekkurler",
    "lutfen abone olun",
    "begenmeyi unutmayin",
    "muzik",
    "son",
    "evet",          # tek kelime "Evet." — sıkça halüsinasyon
})

# Yalnızca noktalama ve boşluktan oluşan çıktı
_JUNK_RE = re.compile(r"^[\W\s]{0,4}$")


def _norm_gate(s: str) -> str:
    """Kıyaslama için minimal normalizasyon; noktalama boşlukla değiştirilir."""
    s = s.lower().strip()
    for tr, en in [
        ("ı", "i"), ("İ", "i"), ("ğ", "g"), ("Ğ", "g"),
        ("ş", "s"), ("Ş", "s"), ("ç", "c"), ("Ç", "c"),
        ("ö", "o"), ("Ö", "o"), ("ü", "u"), ("Ü", "u"),
    ]:
        s = s.replace(tr, en)
    return re.sub(r"[^\w\s]", " ", s).strip()


class STTGate:
    """
    STT güven kapısı — Whisper segment metadata'sını kontrol eder.

    passed=True  → metni routing'e gönder
    passed=False → brain.stt_gate_failed() ile "anlamadım" yoluna git

    reason değerleri:
        "ok"               – tüm kontroller geçildi
        "no_segments"      – Whisper hiç segment üretmedi
        "low_logprob"      – ortalama log-olasılık çok düşük (gürültü)
        "no_speech"        – konuşma yok olasılığı çok yüksek
        "high_compression" – tekrar/halüsinasyon işareti
        "too_short"        – anlamlı token sayısı yetersiz
        "junk"             – yalnızca noktalama/boşluk
        "hallucination"    – bilinen Whisper halüsinasyon kalıbı
        "repetition"       – aynı ifade iki kez (Whisper döngü hatası)
    """

    def check(
        self,
        segments: list,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        segments: list[faster_whisper.transcribe.Segment]
        Dönüş: (passed, reason, metadata_dict)
        """
        if not segments:
            return False, "no_segments", {
                "avg_logprob": None,
                "no_speech_prob": None,
                "compression_ratio": None,
                "token_count": 0,
            }

        # Süreye göre ağırlıklı ortalama (kısa sessizlik segmentleri az etkilesin)
        total_dur = sum(max(s.end - s.start, 1e-9) for s in segments)
        avg_logprob       = sum((s.end - s.start) * s.avg_logprob       for s in segments) / total_dur
        no_speech_prob    = sum((s.end - s.start) * s.no_speech_prob    for s in segments) / total_dur
        compression_ratio = sum((s.end - s.start) * s.compression_ratio for s in segments) / total_dur

        full_text = " ".join(s.text for s in segments).strip()
        norm_text = _norm_gate(full_text)
        tokens    = [w for w in norm_text.split() if len(w) > 1]

        meta: Dict[str, Any] = {
            "avg_logprob":       round(avg_logprob,       4),
            "no_speech_prob":    round(no_speech_prob,    4),
            "compression_ratio": round(compression_ratio, 4),
            "token_count":       len(tokens),
        }

        # ── Kontroller — en hızlı/ucuz önce ─────────────────────────────────

        if avg_logprob < cfg.LOGPROB_MIN:
            return False, "low_logprob", meta

        if no_speech_prob > cfg.NO_SPEECH_MAX:
            return False, "no_speech", meta

        if compression_ratio > cfg.COMPRESSION_MAX:
            return False, "high_compression", meta

        if len(tokens) < cfg.MIN_TOKENS:
            return False, "too_short", meta

        if _JUNK_RE.match(full_text):
            return False, "junk", meta

        if norm_text in _HALLUCINATION_BLOCKLIST:
            return False, "hallucination", meta

        # Tekrar tespiti: Whisper bazen aynı cümleyi arka arkaya üretir
        words = norm_text.split()
        if len(words) >= 6:
            half = len(words) // 2
            if words[:half] == words[half: half * 2]:
                return False, "repetition", meta

        return True, "ok", meta
