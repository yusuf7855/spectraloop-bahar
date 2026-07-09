"""
Spectraloop — Merkezi Konfigürasyon
------------------------------------
STT güven kapısı, hibrit skorlama, üç bantlı karar ve CONFIRM_MODE
tüm eşikleri buradan ayarlanır.  Değişiklik yapmak için bu dosyayı düzenle,
geri kalan kod buradan okur.
"""

# ── STT Güven Kapısı ──────────────────────────────────────────────────────────
# Whisper'ın kendi iç kalite sinyalleri; değerler model belgesiyle uyumlu.
#
# Ortama göre ayar:
#   Sessiz fuar salonu → varsayılanlar yeterli
#   Gürültülü pit alanı → LOGPROB_MIN=-1.3, NO_SPEECH_MAX=0.75, MIN_TOKENS=1

LOGPROB_MIN     = -1.0   # Segment ağırlıklı ort. log-olasılık alt sınırı.
                          # Daha gürültülü → -1.2 veya -1.4'e düşür.
NO_SPEECH_MAX   = 0.60   # Konuşma olmama olasılığı üst sınırı (0-1).
                          # Yanlış redler çoksa → 0.70 veya 0.80'e yükselt.
COMPRESSION_MAX = 2.4    # Sıkıştırma oranı üst sınırı (tekrar/halüsinasyon).
                          # Kalabalık ortamda zaman zaman 2.8'e yükseltebilirsin.
MIN_TOKENS      = 2      # Anlamlı token (len > 1 karakter) alt sınırı.
                          # Tek heceli gürültüyü ("mm", "ah") eliyor.
                          # Sadece tek kelimeyle konuşuluyorsa 1'e düşür.

# ── Hibrit Skorlama ───────────────────────────────────────────────────────────
# final_score = W_SEM * cosine + W_LEX * lexical
# Lexical bileşen STT harf hatalarını (manyatik←→manyetik) telafi eder.

W_SEM = 0.75   # Semantic (embedding cosine) ağırlığı
W_LEX = 0.25   # Lexical (RapidFuzz token_set_ratio) ağırlığı
               # Daha gürültülü / daha çok STT hatası → W_LEX=0.35, W_SEM=0.65

# ── Üç Bantlı Karar ──────────────────────────────────────────────────────────
T_HIGH     = 0.70   # >= T_HIGH                → direkt cevap ver
T_MED      = 0.55   # T_MED..T_HIGH            → margin kontrolüne gir
MARGIN_MIN = 0.08   # top1 − top2 farkı < bu  → "belirsiz" say
                    # Yanlış eşleşme çoksa → 0.12'ye yükselt.

# ── CONFIRM_MODE ──────────────────────────────────────────────────────────────
# True  → belirsiz orta bantta "İtki sistemi hakkında mı soruyorsunuz?"
#         doğrulama sorusu sor; kullanıcı evet derse cevabı ver.
# False → (varsayılan) doğrudan "anlamadım" yanıtına geç; demo hızı korunur.
CONFIRM_MODE = False
