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
        "fren yap","firen yap","firan yap","tiren yap","tiran yap",
        "kiran yap","vren yap",
        "frene bas","frenleri ac","tum frenleri ac",
        "butun frenleri ac","frenle","frenleme yap","frenleri devreye al",
        "frenleri uygula","frenleri kilitle","frenleri sik","frenleri vur",
        "frenleri tut","frenleri tuttur","tam fren","tam frenleme","her iki frene bas",
        "her iki freni ac","iki freni de ac","komple fren","tum frenlere bas",
        "hem on hem arka fren","freni cek","frenleri aktif et",
        "kirani devreye al","tireni devreye al","fireni devreye al",
    ],
    "RELEASE": [
        "freni birak","frenleri birak","serbest birak","freni kapat",
        "frenleri kapat","tum frenleri birak","hepsini birak","hepsini kapat",
        "freni serbest birak","frenleri serbest birak","freni gevset",
        "frenden cik","freni kaldir","frenleri kaldir","freni geri al",
        "fireni birak","fireni kapat","firani birak","kirani birak",
        "tirani birak","tireni birak","freni iptal","freni coz",
        "frenleri bos birak","frene basma","frenleri devre disi birak",
    ],
    "EMERGENCY_STOP": [
        "acil durdur","acil dur","acil stop","acil fren","acil frenleme",
        "hemen durdur","hemen dur","hemen frene bas",
        "e stop","estop","emergency stop","emergency",
        "tehlike durdur","aninda durdur","aninda dur","tam dur","tam durdur",
    ],
    "GET_TEMP": [
        "sicaklik","sicaklik nedir","kac derece","kac dereceyiz","ne kadar sicak",
        "aracin sicakligi","sistem sicakligi","sicakliği soyle","sicakliği ver",
        "isi olcumu","sicaklik raporu","termal durum","sicak mi",
        "kac derecede","derece nedir","kac isi","termometre",
        "isiklik","isinma durumu","ne kadar isi","sicaklik bilgisi",
        # Whisper varyantları
        "sıcaklık","sicak lik","sıcak lık",
    ],
    "GET_VOLTAGE": [
        "voltaj","voltaj nedir","kac volt","batarya durumu","batarya nedir",
        "bataryanin durumu","bataryayi soyle","batarya seviyesi",
        "bataria durumu","batariya durumu",             # Whisper varyantları
        "aku durumu","aku seviyesi","akusu nedir",      # akü varyantları
        "sarj durumu","sarj nedir","sarj seviyesi","sarj var mi",
        "pil durumu","pil seviyesi","gerilim nedir","guc var mi",
        "batarya dolu mu","batarya bitti mi","elektrik durumu",
        "voltaj raporu","batarya raporu",
    ],
    "GET_ALL": [
        "sistem durumu","sistemin durumu","sistem raporu",
        "genel durum","genel rapor","genel bilgi",
        "durum raporu","tam rapor","tam bilgi ver","tam durum",
        "tum sensorler","tum bilgiler","hepsini soyle","hepsini oku","hepsini goster",
        "ne durumda","nasil gidiyor","nasil bir durum",
        "durum ver","rapor ver","bilgi ver",
        "her seyi soyle","ne var ne yok","arac durumu","aracin durumu",
        "son durum","durum nedir","guncel durum","sistem bilgisi",
    ],
    "LED_ON": [
        "led ac","ledi ac","ledleri ac","led yak","ledleri yak",
        "isik ac","isigi ac","isiklari ac","isik ver","isiklari yak",
        "lamba ac","lambayi ac","lambalari ac","lambayi yak",
        "aydinlat","parlat","isiklandir","led devreye al","ledleri aktif et",
        "led on","isik on","lamba on",
        "let ac","yet ac","led ack",                   # Whisper: LED→let/yet
        "isiklari ac","isiklari devreye al","aydinlatmayi ac",
        "ışıkları aç","lambalari yak","ışıkları devreye al",
    ],
    "LED_OFF": [
        "led kapat","ledi kapat","ledleri kapat","led sondur","ledleri sondur",
        "isik kapat","isigi kapat","isiklari kapat","isiklari sondur",
        "lamba kapat","lambayi kapat","lambalari kapat","lambayi sondur",
        "isigi sondur","isiklari sondur","karart","karanlik yap",
        "led devre disi","isik yok","lamba yok","isigi kes",
        "led off","isik off","lamba off",
        "let kapat","yet kapat",                        # Whisper: LED→let/yet
        "aydinlatmayi kapat","isiklari birak","ledleri birak",
        "ışıkları kapat","lambalari kapat","ışıkları söndür",
    ],
    "BUZZER_ON": [
        "alarm ac","alarmi ac","alarm calistir","alarm devreye al",
        "zil cal","zili cal","siren ac","sireni ac",
        "buzzer ac","bazar ac","buzer ac","buser ac",    # Whisper: buzzer→bazar/buzer
        "alarm ver","alarm baslat","alarmi devreye al",
        "ikaz ver","uyari ver","uyari ac","ikaz ac",
        "alarmı aç","alarmı çalıştır","zili çal",
    ],
    "BUZZER_OFF": [
        "alarm kapat","alarmi kapat","alarm durdur","alarm sus","alarm sustur",
        "zil kapat","zili kapat","siren kapat","sireni kapat",
        "buzzer kapat","bazar kapat","buzer kapat","buser kapat",  # Whisper varyantları
        "alarmi durdur","alarmı kapat","alarmı sustur",
        "ikaz kapat","uyari kapat","ikaz durdur",
    ],
    "BUZZER_BEEP": [
        "bip","bip yap","bip ses","bip ver","bip cal","bir bip","tek bip",
        "kisa alarm","kisa ses","kisa bip","klakson","klaksonu cal",
        "beep","beep yap","bir bip sesi","bip sesi ver",
    ],
    "FLASHER_ON": [
        "flasor ac","flaser ac","flesur ac","flashor ac",  # Whisper varyantları
        "flash ac","strob ac","flasher ac",
        "yanip sonsun","yanip sonme","yanip sonmeyi baslat",
        "flasor devreye","flasor baslat","flasor aktif",
        "flaşer aç","flaşör aç","flaşör devreye","flaşörü aç",
        "yanıp sönsün","yanıp sönme aç",
    ],
    "FLASHER_OFF": [
        "flasor kapat","flaser kapat","flasor sondur","flasor durdur",
        "flash kapat","strob kapat","flasher kapat",
        "flaşer kapat","flaşörü kapat","flaşör kapat",    # Whisper varyantları
        "yanip sonmeyi durdur","yanip sonmeyi kapat","yanip sonmeyi kes",
        "yanıp sönmeyi durdur","yanıp sönmeyi kapat",
        "flasor devre disi","flasor birak",
    ],
    "STOP_LIGHT_ON": [
        "stop lambasi ac","stop lambasi yak","stop isigi ac","stop isigi yak",
        "fren lambasi ac","fren lambasi yak","fren isigi ac","fren isigi yak",
        "brake isigi ac","brake lambasi ac",
        "stop lamba yak","stop lamba ac","stop ısığı aç",
    ],
    "STOP_LIGHT_OFF": [
        "stop lambasi kapat","stop lambasi sondur","stop isigi kapat","stop isigi sondur",
        "fren lambasi kapat","fren lambasi sondur","fren isigi kapat","fren isigi sondur",
        "brake isigi kapat","stop lamba sondur","stop lamba kapat",
    ],
}

