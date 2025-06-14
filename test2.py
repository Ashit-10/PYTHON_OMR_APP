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

        # Rename if needed: dup1_, dup2_ etc.
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
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>OMR Sheet Scanner</title>
  <style>
    body, html {
      margin: 0; padding: 0;
      background: black;
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
      flex-shrink: 0;
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
      border: 2px solid lime;
      width: 30px; height: 30px;
      position: absolute;
    }

    .qr-tl { top: 10px; left: 10px; }
    .qr-tr { top: 10px; right: 10px; }
    .qr-bl { bottom: 10px; left: 10px; }
    .qr-br { bottom: 10px; right: 10px; }

    #toggleContainer {
      position: absolute;
      top: 50px;
      right: 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 5px;
    }

    #instantToggle {
      appearance: none;
      width: 40px;
      height: 20px;
      background: #555;
      border-radius: 10px;
      position: relative;
      cursor: pointer;
    }

    #instantToggle::before {
      content: '';
      position: absolute;
      top: 3px;
      left: 3px;
      width: 14px; height: 14px;
      background: white;
      border-radius: 50%;
      transition: 0.2s;
    }

    #instantToggle:checked {
      background: limegreen;
    }

    #instantToggle:checked::before {
      transform: translateX(20px);
    }

    #toggleLabel {
      font-size: 14px;
      color: white;
    }

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

    #toast {
      position: fixed;
      bottom: 260px;
      right: 15px;
      background: white;
      color: black;
      padding: 12px 20px;
      border-radius: 5px;
      font-weight: bold;
      display: none;
      z-index: 9999;
      font-size: 16px;
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

  <div id="toggleContainer">
    <input type="checkbox" id="instantToggle">
    <div id="toggleLabel">Instant</div>
  </div>

  <div class="controls">
    <button id="flashBtn">🔦 Flash</button>
    <button id="captureBtn">📸 Capture</button>
    <button id="refreshBtn">🔄 Refresh</button>
  </div>

  <div id="toast"></div>

  <script>
    let stream, torchOn = false;
    const video = document.getElementById('video');
    const flashBtn = document.getElementById('flashBtn');
    const captureBtn = document.getElementById('captureBtn');
    const refreshBtn = document.getElementById('refreshBtn');
    const instantToggle = document.getElementById('instantToggle');
    const toast = document.getElementById('toast');

    instantToggle.checked = localStorage.getItem('instantMode') === 'true';

    if (!sessionStorage.getItem('initialShown')) {
      alert(`📸 Instant ON:
The processed OMR sheet will appear directly on screen.

📥 Instant OFF:
Just click Capture – it will process in background and show result here.

💡 Recommended: Use Instant OFF for better performance and speed.`);
      sessionStorage.setItem('initialShown', 'true');
    }

    instantToggle.onchange = () => {
      localStorage.setItem('instantMode', instantToggle.checked);
    };

    function showToast(msg) {
      toast.textContent = msg;
      toast.style.display = 'block';
      setTimeout(() => toast.style.display = 'none', 2500);
    }

    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } }
        });
        video.srcObject = stream;
        video.play();
      } catch (e) {
        alert('Camera access denied.');
      }
    }

    async function toggleFlash() {
      if (!stream) return;
      try {
        const track = stream.getVideoTracks()[0];
        await track.applyConstraints({ advanced: [{ torch: !torchOn }] });
        torchOn = !torchOn;
        flashBtn.textContent = torchOn ? 'Flash Off' : '🔦 Flash';
      } catch {
        alert('Flash not supported.');
      }
    }

    function extractCorrect(filename) {
      const parts = filename.split("_");
      return parts[parts.length - 1].split(".")[0];
    }

    captureBtn.onclick = () => {
      const isInstant = instantToggle.checked;
      const c = document.createElement('canvas');
      c.width = video.videoWidth;
      c.height = video.videoHeight;
      c.getContext('2d').drawImage(video, 0, 0);

      c.toBlob(blob => {
        const formData = new FormData();
        formData.append('image', blob, 'capture.jpg');

        if (!isInstant) {
          showToast('🔄 Processing...');
          fetch('/upload', { method: 'POST', body: formData }).then(() => {
            const poll = setInterval(() => {
              fetch('/status').then(r => r.json()).then(data => {
                if (!data.processing) {
                  clearInterval(poll);
                  if (data.filename) {
                    const corr = extractCorrect(data.filename);
                    showToast(`✅ Correct: ${corr}`);
                  } else {
                    showToast('❌ Process failed');
                  }
                }
              }).catch(() => {
                clearInterval(poll);
                showToast('❌ Error');
              });
            }, 1000);
          }).catch(() => {
            showToast('❌ Upload failed');
          });
        } else {
          stream.getTracks().forEach(t => t.stop());
          const loading = document.createElement('div');
          Object.assign(loading.style, {
            position: 'fixed', top: 0, left: 0,
            width: '100vw', height: '100vh',
            background: 'black', color: 'white',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            fontSize: '20px', zIndex: 9999
          });

          const img = document.createElement('img');
          img.src = URL.createObjectURL(blob);
          img.style.maxHeight = '70vh';
          loading.appendChild(img);

          const procTxt = document.createElement('div');
          procTxt.textContent = '🔄 Processing the file…';
          loading.appendChild(procTxt);

          document.body.innerHTML = '';
          document.body.appendChild(loading);

          fetch('/upload', { method: 'POST', body: formData }).then(() => {
            const poll2 = setInterval(() => {
              fetch('/status').then(r => r.json()).then(data => {
                if (!data.processing) {
                  clearInterval(poll2);
                  if (data.filename) {
                    const result = document.createElement('img');
                    result.src = '/temp_output/' + data.filename + '?t=' + Date.now();
                    result.style.cssText = 'width:100vw;height:100vh;object-fit:contain;background:black';

                    refreshBtn.textContent = 'Next';
                    setTimeout(() => {
                      document.body.innerHTML = '';
                      document.body.appendChild(result);
                      document.body.appendChild(refreshBtn);
                    }, 500);
                  }
                }
              });
            }, 1000);
          });
        }
      }, 'image/jpeg');
    };

    refreshBtn.onclick = () => location.reload();
    flashBtn.onclick = toggleFlash;
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
@app.route('/results')
def results():
    img_url = f"/temp_output/{latest_output_filename}?t={int(time.time())}"
    return f"""
    <html>
    <head>
        <title>Result</title>
        <script>
            let lastFilename = "{latest_output_filename}";
            function checkUpdate() {{
                fetch('/status')
                .then(r => r.json())
                .then(data => {{
                    if (data.filename && data.filename !== lastFilename) {{
                        lastFilename = data.filename;
                        document.getElementById("result-img").src = "/temp_output/" + data.filename + "?t=" + Date.now();
                        document.getElementById("ts").textContent = "Updated: " + new Date().toLocaleTimeString();
                    }}
                }});
            }}
            setInterval(checkUpdate, 3000);  // check every 3 seconds
        </script>
    </head>
    <body style="margin:0;background:black;color:white;text-align:center;">
        <div style="padding: 15px;">
            <h3 id="ts">Updated: {datetime.now().strftime('%H:%M:%S')}</h3>
            <img id="result-img" src="{img_url}" style="max-height:90vh;width:auto;margin-top:10px;" />
            <br/><br/>
            <button onclick="location.reload()" style="padding:10px 20px;font-size:16px;">🔄 Refresh</button>
        </div>
    </body>
    </html>
    """

@app.route('/temp_output/<path:filename>')
def get_output(filename):
    return send_from_directory("output", filename)

if __name__ == '__main__':
    threading.Thread(target=watch_folder, daemon=True).start()
    threading.Timer(0.5, open_chrome).start()
    app.run(host='0.0.0.0', port=5000)
