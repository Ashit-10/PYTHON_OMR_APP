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
    os.system("am start -n com.android.chrome/com.google.android.apps.chrome.Main -a android.intent.action.VIEW -d https://127.0.0.1:7860")

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

    current_filename = os.path.basename(file_path)
    shutil.move(file_path, os.path.join(input_folder, current_filename))

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
        src_path = os.path.join(output_folder, latest_output_filename)

        base_name = os.path.basename(latest_output_filename)
        dest_path = os.path.join("output", base_name)

        if os.path.exists(dest_path):
            count = 1
            while True:
                new_name = f"dup{count}_{base_name}"
                dest_path = os.path.join("output", new_name)
                if not os.path.exists(dest_path):
                    break
                count += 1
            latest_output_filename = new_name
        else:
            latest_output_filename = base_name

        shutil.copy(src_path, os.path.join("output", latest_output_filename))
    else:
        latest_output_filename = ""

    processing = False

def watch_folder():
    moved = []
    for f in glob.glob('/sdcard/Download/*ans*_key*.txt*'):
        try:
            shutil.move(f, f'./{os.path.basename(f)}')
            moved.append(os.path.basename(f))
            print("Moved answer key:", moved)
        except: 
            pass

    seen = set()
    while True:
        files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.endswith(extensions)]
        for f in files:
            path = os.path.join(download_folder, f)
            if path not in seen:
                move_and_process(path)
                seen.add(path)
        time.sleep(1)

@app.route('/upload', methods=['POST'])
def upload():
    global current_filename
    file = request.files['image']
    current_filename = f"OMR_{int(time.time())}.jpg"
    path = os.path.join(download_folder, current_filename)
    file.save(path)
    return jsonify({"message": "OK"})

@app.route('/status')
def status():
    return jsonify({
        "processing": processing,
        "filename": latest_output_filename,
        "input_filename": current_filename
    })

@app.route('/temp_output/<path:filename>')
def get_output(filename):
    return send_from_directory("output", filename)

@app.route('/temp_input/<path:filename>')
def get_input(filename):
    return send_from_directory("temp_input", filename)

@app.route('/results')
def results():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
  <title>Result</title>
  <style>
    body {
      margin: 0;
      background: black;
      color: white;
      text-align: center;
      font-family: sans-serif;
    }
    #status {
      margin-top: 20px;
      font-size: 22px;
    }
    #image-box {
      margin-top: 15px;
    }
    img {
      max-height: 80vh;
      width: auto;
      display: block;
      margin: 0 auto;
      border: 3px solid white;
    }
    #timestamp {
      font-size: 200px; /* 10x size */
      font-weight: bold;
      margin-top: 10px;
      color: #00ffcc;
    }
    #refresh {
      padding: 10px 20px;
      font-size: 16px;
      margin-top: 20px;
    }
  </style>
  <script>
    let lastInput = "";
    let lastOutput = "";
    let hasShownProcessing = false;

    async function fileExists(url) {
      try {
        const res = await fetch(url, { method: 'HEAD' });
        return res.ok;
      } catch {
        return false;
      }
    }

    function getTimeString() {
      const now = new Date();
      return now.getHours().toString().padStart(2, '0') + ":" +
             now.getMinutes().toString().padStart(2, '0');
    }

    async function pollStatus() {
      try {
        const response = await fetch('/status');
        const data = await response.json();

        const statusDiv = document.getElementById("status");
        const imgTag = document.getElementById("result-img");
        const ts = document.getElementById("timestamp");

        if (data.input_filename && data.input_filename !== lastInput) {
          const inputURL = "/temp_input/" + data.input_filename;

          if (await fileExists(inputURL)) {
            lastInput = data.input_filename;
            lastOutput = "";
            hasShownProcessing = false;
            statusDiv.textContent = "🟡 Got new image, processing now…";
            imgTag.src = inputURL + "?t=" + Date.now();
            imgTag.style.display = "block";
            ts.textContent = getTimeString();
            return;
          }
        }

        if (!data.processing && data.filename && data.filename !== lastOutput) {
          const outputURL = "/temp_output/" + data.filename;

          if (await fileExists(outputURL)) {
            lastOutput = data.filename;
            statusDiv.textContent = "✅ Processed successfully.";
            imgTag.src = outputURL + "?t=" + Date.now();
            ts.textContent = getTimeString();
            return;
          }
        }

        if (!data.processing && !data.filename && lastInput && !hasShownProcessing) {
          const fallbackURL = "/temp_input/" + lastInput;
          if (await fileExists(fallbackURL)) {
            statusDiv.textContent = "❌ Error in processing.";
            imgTag.src = fallbackURL + "?t=" + Date.now();
            ts.textContent = getTimeString();
            hasShownProcessing = true;
            return;
          }
        }
      } catch (err) {
        document.getElementById("status").textContent = "❌ Failed to fetch status.";
      }
    }

    setInterval(pollStatus, 500);
  </script>
</head>
<body>
  <h2>📸 OMR Result Viewer</h2>
  <div id="status">⏳ Waiting for new image…</div>
  <div id="image-box">
    <img id="result-img" src="" style="display:none;" />
    <div id="timestamp"></div>
  </div>
  <button id="refresh" onclick="location.reload()">🔄 Refresh</button>
</body>
</html>
    """)

@app.route('/')
def index():
    with open("camera_ui.html") as f:
        return f.read()

if __name__ == '__main__':
    threading.Thread(target=watch_folder, daemon=True).start()
    threading.Timer(0.5, open_chrome).start()
    app.run(host='0.0.0.0', port=7860, ssl_context=('certs/cert.pem', 'certs/key.pem'), threaded=True)
