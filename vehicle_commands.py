"""
Spectraloop - Araç Komut Algılayıcı
Türkçe sesli girişten araç komutunu tespit eder.
Kapsam: motor, fren (ön/arka/tüm), acil durdurma, sensörler.
"""


def _norm(s: str) -> str:
    s = s.lower().strip()
    for tr, en in [('ı','i'),('İ','i'),('ğ','g'),('Ğ','g'),('ş','s'),('Ş','s'),
                   ('ç','c'),('Ç','c'),('ö','o'),('Ö','o'),('ü','u'),('Ü','u')]:
        s = s.replace(tr, en)
    return s


_FILLERS = {
    "bir","bi","hadi","haydi","simdi","lutfen","acaba","bakalim",
    "sana","bana","ama","yani","tamam","peki","ee","ey","hey","iste",
    "biraz","de","da","mi","mu","ya","la","ha","e",
}


def detect_vehicle_command(text: str):
    """
    Türkçe metinden araç komutunu tespit eder.
    Döner: komut adı (str) veya None.
    """
    tn = _norm(text)
    tw = set(tn.split()) - _FILLERS

    def has(kws):    return any(k in tn for k in kws)
    def has_w(kws):  return bool(kws & tw)

    # ── ACİL DURDURMA ────────────────────────────────────────────────────────
    if has(["estop", "e stop", "e-stop"]):
        return "EMERGENCY_STOP"
    if "acil" in tn and (has(["durdur","dur","stop","kes"]) or has_w({"dur","stop","kes"})):
        return "EMERGENCY_STOP"

    # ── MOTOR ────────────────────────────────────────────────────────────────
    if "motor" in tn:
        if has(["durum","nasil","calisiyor","kontrol","acik mi","kapali mi",
                "ne yapiyor","var mi","izle","bakiyor"]):
            return "MOTOR_STATUS"
        if has(["calistir","baslat","devreye","aktif","start","basla","ver"]) or has_w({"ac","on"}):
            return "MOTOR_ON"
        if has(["durdur","kapat","bitir","pasif","devre disi","kes","off","stop"]) or has_w({"dur"}):
            return "MOTOR_OFF"
        return "MOTOR_STATUS"

    # ── SENSÖRLER ────────────────────────────────────────────────────────────
    if has(["sicaklik","isi ","derece","kac derece","ne kadar sicak"]):
        return "GET_TEMP"

    if has(["voltaj","volt","batarya","gerilim","sarj","pil","kac volt"]):
        return "GET_VOLTAGE"

    if has(["sistem durumu","genel durum","durum raporu","tum sensor","ne durumda",
            "rapor ver","durum ver","tam rapor","hepsini oku","nasil gidiyor"]):
        return "GET_ALL"

    # ── FREN ────────────────────────────────────────────────────────────────
    is_rear  = has(["arka","orka","geri","rear"])
    is_front = has(["on fren","ileri","ondeki","onde","front"]) or \
               " on " in tn or tn.startswith("on ") or tn.endswith(" on")
    is_off   = has(["kapat","birak","serbest","gevset","kaldir","geri al","coz","iptal"])
    is_on    = has(["bas","sik","uygula","devreye","aktif","kilitle","cek"]) or has_w({"ac","on"})
    has_brk  = has(["fren","firen","firan","frem","brake"])

    if has_brk or is_rear or is_front:
        if is_off:
            if is_front and not is_rear: return "FRONT_OFF"
            if is_rear  and not is_front: return "REAR_OFF"
            return "RELEASE"
        else:
            if is_front and not is_rear: return "FRONT_ON"
            if is_rear  and not is_front: return "REAR_ON"
            return "ALL"

    return None
