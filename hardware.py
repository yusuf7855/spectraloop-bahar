"""
Spectraloop - Donanım Katmanı
Araç komutlarını TCP üzerinden Raspberry Pi'ye gönderir.
"""
import socket

PI_HOST = "192.168.1.8"
PI_PORT = 5005

COMMAND_LABELS = {
    "FRONT_ON":       "Ön fren devreye alındı.",
    "FRONT_OFF":      "Ön fren serbest bırakıldı.",
    "REAR_ON":        "Arka fren devreye alındı.",
    "REAR_OFF":       "Arka fren serbest bırakıldı.",
    "ALL":            "Tüm frenler devreye alındı.",
    "RELEASE":        "Tüm frenler serbest bırakıldı.",
    "MOTOR_ON":       "Motor çalışıyor.",
    "MOTOR_OFF":      "Motor durduruldu.",
    "EMERGENCY_STOP": "Acil durdurma! Tüm frenler devreye alındı, motor durduruldu.",
    "BUZZER_ON":      "Alarm çalıyor.",
    "BUZZER_OFF":     "Alarm kapatıldı.",
    "BUZZER_BEEP":    "Bip!",
    "FLASHER_ON":     "Flaşör açıldı.",
    "FLASHER_OFF":    "Flaşör kapatıldı.",
    "STOP_LIGHT_ON":  "Stop lambası yandı.",
    "STOP_LIGHT_OFF": "Stop lambası söndürüldü.",
    "LED_ON":         "LED'ler açıldı.",
    "LED_OFF":        "LED'ler kapatıldı.",
}


def _tcp_send(command: str) -> str:
    try:
        with socket.create_connection((PI_HOST, PI_PORT), timeout=3) as s:
            s.sendall((command + "\n").encode())
            return s.recv(1024).decode(errors="ignore").strip()
    except socket.timeout:
        return "ERR:TIMEOUT"
    except ConnectionRefusedError:
        return "ERR:REFUSED"
    except OSError as e:
        if "Network is unreachable" in str(e) or "No route to host" in str(e):
            return "ERR:NETWORK"
        return f"ERR:{e}"
    except Exception as e:
        return f"ERR:{e}"


def _parse_sensor(command: str, data: str) -> str:
    if command == "GET_TEMP":
        try:    return f"Araç sıcaklığı {float(data):.1f} derece."
        except: return f"Sıcaklık: {data}"
    if command == "GET_VOLTAGE":
        try:    return f"Batarya gerilimi {float(data):.1f} volt."
        except: return f"Voltaj: {data}"
    if command == "MOTOR_STATUS":
        return "Motor şu an çalışıyor." if "ON" in data.upper() else "Motor şu an durdu."
    if command == "GET_ALL":
        parts = {}
        for item in data.split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                parts[k.strip().upper()] = v.strip().upper()
        pieces = []
        if "TEMP"    in parts: pieces.append(f"sıcaklık {parts['TEMP']} derece")
        if "VOLT"    in parts: pieces.append(f"batarya {parts['VOLT']} volt")
        if "MOTOR"   in parts: pieces.append(f"motor {'çalışıyor' if parts['MOTOR']=='ON' else 'durdu'}")
        if "BRAKE_F" in parts: pieces.append(f"ön fren {'aktif' if parts['BRAKE_F']=='ON' else 'serbest'}")
        if "BRAKE_R" in parts: pieces.append(f"arka fren {'aktif' if parts['BRAKE_R']=='ON' else 'serbest'}")
        return ("Sistem durumu: " + ", ".join(pieces) + ".") if pieces else "Durum alındı."
    return data


def send_vehicle_command(command: str) -> str:
    raw = _tcp_send(command)
    print(f"[HW] {command} → {raw}")

    if raw == "ERR:TIMEOUT":
        return f"Pi'ye bağlanılamadı. {PI_HOST} adresine ulaşılamadı."
    if raw == "ERR:REFUSED":
        return f"Pi bağlantıyı reddetti. Bridge çalışıyor mu?"
    if raw == "ERR:NETWORK":
        return f"Pi ağda bulunamadı. Aynı Wi-Fi'de misiniz?"
    if raw.startswith("ERR"):
        return f"Hata: {raw}"

    label = COMMAND_LABELS.get(command)
    if label:
        return label if raw.startswith("OK") else f"Komut hatası: {raw}"

    if raw.startswith("DATA:"):
        return _parse_sensor(command, raw[5:])

    return "Komut işlendi."
