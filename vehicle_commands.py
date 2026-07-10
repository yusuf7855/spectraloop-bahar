"""
Spectraloop - Araç Komut Algılayıcı
Üç aşamalı tespit:
  1. Anahtar kelime + kök eşleşmesi  (hızlı)
  2. Difflib benzerlik puanı          (Whisper yanlış okuma fallback)
"""
import difflib
from typing import Optional


# ── Normalize (Türkçe → ASCII küçük harf) ───────────────────────────────────
def _norm(s: str) -> str:
    s = s.lower().strip()
    for tr, en in [
        ('ı','i'),('İ','i'),('ğ','g'),('Ğ','g'),('ş','s'),('Ş','s'),
        ('ç','c'),('Ç','c'),('ö','o'),('Ö','o'),('ü','u'),('Ü','u'),
        ('â','a'),('î','i'),('û','u'),
    ]:
        s = s.replace(tr, en)
    return s


# ── Türkçe fiil eki soyucu ───────────────────────────────────────────────────
# Normalize edilmiş halde, uzundan kısaya sıralı
_SUFFIXES = [
    "abilirmisiniz","ebilirmisiniz",
    "abilirmisin","ebilirmisin",
    "abilirsiniz","ebilirsiniz",
    "abilirsin","ebilirsin",
    "abilirmiyim","ebilirmiyim",
    "abilir","ebilir",
    "iversene","iversana",
    "abilirmiyiz","ebilirmiyiz",
    "alim","elim",           # çalıştıralım → çalıştır
    "iver",
    "sene","sana",
    "siniz","sunuz",
    "iyor","uyor",
    "acak","ecek",
    "masi","mesi",
    "mak","mek",
    "sin","sun",
    "lim",                   # basalım → bas
    "ali","eli",
]

def _stem(word: str) -> str:
    """Kelimeden yaygın fiil ekini soy, tahmini kök döndür."""
    for s in _SUFFIXES:
        if word.endswith(s) and len(word) - len(s) >= 3:
            return word[:-len(s)]
    return word

def _expand(tokens: set) -> set:
    """Token seti + her tokenin kökü."""
    expanded = set(tokens)
    for w in tokens:
        root = _stem(w)
        if root != w:
            expanded.add(root)
    return expanded


# ── Filtre kelimeleri ────────────────────────────────────────────────────────
_FILLERS = {
    "bir","bi","hadi","haydi","simdi","lutfen","acaba","bakalim",
    "sana","bana","ama","yani","tamam","peki","ee","ey","hey","iste",
    "biraz","sence","de","da","mi","mu","ya","la","ha","e","su","bu","o",
    "eger","belki","galiba","sanki","artik","zaten","sadece","yalnizca",
    "simdi","lutfen","evet","hayir","tabi","tabii","elbette",
}


