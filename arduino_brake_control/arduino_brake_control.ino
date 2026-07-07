/*
 * Spectraloop - Arac Kontrol Sistemi (Arduino Uno)
 * -------------------------------------------------
 * Donanim:
 *   D6  -> Motor rolesi IN
 *   D7  -> On fren rolesi IN
 *   D8  -> Arka fren rolesi IN
 *   D9  -> Buzzer / Alarm rolesi IN
 *   D10 -> Flasor rolesi IN
 *   D11 -> Stop lambasi rolesi IN
 *   D12 -> LED surucusu (MOSFET gate veya rele IN)
 *   A0  -> NTC sicaklik sensoru (10k NTC + 10k pull-up, 5V)
 *   A1  -> Batarya voltaj bolucusu (R1=30k, R2=10k, max 20V -> max 5V)
 *
 * Komut protokolu (\n ile sonlanan dizeler):
 *   Tek-karakter geri-uyumlu fren komutlari:
 *     'A'  -> Tum frenler ON
 *     'X'  -> Tum frenler OFF
 *     'F'  -> On fren ON
 *     'f'  -> On fren OFF
 *     'R'  -> Arka fren ON
 *     'r'  -> Arka fren OFF
 *
 *   Motor:
 *     "MN" -> Motor ON          -> "OK:MN\n"
 *     "MF" -> Motor OFF         -> "OK:MF\n"
 *     "MS" -> Motor durumu      -> "DATA:MOTOR:ON\n" veya "DATA:MOTOR:OFF\n"
 *
 *   Sensorler:
 *     "GT" -> Sicaklik al       -> "DATA:23.5\n"
 *     "GV" -> Voltaj al         -> "DATA:12.3\n"
 *     "GA" -> Tum sensor verisi -> "DATA:TEMP:23.5,VOLT:12.3,MOTOR:OFF,BRAKE_F:OFF,BRAKE_R:OFF\n"
 *
 *   Acil:
 *     "ES" -> Acil durdurma     -> "OK:ES\n"  (motor OFF + iki fren ON, atomik)
 *
 *   Isik / Ses:
 *     "BN"  -> Alarm surekli ON  -> "OK:BN\n"
 *     "BF"  -> Alarm OFF         -> "OK:BF\n"
 *     "BB"  -> Kisa bip (100ms)  -> "OK:BB\n"
 *     "FLN" -> Flasor ON (500ms) -> "OK:FLN\n"
 *     "FLF" -> Flasor OFF        -> "OK:FLF\n"
 *     "SLN" -> Stop lambasi ON   -> "OK:SLN\n"
 *     "SLF" -> Stop lambasi OFF  -> "OK:SLF\n"
 *     "LN"  -> LED ON            -> "OK:LN\n"
 *     "LF"  -> LED OFF           -> "OK:LF\n"
 *
 *   Bilinmeyen komut            -> "ERR:cmd\n"
 *
 * Role mantigi (standart Arduino role karti = AKTIF-LOW):
 *   LOW  = role kapali = yuk ON
 *   HIGH = role acik   = yuk OFF
 *
 * Steinhart-Hart (B parametreli basitlestirilmis):
 *   B = 3950, R0 = 10000 ohm, T0 = 25 degC (298.15 K)
 *
 * Voltaj olcegi:
 *   Bolucusu orani = (30k + 10k) / 10k = 4
 *   scale = 5.0 / 1023.0 * 4.0
 */

#include <math.h>

// ── Pin tanimlari ─────────────────────────────────────────────────────────────
const int PIN_MOTOR       = 6;
const int PIN_RELAY_FRONT = 7;
const int PIN_RELAY_REAR  = 8;
const int PIN_BUZZER      = 9;
const int PIN_FLASHER     = 10;
const int PIN_STOP_LIGHT  = 11;
const int PIN_LED         = 12;
const int PIN_TEMP        = A0;
const int PIN_VOLT        = A1;

// Role mantigi (AKTIF-LOW)
const int RELAY_ON  = LOW;
const int RELAY_OFF = HIGH;

// ── NTC sabitleri ─────────────────────────────────────────────────────────────
const float NTC_B  = 3950.0f;
const float NTC_R0 = 10000.0f;
const float NTC_T0 = 298.15f;   // 25 degC cinsinden Kelvin
const float PULL_R  = 10000.0f; // 10k pull-up

