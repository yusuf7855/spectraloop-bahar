#!/usr/bin/env python3
"""
Spectraloop - Web Arayüz Sunucusu (Gelişmiş)
----------------------------------------------
pip install flask flask-socketio
Çalıştır: python3 ui_server.py
Tarayıcı: http://localhost:5001
"""
import subprocess
import queue
import threading
import time
import socket as _sock

import numpy as np
import sounddevice as sd
from pynput import keyboard as kb_module
from faster_whisper import WhisperModel
from flask import Flask, send_from_directory
from flask_socketio import SocketIO

from brain            import Brain
from hardware         import send_vehicle_command, PI_HOST, PI_PORT
from vehicle_commands import detect_vehicle_command

# ── Flask + SocketIO ─────────────────────────────────────────────────────────
app      = Flask(__name__, static_folder=".", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading",
                    logger=False, engineio_logger=False)

# ── Ayarlar ───────────────────────────────────────────────────────────────────
PTT_KEY       = "s"
RESET_KEY     = "r"
SAMPLE_RATE   = 16000
WHISPER_MODEL = "small"
TTS_VOICE     = "Yelda"
TTS_RATE      = "190"
UI_PORT       = 5001

# ── Yardımcılar ───────────────────────────────────────────────────────────────
def _emit(event, data):
    """Thread-safe emit."""
    socketio.emit(event, data)

def _sys_log(text, type_="info"):
    _emit("sys_log", {"type": type_, "text": text})

# ── TTS ──────────────────────────────────────────────────────────────────────
_tts_q    = queue.Queue()
_tts_proc = None
_tts_lock = threading.Lock()

_PRONOUNCE = [
    ("Spectraloop", "Spektıraloop"),
    ("SPECTRALOOP", "Spektıraloop"),
    ("Spectra",     "Spektıra"),
    ("SPECTRA",     "Spektıra"),
    ("spectra",     "spektıra"),
]

def _pronounce(text: str) -> str:
    for src, dst in _PRONOUNCE:
        text = text.replace(src, dst)
    return text


def _tts_worker():
    global _tts_proc
    while True:
        text = _tts_q.get()
        if text is None:
            _tts_q.task_done()
            break
        with _tts_lock:
            _tts_proc = subprocess.Popen(
                ["say", "-v", TTS_VOICE, "-r", TTS_RATE, _pronounce(text)]
            )
        _tts_proc.wait()
        _tts_q.task_done()
        if _tts_q.empty():
            _emit("state", {"mode": "idle"})


def speak(text: str):
    if not text:
        return
    print(f"Spectra: {text}")
    _emit("state", {"mode": "speaking", "text": text})
    _tts_q.put(text)


def stop_speaking():
    while not _tts_q.empty():
        try:
            _tts_q.get_nowait()
            _tts_q.task_done()
        except queue.Empty:
            break
    with _tts_lock:
        if _tts_proc and _tts_proc.poll() is None:
            _tts_proc.terminate()

# ── Araç komut gönderici (log ile) ───────────────────────────────────────────
def vehicle_cmd_send(cmd: str) -> str:
    result = send_vehicle_command(cmd)
    _emit("cmd_log", {"cmd": cmd, "result": result})
    return result

# ── Ses kaydı ─────────────────────────────────────────────────────────────────
audio_q   = queue.Queue()
recording = False


def audio_callback(indata, frames, time_info, status):
    if recording:
        audio_q.put(indata.copy())


