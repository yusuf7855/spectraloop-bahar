"""
Spectraloop - Araç Komut Algılayıcı
Türkçe sesli girişten araç komutunu tespit eder.
Kapsam: fren, motor, sensör, alarm, flaşör, stop lambası.
"""
import difflib
from typing import Optional

# ── Difflib fallback için normalize cümleler ─────────────────────────────────
BRAKE_PHRASES = {
    "FRONT_ON":  [
        "on freni ac","on fren ac","on frene bas","on freni sik","on fireni ac",
        "on firani ac","onde freni ac","on freni devreye al","on freni uygula",
        "on frene koy","on freni kilitle","on taraftaki freni ac",
    ],
    "REAR_ON":   [
        "arka freni ac","arka fren ac","arka frene bas","arka freni sik",
        "arka fireni ac","orka freni ac","arka freni devreye al","arka freni uygula",
        "arka frene koy","arka freni kilitle","arkadaki freni ac",
    ],
    "FRONT_OFF": [
        "on freni kapat","on fren kapat","on freni birak","on fren birak",
        "on freni serbest","on fireni kapat","on freni geri al","on freni kaldir",
        "on fren serbest birak","on freni coz","on frenden cik",
    ],
    "REAR_OFF":  [
        "arka freni kapat","arka fren kapat","arka freni birak","arka fren birak",
        "arka freni serbest","arka fireni kapat","arka freni geri al","arka freni kaldir",
        "arka fren serbest birak","arka freni coz","arka frenden cik",
    ],
    "ALL":       [
        "tum frenleri ac","hepsini ac","frenlere bas","tum frenlere bas",
        "butun frenleri ac","frenleri sik","tam fren","her iki freni ac",
        "fren yap","frenle","freni cek","frenleri devreye al","frenleri kilitle",
        "iki freni de ac","her iki frene bas",
    ],
    "RELEASE":   [
        "serbest birak","frenleri birak","freni birak","hepsini birak",
        "tum frenleri kapat","hepsini kapat","serbest","gevset","frenden cik",
        "freni kaldir","frenleri kaldir","gevse","bos birak","frenleri coz",
        "frenleri geri al","fren yok","frensiz","freni bos birak",
    ],
}


def _norm(s: str) -> str:
    s = s.lower().strip()
    for tr, en in [('ı','i'),('İ','i'),('ğ','g'),('Ğ','g'),('ş','s'),('Ş','s'),
                   ('ç','c'),('Ç','c'),('ö','o'),('Ö','o'),('ü','u'),('Ü','u')]:
        s = s.replace(tr, en)
    return s


_NORM_PHRASES = {cmd: [_norm(p) for p in phrases] for cmd, phrases in BRAKE_PHRASES.items()}

# Konuşmada anlam taşımayan dolgu sözcükleri — tw'den çıkarılır
_FILLERS = {
    "bir","bi","hadi","haydi","simdi","lutfen","acaba","bakalim",
    "sana","bana","ama","yani","tamam","peki","ee","ey","hey","iste",
    "biraz","sence","de","da","mi","mu","mu","ya","la","ha","e",
}


