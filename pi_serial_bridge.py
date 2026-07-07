#!/usr/bin/env python3
"""
Spectraloop - Raspberry Pi Seri Kopru
--------------------------------------
MacBook'tan TCP ile komut alir, Arduino'ya UART (RX/TX) ile iletir.

Baglanti:
    Pi GPIO 14 (TXD) --> Arduino RX (D0)
    Pi GPIO 15 (RXD) --> Arduino TX (D1)
    GND              --> GND  (ortak toprak zorunlu)

Pi UART etkinlestirme (/boot/config.txt veya raspi-config):
    enable_uart=1
    dtoverlay=disable-bt   # Pi 3/4/5: Bluetooth'u devre disi birak,
                           # boylece /dev/ttyAMA0 Arduino'ya baglanir

Kurulum:   pip3 install pyserial
Calistir:  python3 pi_serial_bridge.py

Komut eslemesi (TCP metin -> Arduino dizesi):
    ALL          -> 'A'    (tum frenler ON)
    RELEASE      -> 'X'    (tum frenler serbest)
    FRONT_ON     -> 'F'    (on fren ON)
    FRONT_OFF    -> 'f'    (on fren OFF)
    REAR_ON      -> 'R'    (arka fren ON)
    REAR_OFF     -> 'r'    (arka fren OFF)
    MOTOR_ON     -> 'MN'   (motor ON)
    MOTOR_OFF    -> 'MF'   (motor OFF)
    MOTOR_STATUS -> 'MS'   (motor durumu)
    GET_TEMP     -> 'GT'   (sicaklik)
    GET_VOLTAGE  -> 'GV'   (voltaj)
    GET_ALL      -> 'GA'   (tum sensor verileri)
    LED_ON       -> 'LN'   (LED ac)
    LED_OFF      -> 'LF'   (LED kapat)
"""
import socket
import time
import serial

# --- Ayarlar ---
SERIAL_PORT = "/dev/ttyAMA0"   # Pi hardware UART (GPIO14/15). Bluetooth kapali olmali.
BAUD = 115200
TCP_HOST = "0.0.0.0"           # Tum arayuzlerde dinle
TCP_PORT = 5005

CMD_MAP = {
    "ALL":            "A",
    "RELEASE":        "X",
    "FRONT_ON":       "F",
    "FRONT_OFF":      "f",
    "REAR_ON":        "R",
    "REAR_OFF":       "r",
    "MOTOR_ON":       "MN",
    "MOTOR_OFF":      "MF",
    "MOTOR_STATUS":   "MS",
    "GET_TEMP":       "GT",
    "GET_VOLTAGE":    "GV",
    "GET_ALL":        "GA",
    "EMERGENCY_STOP": "ES",
    "BUZZER_ON":      "BN",
    "BUZZER_OFF":     "BF",
    "BUZZER_BEEP":    "BB",
    "FLASHER_ON":     "FLN",
    "FLASHER_OFF":    "FLF",
    "STOP_LIGHT_ON":  "SLN",
    "STOP_LIGHT_OFF": "SLF",
    "LED_ON":         "LN",
    "LED_OFF":        "LF",
}


def main():
    # Arduino'ya baglan
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
    time.sleep(2)  # Arduino reset sonrasi bekle
    print(f"[Pi] Arduino baglandi: {SERIAL_PORT}")

    # TCP sunucu
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((TCP_HOST, TCP_PORT))
    srv.listen(1)
    print(f"[Pi] TCP dinleniyor: 0.0.0.0:{TCP_PORT}")

    while True:
        conn, addr = srv.accept()
        print(f"[Pi] Baglanti: {addr}")
        with conn:
            buffer = ""
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    cmd = line.strip().upper()
                    if not cmd:
                        continue
                    serial_cmd = CMD_MAP.get(cmd)
                    if serial_cmd is None:
                        print(f"[Pi] Bilinmeyen komut: {cmd}")
                        conn.sendall(b"ERR\n")
                        continue
                    ser.write((serial_cmd + "\n").encode())
                    print(f"[Pi] -> Arduino: {cmd} ({serial_cmd!r})")
                    resp = ser.readline().decode(errors="ignore").strip()
                    conn.sendall((resp + "\n").encode())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Pi] Kapatiliyor.")
