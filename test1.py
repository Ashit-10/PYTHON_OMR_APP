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
  <title>OMR Capture</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    html, body {
      margin: 0;
      padding: 0;
      background: black;
      color: white;
      font-family: sans-serif;
    }
    #wrap {
      width: 180px;
      height: 480px;
      border: 4px solid white;
      margin: auto;
      margin-top: 20px;
      position: relative;
    }
    video {
      width: 180px;
      height: 480px;
      object-fit: cover;
    }
    .overlay {
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      pointer-events: none;
    }
    .qr-box {
      position: absolute;
      width: 30px;
      height: 30px;
      border: 2px solid lime;
    }
    .qr-tl { top: 10px; left: 10px; }
    .qr-tr { top: 10px; right: 10px; }
    .qr-bl { bottom: 10px; left: 10px; }
    .qr-br { bottom: 10px; right: 10px; }

    .controls {
      text-align: center;
      margin: 15px 0;
    }

    button {
      padding: 10px 15px;
      font-size: 16px;
      background: white;
      color: black;
      border: none;
      border-radius: 5px;
      margin: 5px;
    }

    #resultImg {
      display: none;
      width: 100vw;
      height: 100vh;
      object-fit: contain;
    }

    #loadingOverlay {
      position: fixed;
      top: 0; left: 0;
      width: 100vw;
      height: 100vh;
      background: black;
      color: white;
      display: flex;
      justify-content: center;
      align-items: center;
      font-size: 20px;
      z-index: 9999;
    }
  </style>
</head>
<body>
  <div id="mainUI">
    <div id="wrap">
      <video id="video" autoplay playsinline muted></video>
      <div class="overlay">
        <div class="qr-box qr-tl"></div>
        <div class="qr-box qr-tr"></div>
        <div class="qr-box qr-bl"></div>
        <div class="qr-box qr-br"></div>
      </div>
    </div>
    <div class="controls">
      <button id="captureBtn">📸 Capture</button>
    </div>
  </div>
  <img id="resultImg" />

  <script>
    const video = document.getElementById("video");
    const captureBtn = document.getElementById("captureBtn");
    const resultImg = document.getElementById("resultImg");

    navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 960 }, height: { ideal: 1920 } }
    }).then(stream => {
      video.srcObject = stream;
    }).catch(err => {
      alert("Camera access denied");
      console.error(err);
    });

    captureBtn.onclick = () => {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // stop camera
      video.srcObject.getTracks().forEach(track => track.stop());

      // loading screen
      const loading = document.createElement("div");
      loading.id = "loadingOverlay";
      loading.textContent = "🔄 Processing the file…";
      document.body.appendChild(loading);

      canvas.toBlob(blob => {
        const form = new FormData();
        form.append("image", blob, "capture.jpg");

        fetch("/upload", { method: "POST", body: form }).then(() => {
          const poll = setInterval(() => {
            fetch("/status").then(res => res.json()).then(data => {
              if (!data.processing && data.filename) {
                clearInterval(poll);
                loading.remove();
                document.getElementById("mainUI").remove();
                resultImg.src = "/temp_output/" + data.filename + "?t=" + new Date().getTime();
                resultImg.style.display = "block";
              }
            });
          }, 1000);
        });
      }, "image/jpeg");
    };
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
