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
    "MOTOR_ON":   "motor_on.mp4",
    "MOTOR_OFF":  "motor_off.mp4",
    "ALL":        "fren_yapiliyor.mp4",
    "RELEASE":    "release.mp4",
    "FLASHER_ON":     "flasher_on.mp4",
    "FLASHER_OFF":    "flasher_off.mp4",
    "STOP_LIGHT_OFF": "stop_light_off.mp4",
    "STOP_LIGHT_ON":   "stop_light_on.mp4",
    "EMERGENCY_STOP":  "emergency_stop.mp4",
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


@socketio.on("button_cmd")
def on_button_cmd(data):
    cmd = data.get("command", "")
    if not cmd:
        return
    print(f"[BTN] {cmd}")
    threading.Thread(target=send_vehicle_command, args=(cmd,), daemon=True).start()
    video = VIDEO_MAP.get(cmd)
    if video:
        socketio.emit("play", {"video": video, "command": cmd})
    else:
        socketio.emit("state", {"state": "idle"})


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
    html, body { background: #000; width: 100vw; height: 100vh; overflow: hidden; }

    #player {
      position: absolute; inset: 0;
      width: 100%; height: 100%;
      object-fit: cover;
      background: #000;
    }

    /* ── Sol Sidebar ───────────────────────────────────────────────────── */
    #sidebar {
      position: fixed; left: 0; top: 0;
      width: 200px; height: 100%;
      z-index: 50;
      background: rgba(8, 4, 28, 0.82);
      border-right: 1px solid rgba(124, 58, 237, 0.35);
      backdrop-filter: blur(6px);
      overflow-y: auto;
      padding: 14px 10px 20px;
      display: flex; flex-direction: column; gap: 6px;
    }
    #sidebar::-webkit-scrollbar { width: 4px; }
    #sidebar::-webkit-scrollbar-track { background: transparent; }
    #sidebar::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.5); border-radius: 2px; }

    .sb-group-label {
      color: rgba(167,139,250,0.7);
      font-family: monospace; font-size: 10px; letter-spacing: 2px;
      text-transform: uppercase;
      margin: 10px 4px 4px;
    }
    .sb-group-label:first-child { margin-top: 2px; }

    .sb-btn {
      width: 100%;
      padding: 9px 12px;
      border: none; border-radius: 8px;
      cursor: pointer;
      font-family: monospace; font-size: 12px;
      color: #fff;
      text-align: left;
      background: linear-gradient(135deg, #3b2fa0 0%, #7c3aed 100%);
      box-shadow: 0 2px 8px rgba(124,58,237,0.25);
      transition: filter .15s, transform .1s;
      line-height: 1.3;
    }
    .sb-btn:hover  { filter: brightness(1.25); }
    .sb-btn:active { transform: scale(0.97); filter: brightness(0.9); }
    .sb-btn.danger {
      background: linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%);
      box-shadow: 0 2px 8px rgba(220,38,38,0.35);
    }
    .sb-btn.sensor {
      background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
      box-shadow: 0 2px 8px rgba(37,99,235,0.25);
    }
    .sb-btn.light {
      background: linear-gradient(135deg, #1a2744 0%, #4f46e5 100%);
      box-shadow: 0 2px 8px rgba(79,70,229,0.25);
    }

    /* ── Durum / overlay ───────────────────────────────────────────────── */
    #status {
      position: fixed; z-index: 60;
      bottom: 20px; left: 50%;
      transform: translateX(-50%);
      color: rgba(255,255,255,0.55);
      font-family: monospace; font-size: 13px;
      pointer-events: none;
    }
    #overlay {
      position: fixed; inset: 0; z-index: 99;
      background: rgba(0,0,0,0.88);
      display: flex; align-items: center; justify-content: center;
      cursor: pointer;
    }
    #overlay span {
      color: rgba(255,255,255,0.9);
      font-family: monospace; font-size: 22px; letter-spacing: 3px;
    }
  </style>
