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

# === Logging Filter ===
class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())

# === Paths ===
download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
error_folder = "error"
extensions = ('.jpg', '.jpeg', '.png')

# === Globals ===
processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

app = Flask(__name__)

# === Signal handler ===
def signal_handler(sig, frame):
    print("\nStopped by user.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# === Utility ===
def get_latest_error_image():
    error_files = glob.glob(os.path.join(error_folder, "*"))
    error_files = [f for f in error_files if f.lower().endswith(extensions)]
    if not error_files:
        return None
    return max(error_files, key=os.path.getmtime)

def move_and_process(file_path):
    global processing, current_filename, latest_output_filename, error_occurred
    filename = os.path.basename(file_path)
    current_filename = filename
    processing = True
    error_occurred = False

    os.system("mkdir -p temp_input temp_output")
    os.system("rm -rf temp_input/*")
    os.system("rm -rf temp_output/*")
    shutil.move(file_path, os.path.join(input_folder, filename))
    print(f"Moved {filename} to input folder.")

    process = subprocess.Popen(
        ["python3", "autoapp.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout, stderr = process.communicate()

    if stdout:
        print("Output from autoapp.py:")
        print(stdout)

    if stderr:
        print("Error from autoapp.py:", file=sys.stderr)
        print(stderr, file=sys.stderr)
        error_occurred = True

    if "fail" in str(stdout).lower() or "fail" in str(stderr).lower():
        error_occurred = True

    output_files = os.listdir(output_folder)
    output_files = [f for f in output_files if f.lower().endswith(extensions)]

    if output_files:
        latest_output_filename = output_files[-1]
        print(f"Processed output: {latest_output_filename}")
    else:
        error_file = get_latest_error_image()
        if error_occurred and error_file:
            dest = os.path.join(output_folder, os.path.basename(error_file))
            shutil.copy(error_file, dest)
            latest_output_filename = os.path.basename(error_file)
            print(f"Displayed error image: {latest_output_filename}")
        else:
            latest_output_filename = ""

    processing = False

def watch_folder():
    print("Watching for new OMR images...")
    already_seen = set()

    while True:
        try:
            key_files = [f for f in os.listdir(download_folder) if f.startswith("answer_key") and f.endswith(".txt")]
            for key_file in key_files:
                key_path = os.path.join(download_folder, key_file)
                shutil.move(key_path, "answer_key.txt")
                print(f"Moved answer key: {key_path}")
        except:
            pass

        try:
            files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.lower().endswith(extensions)]
            for file in files:
                full_path = os.path.join(download_folder, file)
                if full_path not in already_seen:
                    move_and_process(full_path)
                    already_seen.add(full_path)
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OMR Evaluator</title>
  <style>
    body, html {
      margin: 0; padding: 0;
      height: 100%;
      font-family: sans-serif;
      background: black;
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: space-between;
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
      top: 0; left: 0; right: 0; bottom: 0;
      pointer-events: none;
    }

    .controls {
      width: 100%;
      padding: 15px;
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px;
      background-color: rgba(0,0,0,0.8);
    }

    button {
      font-size: 16px;
      padding: 10px 15px;
      border: none;
      border-radius: 5px;
      cursor: pointer;
      background: white;
      color: black;
    }

    #resultImg {
      display: none;
      width: 100vw;
      height: auto;
    }
  </style>
</head>
<body>

  <div id="wrap">
    <video id="video" autoplay playsinline muted></video>
    <canvas id="canvas"></canvas>
    <div class="overlay">
      <div class="qr-box qr-tl"></div>
      <div class="qr-box qr-tr"></div>
      <div class="qr-box qr-bl"></div>
      <div class="qr-box qr-br"></div>
    </div>
  </div>

  <img id="resultImg" />

  <div class="controls">
    <button id="flashlightButton">🔦 Flash</button>
    <button id="captureBtn">📸 Capture</button>
    <button id="nextBtn" style="display:none;" onclick="location.reload()">🔁 Next</button>
    <button id="toggleCameraBtn">📷 Camera Off</button>
  </div>

  <script>
    let stream, track;
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const resultImg = document.getElementById('resultImg');
    const captureBtn = document.getElementById('captureBtn');
    const nextBtn = document.getElementById('nextBtn');
    const flashlightButton = document.getElementById('flashlightButton');
    const toggleCameraBtn = document.getElementById('toggleCameraBtn');

    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 960 },
            height: { ideal: 1920 },
            facingMode: { ideal: "environment" }
          }
        });
        track = stream.getVideoTracks()[0];
        video.srcObject = stream;
        video.play();
      } catch (e) {
        alert("Back camera not accessible.");
        console.error(e);
      }
    }

    async function toggleFlash() {
      if (!track) return;
      try {
        const settings = track.getSettings();
        const torch = !settings.torch;
        await track.applyConstraints({ advanced: [{ torch }] });
        flashlightButton.textContent = torch ? "Flash Off" : "🔦 Flash";
      } catch (e) {
        alert("Flash not supported.");
      }
    }

    toggleCameraBtn.onclick = () => {
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
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
      canvas.getContext('2d').drawImage(video, 0, 0);

      if (stream) stream.getTracks().forEach(t => t.stop());
      document.getElementById('wrap').style.display = "none";

      const loading = document.createElement('div');
      loading.id = 'loadingOverlay';
      loading.textContent = "🔄 Processing the file…";
      Object.assign(loading.style, {
        position: 'fixed', top: 0, left: 0,
        width: '100vw', height: '100vh',
        background: 'black', color: 'white',
        fontSize: '22px',
        display: 'flex', justifyContent: 'center', alignItems: 'center',
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
                    captureBtn.style.display = "none";
                    nextBtn.style.display = "inline-block";
                  }
                });
            }, 1000);
          });
      }, 'image/jpeg');
    };

    flashlightButton.onclick = toggleFlash;
    startCamera();
  </script>
</body>
</html>
''')

@app.route('/status')
def status():
    return jsonify({
        "processing": processing,
        "filename": current_filename if processing else latest_output_filename
    })

@app.route('/temp_output/<path:filename>')
def serve_output_file(filename):
    return send_from_directory(output_folder, filename)

@app.route('/upload', methods=['POST'])
def upload():
    try:
        file = request.files['image']
        filename = f"OMR_camera_{int(time.time())}.jpg"
        file_path = os.path.join(download_folder, filename)
        file.save(file_path)
        print(f"Captured image saved as {filename}")
        return jsonify({"message": "Image uploaded successfully", "filename": filename})
    except Exception as e:
        print("Upload error:", e)
        return jsonify({"message": "Upload failed"}), 500

# === Run Server ===
if __name__ == "__main__":
    threading.Thread(target=watch_folder, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