// ── Durum degiskenleri ────────────────────────────────────────────────────────
bool motorOn     = false;
bool brakeFront  = false;
bool brakeRear   = false;
bool buzzerOn    = false;
bool flasherOn   = false;
bool stopLightOn = false;
bool ledOn       = false;

// ── Zamanlayici degiskenleri ──────────────────────────────────────────────────
unsigned long lastFlashTime = 0;
bool          flashState    = false;
const unsigned long FLASH_INTERVAL = 500UL;  // ms — yanip sonme suresi

unsigned long beepEndTime = 0;
bool          beepActive  = false;
const unsigned long BEEP_DURATION = 100UL;   // ms — kisa bip suresi

// ── Seri tampon ───────────────────────────────────────────────────────────────
String inputBuffer = "";

// ── Yardimci: sicaklik oku (Celsius) ─────────────────────────────────────────
float readTemperature() {
    int raw = analogRead(PIN_TEMP);
    if (raw <= 0 || raw >= 1023) return -999.0f;
    float vRatio = (float)raw / 1023.0f;
    float rNTC   = PULL_R * vRatio / (1.0f - vRatio);
    float lnR    = log(rNTC / NTC_R0);
    float tempK  = 1.0f / (1.0f / NTC_T0 + lnR / NTC_B);
    return tempK - 273.15f;
}

// ── Yardimci: voltaj oku (Volt) ───────────────────────────────────────────────
float readVoltage() {
    int raw = analogRead(PIN_VOLT);
    return (float)raw * 5.0f / 1023.0f * 4.0f;
}

// ── Komut isleme ──────────────────────────────────────────────────────────────
void handleCommand(String line) {

    // ── Tek-karakter geri-uyumlu fren komutlari ──────────────────────────────
    if (line.length() == 1) {
        char cmd = line.charAt(0);
        switch (cmd) {
            case 'A':
                digitalWrite(PIN_RELAY_FRONT, RELAY_ON);
                digitalWrite(PIN_RELAY_REAR,  RELAY_ON);
                brakeFront = true; brakeRear = true;
                Serial.println("OK:A"); break;
            case 'X':
                digitalWrite(PIN_RELAY_FRONT, RELAY_OFF);
                digitalWrite(PIN_RELAY_REAR,  RELAY_OFF);
                brakeFront = false; brakeRear = false;
                Serial.println("OK:X"); break;
            case 'F':
                digitalWrite(PIN_RELAY_FRONT, RELAY_ON);
                brakeFront = true;
                Serial.println("OK:F"); break;
            case 'f':
                digitalWrite(PIN_RELAY_FRONT, RELAY_OFF);
                brakeFront = false;
                Serial.println("OK:f"); break;
            case 'R':
                digitalWrite(PIN_RELAY_REAR, RELAY_ON);
                brakeRear = true;
                Serial.println("OK:R"); break;
            case 'r':
                digitalWrite(PIN_RELAY_REAR, RELAY_OFF);
                brakeRear = false;
                Serial.println("OK:r"); break;
            default:
                Serial.print("ERR:"); Serial.println(cmd); break;
        }
        return;
    }

    // ── Motor ────────────────────────────────────────────────────────────────
    if (line == "MN") {
        digitalWrite(PIN_MOTOR, RELAY_ON);
        motorOn = true;
        Serial.println("OK:MN");
        return;
    }
    if (line == "MF") {
        digitalWrite(PIN_MOTOR, RELAY_OFF);
        motorOn = false;
        Serial.println("OK:MF");
        return;
    }
    if (line == "MS") {
        Serial.println(motorOn ? "DATA:MOTOR:ON" : "DATA:MOTOR:OFF");
        return;
    }

    // ── Sensorler ────────────────────────────────────────────────────────────
    if (line == "GT") {
        float t = readTemperature();
        Serial.print("DATA:"); Serial.println(t, 1);
        return;
    }
    if (line == "GV") {
        float v = readVoltage();
        Serial.print("DATA:"); Serial.println(v, 1);
        return;
    }
    if (line == "GA") {
        float t = readTemperature();
        float v = readVoltage();
        Serial.print("DATA:TEMP:"); Serial.print(t, 1);
        Serial.print(",VOLT:");     Serial.print(v, 1);
        Serial.print(",MOTOR:");    Serial.print(motorOn    ? "ON" : "OFF");
        Serial.print(",BRAKE_F:");  Serial.print(brakeFront ? "ON" : "OFF");
        Serial.print(",BRAKE_R:");  Serial.print(brakeRear ? "ON" : "OFF");
        Serial.print(",LED:");      Serial.println(ledOn ? "ON" : "OFF");
        return;
    }

    // ── Acil durdurma ────────────────────────────────────────────────────────
    if (line == "ES") {
        digitalWrite(PIN_MOTOR,       RELAY_OFF);
        digitalWrite(PIN_RELAY_FRONT, RELAY_ON);
        digitalWrite(PIN_RELAY_REAR,  RELAY_ON);
        motorOn = false; brakeFront = true; brakeRear = true;
        Serial.println("OK:ES");
        return;
    }

    // ── Alarm / Buzzer ───────────────────────────────────────────────────────
    if (line == "BN") {
        beepActive = false;
        digitalWrite(PIN_BUZZER, RELAY_ON);
        buzzerOn = true;
        Serial.println("OK:BN");
        return;
    }
    if (line == "BF") {
        beepActive = false;
        digitalWrite(PIN_BUZZER, RELAY_OFF);
        buzzerOn = false;
        Serial.println("OK:BF");
        return;
    }
    if (line == "BB") {
        digitalWrite(PIN_BUZZER, RELAY_ON);
        beepEndTime = millis() + BEEP_DURATION;
        beepActive  = true;
        Serial.println("OK:BB");
        return;
    }

    // ── Flasor ───────────────────────────────────────────────────────────────
    if (line == "FLN") {
        flasherOn   = true;
        flashState  = false;
        lastFlashTime = millis();
        digitalWrite(PIN_FLASHER, RELAY_ON);  // hemen yak, ilk aralik gecince toggle
        Serial.println("OK:FLN");
        return;
    }
    if (line == "FLF") {
        flasherOn = false;
        digitalWrite(PIN_FLASHER, RELAY_OFF);
        Serial.println("OK:FLF");
        return;
    }

    // ── Stop lambasi ─────────────────────────────────────────────────────────
    if (line == "SLN") {
        digitalWrite(PIN_STOP_LIGHT, RELAY_ON);
        stopLightOn = true;
        Serial.println("OK:SLN");
        return;
    }
    if (line == "SLF") {
        digitalWrite(PIN_STOP_LIGHT, RELAY_OFF);
        stopLightOn = false;
        Serial.println("OK:SLF");
        return;
    }

    // ── LED ──────────────────────────────────────────────────────────────────
    if (line == "LN") {
        digitalWrite(PIN_LED, HIGH);   // MOSFET gate / aktif-HIGH surucu
        ledOn = true;
        Serial.println("OK:LN");
        return;
    }
    if (line == "LF") {
        digitalWrite(PIN_LED, LOW);
        ledOn = false;
        Serial.println("OK:LF");
        return;
    }

    // ── Bilinmeyen komut ─────────────────────────────────────────────────────
    Serial.print("ERR:"); Serial.println(line);
}

