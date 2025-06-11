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
from datetime import datetime
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

    # Clear previous inputs and outputs
    shutil.rmtree(input_folder)
    shutil.rmtree(output_folder)
    os.makedirs(input_folder)
    os.makedirs(output_folder)

    # Move the input file
    shutil.move(file_path, os.path.join(input_folder, os.path.basename(file_path)))

    # Run processing script
    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stdout:
        print(stdout.decode())
    if stderr:
        print(stderr.decode(), file=sys.stderr)
        error_occurred = True

    # Fetch processed file
    files = [f for f in os.listdir(output_folder) if f.endswith(extensions)]
    if files:
        latest_output_filename = files[-1]
        src_path = os.path.join(output_folder, latest_output_filename)

        # Ensure unique filename in "output" folder
        base_name, ext = os.path.splitext(latest_output_filename)
        dest_path = os.path.join("output", latest_output_filename)
        count = 1
        while os.path.exists(dest_path):
            timestamp = datetime.now().strftime("dup_%H_%M_%S")
            new_name = f"{timestamp}{ext}"
            dest_path = os.path.join("output", new_name)
            count += 1

        shutil.copy(src_path, dest_path)
        latest_output_filename = os.path.basename(dest_path)  # Update the variable with the renamed one if needed
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
    html, body {
      margin: 0;
      padding: 0;
      background: black;
      color: white;
      font-family: sans-serif;
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

    video {
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

    #instantBtn {
      position: absolute;
      left: calc(50% + 100px);
      top: 0;
      padding: 10px;
      font-size: 16px;
      border-radius: 8px;
      border: 2px solid white;
      cursor: pointer;
      font-weight: bold;
    }

    #instantBtn.on {
      background: lime;
      color: black;
    }

    #toast {
      position: fixed;
      top: 40px;
      right: 10px;
      background: white;
      color: black;
      padding: 14px 22px;
      border-radius: 8px;
      font-size: 18px;
      font-weight: bold;
      display: none;
      z-index: 9999;
      box-shadow: 0 0 10px #fff;
    }
  </style>
</head>
<body>

  <div id="wrap">
    <video id="video" autoplay playsinline muted></video>
    <div class="overlay">
      <div class="qr-box qr-tl"></div>
      <div class="qr-box qr-tr"></div>
      <div class="qr-box qr-bl"></div>
      <div class="qr-box qr-br"></div>
    </div>
  </div>

  <button id="instantBtn">Instant</button>

  <div class="controls">
    <button id="flashBtn">🔦 Flash</button>
    <button id="captureBtn">📸 Capture</button>
    <button id="refreshBtn">🔄 Refresh</button>
  </div>

  <div id="toast"></div>

  <script>
    const video = document.getElementById("video");
    const flashBtn = document.getElementById("flashBtn");
    const captureBtn = document.getElementById("captureBtn");
    const refreshBtn = document.getElementById("refreshBtn");
    const instantBtn = document.getElementById("instantBtn");
    const toast = document.getElementById("toast");

    let stream = null;
    let torchOn = false;

    function showToast(msg) {
      toast.textContent = msg;
      toast.style.display = "block";
      setTimeout(() => toast.style.display = "none", 2500);
    }

    function setInstantMode(mode) {
      localStorage.setItem("instant", mode ? "1" : "0");
      instantBtn.classList.toggle("on", mode);
    }

    function getInstantMode() {
      return localStorage.getItem("instant") === "1";
    }

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
        const track = stream.getVideoTracks()[0];
        await track.applyConstraints({ advanced: [{ torch: !torchOn }] });
        torchOn = !torchOn;
        flashBtn.textContent = torchOn ? "Flash Off" : "🔦 Flash";
      } catch (e) {
        alert("Flash not supported.");
      }
    }

    function sendToServer(blob, callback) {
      const formData = new FormData();
      formData.append("image", blob, "capture.jpg");

      fetch("/upload", { method: "POST", body: formData })
        .then(() => {
          showToast("🔄 Processing...");
          const interval = setInterval(() => {
            fetch("/status")
              .then(res => res.json())
              .then(data => {
                if (!data.processing) {
                  clearInterval(interval);
                  if (data.filename) {
                    callback && callback(data.filename);
                  } else {
                    showToast("❌ Failed to process");
                  }
                }
              })
              .catch(() => {
                clearInterval(interval);
                showToast("❌ Error checking status");
              });
          }, 1000);
        })
        .catch(() => showToast("❌ Upload failed"));
    }

    captureBtn.onclick = () => {
      const showOutput = getInstantMode();
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0);

      canvas.toBlob(blob => {
        sendToServer(blob, filename => {
          if (showOutput) {
            const resultImg = document.createElement("img");
            resultImg.src = "/temp_output/" + filename + "?t=" + Date.now();
            resultImg.style.width = "100vw";
            resultImg.style.height = "100vh";
            resultImg.style.objectFit = "contain";
            resultImg.onload = () => {
              document.body.innerHTML = "";
              document.body.appendChild(resultImg);
              document.body.appendChild(refreshBtn);
            };
            resultImg.onerror = () => {
              document.body.innerHTML = "❌ Could not load output image.";
              document.body.appendChild(refreshBtn);
            };
          } else {
            const correct = filename.split("_")[1]?.split(".")[0];
            showToast(`✅ Processed! Correct: ${correct || "?"}`);
          }
        });
      }, "image/jpeg");
    };

    instantBtn.onclick = () => {
      const current = getInstantMode();
      setInstantMode(!current);
    };

    flashBtn.onclick = toggleFlash;
    refreshBtn.onclick = () => location.reload();

    // Initialize
    if (getInstantMode()) instantBtn.classList.add("on");
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
