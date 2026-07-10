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
import os

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard
from flask import Flask, render_template_string, send_from_directory
from flask_socketio import SocketIO

from vehicle_commands import detect_vehicle_command
from hardware import send_vehicle_command

# ── Ayarlar ───────────────────────────────────────────────────────────────────
PTT_KEY       = "s"
SAMPLE_RATE   = 16000
WHISPER_MODEL = "small"
PORT          = 5050

# Komut → video dosyası eşlemesi
# Sadece mevcut videolar burada — eşleşme yoksa idle'a dönülür
VIDEO_MAP = {
    "MOTOR_ON": "motor_on.mp4",
    "ALL":      "fren_yapiliyor.mp4",
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
        socketio.emit("state", {"state": "idle"})
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
        threading.Thread(target=send_vehicle_command, args=(cmd,), daemon=True).start()
        video = VIDEO_MAP.get(cmd)
        if video:
            print(f"[CMD] {cmd} → {video}")
            socketio.emit("play", {"video": video, "command": cmd})
        else:
            print(f"[CMD] {cmd} → video yok, idle'a dön")
            socketio.emit("state", {"state": "idle"})
    else:
        print("[CMD] Komut bulunamadı")
        socketio.emit("state", {"state": "idle"})


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
    body { background: #000; width: 100vw; height: 100vh; overflow: hidden; }

    #wrap { position: relative; width: 100%; height: 100%; }

    /* va: ALT KATMAN — duragan, her zaman çalışır */
    /* vb: ÜST KATMAN — giriş + komut videoları */
    .vp {
      position: absolute; inset: 0;
      width: 100%; height: 100%;
      object-fit: cover;
      opacity: 0;
      transition: opacity 0.35s ease;
    }
    #va { z-index: 1; }
    #vb { z-index: 2; }
    .vp.vis { opacity: 1; }

    #status {
      position: fixed; z-index: 10;
      bottom: 20px; left: 50%;
      transform: translateX(-50%);
      color: rgba(255,255,255,0.55);
      font-family: monospace; font-size: 13px;
      pointer-events: none;
    }
    #overlay {
      position: fixed; inset: 0; z-index: 99;
      background: rgba(0,0,0,0.85);
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
    }
    #overlay span {
      color: rgba(255,255,255,0.85);
      font-family: monospace; font-size: 20px; letter-spacing: 3px;
    }
  </style>
</head>
<body>
  <div id="overlay"><span>BAŞLATMAK İÇİN TIKLA</span></div>

  <div id="wrap">
    <video id="va" class="vp" playsinline loop muted></video>
    <video id="vb" class="vp" playsinline></video>
  </div>
  <div id="status"></div>

  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script>
    const overlay = document.getElementById('overlay');
    const status  = document.getElementById('status');
    const va = document.getElementById('va');   // duragan — hiç durmuyor
    const vb = document.getElementById('vb');   // giriş / komut

    const GIRIS = '/videos/giris.mp4';
    const IDLE  = '/videos/duragan.mp4';

    let phase = 'locked';

    // ── va: duragan her zaman arka planda hazır ──────────────────────────────
    va.src = IDLE;
    va.load();

    // ── Overlay tıkla → ses kilidi aç ───────────────────────────────────────
    overlay.addEventListener('click', () => {
      overlay.style.display = 'none';
      phase = 'intro';

      // Arka planda duragan başlat (sessize)
      va.play().catch(() => {});
      va.classList.add('vis');   // duragan görünür (giris üstüne çıkana kadar)

      // Giriş videosunu üstte sesli oynat
      vb.muted  = false;
      vb.volume = 1.0;
      vb.loop   = false;
      vb.src    = GIRIS;
      vb.load();

      vb.addEventListener('canplay', () => {
        vb.classList.add('vis');   // giris üste çıkar
      }, { once: true });

      vb.addEventListener('ended', () => {
        // Giriş bitti → vb solar, duragan (va) görünür kalır
        vb.classList.remove('vis');
        phase = 'idle';
        status.textContent = 'Hazır  [ S = konuş ]';
      }, { once: true });

      vb.play().catch(e => console.warn('giris:', e));
    });

    // ── SocketIO ─────────────────────────────────────────────────────────────
    const socket = io();

    socket.on('state', data => {
      if (phase === 'locked') return;
      if (data.state === 'listening') {
        phase = 'listening';
        status.textContent = '● Dinliyor...';
        // va (duragan) kesmeden çalmaya devam eder
      } else if (data.state === 'idle') {
        phase = 'idle';
        status.textContent = 'Hazır  [ S = konuş ]';
        // va zaten çalışıyor — hiçbir şey yapmaya gerek yok
      }
    });

    socket.on('play', data => {
      if (phase === 'locked') return;
      phase = 'playing';
      status.textContent = data.command || '';

      // Komut videosunu üstte sesli oynat; duragan (va) altta çalmaya devam eder
      vb.muted  = false;
      vb.volume = 1.0;
      vb.loop   = false;
      vb.src    = '/videos/' + data.video;
      vb.load();

      vb.addEventListener('canplay', () => {
        vb.classList.add('vis');
      }, { once: true });

      vb.addEventListener('ended', () => {
        vb.classList.remove('vis');
        phase = 'idle';
        status.textContent = 'Hazır  [ S = konuş ]';
      }, { once: true });

      vb.play().catch(e => console.warn('cmd:', e));
    });
  </script>
</body>
</html>"""


# ── Video dosyalarını sun ──────────────────────────────────────────────────────
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