# Normalize + _PHRASES listesi (başlangıçta bir kez hazırlanır)
_NORM_PHRASES = {
    cmd: [_norm(p) for p in phrases]
    for cmd, phrases in _PHRASES.items()
}

DIFFLIB_THRESHOLD = 0.70   # altında → emin değil → None döner


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

    # ── 0. OLUMSUZLAMA — "istemiyorum/yapma/hayır" varsa komut yok ───────────
    _NEGATIONS = ["istemiyorum","istemem","yapmayin","yapmayalim",
                  "yapmak istemiyorum","yapmak istemem"]
    if any(neg in tn for neg in _NEGATIONS):
        return None

    # ── 1. ACİL DURDURMA — her şeyden önce ──────────────────────────────────
    if has(["estop","e stop","e-stop","emergency"]):
        return "EMERGENCY_STOP"
    # "acil" veya ses benzerleri (asil/acal/hacil) + eylem kelimesi
    _EMRG_TRIGGERS = {"acil","asil","acal","hacil","acill","asill"}
    _EMRG_ACTIONS  = {"durdur","dur","stop","kes","fren","frene","bas",
                      "durttur","durduru","durtur"}
    if tws & _EMRG_TRIGGERS:
        # Tek başına "acil" bile yeterli (demos ortamında her acil = emergency)
        if "acil" in tn or (tws & _EMRG_TRIGGERS and tws & _EMRG_ACTIONS):
            return "EMERGENCY_STOP"

    # ── 2. ALARM / BUZZER ────────────────────────────────────────────────────
    # "bazar/buzer/buser" → Whisper'ın "buzzer" için ürettiği varyantlar
    if has(["alarm","alarmi","alarmi","buzzer","bazar","buzer","buser","zil","siren","sireni","ikaz","uyari"]):
        if has(["kapat","durdur","sus","sustur","kes","off","birak","iptal"]):
            return "BUZZER_OFF"
        if has(["bip","klakson","kisa","tek","beep"]):
            return "BUZZER_BEEP"
        if has(["ac","calistir","devreye","ver","baslat","cal","on","aktif","ver","calis"]):
            return "BUZZER_ON"
        # alarm detected but no explicit action → fall through
    if has(["bip","beep"]):
        return "BUZZER_BEEP"

    # ── 3. FLAŞÖR ────────────────────────────────────────────────────────────
    # "flaser/flesur/flashor/flasor" → Whisper varyantları
    if has(["flasor","flaser","flesur","flashor","flash","strob",
            "yanip sonsun","yanip sonme","yanip"]):
        if has(["kapat","durdur","sondur","off","dur","birak","iptal"]):
            return "FLASHER_OFF"
        return "FLASHER_ON"

    # ── 4. STOP LAMBASI / LED ────────────────────────────────────────────────
    # "let/yet" → Whisper'ın "LED" için ürettiği varyantlar
    if has(["lamba","lambayi","lambalari","isik","isigi","isiklari","isig",
            "led","ledi","ledleri","let","yet","aydinlat","parlat","karanlik"]):
        # Stop lambası
        if has(["stop","brake"]) or (has(["fren"]) and has(["lamba","isik","led"])):
            return "STOP_LIGHT_OFF" if has(["kapat","sondur","off","birak"]) else "STOP_LIGHT_ON"
        # Genel LED
        is_off = has(["kapat","sondur","birak","kes","off","karart","karanlik",
                      "sondurabilir","kapatabilir"]) and \
                 not has(["ac","yak","ver","devreye","aktif"])
        is_on  = has(["ac","yak","ver","devreye","aktif","on","parlat","aydinlat"])
        if is_off:
            return "LED_OFF"
        if is_on:
            return "LED_ON"
        # LED kelimesi var ama açık/kapalı belli değil → geç

    # ── 5. MOTOR ─────────────────────────────────────────────────────────────
    _MOTOR_WORDS = ["motor","motoru","motori","motore","motorun","motorlari",
                    "motur","moturu","moter","motora","motoyu","matoru"]
    if has(_MOTOR_WORDS):
        # Durum sorgusu
        if has(["durum","nasil","calisiyor mu","kontrol","acik mi","kapali mi",
                "ne yapiyor","var mi","izle","bakiyor","calisip"]):
            return "MOTOR_STATUS"
        # ON
        if has(["calistir","calısır","baslat","devreye","aktif","yak","devret",
                "guc ver","start","calismaya","hazirla","acabilir","acabilirim",
                "acalim","calissin","calıssin"]) \
           or has_w({"ac","on","baslat","calistir","calis","koy","yak"}):
            return "MOTOR_ON"
        # OFF
        if has(["durdur","durttur","durtur","kapat","bitir","pasif","devre disi",
                "sondur","sustur","sonlandir","kes","off","stop","kapatabilir"]) \
           or has_w({"dur","durdur","kapat","kes","sondur","bitir","sustur"}):
            return "MOTOR_OFF"
        return "MOTOR_STATUS"

    # ── 6. SENSÖRLER ─────────────────────────────────────────────────────────
    # GET_TEMP — "ısıklık" gibi Whisper hataları + termometre + kaç ısı
    if has(["sicaklik","sicakligi","sicakliği","sicakligini","sicaklikta",
            "derece","kac derece","kac dereceyiz","ne kadar sicak",
            "termal","isinma","termometre","kac isi","isi olcumu",
            "isinma durumu","sicak mi","ne kadar isi"]):
        return "GET_TEMP"

    # GET_VOLTAGE — "bataria/batariya/aku/paterya" Whisper varyantları
    if has(["voltaj","volt","batarya","bataryanin","bataryayi","bataryasi",
            "bataria","batariya","paterya",
            "aku","akü","akusu","aküsü",
            "gerilim","sarj","sarji","pil","pili",
            "kac volt","elektrik","guc seviyesi","sarj seviyesi",
            "batarya dolu","batarya bitti"]):
        return "GET_VOLTAGE"

    # GET_ALL — daha fazla doğal söylem
    if has(["sistem durumu","sistemin durumu","sistem raporu",
            "genel durum","genel rapor","genel bilgi",
            "durum raporu","tam rapor","tam bilgi",
            "tum sensor","tum sensorler",
            "ne durumda","nasil gidiyor",
            "rapor ver","durum ver","bilgi ver","hepsini goster","hepsini oku",
            "her seyi soyle","ne var ne yok","arac durumu","aracin durumu",
            "durum nedir","durum soyle","son durum"]):
        return "GET_ALL"

    # ── 7. FREN — anahtar kelime + kök eşleşmesi ─────────────────────────────
    is_rear  = has(["arka","orka","geri","rear"])
    is_front = has(["on fren","onfren","onfrene","onfreni","ileri","ondeki","onde","front"])
    is_off   = has(["kapat","birak","birakin","serbest","gevset","kaldir",
                    "geri al","coz","iptal","birakiyor","bos birak"]) \
               or has_w({"kapat","birak","gevset","kaldir","iptal","coz"})
    is_on    = has(["bas","sik","uygula","devreye","aktif","kilitle","cek",
                    "yap","vur","tut","frenle","tuttur"]) \
               or has_w({"ac","on","bas","sik","uygula","tut","vur","yap"})
    has_brk  = has(["fren","freni","frene","frenleri","frenler","frenle",
                    "firen","fireni","firene","firenle",
                    "firan","firani","filen","frem",
                    "kiran","kirani","kirane","kiranleri",   # Whisper: fren→kiran
                    "tiren","tireni","tirene",               # Whisper: fren→tiren
                    "tiran","tirani",                        # Whisper: fren→tiran
                    "vren","vreni",                          # Whisper: fren→vren
                    "brake"])

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
    _MOTOR_SET   = {"motor","motoru","motur","motori","motore","motorun"}
    _VOLTAGE_SET = {"voltaj","volt","batarya","aku","sarj","gerilim","pil"}
    _BRAKE_SET   = {"fren","freni","frene","firan","firen","kiran","tiren","tiran","vren","brake"}
    _LED_SET     = {"led","ledi","ledleri","lamba","lambayi","isik","isigi","isiklari","let","yet","aydinlat"}
    _ALARM_SET   = {"alarm","alarmi","buzzer","bazar","buzer","buser","zil","siren","ikaz","uyari"}

    best_cmd, best_score = _difflib_match(tn)
    if best_score >= DIFFLIB_THRESHOLD:
        # Bağlam doğrulaması: ilgili kök kelime yoksa reddet
        if best_cmd in ("MOTOR_ON","MOTOR_OFF","MOTOR_STATUS") and not (tws & _MOTOR_SET):
            return None
        if best_cmd == "GET_VOLTAGE" and not (tws & _VOLTAGE_SET):
            return None
        if best_cmd in ("FRONT_ON","FRONT_OFF","REAR_ON","REAR_OFF","ALL","RELEASE") \
                and not (tws & _BRAKE_SET) and not is_rear and not is_front:
            return None
        if best_cmd in ("LED_ON","LED_OFF") and not (tws & _LED_SET):
            return None
        if best_cmd in ("BUZZER_ON","BUZZER_OFF","BUZZER_BEEP") and not (tws & _ALARM_SET):
            return None
        print(f"[CMD] difflib: {best_cmd} ({best_score:.2f}) ← \"{text}\"")
        return best_cmd

    return None