# ── Difflib için kapsamlı söylem listesi ─────────────────────────────────────
_PHRASES = {
    "MOTOR_ON": [
        "motoru calistir","motoru baslat","motoru ac","motoru devreye al",
        "motoru aktif et","motoru yak","motoru ver","motoru koy","motoru hazirla",
        "motor calistir","motor ac","motor baslat","motor on","motor devreye",
        "motorlari calistir","motorlari ac",
        "moturu calistir","motur ac","motur calistir","motur baslat",
        "motori ac","motore calistir","motori calistir",
        "calistir motoru","ac motoru","baslat motoru",
        "motoru calismaya basla","motoru calismaya koy",
        "motoru start et","motoru devret","motoru guc ver",
    ],
    "MOTOR_OFF": [
        "motoru durdur","motoru kapat","motoru sondur","motoru kes",
        "motoru pasif et","motoru devre disi birak","motoru bitir",
        "motor durdur","motor kapat","motor kes","motor off","motor dur",
        "motorlari durdur","motorlari kapat",
        "moturu durdur","motur kapat","motur durdur",
        "durdur motoru","kapat motoru","kes motoru",
        "motoru sustur","motoru sonlandir",
    ],
    "MOTOR_STATUS": [
        "motor durumu","motorun durumu","motor nasil","motor calisiyor mu",
        "motor acik mi","motor kapali mi","motor ne yapiyor","motor kontrol",
        "motorun calisiyor mu","motorun acik mi","motor var mi",
        "motoru kontrol et","motorun durumunu soyle",
        "motor izle","motor bilgi","motor durum raporu",
    ],
    "FRONT_ON": [
        "on freni ac","on fren ac","on frene bas","on freni devreye al",
        "on freni uygula","on freni aktif et","on freni sik","on freni kilitle",
        "on freni yap","on fireni ac","on firene bas","on fireni uygula",
        "on firani ac","ondeki freni ac","onde fren yap","onde frene bas",
        "ileri freni ac","ileri frene bas","front freni ac",
        "on freni devret","on freni tuttur","on freni vur","on freni cek",
        "on freni tut","on freni bas","onde frene bas",
    ],
    "FRONT_OFF": [
        "on freni kapat","on fren kapat","on freni birak","on freni serbest birak",
        "on freni kaldir","on freni gevset","on freni iptal","on freni coz",
        "on fireni kapat","on fireni birak","on firani kapat",
        "ondeki freni kapat","onde freni birak","on frenden cik",
        "on freni geri al","on freni serbeste birak","on freni bos birak",
    ],
    "REAR_ON": [
        "arka freni ac","arka fren ac","arka frene bas","arka freni devreye al",
        "arka freni uygula","arka freni aktif et","arka freni sik","arka freni kilitle",
        "arka freni yap","arka fireni ac","arka firene bas","arka fireni uygula",
        "arka firani ac","arkadaki freni ac","arkada fren yap","arkada frene bas",
        "geri freni ac","geri frene bas","rear freni ac",
        "arka freni devret","arka freni tuttur","arka freni vur","arka freni cek",
        "arka freni tut","arka freni bas","orka freni ac","orka frene bas",
    ],
    "REAR_OFF": [
        "arka freni kapat","arka fren kapat","arka freni birak","arka freni serbest birak",
        "arka freni kaldir","arka freni gevset","arka freni iptal","arka freni coz",
        "arka fireni kapat","arka fireni birak","arka firani kapat",
        "arkadaki freni kapat","arkada freni birak","arka frenden cik",
        "arka freni geri al","arka freni serbeste birak","orka freni kapat",
    ],
    "ALL": [
        "fren yap","firen yap","frene bas","frenleri ac","tum frenleri ac",
        "butun frenleri ac","frenle","frenleme yap","frenleri devreye al",
        "frenleri uygula","frenleri kilitle","frenleri sik","frenleri vur",
        "frenleri tut","frenleri tuttur","tam fren","tam frenleme","her iki frene bas",
        "her iki freni ac","iki freni de ac","komple fren","tum frenlere bas",
        "hem on hem arka fren","freni cek","frenleri aktif et",
    ],
    "RELEASE": [
        "freni birak","frenleri birak","serbest birak","freni kapat",
        "frenleri kapat","tum frenleri birak","hepsini birak","hepsini kapat",
        "freni serbest birak","frenleri serbest birak","freni gevset",
        "frenden cik","freni kaldir","frenleri kaldir","freni geri al",
        "fireni birak","freni iptal","freni coz","frenleri bos birak",
        "frene basma","frenleri devre disi birak","freni birakiyor",
    ],
    "EMERGENCY_STOP": [
        "acil durdur","acil dur","acil stop","acil fren","acil frenleme",
        "hemen durdur","hemen dur","hemen frene bas",
        "e stop","estop","emergency stop","emergency",
        "tehlike durdur","aninda durdur","aninda dur","tam dur","tam durdur",
    ],
    "GET_TEMP": [
        "sicaklik","sicaklik nedir","kac derece","ne kadar sicak",
        "aracin sicakligi","sistem sicakligi","isi olcumu","sicaklik raporu",
        "termal durum","sicak mi","kac derecede","derece nedir",
    ],
    "GET_VOLTAGE": [
        "voltaj","voltaj nedir","kac volt","batarya durumu","batarya nedir",
        "sarj durumu","sarj nedir","pil durumu","gerilim nedir",
        "batarya dolu mu","batarya bitti mi","sarj var mi","guc var mi",
        "batarya raporu","voltaj raporu","elektrik durumu",
    ],
    "GET_ALL": [
        "sistem durumu","genel durum","durum raporu","tam rapor",
        "tum sensorler","hepsini soyle","hepsini oku","ne durumda",
        "nasil gidiyor","durum ver","rapor ver","bilgi ver",
        "son durum","aracin durumu","her seyi soyle","ne var ne yok",
    ],
    "LED_ON": [
        "led ac","ledi ac","ledleri ac","led yak","ledleri yak",
        "isik ac","isigi ac","isiklari ac","isik ver","isiklari yak",
        "lamba ac","lambayi ac","lambalari ac","lambayi yak",
        "aydinlat","parlat","isiklandir","led devreye al","ledleri aktif et",
        "led on","isik on","lamba on","let ac","yet ac",
    ],
    "LED_OFF": [
        "led kapat","ledi kapat","ledleri kapat","led sondur","ledleri sondur",
        "isik kapat","isigi kapat","isiklari kapat","isiklari sondur",
        "lamba kapat","lambayi kapat","lambalari kapat","lambayi sondur",
        "isigi sondur","karart","karanlik yap","led devre disi",
        "isik yok","lamba yok","isigi kes","led off","isik off","lamba off",
        "let kapat","yet kapat",
    ],
    "BUZZER_ON": [
        "alarm ac","alarm calistir","alarm devreye","zil cal","siren ac",
        "buzzer ac","alarm ver","alarm baslat","alarmi cal",
    ],
    "BUZZER_OFF": [
        "alarm kapat","alarm durdur","alarm sus","alarm sustur","zil kapat",
        "siren kapat","buzzer kapat","alarmi kapat","alarmi durdur",
    ],
    "BUZZER_BEEP": [
        "bip","bip yap","bip ses","kisa alarm","tek bip","klakson",
        "bip ver","bip cal","kisa ses","bir bip",
    ],
    "FLASHER_ON": [
        "flasor ac","flash ac","strob ac","yanip sonsun","flasor devreye",
        "flasher ac","flasor baslat","yanip sonme",
    ],
    "FLASHER_OFF": [
        "flasor kapat","flash kapat","strob kapat","flasor durdur",
        "flasher kapat","flasor sondur","yanip sonmeyi durdur",
    ],
    "STOP_LIGHT_ON": [
        "stop lambasi ac","stop isigi ac","fren lambasi ac","brake isigi ac",
        "stop lamba yak","fren isigi yak",
    ],
    "STOP_LIGHT_OFF": [
        "stop lambasi kapat","stop isigi kapat","fren lambasi kapat",
        "stop lamba sondur","fren isigi sondur",
    ],
}

