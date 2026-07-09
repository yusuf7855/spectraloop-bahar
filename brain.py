"""
Spectraloop - Beyin Katmanı
----------------------------
Strateji:
  1. Kalıp tablosu (~90% konuşma) → anında, doğal Türkçe
  2. Ollama (kalan %10) → İngilizce sistem promptu + direkt Türkçe çıktı
  3. VIP sistemi → TÜBİTAK/Bakanlık/TEKNOFEST ziyaretçilerini tanır,
     "Sayın [Unvan]" hitabıyla karşılar, konuşmaya uygun sorular sorar.
"""
import re
import random
import requests
from datetime import datetime
from typing import Optional

from chat_patterns import detect_pattern
from response_cleaner import clean as clean_response
from vip_registry import lookup_vip, get_vip_greeting, get_vip_question, get_system_addendum
from qa_router import get_router

# Modül singleton — brain ve ui_server aynı örneği paylaşır.
_qa_router = get_router()

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

SYSTEM_PROMPT = """You are Spectra, a voice assistant for the Spectraloop hyperloop racing team \
from Samsun University, competing in TEKNOFEST Turkey.

Respond ONLY in Turkish. Zero English words in your response.
Use formal "siz", NEVER informal "sen".
Max 2-3 short sentences. No bullet points, no markdown. No emojis.
Stay on topic: if asked something unrelated to the team, vehicle or hyperloop,
politely redirect to the project ("Bu konuda yardımcı olamam, ancak aracımız hakkında \
sorularınızı yanıtlamaktan memnuniyet duyarım.").
If you genuinely don't know something, say "Bu konuda net bir bilgim yok" — never fabricate.

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

# İsim tespitinde atlanacak kelimeler
_NAME_STOPWORDS = {
    "bir","bu","şu","ben","sen","biz","siz","de","da","ki","mi","mu","mü",
    "ve","ile","için","ama","ya","veya","benim","ismim","adım","adim",
    "tamam","evet","hayır","hayir","selam","merhaba","hey","günaydın",
    "nasil","nasilsiniz","nasilsin","tesekkur","tabii","anladim","anliyorum",
    "iyi","peki","olur","oldu","tabi","tabiki","elbette","efendim",
}

# Araç/teknik komut içeren kelimelerin olduğu girişleri isim olarak işleme
_COMMAND_WORDS = {
    "fren","motor","sensor","sicaklik","voltaj","durumu","calistir","durdur",
    "baslat","kapat","ac","nedir","nasil","neden","ne","kim","hangisi",
    "soyle","anlat","yardim","kontrol","test","sistem","rapor","oku"
}

# ── Anlamadım Yanıtları (3 kademeli tırmanma) ────────────────────────────────
_NO_UNDERSTANDING = [
    "Özür dilerim, tam anlayamadım. Tekrar söyler misiniz?",
    "Sesınizi yeterince duyamıyorum. Biraz daha yakın ya da yüksek sesle söyler misiniz?",
    "Hâlâ anlayamıyorum. Bir takım üyemizi yardıma çağırmamı ister misiniz?",
]

# CONFIRM_MODE onay sözcükleri
_YES_WORDS: frozenset = frozenset({
    "evet", "yes", "dogru", "doğru", "aynen", "kesinlikle",
    "tamam", "tabi", "tabii", "elbette", "harika", "olur",
})


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


def _normalize_tr(s: str) -> str:
    s = s.lower().strip()
    for tr, en in [
        ('ı','i'),('İ','i'),('ğ','g'),('Ğ','g'),('ş','s'),('Ş','s'),
        ('ç','c'),('Ç','c'),('ö','o'),('Ö','o'),('ü','u'),('Ü','u'),
    ]:
        s = s.replace(tr, en)
    return re.sub(r'[^\w\s]', '', s)


class Brain:
    def __init__(self, hardware_fn):
        self.history      = []
        self.hardware_fn  = hardware_fn
        self.user_name: Optional[str]  = None
        self.vip_info:  Optional[dict] = None
        self.greeted          = False
        self.waiting_for_name = True   # İlk girişi isim olarak işle
        self.consecutive_no_understanding: int  = 0   # ardışık anlayamadım sayacı
        self._pending_confirm: Optional[tuple]  = None  # (answer, entry_id)

    # ── İsim çıkarma (cümlede gömülü isim) ──────────────────────────────────
    def _extract_embedded_name(self, text: str) -> Optional[str]:
        """'Adım Yusuf', 'ismim Kacır' gibi kalıplardan isim çıkarır."""
        patterns = [
            r"(?:benim\s+)?adım\s+([\w]+(?:\s+[\w]+){0,2})",
            r"ismim\s+([\w]+(?:\s+[\w]+){0,2})",
            r"bana\s+([\w]+(?:\s+[\w]+){0,1})\s+(?:de|diyebilirsin|çağır)",
            r"ben\s+([\w]+(?:\s+[\w]+){0,2})[,.]?\s*$",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                first = candidate.split()[0].lower()
                if len(first) > 1 and _normalize_tr(first) not in _NAME_STOPWORDS:
                    return candidate.title()
        return None

    # ── İsim girişini işle (waiting_for_name modunda) ───────────────────────
    def _process_name_input(self, text: str):
        """
        Kullanıcının isim girişini işler.
        Döndürür: (isim_str veya None, vip_dict veya None)
        """
        stripped = text.strip()
        words    = stripped.split()
        norm     = _normalize_tr(stripped)
        norm_set = set(norm.split())

        # Araç/teknik komut mu? → isim değil
        if norm_set & _COMMAND_WORDS:
            return None, None

        # Uzun cümle mi? → isim değil
        if len(words) > 5:
            return None, None

        # VIP kontrolü (önce tam metin, sonra parçalı)
        vip = lookup_vip(stripped)
        if vip:
            return vip["ad_soyad"], vip

        # Gömülü isim kalıbı ("adım X")
        embedded = self._extract_embedded_name(stripped)
        if embedded:
            return embedded, lookup_vip(embedded)

        # Kısa cevap: anlamlı kelimeleri filtrele, birincisini isim say
        meaningful = [
            w for w in words
            if _normalize_tr(w) not in _NAME_STOPWORDS and len(w) > 1
        ]
        if meaningful:
            name = meaningful[0].capitalize()
            vip  = lookup_vip(" ".join(meaningful))
            return name, vip

        return None, None

    # ── STT Kapısı Başarısızlık İşleyici ─────────────────────────────────────
    def stt_gate_failed(self, stt_meta: Optional[dict] = None) -> str:
        """
        STT güven kapısı sesi reddetti.
        Konuşma geçmişine yazılmaz; yalnızca sesli geri bildirim döndürür.
        """
        return self._no_understanding_response()

    def _no_understanding_response(self) -> str:
        """Kademeli tırmanma: ilk 3 ardışık başarısızlıkta farklı yanıt."""
        idx = min(self.consecutive_no_understanding, len(_NO_UNDERSTANDING) - 1)
        self.consecutive_no_understanding += 1
        return _NO_UNDERSTANDING[idx]

    def _handle_confirm_response(self, user_input: str):
        """
        Generator — CONFIRM_MODE doğrulama yanıtını işler.
        Evet → bekleyen cevabı seslendir.
        Hayır → nötr yönlendirme.
        """
        norm_words = set(_normalize_tr(user_input).split())
        if norm_words & _YES_WORDS:
            answer, _entry_id = self._pending_confirm
            self._pending_confirm = None
            self.consecutive_no_understanding = 0
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": answer})
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]
            yield answer
        else:
            self._pending_confirm = None
            resp = "Anladım. Başka bir konuda yardımcı olabilir miyim?"
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": resp})
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]
            yield resp

    # ── Düşük seviye Ollama çağrısı ──────────────────────────────────────────
    def _ollama(self, messages: list, use_tools: bool = False,
                options: Optional[dict] = None) -> dict:
        payload = {
            "model":    MODEL,
            "messages": messages,
            "stream":   False,
            "options":  options if options is not None else OLLAMA_OPTIONS,
        }
        if use_tools:
            payload["tools"] = TOOLS
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["message"]

    # ── Sistem promptu oluştur ───────────────────────────────────────────────
    def _build_system(self, grounding: str = "") -> str:
        now = datetime.now().strftime("%d %B %Y, %H:%M")
        sys = SYSTEM_PROMPT
        if self.vip_info:
            sys += get_system_addendum(self.vip_info)
        elif self.user_name:
            sys += (
                f"\n\nUser's first name: {self.user_name}. "
                f"Use it naturally occasionally with formal 'siz'."
            )
        if grounding:
            sys += f"\n\n{grounding}"
        sys += f"\nTime: {now}"
        return sys

    # ── Ana sohbet ───────────────────────────────────────────────────────────
    def chat_stream(self, user_input: str, stt_meta: Optional[dict] = None):
        """Generator — cümle cümle Türkçe yanıt yield eder."""

        def _push(text: str):
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": text})
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]

        # ── 0. Doğrulama modu (CONFIRM_MODE) ─────────────────────────────────
        if self._pending_confirm is not None:
            yield from self._handle_confirm_response(user_input)
            return

        norm_in = _normalize_tr(user_input)
        is_greeting = any(
            w in norm_in
            for w in ["merhaba","selam","hey","gunaydin","iyi aksam","iyi gunler"]
        )

        # ── 1. İlk giriş → isim bekleme modu ─────────────────────────────────
        if self.waiting_for_name:

            if is_greeting:
                # Selamı karşıla, tekrar sor
                resp = (
                    "Merhaba! Ben Spectra, Samsun Üniversitesi Spectraloop takımının "
                    "sesli asistanıyım. Sizi tanımak isterim — "
                    "adınızı öğrenebilir miyim?"
                )
                _push(resp)
                yield resp
                return

            name, vip = self._process_name_input(user_input)

            if vip:
                # VIP tespit edildi
                self.vip_info    = vip
                self.user_name   = vip["ad_soyad"]
                self.waiting_for_name = False
                self.greeted     = True
                greeting  = get_vip_greeting(vip)
                question  = get_vip_question(vip)
                resp = f"{greeting} {question}"
                _push(resp)
                yield resp
                return

            if name:
                # Normal ziyaretçi
                self.user_name        = name
                self.waiting_for_name = False
                self.greeted          = True
                questions = [
                    f"Merhaba {name}! Tanıştığımıza çok memnun oldum. "
                    f"Hyperloop sistemimiz veya takımımız hakkında merak ettiğiniz bir şey var mı?",
                    f"Hoş geldiniz {name}! Ben Spectra. "
                    f"Spectraloop'un sesli asistanıyım. Size nasıl yardımcı olabilirim?",
                    f"Merhaba {name}! Sizi aramıza hoş geldiniz. "
                    f"Araç kontrol sistemi, hyperloop teknolojisi veya başka bir konuda "
                    f"yardımcı olmaktan memnuniyet duyarım.",
                ]
                resp = random.choice(questions)
                _push(resp)
                yield resp
                return

            # İsim anlaşılamadı ama teknik soru gibi görünüyor — normal akışa geç
            if norm_in.strip():
                self.waiting_for_name = False
                # Aşağıya düş (normal sohbet)
            else:
                resp = "Affedersiniz, adınızı tam anlayamadım. Tekrar söyler misiniz?"
                _push(resp)
                yield resp
                return

        # ── 2. Gömülü isim öğrenme (sohbet ortasında) ───────────────────────
        if not self.vip_info:
            embedded = self._extract_embedded_name(user_input)
            if embedded:
                vip = lookup_vip(embedded)
                if vip and not self.vip_info:
                    self.vip_info  = vip
                    self.user_name = vip["ad_soyad"]
                elif not self.user_name:
                    self.user_name = embedded.split()[0].capitalize()

        # ── 3. Bilinen kalıp? ────────────────────────────────────────────────
        pattern_resp = detect_pattern(user_input)
        if pattern_resp:
            if self.vip_info:
                # VIP ise hitap ekle (bazen)
                if random.random() < 0.35:
                    pattern_resp = (
                        f"{self.vip_info['hitap']}, {pattern_resp[0].lower()}{pattern_resp[1:]}"
                    )
            elif self.user_name and random.random() < 0.35:
                pattern_resp = f"{self.user_name}, {pattern_resp[0].lower()}{pattern_resp[1:]}"
            _push(pattern_resp)
            yield pattern_resp
            return

        # ── 3.5 QA Bilgi Tabanı ──────────────────────────────────────────────
        qa_answer, qa_decision, qa_score, top1_id, top2_id = \
            _qa_router.route_v2(user_input, stt_meta=stt_meta)

        if qa_decision == "answer" and qa_answer:
            self.consecutive_no_understanding = 0
            _push(qa_answer)
            yield qa_answer
            return

        elif qa_decision == "confirm":
            # CONFIRM_MODE=True — doğrulama sorusu sor; cevabı sakla
            pending_answer = _qa_router.get_by_id(top1_id)
            self._pending_confirm = (pending_answer, top1_id)
            display = _qa_router.get_display_name(top1_id)
            confirm_q = f"{display} hakkında mı soruyorsunuz?"
            _push(confirm_q)
            yield confirm_q
            return

        elif qa_decision == "repeat":
            # Belirsiz eşleşme ve CONFIRM_MODE=False — anlamadım yoluna git
            resp = self._no_understanding_response()
            _push(resp)
            yield resp
            return

        # qa_decision == "llm" → Ollama'ya geç (aşağıya düş)

        # ── 4. Ollama (grounding ile) ─────────────────────────────────────────
        # QA router eşleşmedi: bilgi tabanını grounding olarak system prompt'a enjekte et
        grounding = _qa_router.grounding_text(query=user_input)
        try:
            self.history.append({"role": "user", "content": user_input})
            if len(self.history) > MAX_HISTORY:
                self.history = self.history[-MAX_HISTORY:]

            messages = [{"role": "system", "content": self._build_system(grounding)}] + self.history
            # Grounding context daha fazla token gerektiriyor; num_ctx'i artır
            grounded_options = {**OLLAMA_OPTIONS, "num_ctx": 4096}
            msg = self._ollama(messages, use_tools=True, options=grounded_options)

            # Tool çağrısı
            if msg.get("tool_calls"):
                self.history.append(msg)
                for call in msg["tool_calls"]:
                    if call["function"]["name"] == "control_vehicle":
                        cmd       = call["function"]["arguments"].get("command", "RELEASE")
                        hw_result = self.hardware_fn(cmd)
                        print(f"[Brain] control_vehicle({cmd}) → {hw_result}")
                        self.history.append({"role": "tool", "content": hw_result})
                msgs2   = [{"role": "system", "content": self._build_system()}] + self.history
                final   = self._ollama(msgs2, use_tools=False)
                content = clean_response(final.get("content", "Tamam."))
                self.history.append({"role": "assistant", "content": content})
                yield from _split_sentences(content)
                return

            content = clean_response(msg.get("content", ""))
            self.history.append({"role": "assistant", "content": content})
            self.consecutive_no_understanding = 0
            yield from _split_sentences(content)

        except requests.exceptions.ConnectionError:
            yield "Ollama'ya bağlanılamadı. Ollama çalışıyor mu?"
        except Exception as e:
            print(f"[Brain] Hata: {e}")
            yield "Bir hata oluştu, tekrar dener misiniz?"

    # ─────────────────────────────────────────────────────────────────────────
    def chat(self, user_input: str) -> str:
        return " ".join(self.chat_stream(user_input))

    def reset(self):
        self.history          = []
        self.user_name        = None
        self.vip_info         = None
        self.greeted          = False
        self.waiting_for_name = True
        self.consecutive_no_understanding = 0
        self._pending_confirm = None
        print("[Brain] Geçmiş sıfırlandı.")
