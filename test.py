import os
import time
import shutil
import subprocess
import signal
import sys
import threading
import glob
from flask import Flask, send_from_directory, render_template_string, jsonify, request

app = Flask(__name__)

download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
error_folder = "error"
extensions = ('.jpg', '.jpeg', '.png')

processing = False
latest_output_filename = ""
error_occurred = False

# Ensure folders exist
os.makedirs(input_folder, exist_ok=True)
os.makedirs(output_folder, exist_ok=True)
os.makedirs(error_folder, exist_ok=True)

def safe_move_answer_key():
    # Move answer_key*.txt files if available
    try:
        key_files = [f for f in os.listdir(download_folder) if f.startswith("answer_key") and f.endswith(".txt")]
        for key_file in key_files:
            src = os.path.join(download_folder, key_file)
            dst = "answer_key.txt"
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
            print(f"Moved answer key: {key_file}")
    except Exception as e:
        print(f"Error moving answer key: {e}")

def process_image(file_path):
    global processing, latest_output_filename, error_occurred
    processing = True
    error_occurred = False

    # Clear temp folders
    for folder in [input_folder, output_folder]:
        for f in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, f))
            except Exception:
                pass

    filename = os.path.basename(file_path)
    shutil.move(file_path, os.path.join(input_folder, filename))
    print(f"Moved file {filename} to input folder")

    # Run your processing script here (replace 'autoapp.py' with your actual processing script)
    process = subprocess.Popen(
        ["python3", "autoapp.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate()
    print("Processing stdout:", stdout)
    print("Processing stderr:", stderr)

    if "fail" in stdout.lower() or "fail" in stderr.lower():
        error_occurred = True

    # Find output image
    output_images = [f for f in os.listdir(output_folder) if f.lower().endswith(extensions)]
    if output_images:
        # Use the last created output image and copy it to a stable filename
        latest_file = sorted(output_images, key=lambda f: os.path.getmtime(os.path.join(output_folder, f)))[-1]
        src = os.path.join(output_folder, latest_file)
        dst = os.path.join(output_folder, "latest_output.jpg")
        shutil.copy(src, dst)
        latest_output_filename = "latest_output.jpg"
        print(f"Output image ready: {latest_output_filename}")
    else:
        # Show error image if exists
        error_images = [f for f in os.listdir(error_folder) if f.lower().endswith(extensions)]
        if error_images:
            latest_error = sorted(error_images, key=lambda f: os.path.getmtime(os.path.join(error_folder, f)))[-1]
            src = os.path.join(error_folder, latest_error)
            dst = os.path.join(output_folder, latest_error)
            shutil.copy(src, dst)
            latest_output_filename = latest_error
            error_occurred = True
            print(f"Error image displayed: {latest_output_filename}")
        else:
            latest_output_filename = ""
            print("No output or error images found.")

    processing = False

def watch_folder_thread():
    # Continuously watch for new images and answer keys
    while True:
        safe_move_answer_key()
        files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.lower().endswith(extensions)]
        for f in files:
            full_path = os.path.join(download_folder, f)
            if not processing:
                try:
                    print(f"Found new file to process: {f}")
                    process_image(full_path)
                except Exception as e:
                    print(f"Error processing file {f}: {e}")
        time.sleep(2)

@app.route("/")
def index():
    # Serve main page with full UI logic handled by JS below
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Camera OMR</title>
<style>
  body { margin:0; background:#111; color:#eee; font-family: Arial, sans-serif; }
  #camera-container { position: relative; width: 180px; height: 480px; margin: 20px auto; border: 3px solid #0f0; box-sizing: border-box; }
  video#video { width: 180px; height: 480px; object-fit: cover; background:#000; }
  #overlay-box { position: absolute; top: 50px; left: 10px; width: 160px; height: 380px; border: 2px solid lime; pointer-events:none; }
  #output-image { display:none; max-width: 100vw; max-height: 100vh; margin: auto; }
  #message { text-align:center; margin: 15px 0; font-size: 1.2em; }
  #buttons { text-align:center; margin: 10px; }
  button {
    background: #222;
    color: #0f0;
    border: 1px solid #0f0;
    padding: 8px 12px;
    margin: 5px;
    font-size: 1em;
    cursor: pointer;
    border-radius: 4px;
  }
  button:disabled {
    color: #444;
    border-color: #444;
    cursor: default;
  }
</style>
</head>
<body>

<div id="camera-container">
  <video id="video" autoplay playsinline></video>
  <div id="overlay-box"></div>
</div>

<img id="output-image" src="" alt="Output Result" />

<div id="message"></div>

<div id="buttons">
  <button id="flash-btn">Flash On</button>
  <button id="capture-btn">Capture</button>
  <button id="refresh-btn" style="display:none;">Refresh</button>
  <button id="next-btn" style="display:none;">Next</button>
</div>

<script>
  const video = document.getElementById('video');
  const outputImage = document.getElementById('output-image');
  const message = document.getElementById('message');
  const flashBtn = document.getElementById('flash-btn');
  const captureBtn = document.getElementById('capture-btn');
  const refreshBtn = document.getElementById('refresh-btn');
  const nextBtn = document.getElementById('next-btn');
  const cameraContainer = document.getElementById('camera-container');

  let stream = null;
  let track = null;
  let flashOn = false;
  let processing = false;
  let cameraOn = true;

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { exact: "environment" }, width: 180, height: 480 },
        audio: false
      });
      video.srcObject = stream;
      track = stream.getVideoTracks()[0];
      flashBtn.style.display = 'inline-block';
      captureBtn.style.display = 'inline-block';
      refreshBtn.style.display = 'none';
      nextBtn.style.display = 'none';
      message.textContent = '';
      outputImage.style.display = 'none';
      cameraContainer.style.display = 'block';
      cameraOn = true;
      processing = false;
      flashOn = false;
      flashBtn.textContent = 'Flash On';
    } catch (e) {
      message.textContent = 'Error accessing back camera.';
      flashBtn.style.display = 'none';
      captureBtn.style.display = 'none';
      refreshBtn.style.display = 'inline-block';
      nextBtn.style.display = 'none';
      cameraOn = false;
      console.error(e);
    }
  }

  async function stopCamera() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
      track = null;
      cameraOn = false;
      flashOn = false;
      flashBtn.textContent = 'Flash On';
    }
  }

  flashBtn.onclick = async () => {
    if (!track) return;
    try {
      const capabilities = track.getCapabilities();
      if (!capabilities.torch) {
        alert('Flash not supported on this device');
        return;
      }
      flashOn = !flashOn;
      await track.applyConstraints({ advanced: [{ torch: flashOn }] });
      flashBtn.textContent = flashOn ? 'Flash Off' : 'Flash On';
    } catch (err) {
      alert('Error toggling flash: ' + err.message);
    }
  };

  captureBtn.onclick = () => {
    if (!stream || processing) return;
    processing = true;

    // Show processing message and refresh button only
    message.textContent = 'Processing the file…';
    refreshBtn.style.display = 'inline-block';
    flashBtn.style.display = 'none';
    captureBtn.style.display = 'none';
    nextBtn.style.display = 'none';
    outputImage.style.display = 'none';
    cameraContainer.style.display = 'block';

    // Capture the photo
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 180;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      if (!blob) {
        alert('Failed to capture image');
        processing = false;
        return;
      }
      // Send blob to server
      const formData = new FormData();
      formData.append('file', blob, 'capture.jpg');

      try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.status === 'processing') {
          pollResult();
        } else {
          showError('Unexpected server response');
        }
      } catch (e) {
        showError('Upload failed: ' + e.message);
      }
    }, 'image/jpeg');
  };

  refreshBtn.onclick = () => {
    // Reset UI to initial camera mode
    if (processing) return; // block refresh during processing
    message.textContent = '';
    outputImage.style.display = 'none';
    cameraContainer.style.display = 'block';
    flashBtn.style.display = 'inline-block';
    captureBtn.style.display = 'inline-block';
    refreshBtn.style.display = 'none';
    nextBtn.style.display = 'none';
    startCamera();
  };

  nextBtn.onclick = () => {
    // Clear output and start fresh camera
    message.textContent = '';
    outputImage.style.display = 'none';
    cameraContainer.style.display = 'block';
    flashBtn.style.display = 'inline-block';
    captureBtn.style.display = 'inline-block';
    refreshBtn.style.display = 'none';
    nextBtn.style.display = 'none';
    startCamera();
  };

  function showError(text) {
    processing = false;
    message.textContent = text;
    cameraContainer.style.display = 'none';
    outputImage.style.display = 'block';
    outputImage.src = '';
    refreshBtn.style.display = 'none';
    flashBtn.style.display = 'none';
    captureBtn.style.display = 'none';
    nextBtn.style.display = 'inline-block';
  }

  async function pollResult() {
    try {
      const res = await fetch('/status');
      const data = await res.json();

      if (data.processing) {
        setTimeout(pollResult, 1500);
      } else if (data.error) {
        // Show error image + next button only
        showOutputImage(data.output_url);
        message.textContent = 'Error occurred during processing.';
        flashBtn.style.display = 'none';
        captureBtn.style.display = 'none';
        refreshBtn.style.display = 'none';
        nextBtn.style.display = 'inline-block';
        processing = false;
      } else if (data.output_url) {
        // Show full output image + next button
        showOutputImage(data.output_url);
        message.textContent = '';
        flashBtn.style.display = 'none';
        captureBtn.style.display = 'none';
        refreshBtn.style.display = 'none';
        nextBtn.style.display = 'inline-block';
        processing = false;
      } else {
        showError('No output image found.');
      }
    } catch (e) {
      showError('Error fetching status: ' + e.message);
    }
  }

  function showOutputImage(url) {
    cameraContainer.style.display = 'none';
    outputImage.style.display = 'block';
    outputImage.src = url + '?_=' + new Date().getTime(); // cache bust
  }

  window.addEventListener('beforeunload', () => {
    stopCamera();
  });

  // Start camera on page load
  window.onload = () => {
    refreshBtn.style.display = 'none';
    nextBtn.style.display = 'none';
    flashBtn.style.display = 'inline-block';
    captureBtn.style.display = 'inline-block';
    startCamera();
  };
</script>

</body>
</html>
    """)

from flask import request

@app.route('/upload', methods=['POST'])
def upload():
    global processing, error_occurred
    if processing:
        return jsonify({"status": "busy"})

    file = request.files.get('file')
    if not file:
        return jsonify({"status": "error", "message": "No file received"})

    filepath = os.path.join(download_folder, file.filename)
    file.save(filepath)
    print(f"Received file {file.filename}")

    threading.Thread(target=process_image, args=(filepath,), daemon=True).start()
    return jsonify({"status": "processing"})

@app.route('/status')
def status():
    global processing, latest_output_filename, error_occurred
    if processing:
        return jsonify({"processing": True})
    if latest_output_filename:
        url_path = "/output/" + latest_output_filename
        return jsonify({"processing": False, "output_url": url_path, "error": error_occurred})
    return jsonify({"processing": False, "output_url": None})

@app.route('/output/<filename>')
def serve_output(filename):
    return send_from_directory(output_folder, filename)

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

if __name__ == "__main__":
    # Start folder watcher in background thread
    watcher = threading.Thread(target=watch_folder_thread, daemon=True)
    watcher.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
