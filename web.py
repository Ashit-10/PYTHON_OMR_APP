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

    #fullImageView {
      width: 100vw;
      height: 100vh;
      object-fit: contain;
      background: black;
    }

    #errorMessage {
      color: red;
      font-size: 18px;
      margin-top: 20px;
    }

    #processingImage {
      max-height: 70vh;
      width: auto;
      object-fit: contain;
      margin-bottom: 10px;
      margin-top: -10px;
    }
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
    <button id="nextBtn" style="display:none;">🔁 Next</button>
    <button id="refreshBtn" style="display:none;">🔄 Refresh</button>
  </div>

  <div id="errorMessage"></div>

  <script>
    let stream = null;
    let torchOn = false;

    const video = document.getElementById("video");
    const canvas = document.getElementById("canvas");
    const resultImg = document.getElementById("resultImg");
    const flashBtn = document.getElementById("flashBtn");
    const captureBtn = document.getElementById("captureBtn");
    const nextBtn = document.getElementById("nextBtn");
    const refreshBtn = document.getElementById("refreshBtn");
    const overlay = document.getElementById("overlay");
    const errorMessage = document.getElementById("errorMessage");

    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } }
        });
        video.srcObject = stream;
        video.play();
      } catch (e) {
        alert("Camera access denied.");
      }
    }

    async function toggleFlash() {
      try {
        if (!stream) return;
        const track = stream.getVideoTracks()[0];
        await track.applyConstraints({
          advanced: [{ torch: !torchOn }]
        });
        torchOn = !torchOn;
        flashBtn.textContent = torchOn ? "Flash Off" : "🔦 Flash";
      } catch (e) {
        alert("Flash not supported.");
      }
    }

    document.addEventListener("visibilitychange", () => {
      if (document.hidden && stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
      }
    });

    function showControls(mode) {
      flashBtn.style.display = (mode === "initial") ? "inline-block" : "none";
      captureBtn.style.display = (mode === "initial") ? "inline-block" : "none";
      refreshBtn.style.display = (mode === "initial" || mode === "processing") ? "inline-block" : "none";
      nextBtn.style.display = (mode === "result" || mode === "error") ? "inline-block" : "none";
    }

    captureBtn.onclick = () => {
      errorMessage.textContent = "";
      showControls("processing");

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const imageDataURL = canvas.toDataURL("image/jpeg");

      stream.getTracks().forEach(t => t.stop());
      video.style.display = "none";
      overlay.style.display = "none";

      const loading = document.createElement("div");
      loading.id = "loadingOverlay";
      Object.assign(loading.style, {
        position: 'fixed',
        top: 0, left: 0,
        width: '100vw',
        height: '100vh',
        background: 'black',
        color: 'white',
        fontSize: '22px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 9999,
        textAlign: 'center'
      });

      const capturedImg = document.createElement("img");
      capturedImg.id = "processingImage";
      capturedImg.src = imageDataURL;

      const processingText = document.createElement("div");
      processingText.textContent = "🔄 Processing the file…";

      loading.appendChild(capturedImg);
      loading.appendChild(processingText);
      document.body.appendChild(loading);

      canvas.toBlob(blob => {
        const formData = new FormData();
        formData.append("image", blob, "capture.jpg");

        fetch("/upload", { method: "POST", body: formData })
          .then(() => {
            const interval = setInterval(() => {
              fetch("/status")
                .then(res => res.json())
                .then(data => {
                  if (!data.processing) {
                    clearInterval(interval);
                    loading.remove();
                    if (data.filename) {
                      resultImg.src = "/temp_output/" + data.filename + "?t=" + Date.now();
                      resultImg.id = "fullImageView";
                      document.body.innerHTML = "";
                      document.body.appendChild(resultImg);
                      document.body.appendChild(nextBtn);
                      showControls("result");
                    } else {
                      errorMessage.textContent = "❌ Failed to process the image.";
                      document.body.innerHTML = "";
                      document.body.appendChild(errorMessage);
                      document.body.appendChild(nextBtn);
                      showControls("error");
                    }
                  }
                })
                .catch(err => {
                  clearInterval(interval);
                  loading.remove();
                  errorMessage.textContent = "❌ Error during processing.";
                  document.body.innerHTML = "";
                  document.body.appendChild(errorMessage);
                  document.body.appendChild(nextBtn);
                  showControls("error");
                });
            }, 1000);
          })
          .catch(err => {
            loading.remove();
            errorMessage.textContent = "❌ Upload error.";
            document.body.innerHTML = "";
            document.body.appendChild(errorMessage);
            document.body.appendChild(nextBtn);
            showControls("error");
          });
      }, "image/jpeg");
    };

    flashBtn.onclick = toggleFlash;
    refreshBtn.onclick = () => location.reload();
    nextBtn.onclick = () => location.reload();

    startCamera();
    showControls("initial");
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