def process_audio():
    chunks = []
    while not audio_q.empty():
        chunks.append(audio_q.get())

    if not chunks:
        _emit("state", {"mode": "idle"})
        return

    audio = np.concatenate(chunks, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.3:
        print("[çok kısa]")
        _sys_log("Çok kısa ses, tekrar dene")
        _emit("state", {"mode": "idle"})
        return

    _emit("state", {"mode": "thinking"})
    print("...")

    segments, _ = whisper.transcribe(
        audio, language="tr", beam_size=1, vad_filter=True
    )
    text = " ".join(seg.text for seg in segments).strip()

    if not text:
        print("[anlaşılamadı]")
        _sys_log("Ses anlaşılamadı", "err")
        _emit("state", {"mode": "idle"})
        return

    print(f"Sen: {text}")
    _emit("heard", {"text": text})

    vehicle_cmd = detect_vehicle_command(text)
    if vehicle_cmd:
        result = vehicle_cmd_send(vehicle_cmd)
        speak(result)
        return

    for sentence in brain.chat_stream(text):
        speak(sentence)

# ── Klavye ───────────────────────────────────────────────────────────────────
def on_press(key):
    global recording
    try:
        ch = key.char
        if ch == PTT_KEY and not recording:
            stop_speaking()
            recording = True
            while not audio_q.empty():
                audio_q.get()
            _emit("state", {"mode": "listening"})
            _emit("clear", {})
            print("\n[● Dinliyor...]")

        elif ch == RESET_KEY:
            brain.reset()
            speak("Tamam, konuşmayı sıfırladım.")
            _sys_log("Geçmiş sıfırlandı")

    except AttributeError:
        pass


def on_release(key):
    global recording
    try:
        if key.char == PTT_KEY and recording:
            recording = False
            threading.Thread(target=process_audio, daemon=True).start()
    except AttributeError:
        pass
    if key == kb_module.Key.esc:
        return False

# ── Pi bağlantı + ping monitörü ──────────────────────────────────────────────
_pi_connected = False
_pi_ping_ms   = -1


def _pi_monitor():
    global _pi_connected, _pi_ping_ms
    while True:
        t0 = time.time()
        try:
            with _sock.create_connection((PI_HOST, PI_PORT), timeout=2):
                ping_ms = int((time.time() - t0) * 1000)
                connected = True
        except Exception:
            ping_ms   = -1
            connected = False

        changed = (connected != _pi_connected) or (ping_ms != _pi_ping_ms)
        _pi_connected = connected
        _pi_ping_ms   = ping_ms

        if changed:
            _emit("state", {
                "pi_connected": connected,
                "pi_ip":        PI_HOST,
                "pi_ping":      ping_ms,
            })
            if not connected:
                _sys_log(f"Pi bağlantısı kesildi ({PI_HOST})", "err")
            else:
                _sys_log(f"Pi bağlı — {ping_ms}ms ({PI_HOST})")
        time.sleep(10)

# ── Flask rotaları ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(".", "ui.html")


@socketio.on("connect")
def on_ws_connect():
    _emit("state", {
        "mode":         "idle",
        "pi_connected": _pi_connected,
        "pi_ip":        PI_HOST,
        "pi_ping":      _pi_ping_ms,
    })
    _sys_log("Arayüz bağlandı")

# ── Başlatma ─────────────────────────────────────────────────────────────────
def main():
    global whisper, brain

    print("Whisper yükleniyor...")
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    brain   = Brain(hardware_fn=send_vehicle_command)

    threading.Thread(target=_tts_worker,  daemon=True).start()
    threading.Thread(target=_pi_monitor,  daemon=True).start()

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=audio_callback)
    stream.start()

    print(f"\nSpectra hazır.  [ S = konuş | R = sıfırla | ESC = çıkış ]")
    print(f"Tarayıcı: http://localhost:{UI_PORT}\n")

    speak(
        "Merhaba! Ben Spectra, Samsun Üniversitesi Spectraloop takımının "
        "sesli asistanıyım. Motor, fren, sensör kontrolü ve daha fazlası "
        "için buradayım. Nasıl yardımcı olabilirim?"
    )

    def _keyboard():
        with kb_module.Listener(on_press=on_press, on_release=on_release) as l:
            l.join()
        stream.stop()

    threading.Thread(target=_keyboard, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=UI_PORT, use_reloader=False)


if __name__ == "__main__":
    main()
