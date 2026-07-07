"""
Spectraloop - Beyin Katmani
----------------------------
Strateji:
  1. Kalıp tablosu (~90% konuşma) → anında, doğal Türkçe
  2. Ollama (kalan %10, özgün sorular) → İngilizce sistem promptu + direkt Türkçe çıktı
"""
import re
import json
import requests
from datetime import datetime
from typing import Optional
from chat_patterns import detect_pattern
from response_cleaner import clean as clean_response

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen2.5:3b"
MAX_HISTORY = 16

OLLAMA_OPTIONS = {
    "temperature":    0.60,
    "top_p":          0.88,
    "top_k":          35,
    "repeat_penalty": 1.18,
    "num_ctx":        2048,
    "num_predict":    150,
}

# İngilizce sistem promptu — model bu dilde talimatları daha iyi anlar
# Ama yanıtı Türkçe vermesini zorunlu kılıyoruz
SYSTEM_PROMPT = """You are Spectra, a voice assistant for the Spectraloop hyperloop racing team from Samsun University, competing in TEKNOFEST Turkey.

Respond ONLY in Turkish. Zero English words in your response.
Use formal "siz", NEVER informal "sen".
Max 2-3 short sentences. No bullet points, no markdown.
Be warm and natural like a close friend.
If you don't know something, admit it simply.

Vehicle control — use control_vehicle tool:
BRAKES: FRONT_ON, FRONT_OFF, REAR_ON, REAR_OFF, ALL, RELEASE
MOTOR: MOTOR_ON (start), MOTOR_OFF (stop), MOTOR_STATUS (query)
SENSORS: GET_TEMP (temperature), GET_VOLTAGE (battery), GET_ALL (full status)"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "control_vehicle",
            "description": "Controls the hyperloop vehicle: brakes, motor, and sensor queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": [
                            "FRONT_ON", "FRONT_OFF", "REAR_ON", "REAR_OFF", "ALL", "RELEASE",
                            "MOTOR_ON", "MOTOR_OFF", "MOTOR_STATUS",
                            "GET_TEMP", "GET_VOLTAGE", "GET_ALL",
                            "EMERGENCY_STOP",
                            "BUZZER_ON", "BUZZER_OFF", "BUZZER_BEEP",
                            "FLASHER_ON", "FLASHER_OFF",
                            "STOP_LIGHT_ON", "STOP_LIGHT_OFF",
                            "LED_ON", "LED_OFF"
                        ],
                        "description": "The vehicle command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

_SENT_ENDS = ('. ', '! ', '? ', '.\n', '!\n', '?\n', '... ', '…')


def _split_sentences(text: str):
    buf = text
    while buf:
        best_idx = len(buf)
        best_len = 1
        for delim in _SENT_ENDS:
            idx = buf.find(delim)
            if 0 < idx < best_idx:
                best_idx = idx
                best_len = len(delim)
        sentence = buf[:best_idx + 1].strip()
        buf = buf[best_idx + best_len:]
        if sentence:
            yield sentence
        if best_idx >= len(buf) + best_len - 1:
            if buf.strip():
                yield buf.strip()
            break


class Brain:
    def __init__(self, hardware_fn):
        self.history     = []
        self.hardware_fn = hardware_fn
        self.user_name: Optional[str] = None
        self.greeted     = False   # ilk selamı yaptık mı?

    # ── İsim çıkarma ─────────────────────────────────────────────────────────
    def _extract_name(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:benim\s+)?adım\s+(\w+)",
            r"ismim\s+(\w+)",
            r"bana\s+(\w+)\s+(?:de|diyebilirsin|çağır)",
            r"ben\s+(\w+)(?:\s+değilim)?[,.]?$",
        ]
        for p in patterns:
            m = re.search(p, text.lower())
            if m:
                name = m.group(1).capitalize()
                if len(name) > 1 and name.lower() not in (
                    "bir","bu","şu","ben","sen","de","da","ki","mi","mu","mü"
                ):
                    return name
        return None

    # ── Düşük seviye Ollama çağrısı ───────────────────────────────────────────
    def _ollama(self, messages: list, use_tools: bool = False) -> dict:
        payload = {
            "model":    MODEL,
            "messages": messages,
            "stream":   False,
            "options":  OLLAMA_OPTIONS,
        }
        if use_tools:
            payload["tools"] = TOOLS
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["message"]

    # ── Ana sohbet ────────────────────────────────────────────────────────────
    def chat_stream(self, user_input: str):
        """Generator — cümle cümle Türkçe yanıt yield eder."""

        # 1) İsim çıkar
        found = self._extract_name(user_input)
        if found:
            self.user_name = found

        # 2) İlk selamlama: isim bilinmiyorsa sor
        norm_in = user_input.lower().strip()
        is_greeting = any(w in norm_in for w in ["merhaba","selam","hey","günaydın","iyi akşam"])
        if is_greeting and not self.greeted and not self.user_name:
            self.greeted = True
            resp = "Merhaba! Ben Spectra, Spectraloop takımının sesli asistanıyım. Sizinle tanışmak güzel! İsminiz ne?"
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": resp})
            yield resp
            return

        # 3) İsim öğrendikten sonra özel karşılama
        if found and not self.greeted:
            self.greeted = True
            resp = f"Merhaba {found} Bey/Hanım! Sizinle tanışmak güzel. Size nasıl yardımcı olabilirim?"
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": resp})
            yield resp
            return
        if found:
            resp = f"Güzel, sizi tanıdım {found}! Bundan sonra isminizi bileceğim."
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": resp})
            yield resp
            return

        # 4) Bilinen kalıp mı?
        pattern_resp = detect_pattern(user_input)
        if pattern_resp:
            # %40 ihtimalle ismi başa ekle
            if self.user_name:
                import random
                if random.random() < 0.4:
                    first = pattern_resp[0].lower() + pattern_resp[1:]
                    pattern_resp = f"{self.user_name}, {first}"
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": pattern_resp})
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]
            yield pattern_resp
            return

        # 5) Ollama'ya gönder
        try:
            self.history.append({"role": "user", "content": user_input})
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]

            now = datetime.now().strftime("%d %B %Y, %H:%M")
            sys = SYSTEM_PROMPT
            if self.user_name:
                sys += f"\n\nUser's name: {self.user_name}. Use it naturally sometimes with formal 'siz' address."
            sys += f"\nTime: {now}"

            messages = [{"role": "system", "content": sys}] + self.history
            msg = self._ollama(messages, use_tools=True)

            # Tool çağrısı
            if msg.get("tool_calls"):
                self.history.append(msg)
                for call in msg["tool_calls"]:
                    if call["function"]["name"] == "control_vehicle":
                        cmd       = call["function"]["arguments"].get("command", "RELEASE")
                        hw_result = self.hardware_fn(cmd)
                        print(f"[Brain] control_vehicle({cmd}) → {hw_result}")
                        self.history.append({"role": "tool", "content": hw_result})
                msgs2   = [{"role": "system", "content": sys}] + self.history
                final   = self._ollama(msgs2, use_tools=False)
                content = final.get("content", "Tamam.")
                content = clean_response(content)
                self.history.append({"role": "assistant", "content": content})
                yield from _split_sentences(content)
                return

            content = msg.get("content", "")
            content = clean_response(content)
            self.history.append({"role": "assistant", "content": content})
            yield from _split_sentences(content)

        except requests.exceptions.ConnectionError:
            yield "Ollama'ya bağlanılamadı. Ollama çalışıyor mu?"
        except Exception as e:
            print(f"[Brain] Hata: {e}")
            yield "Bir hata oluştu, tekrar dener misin?"

    # ─────────────────────────────────────────────────────────────────────────
    def chat(self, user_input: str) -> str:
        return " ".join(self.chat_stream(user_input))

    def reset(self):
        self.history   = []
        self.user_name = None
        self.greeted   = False
        print("[Brain] Geçmiş sıfırlandı.")