// ── Kurulum ───────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);

    int outputs[] = {PIN_MOTOR, PIN_RELAY_FRONT, PIN_RELAY_REAR,
                     PIN_BUZZER, PIN_FLASHER, PIN_STOP_LIGHT, PIN_LED};
    for (int i = 0; i < 7; i++) {
        pinMode(outputs[i], OUTPUT);
        digitalWrite(outputs[i], RELAY_OFF);
    }

    motorOn = false; brakeFront = false; brakeRear   = false;
    buzzerOn = false; flasherOn = false; stopLightOn = false;
    ledOn   = false;

    Serial.println("READY");
}

// ── Ana dongu (non-blocking) ──────────────────────────────────────────────────
void loop() {

    // Seri okuma — bloklama yok, her karakter gelince tamponla
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n') {
            inputBuffer.trim();
            if (inputBuffer.length() > 0) {
                handleCommand(inputBuffer);
                inputBuffer = "";
            }
        } else if (c != '\r') {
            inputBuffer += c;
        }
    }

    // Flasor toggle — 500ms'de bir durum degistir
    if (flasherOn) {
        unsigned long now = millis();
        if (now - lastFlashTime >= FLASH_INTERVAL) {
            lastFlashTime = now;
            flashState = !flashState;
            digitalWrite(PIN_FLASHER, flashState ? RELAY_ON : RELAY_OFF);
        }
    }

    // Kisa bip zamanlayici — sure dolunca buzzer'i kapat
    if (beepActive && millis() >= beepEndTime) {
        beepActive = false;
        // Surekli alarm aciksa tekrar devreye al, degilse kapat
        digitalWrite(PIN_BUZZER, buzzerOn ? RELAY_ON : RELAY_OFF);
    }
}
