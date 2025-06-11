# app.py
import os
import time
import shutil
import subprocess
import signal
import sys
import threading
import glob
from flask import Flask, send_from_directory, render_template_string, jsonify, request

import logging

class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())


download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
extensions = ('.jpg', '.jpeg', '.png')

app = Flask(__name__)
processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

def open_chrome():
    os.system("am start -n com.android.chrome/com.google.android.apps.chrome.Main -a android.intent.action.VIEW -d http://127.0.0.1:5000")

def move_and_process(file_path):
    global processing, current_filename, latest_output_filename, error_occurred
    processing = True
    error_occurred = False
    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)
    shutil.rmtree(input_folder)
    shutil.rmtree(output_folder)
    os.makedirs(input_folder)
    os.makedirs(output_folder)
    shutil.move(file_path, os.path.join(input_folder, os.path.basename(file_path)))

    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stdout:
        print(stdout.decode())
    if stderr:
        print(stderr.decode(), file=sys.stderr)
        error_occurred = True

    files = [f for f in os.listdir(output_folder) if f.endswith(extensions)]
    if files:
        latest_output_filename = files[-1]
        shutil.copy(os.path.join(output_folder, latest_output_filename),
                    os.path.join("output", latest_output_filename))
    else:
        latest_output_filename = ""

    processing = False

def watch_folder():
    seen = set()
    while True:
        files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.endswith(extensions)]
        for f in files:
            path = os.path.join(download_folder, f)
            if path not in seen:
                move_and_process(path)
                seen.add(path)
        time.sleep(1)

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OMR Sheet Evaluator</title>
  <style>
    body, html {
      margin: 0; padding: 0;
      background-color: black; color: white;
      font-family: sans-serif;
      height: 100%;
      overflow: hidden;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
    }
    #wrap {
      position: relative; width: 180px; height: 480px;
      border: 4px solid white; box-sizing: content-box;
    }
    video, canvas, #resultImg {
      width: 180px; height: 480px;
      object-fit: cover; display: block;
    }
    .overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; pointer-events: none; }
    .qr-box {
      border: 2px solid lime; width: 30px; height: 30px; position: absolute;
    }
    .qr-tl { top: 10px; left: 10px; }
    .qr-tr { top: 10px; right: 10px; }
    .qr-bl { bottom: 10px; left: 10px; }
    .qr-br { bottom: 10px; right: 10px; }
    .controls {
      margin-top: 10px;
      display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;
    }
    button {
      font-size: 16px; padding: 10px 15px;
      border: none; border-radius: 5px;
      background: white; color: black; cursor: pointer;
    }
    #canvas, #resultImg { display: none; position: absolute; top: 0; left: 0; }
    .toast {
      position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
      background: #333; color: white; padding: 10px 20px;
      border-radius: 5px; font-size: 16px;
      z-index: 9999; opacity: 0.9;
    }
  </style>
</head>
<body>

<div id="wrap">
  <video id="video" autoplay playsinline muted></video>
  <canvas id="canvas"></canvas>
  <div class="overlay" id="overlay">
    <div class="qr-box qr-tl"></div>
    <div class="qr-box qr-tr"></div>
    <div class="qr-box qr-bl"></div>
    <div class="qr-box qr-br"></div>
  </div>
</div>

<div class="controls">
  <button id="flashBtn">🔦 Flash</button>
  <button id="captureBtn">📸 Capture</button>
  <button id="refreshBtn">🔄 Refresh</button>
  <label>
    <input type="checkbox" id="instantToggle" checked>
    Instant Result
  </label>
</div>

<script>
let stream = null;
let torchOn = false;
let lastResetTime = Date.now();

const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const flashBtn = document.getElementById("flashBtn");
const captureBtn = document.getElementById("captureBtn");
const refreshBtn = document.getElementById("refreshBtn");
const toggle = document.getElementById("instantToggle");

function showToast(msg) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerText = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } });
    video.srcObject = stream;
    video.play();
  } catch (e) {
    alert("Camera access denied.");
  }
}

function toggleFlash() {
  if (!stream) return;
  const track = stream.getVideoTracks()[0];
  track.applyConstraints({ advanced: [{ torch: !torchOn }] })
    .then(() => {
      torchOn = !torchOn;
      flashBtn.textContent = torchOn ? "Flash Off" : "🔦 Flash";
    })
    .catch(() => alert("Flash not supported."));
}

function autoResetCamera() {
  setInterval(() => {
    const now = Date.now();
    if (now - lastResetTime > 120000) {
      showToast("⚠️ Resetting camera and flash for safety...");
      stopStream();
      setTimeout(() => {
        startCamera();
        if (torchOn) toggleFlash(); // restore if flash was on
      }, 5000);
      lastResetTime = now;
    }
  }, 5000);
}

function stopStream() {
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
    stream = null;
  }
}

function sendForProcessing(blob) {
  const formData = new FormData();
  formData.append("image", blob, "capture.jpg");
  showToast("Processing...");
  fetch("/upload", { method: "POST", body: formData })
    .then(() => {
      setTimeout(() => {
        fetch("/status")
          .then(res => res.json())
          .then(data => {
            if (data.filename) {
              const correct = data.filename.split("_")[1]?.split(".")[0] || "N/A";
              showToast(`✅ Processed | Correct: ${correct}`);
            } else {
              showToast("❌ Processing failed");
            }
          });
      }, 1000);
    })
    .catch(() => showToast("❌ Upload error"));
}

captureBtn.onclick = () => {
  const tempCanvas = document.createElement("canvas");
  tempCanvas.width = video.videoWidth;
  tempCanvas.height = video.videoHeight;
  const ctx = tempCanvas.getContext("2d");
  ctx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);

  tempCanvas.toBlob(blob => {
    const downloadLink = document.createElement("a");
    downloadLink.href = URL.createObjectURL(blob);
    downloadLink.download = "OMR_" + Date.now() + ".jpg";
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);

    if (toggle.checked) {
      // Instant mode
      const formData = new FormData();
      formData.append("image", blob, "capture.jpg");
      showToast("Processing...");
      fetch("/upload", { method: "POST", body: formData })
        .then(() => {
          setTimeout(() => {
            fetch("/status")
              .then(res => res.json())
              .then(data => {
                if (data.filename) {
                  const correct = data.filename.split("_")[1]?.split(".")[0] || "N/A";
                  showToast(`✅ Processed | Correct: ${correct}`);
                } else {
                  showToast("❌ Processing failed");
                }
              });
        }, 1000);
      });
    } else {
      sendForProcessing(blob);
    }
  }, "image/jpeg");
};

flashBtn.onclick = toggleFlash;
refreshBtn.onclick = () => location.reload();

startCamera();
autoResetCamera();
</script>
</body>
</html>


''')


@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['image']
    filename = f"OMR_{int(time.time())}.jpg"
    path = os.path.join(download_folder, filename)
    file.save(path)
    return jsonify({"message": "OK"})

@app.route('/status')
def status():
    return jsonify({
        "processing": processing,
        "filename": latest_output_filename
    })

@app.route('/temp_output/<path:filename>')
def get_output(filename):
    return send_from_directory(output_folder, filename)

if __name__ == '__main__':
    threading.Thread(target=watch_folder, daemon=True).start()
    threading.Timer(0.5, open_chrome).start()
    app.run(host='0.0.0.0', port=5000)
