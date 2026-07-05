"""
Spectraloop - Yanıt Temizleyici
---------------------------------
LLM çıktısındaki İngilizce sızıntılarını ve bozuk kelimeleri temizler.
Resmi "siz" hitabı korunur (sen→siz dönüşümü yapılmaz).
"""
import re
from typing import List

# ─────────────────────────────────────────────────────────────────────────────
# siz → sen dönüşüm tablosu (en uzun önce — üst-küme önce eşleşsin)
# ─────────────────────────────────────────────────────────────────────────────
_SIZ_REPLACEMENTS = [
    # 6+ karakter — önce bunlar
    ("sizinle", "seninle"),
    ("sizden",  "senden"),
    ("sizde",   "sende"),
    ("sizin",   "senin"),
    # 4 karakter
    ("size",    "sana"),
    # 3 karakter — en son
    ("siz",     "sen"),
]


def _replace_siz(text: str) -> str:
    """Büyük/küçük harf duyarsız siz→sen dönüşümü; sözcük sınırlarına dikkat eder."""
    for old, new in _SIZ_REPLACEMENTS:
        # \b kelime sınırı — Türkçe için yeterince iyi
        pattern = re.compile(r'\b' + re.escape(old) + r'\b', re.IGNORECASE)
        def _repl(m: re.Match, _new: str = new) -> str:
            matched = m.group(0)
            if matched.isupper():
                return _new.upper()
            if matched[0].isupper():
                return _new.capitalize()
            return _new
        text = pattern.sub(_repl, text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Yaygın İngilizce sızıntı kelimeleri
# ─────────────────────────────────────────────────────────────────────────────
_ENGLISH_LEAKS = [
    "ok", "sure", "yes", "no", "the", "is", "are", "was", "were",
    "it", "its", "this", "that", "with", "for", "and", "but", "or",
    "not", "have", "has", "had", "will", "would", "can", "could",
    "should", "may", "might", "do", "does", "did", "be", "been",
    "being", "of", "in", "on", "at", "to", "from", "by", "an", "a",
    "i", "you", "we", "they", "he", "she", "my", "your", "our",
    "so", "if", "as", "up", "out", "just", "also", "very", "well",
    "now", "here", "there", "then", "than", "when", "what", "how",
    "why", "who", "which", "get", "got", "let", "like", "know",
    "think", "come", "go", "see", "say", "said", "use", "used",
    "great", "good", "right", "really", "actually", "basically",
]

_LEAK_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in _ENGLISH_LEAKS) + r')\b',
    re.IGNORECASE,
)


def _remove_english_leaks(text: str) -> str:
    return _LEAK_PATTERN.sub('', text)


# ─────────────────────────────────────────────────────────────────────────────
# Bozuk / garbled kelime tespiti
# ─────────────────────────────────────────────────────────────────────────────
# Açık liste: bilinen garip Türkçe-görünümlü bozuk kelimeler
_GARBLED_EXPLICIT = re.compile(
    r'\b(revolüsyonize|transpoorn|transpoo|hyperl00p|transportasyon[a-z]{3,})\b',
    re.IGNORECASE,
)

# 8+ karakter, tamamen ASCII harflerden oluşan kelimeler (Türkçe değil büyük ihtimalle)
# Türkçe harfler içeriyorsa veya bilinen Türkçe/teknik kelimeyse atla
_PURE_ASCII_LONG = re.compile(r'\b([A-Za-z]{8,})\b')

# Teknofest, hyperloop, spectraloop, spectra gibi teknik terimleri koru
_ALLOWED_LONG_ASCII = {
    "hyperloop", "spectraloop", "spectra", "teknofest", "elektromanyetik",
    "manyetik", "levitasyon", "pneumatik", "supersonic", "capsule",
    "electromagnetic", "acceleration", "deceleration", "temperature",
    "controller", "software", "hardware", "engineering", "competition",
    "presentation", "performance", "simulation", "navigation", "suspension",
}


def _sentence_has_garbled(sentence: str) -> bool:
    """Cümle bozuk kelime içeriyorsa True döner."""
    if _GARBLED_EXPLICIT.search(sentence):
        return True
    for m in _PURE_ASCII_LONG.finditer(sentence):
        word_lower = m.group(1).lower()
        if word_lower not in _ALLOWED_LONG_ASCII:
            return True
    return False


def _filter_garbled_sentences(text: str) -> str:
    """Bozuk kelime içeren cümleleri metnin dışına atar."""
    # Nokta, !, ? ile biten cümleleri ayır
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    clean_sentences: List[str] = []
    for s in raw_sentences:
        if s.strip() and not _sentence_has_garbled(s):
            clean_sentences.append(s.strip())
    return ' '.join(clean_sentences) if clean_sentences else text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Ana temizleme fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────
def clean(text: str) -> str:
    """
    LLM yanıtını temizler:
    1. Yaygın İngilizce sızıntı kelimelerini kaldırır
    2. Bozuk / garbled kelime içeren cümleleri filtreler
    3. Fazladan boşlukları düzeltir
    Not: "siz" hitabı korunur, sen'e dönüştürülmez.
    """
    if not text:
        return text

    # 1) İngilizce sızıntı kelimeleri kaldır
    text = _remove_english_leaks(text)

    # 2) Garbled cümleleri filtrele
    text = _filter_garbled_sentences(text)

    # 3) Fazla boşluk temizle
    text = re.sub(r'[ \t]+', ' ', text)          # çoklu boşluk → tek
    text = re.sub(r' ([,;:.!?])', r'\1', text)   # noktalama öncesi boşluk
    text = re.sub(r'\s{2,}', ' ', text)
    text = text.strip()

    return text