# Normalize + _PHRASES listesi (başlangıçta bir kez hazırlanır)
_NORM_PHRASES = {
    cmd: [_norm(p) for p in phrases]
    for cmd, phrases in _PHRASES.items()
}

DIFFLIB_THRESHOLD = 0.54


def _difflib_match(tn: str):
    best_cmd, best_score = None, 0.0
    for cmd, phrases in _NORM_PHRASES.items():
        for phrase in phrases:
            s = difflib.SequenceMatcher(None, tn, phrase).ratio()
            if s > best_score:
                best_score, best_cmd = s, cmd
    return best_cmd, best_score


def detect_vehicle_command(text: str) -> Optional[str]:
    """
    Türkçe metinden araç komutunu tespit eder.
    Döner: komut adı (str) veya None.
    """
    tn  = _norm(text)
    tw  = set(tn.split()) - _FILLERS        # ham token seti
    tws = _expand(tw)                        # ham + kökler

    def has(kws):    return any(k in tn for k in kws)
    def has_w(kws):  return bool(kws & tws)  # kök dahil eşleşme

    # ── 1. ACİL DURDURMA — her şeyden önce ──────────────────────────────────
    if has(["estop","e stop","e-stop","emergency"]):
        return "EMERGENCY_STOP"
    if "acil" in tn:
        return "EMERGENCY_STOP"

    # ── 2. ALARM / BUZZER ────────────────────────────────────────────────────
    if has(["alarm","buzzer","zil","siren"]):
        if has(["kapat","durdur","sus","sustur","kes","off","birak"]):
            return "BUZZER_OFF"
        if has(["bip","klakson","kisa","tek"]):
            return "BUZZER_BEEP"
        return "BUZZER_ON"
    if "bip" in tn:
        return "BUZZER_BEEP"

    # ── 3. FLAŞÖR ────────────────────────────────────────────────────────────
    if has(["flasor","flash","strob","yanip sonsun","yanip sonme"]):
        if has(["kapat","durdur","sondur","off","dur"]):
            return "FLASHER_OFF"
        return "FLASHER_ON"

    # ── 4. STOP LAMBASI / LED ────────────────────────────────────────────────
    if has(["lamba","isik","isig","led","aydinlat","parlat"]):
        if has(["stop","brake"]) or (has(["fren"]) and has(["lamba","isik","isig","led"])):
            return "STOP_LIGHT_OFF" if has(["kapat","sondur","off","birak"]) else "STOP_LIGHT_ON"
        is_off = has_w({"kapat","sondur","birak","kes","off","karart"}) and \
                 not has_w({"ac","yak","ver","on"})
        return "LED_OFF" if is_off else "LED_ON"

    # ── 5. MOTOR ─────────────────────────────────────────────────────────────
    if has(["motor","motoru","motori","motore","motur","moter"]):
        # Durum sorgusu
        if has(["durum","nasil","calisiyor mu","kontrol","acik mi","kapali mi",
                "ne yapiyor","var mi","izle","bakiyor"]):
            return "MOTOR_STATUS"
        # ON: anahtar kelime veya kök eşleşmesi
        if has(["calistir","baslat","devreye","aktif","yak","devret","guc ver",
                "start","calismaya","hazirla","acabilir","acabilirim","acalim"]) \
           or has_w({"ac","on","baslat","calistir","calis","ver","koy"}):
            return "MOTOR_ON"
        # OFF: anahtar kelime veya kök eşleşmesi
        if has(["durdur","kapat","bitir","pasif","devre disi","sondur","sustur",
                "sonlandir","kes","off","stop"]) \
           or has_w({"dur","durdur","kapat","kes","sondur","bitir"}):
            return "MOTOR_OFF"
        return "MOTOR_STATUS"

    # ── 6. SENSÖRLER ─────────────────────────────────────────────────────────
    if has(["sicaklik","derece","kac derece","ne kadar sicak","termal","isinma"]):
        return "GET_TEMP"
    if has(["voltaj","volt","batarya","gerilim","sarj","pil","kac volt","elektrik"]):
        return "GET_VOLTAGE"
    if has(["sistem durumu","genel durum","durum raporu","tum sensor","ne durumda",
            "rapor ver","durum ver","tam rapor","hepsini oku","nasil gidiyor",
            "her seyi soyle","ne var ne yok","arac durumu"]):
        return "GET_ALL"

    # ── 7. FREN — anahtar kelime + kök eşleşmesi ─────────────────────────────
    is_rear  = has(["arka","orka","geri","rear"])
    is_front = has(["on fren","ileri","ondeki","onde","front"]) or \
               " on " in tn or tn.startswith("on ") or tn.endswith(" on")
    is_off   = has(["kapat","birak","birakin","serbest","gevset","kaldir",
                    "geri al","coz","iptal","birakiyor","bos birak"]) \
               or has_w({"kapat","birak","gevset","kaldir","iptal","coz"})
    is_on    = has(["bas","sik","uygula","devreye","aktif","kilitle","cek",
                    "yap","vur","tut","frenle","tuttur"]) \
               or has_w({"ac","on","bas","sik","uygula","tut","vur","yap"})
    has_brk  = has(["fren","freni","frene","frenleri","frenler","frenle",
                    "firen","fireni","firene","firenle",
                    "firan","firani","filen","frem","brake"])

    if has_brk or is_rear or is_front:
        if is_off:
            if is_front and not is_rear: return "FRONT_OFF"
            if is_rear  and not is_front: return "REAR_OFF"
            return "RELEASE"
        else:
            if is_front and not is_rear: return "FRONT_ON"
            if is_rear  and not is_front: return "REAR_ON"
            return "ALL"

    # ── 8. DIFFLIB FALLBACK ───────────────────────────────────────────────────
    best_cmd, best_score = _difflib_match(tn)
    if best_score >= DIFFLIB_THRESHOLD:
        print(f"[CMD] difflib: {best_cmd} ({best_score:.2f}) ← \"{text}\"")
        return best_cmd

    return None