</head>
<body>
  <div id="overlay"><span>BAŞLATMAK İÇİN TIKLA</span></div>
  <video id="player" playsinline></video>

  <!-- ── Sol Sidebar ──────────────────────────────────────────────────── -->
  <div id="sidebar">

    <div class="sb-group-label">Motor</div>
    <button class="sb-btn" onclick="sendCmd('MOTOR_ON')">▶ Motoru Çalıştır</button>
    <button class="sb-btn" onclick="sendCmd('MOTOR_OFF')">■ Motoru Durdur</button>

    <div class="sb-group-label">Frenler</div>
    <button class="sb-btn" onclick="sendCmd('ALL')">Tüm Frenler Devreye</button>
    <button class="sb-btn" onclick="sendCmd('RELEASE')">Tüm Frenler Serbest</button>

    <div class="sb-group-label">Işık &amp; Ses</div>
    <button class="sb-btn light" onclick="sendCmd('FLASHER_ON')">Flaşör Aç</button>
    <button class="sb-btn light" onclick="sendCmd('FLASHER_OFF')">Flaşör Kapat</button>
    <button class="sb-btn light" onclick="sendCmd('STOP_LIGHT_ON')">Stop Lambası Aç</button>
    <button class="sb-btn light" onclick="sendCmd('STOP_LIGHT_OFF')">Stop Lambası Kapat</button>

    <div class="sb-group-label">Acil</div>
    <button class="sb-btn danger" onclick="sendCmd('EMERGENCY_STOP')">⚠ ACİL DURDURMA</button>

  </div>

  <div id="status"></div>

  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script>
    const overlay = document.getElementById('overlay');
    const status  = document.getElementById('status');
    const player  = document.getElementById('player');

    const GIRIS = '/videos/giris.mp4';
    const IDLE  = '/videos/duragan.mp4';

    let phase = 'locked';

    function goIdle() {
      phase = 'idle';
      player.loop   = true;
      player.muted  = true;
      player.volume = 1.0;
      player.src    = IDLE;
      player.load();
      player.play().catch(() => {});
      status.textContent = 'Hazır  [ S = konuş ]';
    }

    // ── Overlay tıkla → ses kilidi aç, giriş videosu ────────────────────────
    overlay.addEventListener('click', () => {
      overlay.style.display = 'none';
      phase = 'intro';

      const preload = document.createElement('video');
      preload.src = IDLE;
      preload.load();

      player.loop   = false;
      player.muted  = false;
      player.volume = 1.0;
      player.src    = GIRIS;
      player.load();
      player.play().catch(e => console.warn('giris:', e));

      player.addEventListener('ended', () => goIdle(), { once: true });
    });

    // ── Buton komutu gönder ──────────────────────────────────────────────────
    const socket = io();

    function sendCmd(cmd) {
      if (phase === 'locked') return;
      socket.emit('button_cmd', { command: cmd });
      status.textContent = cmd.replace(/_/g, ' ');
    }

    // ── SocketIO ─────────────────────────────────────────────────────────────
    socket.on('state', data => {
      if (phase === 'locked') return;
      if (data.state === 'listening') {
        phase = 'listening';
        status.textContent = '● Dinliyor...';
      } else if (data.state === 'idle') {
        if (phase !== 'idle') goIdle();
      }
    });

    socket.on('play', data => {
      if (phase === 'locked') return;
      phase = 'playing';
      status.textContent = data.command || '';

      player.loop   = false;
      player.muted  = false;
      player.volume = 1.0;
      player.src    = '/videos/' + data.video;
      player.load();
      player.play().catch(e => console.warn('cmd:', e));

      player.addEventListener('ended', () => goIdle(), { once: true });
    });

    // ── Güvenlik: duragan durursa her 2sn'de yeniden başlat ─────────────────
    setInterval(() => {
      if (phase === 'idle' && player.paused) {
        player.play().catch(() => {});
      }
    }, 2000);
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
