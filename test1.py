import os
import shutil
import subprocess
import sys
import threading
import time
import signal
import glob
from flask import Flask, send_from_directory, render_template_string, request, jsonify
import logging
from datetime import datetime

# Logging setup
class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())

# Paths
download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
error_folder = "error"
extensions = ('.jpg', '.jpeg', '.png')

# Globals
processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

app = Flask(__name__)
signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))

os.makedirs(input_folder, exist_ok=True)
os.makedirs(output_folder, exist_ok=True)

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

    os.system("rm -rf temp_input/* temp_output/*")
    shutil.move(file_path, os.path.join(input_folder, filename))
    print(f"Moved {filename} to input folder.")

    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if stdout: print(stdout)
    if stderr: print(stderr, file=sys.stderr)

    if "fail" in stdout.lower() or "fail" in stderr.lower():
        error_occurred = True

    output_files = [f for f in os.listdir(output_folder) if f.lower().endswith(extensions)]
    if output_files:
        latest_output_filename = output_files[-1]
    else:
        err_img = get_latest_error_image()
        if error_occurred and err_img:
            dest = os.path.join(output_folder, os.path.basename(err_img))
            shutil.copy(err_img, dest)
            latest_output_filename = os.path.basename(err_img)
        else:
            latest_output_filename = ""

    processing = False

@app.route('/')
def index():
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
      font-family: sans-serif;
      background-color: black;
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
    video, canvas, #resultImg {
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
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
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

    canvas, #resultImg {
      position: absolute;
      top: 0;
      left: 0;
      display: none;
    }
  </style>
</head>
<body>

  <div id="wrap">
    <video id="video" autoplay playsinline muted></video>
    <canvas id="canvas"></canvas>
    <img id="resultImg" />
    <div class="overlay">
      <div class="qr-box qr-tl"></div>
      <div class="qr-box qr-tr"></div>
      <div class="qr-box qr-bl"></div>
      <div class="qr-box qr-br"></div>
    </div>
  </div>

  <div class="controls">
    <button id="flashlightButton" onclick="toggleFlash()">🔦 Flash</button>
    <button id="captureBtn">📸 Capture</button>
    <button id="nextBtn" style="display:none;" onclick="location.reload()">🔁 Next</button>
    <button id="toggleCameraBtn">📷 Camera Off</button>
  </div>

  <script>
    let stream, videoStream, track;
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
        videoStream = stream;
        video.srcObject = stream;
        video.play();
      } catch (e) {
        alert("Back camera not accessible. Allow camera access in settings.");
        console.error(e);
      }
    }

    let torchOn = false;

    async function toggleFlash() {
      if (stream) {
        const track = stream.getVideoTracks()[0];
        if (torchOn) {
          await track.applyConstraints({ advanced: [{ torch: false }] });
          torchOn = false;
          location.reload(); // Reload to reset UI
        } else {
          await track.applyConstraints({ advanced: [{ torch: true }] });
          torchOn = true;
          flashlightButton.textContent = "Flash Off";
        }
      }
    }

    let cameraOn = true;
    toggleCameraBtn.onclick = () => {
      if (cameraOn) {
        video.pause();
        if (stream) stream.getTracks().forEach(t => t.stop());
        video.style.display = "none";
        toggleCameraBtn.textContent = "📷 Camera On";
      } else {
        startCamera();
        video.style.display = "block";
        toggleCameraBtn.textContent = "📷 Camera Off";
      }
      cameraOn = !cameraOn;
    };

    captureBtn.onclick = () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(blob => {
        // ⬇️ Trigger download
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = "OMR_sheet.jpg";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        const formData = new FormData();
        formData.append('image', blob, 'capture.jpg');
        fetch('/upload', { method: 'POST', body: formData })
          .then(r => r.json())
          .then(data => {
            video.style.display = "none";
            resultImg.src = "/temp_output/" + data.filename + "?t=" + new Date().getTime();
            resultImg.style.display = "block";
            captureBtn.style.display = "none";
            nextBtn.style.display = "inline-block";
          });
      }, 'image/jpeg');
    };

    document.getElementById('flashlightButton').addEventListener('click', toggleFlash);
    startCamera();
  </script>
</body>
</html>
''')


@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    image = request.files['image']
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"OMR_{timestamp}.jpg"
    save_path = os.path.join(download_folder, filename)
    image.save(save_path)

    threading.Thread(target=move_and_process, args=(save_path,), daemon=True).start()

    # Wait until result is available
    while processing:
        time.sleep(0.5)

    return jsonify({"filename": latest_output_filename})

@app.route('/temp_output/<path:filename>')
def serve_output_file(filename):
    return send_from_directory(output_folder, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
