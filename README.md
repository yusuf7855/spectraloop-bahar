# Spectraloop — Sesli Komut Fren Sistemi (Bas-Konuş)

Bas-konuş (push-to-talk) mantığıyla **Türkçe** sesli komutları fren aktüatörlerine
(test aşamasında MOSFET) çeviren kontrol sistemi. `S` tuşuna basılı tutulur, konuşulur,
bırakılınca komut yazıya çevrilip Raspberry Pi üzerinden Arduino'ya iletilir.

## Mimari

```
MacBook (yer istasyonu)          Raspberry Pi 4            Arduino Uno
 mikrofon + S tuşu     --TCP-->   TCP sunucu     --USB--> 4 MOSFET (D7-D10)  -->  ön / arka
 Whisper (TR) + ayrıştır   WiFi   seri köprü      seri     aktif-HIGH sürme       fren valfleri
```

Komut ayrıştırma MacBook'ta yapılır; Pi sadece köprüdür; Arduino donanımı sürer.

## Dosyalar

| Dosya | Cihaz | Görev |
|---|---|---|
| `mac_voice_client.py` | MacBook | Bas-konuş kaydı, `faster-whisper` ile Türkçe STT, komut ayrıştırma, TCP ile Pi'ye gönderim |
| `pi_serial_bridge.py` | Raspberry Pi 4 | TCP'den komut alır, USB seri ile Arduino'ya iletir |
| `arduino_brake_control/arduino_brake_control.ino` | Arduino Uno | Tek harf komutu (`A/F/R/X`) alıp 4 MOSFET'i sürer |

## Komut haritası

| Söylenen | Komut | Kanal (MOSFET) |
|---|---|---|
| "spectra frenleri sık" | `ALL` (`A`) | 1·2·3·4 (hepsi) |
| "ön freni sık" | `FRONT` (`F`) | 1·2 (D7·D8) |
| "arka frenleri sık" | `REAR` (`R`) | 3·4 (D9·D10) |
| "frenleri bırak" / "serbest" | `RELEASE` (`X`) | hepsi kapanır |

## Donanım / pin haritası

| Röle | Arduino pin | Fren |
|---|---|---|
| Röle 1 | D7 | Ön fren |
| Röle 2 | D8 | Arka fren |

Röle notları (standart Arduino röle kartı, aktif-LOW):
- **Aktif-LOW:** IN pinine LOW = röle kapanır = fren ON.
- Arduino 5V → röle kartı VCC, Arduino GND → röle kartı GND.
- Röle kartın aktif-HIGH ise `arduino_brake_control.ino` içindeki `RELAY_ON = LOW` satırını `HIGH` yap.

## Kurulum

### 1. Arduino
`arduino_brake_control/` klasörünü Arduino IDE ile aç, `arduino_brake_control.ino`'yu yükle (baud 115200).
Seri Monitör'den `A` `F` `R` `X` yazarak kanalları tek tek doğrula.

### 2. Raspberry Pi
```bash
pip3 install pyserial
ls /dev/ttyACM*     # Arduino portu (genelde ttyACM0)
hostname -I         # Pi'nin IP'si (Mac'e lazım)
python3 pi_serial_bridge.py
```
Port farklıysa `pi_serial_bridge.py` içindeki `SERIAL_PORT`'u güncelle.

### 3. MacBook
```bash
brew install portaudio
pip3 install sounddevice numpy faster-whisper pynput
```
- `mac_voice_client.py` içindeki `PI_HOST`'u Pi'nin IP'si yap.
- macOS izni: Sistem Ayarları → Gizlilik ve Güvenlik → **Erişilebilirlik** ve **Girdi İzleme** altında Terminal'e izin ver (yoksa `S` tuşu algılanmaz).
- İlk çalıştırmada Whisper modeli iner (~460 MB, bir kez). Sonrası offline.
```bash
python3 mac_voice_client.py
```
`S`'yi basılı tut → konuş → bırak. Çıkış: `ESC`.

## Güvenlik notu

Sesli komut, STT gecikmesi (~1-2 sn) ve yanlış-anlama ihtimali nedeniyle asıl
**acil-durdurma (E-stop) sisteminin yerine değil**, operatör kolaylığı olarak onun
yanında kullanılmalıdır.

---
Spectraloop • TEKNOFEST Hyperloop
