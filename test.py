# app.py
import os
import time
import shutil
import subprocess
import threading
import glob
from flask import Flask, send_from_directory, render_template_string, jsonify, request

download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
extensions = ('.jpg', '.jpeg', '.png')

app = Flask(__name__)
processing = False
latest_output_filename = ""
error_occurred = False

def move_and_process(file_path):
    global processing, latest_output_filename, error_occurred
    processing = True
    error_occurred = False

    # Clean and recreate folders
    for folder in (input_folder, output_folder):
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder)

    # Move input image to input folder
    shutil.move(file_path, os.path.join(input_folder, os.path.basename(file_path)))

    # Run processing script (make sure autoapp.py outputs images in output_folder)
    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stdout:
        print(stdout.decode())
    if stderr:
        print(stderr.decode(), file=sys.stderr)
        error_occurred = True

    # Find latest output image
    files = sorted([f for f in os.listdir(output_folder) if f.endswith(extensions)])
    if files:
        latest_output_filename = files[-1]
    else:
        latest_output_filename = ""

    processing = False

def watch_folder():
    seen = set()
    while True:
        # Move answer_key*.txt files if any
        answer_key_files = glob.glob(os.path.join(download_folder, "answer_key*.txt"))
        for akf in answer_key_files:
            dest = os.path.basename(akf)
            if not os.path.exists(dest):
                try:
                    shutil.move(akf, dest)
                    print(f"Moved {akf} to {dest}")
                except Exception as e:
                    print(f"Error moving {akf}: {e}")

        # Process new OMR images
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
      display: block;
    }
    #errorMessage {
      color: red;
      font-size: 18px;
      margin-top: 20px;
      display: none;
    }
    #loadingOverlay {
      position: fixed;
      top: 0; left: 0;
      width: 100vw; height: 100vh;
      background: black;
      color: white;
      font-size: 22px;
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 9999;
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
  const wrap = document.getElementById("wrap");

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

  function showControls(mode) {
    // Modes: "initial", "processing", "result", "error"
    flashBtn.style.display = (mode === "initial") ? "inline-block" : "none";
    captureBtn.style.display = (mode === "initial") ? "inline-block" : "none";
    refreshBtn.style.display = (mode === "initial" || mode === "processing") ? "inline-block" : "none";
    nextBtn.style.display = (mode === "result" || mode === "error") ? "inline-block" : "none";
  }

  captureBtn.onclick = () => {
    errorMessage.style.display = "none";
    showControls("processing");

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

    // Stop camera stream safely
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }

    video.style.display = "none";
    overlay.style.display = "none";

    // Show loading overlay
    const loading = document.createElement("div");
    loading.id = "loadingOverlay";
    loading.textContent = "🔄 Processing the file…";
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
                    // Show result image full screen
                    resultImg.src = "/temp_output/" + data.filename + "?t=" + Date.now();
                    resultImg.id = "fullImageView";
                    wrap.style.display = "none";
                    if (!document.body.contains(resultImg)) {
                      document.body.appendChild(resultImg);
                    }
                    showControls("result");
                  } else {
                    errorMessage.textContent = "❌ Failed to process the image.";
                    errorMessage.style.display = "block";
                    showControls("error");
                  }
                }
              })
              .catch(err => {
                clearInterval(interval);
                loading.remove();
                errorMessage.textContent = "❌ Error during processing.";
                errorMessage.style.display = "block";
                showControls("error");
              });
          }, 1000);
        })
        .catch(err => {
          loading.remove();
          errorMessage.textContent = "❌ Upload error.";
          errorMessage.style.display = "block";
          showControls("error");
        });
    }, "image/jpeg");
  };

  flashBtn.onclick = toggleFlash;
  refreshBtn.onclick = () => location.reload();
  nextBtn.onclick = () => location.reload();

  // Safely stop camera on page unload
  window.addEventListener('beforeunload', () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
    }
  });

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
    app.run(host='0.0.0.0', port=5000)
