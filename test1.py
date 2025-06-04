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

download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
extensions = ('.jpg', '.jpeg', '.png')

app = Flask(__name__)
processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

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
  <title>OMR sheet evaluator</title>
  <style>
    body, html {
      margin: 0;
      padding: 0;
      height: 100%;
      background-color: black;
      font-family: sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
      color: white;
    }
    #wrap {
      position: relative;
      width: 180px;
      height: 480px;
      margin-top: 15px;
      border: 4px solid white;
      box-sizing: content-box;
    }
    video, canvas {
      width: 180px;
      height: 480px;
      object-fit: cover;
      display: block;
    }
    #resultImg {
      display: none;
      width: 100vw;
      height: 100vh;
      object-fit: contain;
      background-color: black;
    }
    .overlay .qr-box {
      position: absolute;
      border: 2px solid lime;
      width: 30px;
      height: 30px;
    }
    .qr-tl { top: 10px; left: 10px; }
    .qr-tr { top: 10px; right: 10px; }
    .qr-bl { bottom: 10px; left: 10px; }
    .qr-br { bottom: 10px; right: 10px; }

    .overlay {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      pointer-events: none;
    }

    .controls {
      width: 100%;
      padding: 10px;
      display: flex;
      justify-content: center;
      gap: 10px;
      background-color: rgba(0, 0, 0, 0.8);
      position: fixed;
      bottom: 0;
    }

    button {
      font-size: 16px;
      padding: 8px 12px;
      border: none;
      border-radius: 5px;
      cursor: pointer;
      background: white;
      color: black;
    }

    .hide {
      display: none !important;
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

  <img id="resultImg" />

  <div class="controls">
    <button id="flashlightButton" onclick="toggleFlash()">🔦 Flash</button>
    <button id="captureBtn">📸 Capture</button>
    <button id="nextBtn" onclick="location.reload()">🔁 Next</button>
    <button id="toggleCameraBtn">📷 Camera Off</button>
  </div>

  <script>
    let stream, videoStream, torchOn = false;
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const resultImg = document.getElementById('resultImg');
    const flashlightButton = document.getElementById('flashlightButton');
    const toggleCameraBtn = document.getElementById('toggleCameraBtn');
    const captureBtn = document.getElementById('captureBtn');
    const overlay = document.getElementById('overlay');
    const wrap = document.getElementById('wrap');

    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 960 },
            height: { ideal: 1920 },
            facingMode: { ideal: "environment" }
          }
        });
        video.srcObject = stream;
        video.play();
      } catch (e) {
        alert("Back camera not accessible.");
        console.error(e);
      }
    }

    async function toggleFlash() {
      if (stream) {
        const track = stream.getVideoTracks()[0];
        try {
          await track.applyConstraints({ advanced: [{ torch: !torchOn }] });
          torchOn = !torchOn;
          flashlightButton.textContent = torchOn ? "Flash Off" : "🔦 Flash";
        } catch (e) {
          alert("Flash not supported");
        }
      }
    }

    toggleCameraBtn.onclick = () => {
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
        stream = null;
        video.style.display = "none";
        toggleCameraBtn.textContent = "📷 Camera On";
      } else {
        startCamera();
        video.style.display = "block";
        toggleCameraBtn.textContent = "📷 Camera Off";
      }
    };

    captureBtn.onclick = () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      if (stream) stream.getTracks().forEach(t => t.stop());

      wrap.classList.add("hide");
      overlay.classList.add("hide");

      const loading = document.createElement('div');
      loading.id = 'loadingOverlay';
      loading.textContent = "🔄 Processing the file…";
      Object.assign(loading.style, {
        position: 'fixed',
        top: 0, left: 0,
        width: '100vw', height: '100vh',
        background: 'black',
        color: 'white',
        fontSize: '22px',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 9999
      });
      document.body.appendChild(loading);

      canvas.toBlob(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = "OMR_sheet.jpg";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        const formData = new FormData();
        formData.append('image', blob, 'capture.jpg');

        fetch('/upload', { method: 'POST', body: formData })
          .then(() => {
            const checkStatus = setInterval(() => {
              fetch('/status')
                .then(res => res.json())
                .then(data => {
                  if (!data.processing && data.filename) {
                    clearInterval(checkStatus);
                    loading.remove();
                    resultImg.src = "/temp_output/" + data.filename + "?t=" + new Date().getTime();
                    resultImg.style.display = "block";
                  }
                });
            }, 1000);
          });
      }, 'image/jpeg');
    };

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
    app.run(host='0.0.0.0', port=5000)
