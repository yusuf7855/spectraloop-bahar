"""
Spectraloop - VIP Tanımlama ve Hitap Sistemi
---------------------------------------------
TÜBİTAK Hyperloop, TEKNOFEST, Bakanlık ve diğer önemli ziyaretçiler
için özel karşılama ve hitap şablonları.
"""
import re
import random
from typing import Optional, Dict

# ─────────────────────────────────────────────────────────────────────────────
# VIP Veritabanı
# Anahtar: normalize edilmiş isim (küçük harf, Türkçe karakter → Latin)
# ─────────────────────────────────────────────────────────────────────────────
_VIP_DB: Dict[str, dict] = {

    # ── Cumhurbaşkanlığı ─────────────────────────────────────────────────────
    "recep tayyip erdogan": {
        "ad_soyad": "Recep Tayyip Erdoğan",
        "unvan":    "Cumhurbaşkanı",
        "hitap":    "Sayın Cumhurbaşkanım",
        "kategori": "cumhurbaskani",
        "tanitim":  "Türkiye Cumhuriyeti Cumhurbaşkanı",
    },
    "erdogan": {
        "ad_soyad": "Recep Tayyip Erdoğan",
        "unvan":    "Cumhurbaşkanı",
        "hitap":    "Sayın Cumhurbaşkanım",
        "kategori": "cumhurbaskani",
        "tanitim":  "Türkiye Cumhuriyeti Cumhurbaşkanı",
    },

    # ── Sanayi ve Teknoloji Bakanlığı ─────────────────────────────────────────
    "mehmet fatih kacir": {
        "ad_soyad": "Mehmet Fatih Kacır",
        "unvan":    "Sanayi ve Teknoloji Bakanı",
        "hitap":    "Sayın Bakan Kacır",
        "kategori": "bakan",
        "tanitim":  "Sanayi ve Teknoloji Bakanı",
    },
    "fatih kacir": {
        "ad_soyad": "Mehmet Fatih Kacır",
        "unvan":    "Sanayi ve Teknoloji Bakanı",
        "hitap":    "Sayın Bakan Kacır",
        "kategori": "bakan",
        "tanitim":  "Sanayi ve Teknoloji Bakanı",
    },
    "kacir": {
        "ad_soyad": "Mehmet Fatih Kacır",
        "unvan":    "Sanayi ve Teknoloji Bakanı",
        "hitap":    "Sayın Bakan Kacır",
        "kategori": "bakan",
        "tanitim":  "Sanayi ve Teknoloji Bakanı",
    },
    "mustafa varank": {
        "ad_soyad": "Mustafa Varank",
        "unvan":    "Eski Sanayi ve Teknoloji Bakanı",
        "hitap":    "Sayın Varank",
        "kategori": "bakan",
        "tanitim":  "Eski Sanayi ve Teknoloji Bakanı",
    },
    "varank": {
        "ad_soyad": "Mustafa Varank",
        "unvan":    "Eski Sanayi ve Teknoloji Bakanı",
        "hitap":    "Sayın Varank",
        "kategori": "bakan",
        "tanitim":  "Eski Sanayi ve Teknoloji Bakanı",
    },

    # ── Ulaştırma ve Altyapı Bakanlığı ───────────────────────────────────────
    "abdulkadir uraloglu": {
        "ad_soyad": "Abdülkadir Uraloğlu",
        "unvan":    "Ulaştırma ve Altyapı Bakanı",
        "hitap":    "Sayın Bakan Uraloğlu",
        "kategori": "bakan",
        "tanitim":  "Ulaştırma ve Altyapı Bakanı",
    },
    "uraloglu": {
        "ad_soyad": "Abdülkadir Uraloğlu",
        "unvan":    "Ulaştırma ve Altyapı Bakanı",
        "hitap":    "Sayın Bakan Uraloğlu",
        "kategori": "bakan",
        "tanitim":  "Ulaştırma ve Altyapı Bakanı",
    },

    # ── TÜBİTAK ──────────────────────────────────────────────────────────────
    "hasan mandal": {
        "ad_soyad": "Prof. Dr. Hasan Mandal",
        "unvan":    "TÜBİTAK Başkanı",
        "hitap":    "Sayın Başkan Mandal",
        "kategori": "tubitak",
        "tanitim":  "TÜBİTAK Başkanı",
    },
    "mandal": {
        "ad_soyad": "Prof. Dr. Hasan Mandal",
        "unvan":    "TÜBİTAK Başkanı",
        "hitap":    "Sayın Başkan Mandal",
        "kategori": "tubitak",
        "tanitim":  "TÜBİTAK Başkanı",
    },
    "tubitak baskani": {
        "ad_soyad": "TÜBİTAK Başkanı",
        "unvan":    "TÜBİTAK Başkanı",
        "hitap":    "Sayın TÜBİTAK Başkanım",
        "kategori": "tubitak",
        "tanitim":  "TÜBİTAK Başkanı",
    },

    # ── TEKNOFEST / Baykar ────────────────────────────────────────────────────
    "selcuk bayraktar": {
        "ad_soyad": "Selçuk Bayraktar",
        "unvan":    "TEKNOFEST Yönetim Kurulu Başkanı",
        "hitap":    "Sayın Bayraktar",
        "kategori": "teknofest",
        "tanitim":  "TEKNOFEST Yönetim Kurulu Başkanı, Baykar CTO",
    },
    "haluk bayraktar": {
        "ad_soyad": "Haluk Bayraktar",
        "unvan":    "Baykar CEO",
        "hitap":    "Sayın Bayraktar",
        "kategori": "teknofest",
        "tanitim":  "Baykar Savunma CEO'su",
    },
    "selcuk": {
        "ad_soyad": "Selçuk Bayraktar",
        "unvan":    "TEKNOFEST Yönetim Kurulu Başkanı",
        "hitap":    "Sayın Bayraktar",
        "kategori": "teknofest",
        "tanitim":  "TEKNOFEST Yönetim Kurulu Başkanı",
    },
    "bayraktar": {
        "ad_soyad": "Bayraktar",
        "unvan":    "TEKNOFEST / Baykar Yöneticisi",
        "hitap":    "Sayın Bayraktar",
        "kategori": "teknofest",
        "tanitim":  "TEKNOFEST / Baykar Yöneticisi",
    },
    "teknofest baskani": {
        "ad_soyad": "TEKNOFEST Başkanı",
        "unvan":    "TEKNOFEST Yönetim Kurulu Başkanı",
        "hitap":    "Sayın TEKNOFEST Başkanım",
        "kategori": "teknofest",
        "tanitim":  "TEKNOFEST Yönetim Kurulu Başkanı",
    },

    # ── TEKNOFEST Hyperloop Jürisi ────────────────────────────────────────────
    "juri": {
        "ad_soyad": "Jüri Üyesi",
        "unvan":    "TEKNOFEST Hyperloop Jüri Üyesi",
        "hitap":    "Sayın Jüri Üyemiz",
        "kategori": "juri",
        "tanitim":  "TEKNOFEST Hyperloop Jüri Üyesi",
    },

    # ── Samsun Üniversitesi Yönetimi ──────────────────────────────────────────
    "rektor": {
        "ad_soyad": "Rektör",
        "unvan":    "Rektör",
        "hitap":    "Sayın Rektörüm",
        "kategori": "akademisyen",
        "tanitim":  "Samsun Üniversitesi Rektörü",
    },
    "dekan": {
        "ad_soyad": "Dekan",
        "unvan":    "Dekan",
        "hitap":    "Sayın Dekan",
        "kategori": "akademisyen",
        "tanitim":  "Fakülte Dekanı",
    },
    "bakan": {
        "ad_soyad": "Bakan",
        "unvan":    "Bakan",
        "hitap":    "Sayın Bakanım",
        "kategori": "bakan",
        "tanitim":  "Bakan",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Kategori bazlı karşılama şablonları
# ─────────────────────────────────────────────────────────────────────────────
_GREETING_TEMPLATES = {
    "cumhurbaskani": (
        "{hitap}, Spectraloop takımına şereflendirdiğiniz için son derece mutluyuz! "
        "Samsun Üniversitesi olarak hyperloop teknolojisini ülkemize kazandırmak için "
        "büyük bir özveriyle çalışıyoruz. Projemizin herhangi bir yönünü "
        "sizinle paylaşmaktan büyük onur duyarım. Ne görmek istersiniz?"
    ),
    "bakan": (
        "{hitap}, hoş geldiniz! Spectraloop takımı adına sizi karşılamak büyük bir onur. "
        "Hyperloop aracımızın sesli kontrol sistemi, fren mekanizmaları ve sensör altyapısı "
        "hakkında bilgi vermekten memnuniyet duyarım. "
        "Hangi konular sizi en çok ilgilendiriyor?"
    ),
    "tubitak": (
        "{hitap}, hoş geldiniz! TÜBİTAK'ın bu projeye olan desteği ve vizyonu "
        "bizim için büyük bir motivasyon kaynağı. "
        "Spectraloop olarak hyperloop teknolojisini en yüksek seviyede geliştirmeyi hedefliyoruz. "
        "Teknik detayları sizinle paylaşmaktan memnuniyet duyarım. Ne merak ediyorsunuz?"
    ),
    "teknofest": (
        "{hitap}, hoş geldiniz! TEKNOFEST platformunda yer almak Spectraloop için "
        "inanılmaz bir motivasyon. Ekibimizin aylarca süren çalışması bu alanda somut "
        "bir ürün ortaya çıkardı. Sistemi sizlere tanıtmak harika olur! "
        "Hangi konuda merak ediyorsunuz?"
    ),
    "juri": (
        "{hitap}, hoş geldiniz! Değerlendirmeniz için elimizden gelenin en iyisini sunmaya hazırız. "
        "Hyperloop sistemimiz sesli komutla fren, motor ve sensör kontrolü yapabiliyor. "
        "Teknik kriterleri tek tek ele alabiliriz. Neyi incelemek istersiniz?"
    ),
    "akademisyen": (
        "{hitap}, hoş geldiniz! Spectraloop takımı büyük bir özveriye bu projeyi hayata geçirdi. "
        "Teknik detayları paylaşmaktan memnuniyet duyarım. Ne incelemek istersiniz?"
    ),
}

# Kategoriye göre VIP'e sorulabilecek sohbet soruları
_VIP_QUESTIONS = {
    "cumhurbaskani": [
        "Türkiye'nin yerli hyperloop teknolojisindeki ilerleyişi hakkında neler düşünüyorsunuz?",
        "Gençlerin bu tür projelerdeki katkısına ilişkin düşüncelerinizi merak ediyorum.",
    ],
    "bakan": [
        "Hyperloop projeleri için Bakanlık tarafında gelecekte ne gibi destekler planlanıyor?",
        "Yerli ulaşım teknolojilerinin gelişimi için nasıl bir vizyon izlenmesini uygun görüyorsunuz?",
    ],
    "tubitak": [
        "TÜBİTAK'ın hyperloop araştırma süreçlerine yaklaşımı hakkında bilgi alabilir miyim?",
        "Akademi ile endüstri iş birliğinin bu alandaki önemini nasıl değerlendiriyorsunuz?",
    ],
    "teknofest": [
        "TEKNOFEST Hyperloop kategorisinde bu yıl öne çıkan trend nedir sizce?",
        "Genç mühendislerin yarışma ekosistemindeki rolüne dair neler söylersiniz?",
    ],
    "juri": [
        "Değerlendirme sürecinde en belirleyici teknik kriterleri merak ediyorum.",
        "Güvenlik mi yoksa hız performansı mı sizin için daha öncelikli?",
    ],
    "akademisyen": [
        "Bu alanda öğrencilere ne gibi tavsiyeler verirsiniz?",
        "Hyperloop teknolojisinin akademik açıdan en ilgi çekici yönü nedir sizce?",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    s = s.lower().strip()
    for tr, en in [
        ('ı','i'),('İ','i'),('ğ','g'),('Ğ','g'),('ş','s'),('Ş','s'),
        ('ç','c'),('Ç','c'),('ö','o'),('Ö','o'),('ü','u'),('Ü','u'),
    ]:
        s = s.replace(tr, en)
    return re.sub(r'[^\w\s]', '', s)


def lookup_vip(text: str) -> Optional[dict]:
    """
    Metinden VIP tespiti yapar.
    Eşleşen VIP kaydını döndürür; bulunamazsa None.
    """
    if not text:
        return None
    key = _normalize(text)

    # 1. Doğrudan eşleşme
    if key in _VIP_DB:
        return _VIP_DB[key]

    # 2. Alt-dizi eşleşmesi: VIP anahtarı, girişin içinde mi? (ya da tam tersi)
    for vip_key, vip_data in _VIP_DB.items():
        if vip_key in key or key in vip_key:
            return vip_data

    # 3. Token kesişimi: 2+ kelime girildiyse, en az bir token VIP anahtarında mı?
    key_tokens = set(key.split())
    if len(key_tokens) >= 2:
        for vip_key, vip_data in _VIP_DB.items():
            vip_tokens = set(vip_key.split())
            if key_tokens & vip_tokens:
                return vip_data

    # 4. Tek token: soyad + yaygın kısaltmalar
    if len(key_tokens) == 1:
        tok = list(key_tokens)[0]
        for vip_key, vip_data in _VIP_DB.items():
            if tok in vip_key.split():
                return vip_data

    return None


def get_vip_greeting(vip: dict) -> str:
    kategori = vip.get("kategori", "akademisyen")
    template = _GREETING_TEMPLATES.get(kategori, _GREETING_TEMPLATES["akademisyen"])
    return template.format(hitap=vip["hitap"])


def get_vip_question(vip: dict) -> str:
    kategori = vip.get("kategori", "akademisyen")
    questions = _VIP_QUESTIONS.get(kategori, _VIP_QUESTIONS["akademisyen"])
    return random.choice(questions)


def get_system_addendum(vip: dict) -> str:
    """Ollama sistem promptuna eklenecek VIP bağlamı (İngilizce)."""
    return (
        f"\n\nIMPORTANT: You are currently speaking with {vip['ad_soyad']}, "
        f"{vip['tanitim']}. "
        f"Always address them formally as '{vip['hitap']}'. "
        f"Be highly respectful, informative, and occasionally ask their perspective "
        f"on hyperloop technology. Keep answers concise (2-3 sentences max)."
    )
