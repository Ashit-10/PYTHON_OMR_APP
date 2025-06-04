import os
import time
import shutil
import threading
import glob
from flask import Flask, request, jsonify, send_from_directory, render_template_string

download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
error_folder = "error"
extensions = ('.jpg', '.jpeg', '.png')

processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

app = Flask(__name__)

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

    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)

    # Clear old temp files
    for f in glob.glob(os.path.join(input_folder, "*")):
        os.remove(f)
    for f in glob.glob(os.path.join(output_folder, "*")):
        os.remove(f)

    shutil.move(file_path, os.path.join(input_folder, filename))
    print(f"Moved {filename} to input folder.")

    # Dummy processing simulation (replace with your actual autoapp.py call)
    time.sleep(3)  # simulate processing time
    # For demo, just copy input file to output folder
    shutil.copy(os.path.join(input_folder, filename), os.path.join(output_folder, filename))
    latest_output_filename = filename

    processing = False

def watch_folder():
    print("Watching for new OMR images...")
    already_seen = set()
    while True:
        try:
            files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.lower().endswith(extensions)]
            for file in files:
                full_path = os.path.join(download_folder, file)
                if full_path not in already_seen:
                    move_and_process(full_path)
                    already_seen.add(full_path)
            time.sleep(1)
        except Exception as e:
            print(f"Watch folder error: {e}")
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
    body, html { margin:0; padding:0; background:black; color:white; font-family:sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:flex-start; }
    #wrap { position: relative; width: 180px; height: 480px; margin-top: 15px; border: 4px solid white; }
    video, canvas, #resultImg { width: 180px; height: 480px; object-fit: contain; display: block; }
    #resultImg { display:none; }
    .controls { margin-top: 15px; display: flex; gap: 10px; }
    button { font-size: 16px; padding: 10px 15px; border-radius:5px; cursor:pointer; border:none; background:white; color:black; }
    #loadingOverlay {
      position: fixed; top:0; left:0; width:100vw; height:100vh;
      background: rgba(0,0,0,0.9); color:white; font-size: 22px;
      display:flex; justify-content:center; align-items:center; z-index:9999;
    }
  </style>
</head>
<body>

<div id="wrap">
  <video id="video" autoplay playsinline muted></video>
  <canvas id="canvas" style="display:none;"></canvas>
  <img id="resultImg" />
</div>

<div class="controls">
  <button id="captureBtn">📸 Capture</button>
  <button id="nextBtn" style="display:none;">🔁 Next</button>
</div>

<script>
  const video = document.getElementById('video');
  const canvas = document.getElementById('canvas');
  const resultImg = document.getElementById('resultImg');
  const captureBtn = document.getElementById('captureBtn');
  const nextBtn = document.getElementById('nextBtn');
  let stream;

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: 180,
          height: 480,
          facingMode: "environment"
        }
      });
      video.srcObject = stream;
      await video.play();
    } catch (err) {
      alert("Cannot access back camera. Check permissions.");
      console.error(err);
    }
  }

  captureBtn.onclick = () => {
    if (!video.videoWidth || !video.videoHeight) {
      alert("Video not ready yet.");
      return;
    }
    // Set canvas size same as video stream
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Stop the camera
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
    }
    video.style.display = 'none';

    // Show loading overlay
    const loadingOverlay = document.createElement('div');
    loadingOverlay.id = 'loadingOverlay';
    loadingOverlay.textContent = "🔄 Processing the file…";
    document.body.appendChild(loadingOverlay);

    canvas.toBlob(blob => {
      // Download captured image
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = "OMR_sheet.jpg";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);

      // Upload to backend
      const formData = new FormData();
      formData.append('image', blob, 'capture.jpg');

      fetch('/upload', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
          // Poll for processing status
          const intervalId = setInterval(() => {
            fetch('/status')
              .then(res => res.json())
              .then(status => {
                if (!status.processing && status.filename) {
                  clearInterval(intervalId);
                  loadingOverlay.remove();

                  // Show processed image
                  resultImg.src = "/temp_output/" + status.filename + "?t=" + new Date().getTime();
                  resultImg.style.display = "block";

                  // Hide capture button, show next
                  captureBtn.style.display = "none";
                  nextBtn.style.display = "inline-block";
                }
              });
          }, 1000);
        })
        .catch(err => {
          loadingOverlay.remove();
          alert("Upload or processing failed");
          console.error(err);
        });
    }, 'image/jpeg');
  };

  nextBtn.onclick = () => {
    // Reset UI to take another capture
    resultImg.style.display = 'none';
    captureBtn.style.display = 'inline-block';
    nextBtn.style.display = 'none';
    video.style.display = 'block';
    startCamera();
  };

  startCamera();
</script>

</body>
</html>
    ''')

@app.route('/upload', methods=['POST'])
def upload():
    global processing, current_filename, latest_output_filename, error_occurred
    try:
        file = request.files['image']
        filename = f"OMR_camera_{int(time.time())}.jpg"
        file_path = os.path.join(download_folder, filename)
        file.save(file_path)
        print(f"Image saved: {filename}")
        # Start processing in background thread so upload returns immediately
        threading.Thread(target=move_and_process, args=(file_path,), daemon=True).start()
        return jsonify({"message": "Image uploaded"})
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"message": "Upload failed"}), 500

@app.route('/status')
def status():
    global processing, current_filename, latest_output_filename
    return jsonify({
        "processing": processing,
        "filename": current_filename if processing else latest_output_filename
    })

@app.route('/temp_output/<path:filename>')
def serve_output(filename):
    return send_from_directory(output_folder, filename)

if __name__ == "__main__":
    threading.Thread(target=watch_folder, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