def detect_vehicle_command(text: str) -> Optional[str]:
    """
    Türkçe metinden araç komutunu tespit eder.
    Döner: komut adı (str) veya None.
    """
    tn = _norm(text)
    tw = set(tn.split()) - _FILLERS   # dolgu sözcükleri çıkar

    def has(kws):   return any(k in tn for k in kws)
    def has_w(kws): return bool(kws & tw)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. ACİL DURDURMA — her şeyden önce
    # ─────────────────────────────────────────────────────────────────────────
    if "estop" in tn or "e stop" in tn or "e-stop" in tn:
        return "EMERGENCY_STOP"
    if "acil" in tn:
        if has(["durdur","dur ","stop","kes"]) or \
           has_w({"dur","stop","kes","fren","frene","bas"}):
            return "EMERGENCY_STOP"

    # ─────────────────────────────────────────────────────────────────────────
    # 2. ALARM / BUZZER
    # ─────────────────────────────────────────────────────────────────────────
    if has(["alarm","buzzer","zil","siren"]):
        if has(["kapat","durdur","sus","sustur","kes","off","birak","kes"]):
            return "BUZZER_OFF"
        if has(["bip","klakson","kisa","tek"]):
            return "BUZZER_BEEP"
        return "BUZZER_ON"

    if has(["bip"]):
        return "BUZZER_BEEP"

    # ─────────────────────────────────────────────────────────────────────────
    # 3. FLAŞÖR
    # ─────────────────────────────────────────────────────────────────────────
    if has(["flasor","flash","strob","yanip sonsun","yanik sonsun"]):
        if has(["kapat","durdur","sondur","off","dur"]):
            return "FLASHER_OFF"
        return "FLASHER_ON"

    # ─────────────────────────────────────────────────────────────────────────
    # 4. STOP LAMBASI — "lamba/ışık/led" + "stop/fren" birlikte olmalı
    # ─────────────────────────────────────────────────────────────────────────
    if has(["lamba","isik","isig","led"]):
        if has(["stop","brake"]) or \
           (has(["fren"]) and has(["lamba","isik","isig","led"])):
            is_off = has(["kapat","sondur","off","birak","sondur"])
            return "STOP_LIGHT_OFF" if is_off else "STOP_LIGHT_ON"
        # Genel LED kontrolü — "led aç/kapat", "ışıkları aç/kapat", "lambayı yak/söndür"
        is_off = has(["kapat","sondur","off","birak","gec","koy","yok"])
        return "LED_OFF" if is_off else "LED_ON"

    # ─────────────────────────────────────────────────────────────────────────
    # 5. MOTOR
    # ─────────────────────────────────────────────────────────────────────────
    if has(["motor"]):
        # Durum sorgusu — eylem belirsizse de buraya düşsün
        if has(["durum","nasil","calisiyor","kontrol","aktif mi","kapali mi",
                "ne yapiyor","acik mi","var mi","bakiyor","izle"]):
            return "MOTOR_STATUS"
        # Motor ON
        if has(["calistir","baslat","devreye","sok","aktif","hazirla",
                "ver","start","basla","calismaya"]) or has_w({"ac","on"}):
            return "MOTOR_ON"
        # Motor OFF
        if has(["durdur","kapat","bitir","pasif","devre disi",
                "sonlandir","kes","off","stop"]) or has_w({"dur","koy"}):
            return "MOTOR_OFF"
        # "motor" var ama eylem yok → durum sor
        return "MOTOR_STATUS"

    # ─────────────────────────────────────────────────────────────────────────
    # 6. SENSÖRLER
    # ─────────────────────────────────────────────────────────────────────────
    if has(["sicaklik","isi ","isindi","isiyor","derece","isinma","kac derece",
            "ne kadar sicak","kac isi","ne kadar isti","sicakmi","soguk mu"]):
        return "GET_TEMP"

    # Voltaj — "isi" ile çakışmaması için sensör kontrolünde önce lamba/ışık geldi
    if has(["voltaj","volt","batarya","gerilim","sarj","enerji","pil",
            "guc var","sarj var","batarya bitti","dolu mu","bos mu",
            "kac volt","kac sarj","batarya durum"]):
        return "GET_VOLTAGE"

    if has(["sistem durumu","genel durum","durum raporu","hepsini goster",
            "tum sensor","tum sensorler","ne durumda","rapor ver","durum ver",
            "her seyi soyle","tam rapor","genel rapor","son durum",
            "hepsini oku","hepsini soyle","ne var ne yok","nasil gidiyor"]):
        return "GET_ALL"

    # ─────────────────────────────────────────────────────────────────────────
    # 7. FREN
    # ─────────────────────────────────────────────────────────────────────────
    is_rear  = has(["arka","orka","geri","rear"])
    is_front = has(["on fren","ileri","ondeki","onde","front"]) or \
               " on " in tn or tn.startswith("on ") or tn.endswith(" on")
    is_off   = has(["kapat","birak","birakin","serbest","gevset","kaldir",
                    "geri al","coz","cikar","bosalt"])
    is_on    = has(["bas","sik","uygula","devreye","aktif","kilitle","cek","koy"]) \
               or has_w({"ac","on"})
    has_brk  = has(["fren","firen","firan","filen","frem","brake"])
    has_all  = has(["hepsi","tum","butun","her","all","ikisi","ikisi de"])

    if has_brk or is_rear or is_front:
        if is_off:
            if is_front and not is_rear: return "FRONT_OFF"
            if is_rear  and not is_front: return "REAR_OFF"
            return "RELEASE"
        elif is_on or has_brk:
            if is_front and not is_rear: return "FRONT_ON"
            if is_rear  and not is_front: return "REAR_ON"
            return "ALL"

    # ─────────────────────────────────────────────────────────────────────────
    # 8. DİFFLİB FALLBACK — Whisper'ın yanlış duyduğu fren cümlelerini yakalar
    # ─────────────────────────────────────────────────────────────────────────
    best_cmd, best_score = None, 0.0
    for cmd, phrases in _NORM_PHRASES.items():
        for phrase in phrases:
            s = difflib.SequenceMatcher(None, tn, phrase).ratio()
            if s > best_score:
                best_score, best_cmd = s, cmd
    if best_score >= 0.58:
        return best_cmd

    return None
