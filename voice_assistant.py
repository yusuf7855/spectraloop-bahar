#!/usr/bin/env python3
"""
Spectraloop - Sesli Asistan (Araç Komut Modu)
----------------------------------------------
S = Push-to-talk  |  ESC = Çıkış

Sadece araç komutlarını (motor, fren, sensör, alarm, LED) anlar.
Sohbet, LLM veya bilgi tabanı yoktur.
"""
import subprocess
import queue
import threading

import numpy as np
import sounddevice as sd
from pynput import keyboard
from faster_whisper import WhisperModel

from hardware         import send_vehicle_command
from vehicle_commands import detect_vehicle_command

# ── Ayarlar ──────────────────────────────────────────────────────────────────
PTT_KEY       = "s"
SAMPLE_RATE   = 16000
WHISPER_MODEL = "small"
TTS_VOICE     = "Yelda"
TTS_RATE      = "190"

UNKNOWN_RESPONSE = "Sadece araç komutlarını anlıyorum. Motor, fren veya sensör komutu verebilirsiniz."

# ── TTS ──────────────────────────────────────────────────────────────────────
_tts_q    = queue.Queue()
_tts_proc = None
_tts_lock = threading.Lock()


def _tts_worker():
    global _tts_proc
    while True:
        text = _tts_q.get()
        if text is None:
            _tts_q.task_done()
            break
        with _tts_lock:
            _tts_proc = subprocess.Popen(
                ["say", "-v", TTS_VOICE, "-r", TTS_RATE, text]
            )
        _tts_proc.wait()
        _tts_q.task_done()


def speak(text: str):
    if not text:
        return
    print(f"Spectra: {text}")
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
        return

    audio = np.concatenate(chunks, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.3:
        print("[çok kısa, tekrar dene]")
        return

    print("...")
    segments, _ = whisper.transcribe(audio, language="tr", beam_size=1, vad_filter=True)
    text = " ".join(seg.text for seg in segments).strip()

    if not text:
        print("[anlaşılamadı]")
        return

    print(f"Sen: {text}")

    cmd = detect_vehicle_command(text)
    if cmd:
        result = send_vehicle_command(cmd)
        speak(result)
    else:
        speak(UNKNOWN_RESPONSE)


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
            print("\n[● Dinliyor...]")
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
    if key == keyboard.Key.esc:
        return False


# ── Başlatma ──────────────────────────────────────────────────────────────────
def main():
    global whisper

    print("Whisper yükleniyor...")
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    threading.Thread(target=_tts_worker, daemon=True).start()

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=audio_callback)
    stream.start()

    print(f"\nSpectra hazır.  [ S = konuş | ESC = çıkış ]\n")
    speak("Spectra hazır. Motor, fren veya sensör komutu verebilirsiniz.")

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

    stream.stop()


if __name__ == "__main__":
    main()
