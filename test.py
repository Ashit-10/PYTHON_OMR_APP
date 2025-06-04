import os
import time
import shutil
import subprocess
import signal
import sys
import threading
import glob
import base64
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

# === Signal handler for Ctrl+C ===
def signal_handler(sig, frame):
    print("\nStopped by user.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# === Utility Functions ===
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

# === Routes ===
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
      margin-top: 20px;
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
      gap: 20px;
      background-color: rgba(0,0,0,0.8);
    }

    button {
      font-size: 16px;
      padding: 10px 20px;
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
  <h3>OMR Sheet Evaluator</h3>

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
    <button onclick="toggleFlash()">🔦 Flash</button>
    <button id="captureBtn">📸 Capture</button>
    <button id="nextBtn" style="display:none;" onclick="location.reload()">🔁 Next</button>
  </div>

  <script>
    let stream, track;
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const resultImg = document.getElementById('resultImg');
    const captureBtn = document.getElementById('captureBtn');
    const nextBtn = document.getElementById('nextBtn');

    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 960 },
            height: { ideal: 1920 },
            facingMode: "environment"
          }
        });
        video.srcObject = stream;
        track = stream.getVideoTracks()[0];
      } catch (e) {
        alert("Back camera not accessible. Allow camera access in settings.");
        console.error(e);
      }
    }

    function toggleFlash() {
      if (!track) return;
      const capabilities = track.getCapabilities();
      if ('torch' in capabilities) {
        const isTorchOn = track.getSettings().torch || false;
        track.applyConstraints({ advanced: [{ torch: !isTorchOn }] })
          .catch(e => alert("Torch toggle not supported."));
      } else {
        alert("Torch not available on this device.");
      }
    }

    captureBtn.onclick = () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(blob => {
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

    startCamera();
  </script>
</body>
</html>
''')


@app.route('/status')
def status():
    global processing, current_filename, latest_output_filename
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
        data = request.get_json()
        image_data = data['image'].split(",")[1]
        image_bytes = base64.b64decode(image_data)
        filename = f"OMR_camera_{int(time.time())}.jpg"
        file_path = os.path.join(download_folder, filename)

        with open(file_path, 'wb') as f:
            f.write(image_bytes)

        print(f"Captured image saved as {filename}")
        return jsonify({"message": "Image uploaded successfully"})
    except Exception as e:
        print("Upload error:", e)
        return jsonify({"message": "Upload failed"}), 500

# === Start App ===
if __name__ == "__main__":
    threading.Thread(target=watch_folder, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
