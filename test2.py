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
      margin: 0;
      padding: 0;
      background-color: black;
      color: white;
      font-family: sans-serif;
      height: 100%;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }
    #wrap {
      position: relative;
      width: 180px;
      height: 480px;
      border: 4px solid white;
      box-sizing: content-box;
    }
    video, canvas, #resultImg {
      width: 180px;
      height: 480px;
      object-fit: cover;
      display: block;
    }
    .overlay {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      pointer-events: none;
    }
    .qr-box {
      border: 2px solid lime;
      width: 30px;
      height: 30px;
      position: absolute;
    }
    .qr-tl { top: 10px; left: 10px; }
    .qr-tr { top: 10px; right: 10px; }
    .qr-bl { bottom: 10px; left: 10px; }
    .qr-br { bottom: 10px; right: 10px; }

    .controls {
      margin-top: 10px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: center;
    }
    button {
      font-size: 16px;
      padding: 10px 15px;
      border: none;
      border-radius: 5px;
      background: white;
      color: black;
      cursor: pointer;
    }
    #canvas, #resultImg {
      display: none;
      position: absolute;
      top: 0;
      left: 0;
    }

    #processingImage {
      max-height: 70vh;
      width: auto;
      object-fit: contain;
      margin-bottom: 10px;
      margin-top: -10px;
    }

    .toast {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(0, 0, 0, 0.8);
      color: white;
      padding: 12px 20px;
      border-radius: 5px;
      font-size: 16px;
      z-index: 9999;
      animation: fadein 0.3s, fadeout 0.3s 2.5s;
    }
    @keyframes fadein { from { opacity: 0; } to { opacity: 1; } }
    @keyframes fadeout { from { opacity: 1; } to { opacity: 0; } }
  </style>
</head>
<body>

  <div id="wrap">
    <video id="video" autoplay playsinline muted></video>
    <canvas id="canvas"></canvas>
    <img id="resultImg" />
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
    <button id="bgProcessBtn">📥 Download + Process</button>
    <button id="nextBtn" style="display:none;">🔁 Next</button>
    <button id="refreshBtn" style="display:none;">🔄 Refresh</button>
  </div>

  <script>
    let stream = null;
    let torchOn = false;

    const video = document.getElementById("video");
    const canvas = document.getElementById("canvas");
    const resultImg = document.getElementById("resultImg");
    const flashBtn = document.getElementById("flashBtn");
    const captureBtn = document.getElementById("captureBtn");
    const bgProcessBtn = document.getElementById("bgProcessBtn");
    const nextBtn = document.getElementById("nextBtn");
    const refreshBtn = document.getElementById("refreshBtn");

    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } }
        });
        video.srcObject = stream;
        video.play();
        autoResetLoop();
      } catch (e) {
        alert("Camera access denied.");
      }
    }

    async function toggleFlash(forceOff = false) {
      try {
        if (!stream) return;
        const track = stream.getVideoTracks()[0];
        await track.applyConstraints({
          advanced: [{ torch: forceOff ? false : !torchOn }]
        });
        torchOn = forceOff ? false : !torchOn;
        flashBtn.textContent = torchOn ? "Flash Off" : "🔦 Flash";
      } catch (e) {
        alert("Flash not supported.");
      }
    }

    function autoResetLoop() {
      setInterval(async () => {
        showToast("⚠️ Auto turning off camera + flash briefly...");
        video.srcObject.getTracks().forEach(t => t.stop());
        await new Promise(res => setTimeout(res, 5000));
        startCamera();
        if (torchOn) toggleFlash(); // Turn on again if needed
      }, 120000);
    }

    function showToast(message) {
      const toast = document.createElement("div");
      toast.className = "toast";
      toast.textContent = message;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 3000);
    }

    bgProcessBtn.onclick = () => {
      const tempCanvas = document.createElement("canvas");
      tempCanvas.width = video.videoWidth;
      tempCanvas.height = video.videoHeight;
      const ctx = tempCanvas.getContext("2d");
      ctx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);

      tempCanvas.toBlob(blob => {
        // Download image
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "OMR_" + Date.now() + ".jpg";
        link.click();

        // Upload for processing
        const formData = new FormData();
        formData.append("image", blob, "capture.jpg");
        fetch("/upload", { method: "POST", body: formData })
          .then(() => {
            let retries = 0;
            const interval = setInterval(() => {
              fetch("/status").then(res => res.json()).then(data => {
                if (!data.processing) {
                  clearInterval(interval);
                  if (data.filename) {
                    const match = data.filename.match(/_(\d+)\.jpg$/);
                    const correct = match ? match[1] : 'N/A';
                    showToast(`✅ Processed successfully • Correct: ${correct}`);
                  } else {
                    showToast("❌ Processing failed");
                  }
                }
              });
              if (++retries > 10) clearInterval(interval);
            }, 1500);
          }).catch(() => {
            showToast("❌ Upload failed");
          });
      }, "image/jpeg");
    };

    captureBtn.onclick = () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const imageDataURL = canvas.toDataURL("image/jpeg");

      video.style.display = "none";
      document.getElementById("overlay").style.display = "none";

      const loading = document.createElement("div");
      Object.assign(loading.style, {
        position: 'fixed',
        top: 0, left: 0,
        width: '100vw', height: '100vh',
        background: 'black',
        color: 'white',
        fontSize: '22px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 9999
      });

      const img = document.createElement("img");
      img.src = imageDataURL;
      img.style.maxHeight = "70vh";
      img.style.marginBottom = "10px";

      const text = document.createElement("div");
      text.textContent = "🔄 Processing the file…";

      loading.appendChild(img);
      loading.appendChild(text);
      document.body.appendChild(loading);

      canvas.toBlob(blob => {
        const formData = new FormData();
        formData.append("image", blob, "capture.jpg");
        fetch("/upload", { method: "POST", body: formData })
          .then(() => {
            const interval = setInterval(() => {
              fetch("/status").then(res => res.json()).then(data => {
                if (!data.processing) {
                  clearInterval(interval);
                  loading.remove();
                  if (data.filename) {
                    resultImg.src = "/temp_output/" + data.filename + "?t=" + Date.now();
                    resultImg.id = "fullImageView";
                    document.body.innerHTML = "";
                    document.body.appendChild(resultImg);
                    document.body.appendChild(nextBtn);
                    document.body.appendChild(refreshBtn);
                  } else {
                    document.body.innerHTML = "❌ Failed to process the image.<br>";
                    document.body.appendChild(nextBtn);
                    document.body.appendChild(refreshBtn);
                  }
                }
              });
            }, 1000);
          }).catch(() => {
            loading.remove();
            document.body.innerHTML = "❌ Upload error<br>";
            document.body.appendChild(nextBtn);
            document.body.appendChild(refreshBtn);
          });
      }, "image/jpeg");
    };

    flashBtn.onclick = toggleFlash;
    refreshBtn.onclick = () => location.reload();
    nextBtn.onclick = () => location.reload();

    startCamera();
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
