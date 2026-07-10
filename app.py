#!/usr/bin/env python3
"""
Spectraloop - Ana Uygulama
--------------------------
Flask + SocketIO sunucu + ses dinleyici tek süreçte çalışır.

Çalıştır:  python3 app.py
Arayüz:    http://localhost:5050  (tam ekran aç)
"""
import threading
import queue

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard
from flask import Flask, render_template_string
from flask_socketio import SocketIO

from vehicle_commands import detect_vehicle_command
from hardware import send_vehicle_command

# ── Ayarlar ───────────────────────────────────────────────────────────────────
PTT_KEY       = "s"
SAMPLE_RATE   = 16000
WHISPER_MODEL = "small"
PORT          = 5050

# Komut → video dosyası eşlemesi
VIDEO_MAP = {
    "MOTOR_ON":       "motor_on.mp4",
    "MOTOR_OFF":      "motor_off.mp4",
    "MOTOR_STATUS":   "motor_status.mp4",
    "FRONT_ON":       "front_on.mp4",
    "FRONT_OFF":      "front_off.mp4",
    "REAR_ON":        "rear_on.mp4",
    "REAR_OFF":       "rear_off.mp4",
    "ALL":            "all_brakes.mp4",
    "RELEASE":        "release.mp4",
    "EMERGENCY_STOP": "emergency.mp4",
    "GET_TEMP":       "sensor_temp.mp4",
    "GET_VOLTAGE":    "sensor_voltage.mp4",
    "GET_ALL":        "sensor_all.mp4",
    "LED_ON":         "led_on.mp4",
    "LED_OFF":        "led_off.mp4",
    "BUZZER_ON":      "buzzer_on.mp4",
    "BUZZER_OFF":     "buzzer_off.mp4",
    "BUZZER_BEEP":    "buzzer_beep.mp4",
    "FLASHER_ON":     "flasher_on.mp4",
    "FLASHER_OFF":    "flasher_off.mp4",
}

# ── Flask + SocketIO ───────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "spectraloop"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


@app.route("/")
def index():
    return render_template_string(HTML)


@socketio.on("connect")
def on_connect():
    print("[UI] Tarayıcı bağlandı.")


# ── Ses & Whisper ─────────────────────────────────────────────────────────────
audio_q   = queue.Queue()
recording = False
whisper   = None   # main()'de yüklenir


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
        print("[çok kısa]")
        socketio.emit("state", {"state": "idle"})
        return

    print("...")
    segments, _ = whisper.transcribe(audio, language="tr", beam_size=1, vad_filter=True)
    text = " ".join(seg.text for seg in segments).strip()

    if not text:
        print("[anlaşılamadı]")
        socketio.emit("state", {"state": "idle"})
        return

    print(f"Sen: {text}")
    cmd = detect_vehicle_command(text)

    if cmd:
        video = VIDEO_MAP.get(cmd, "unknown.mp4")
        print(f"[CMD] {cmd} → {video}")
        # Donanıma gönder (Pi)
        threading.Thread(target=send_vehicle_command, args=(cmd,), daemon=True).start()
        # UI'a video oynat
        socketio.emit("play", {"video": video, "command": cmd})
    else:
        print("[CMD] Komut bulunamadı")
        socketio.emit("play", {"video": "unknown.mp4", "command": None})


# ── Klavye (PTT) ──────────────────────────────────────────────────────────────
def on_press(key):
    global recording
    try:
        if key.char == PTT_KEY and not recording:
            recording = True
            while not audio_q.empty():
                audio_q.get()
            print("\n[● Dinliyor...]")
            socketio.emit("state", {"state": "listening"})
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


def keyboard_thread():
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


# ── HTML Arayüzü ──────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <title>Spectraloop</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #000;
      width: 100vw; height: 100vh;
      overflow: hidden;
      display: flex; align-items: center; justify-content: center;
    }
    #player {
      width: 100%; height: 100%;
      object-fit: cover;
    }
    #status {
      position: fixed;
      bottom: 24px; left: 50%;
      transform: translateX(-50%);
      color: rgba(255,255,255,0.6);
      font-family: monospace;
      font-size: 14px;
      pointer-events: none;
    }
    #ptt-hint {
      position: fixed;
      bottom: 48px; left: 50%;
      transform: translateX(-50%);
      color: rgba(255,255,255,0.3);
      font-family: monospace;
      font-size: 12px;
      pointer-events: none;
    }
  </style>
</head>
<body>
  <video id="player" autoplay loop muted playsinline>
    <source src="/videos/idle.mp4" type="video/mp4">
  </video>
  <div id="ptt-hint">[ S = konuş | ESC = çıkış ]</div>
  <div id="status">Hazır</div>

  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script>
    const player  = document.getElementById('player');
    const status  = document.getElementById('status');
    const IDLE    = '/videos/idle.mp4';
    const LISTEN  = '/videos/listening.mp4';
    let   isIdle  = true;

    function playVideo(src, loop) {
      player.loop = loop;
      player.muted = loop;   // idle/listening = muted; komut videoları sesli
      const source = player.querySelector('source');
      source.src = src;
      player.load();
      player.play().catch(e => console.warn('play:', e));
    }

    function goIdle() {
      isIdle = true;
      playVideo(IDLE, true);
    }

    // Video bitti → idle'a dön
    player.addEventListener('ended', () => {
      if (!isIdle) goIdle();
    });

    // SocketIO
    const socket = io();

    socket.on('state', data => {
      if (data.state === 'listening') {
        isIdle = false;
        playVideo(LISTEN, true);
        status.textContent = '● Dinliyor...';
      } else if (data.state === 'idle') {
        goIdle();
        status.textContent = 'Hazır';
      }
    });

    socket.on('play', data => {
      isIdle = false;
      const src = '/videos/' + data.video;
      playVideo(src, false);
      status.textContent = data.command || '?';
    });

    // Eksik video → idle'a dön
    player.addEventListener('error', () => {
      console.warn('Video yok:', player.querySelector('source').src);
      goIdle();
      status.textContent = 'Video bulunamadı';
    });
  </script>
</body>
</html>"""


# ── Video dosyalarını sun ──────────────────────────────────────────────────────
import os
from flask import send_from_directory

@app.route("/videos/<path:filename>")
def serve_video(filename):
    video_dir = os.path.join(os.path.dirname(__file__), "videos")
    return send_from_directory(video_dir, filename)


# ── Başlatma ──────────────────────────────────────────────────────────────────
def main():
    global whisper

    print("Whisper yükleniyor...")
    whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=audio_callback)
    stream.start()

    threading.Thread(target=keyboard_thread, daemon=True).start()

    print(f"\nSpectraloop hazır.")
    print(f"Arayüz: http://localhost:{PORT}")
    print(f"[ S = konuş | ESC = çıkış ]\n")

    socketio.run(app, host="0.0.0.0", port=PORT, use_reloader=False)


if __name__ == "__main__":
    main()
