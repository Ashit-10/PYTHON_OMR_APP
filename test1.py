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
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>OMR sheet evaluator</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
            }
            video, canvas, #resultImg {
                width: 90%;
                max-width: 400px;
                margin: 10px auto;
                display: block;
                border: 4px solid black;
            }
            .qr-box {
                position: absolute;
                border: 3px solid lime;
                width: 50px; height: 50px;
            }
            .qr-tl { top: 10%; left: 10%; }
            .qr-tr { top: 10%; right: 10%; }
            .qr-bl { bottom: 10%; left: 10%; }
            .qr-br { bottom: 10%; right: 10%; }

            .overlay {
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                pointer-events: none;
            }

            .hidden {
                display: none;
            }

            button {
                padding: 12px 24px;
                font-size: 16px;
                margin: 10px;
            }

            #wrap {
                position: relative;
                display: inline-block;
            }
        </style>
    </head>
    <body>
        <h2>OMR sheet evaluator</h2>

        <div id="wrap">
            <video id="video" autoplay playsinline></video>
            <canvas id="canvas" class="hidden"></canvas>
            <div class="overlay">
                <div class="qr-box qr-tl"></div>
                <div class="qr-box qr-tr"></div>
                <div class="qr-box qr-bl"></div>
                <div class="qr-box qr-br"></div>
            </div>
        </div>

        <div>
            <button id="captureBtn">Capture</button>
            <button id="nextBtn" class="hidden" onclick="location.reload()">Next / Redo</button>
        </div>

        <img id="resultImg" class="hidden" />

        ;
    }, 'image/jpeg', 0.9);
  };

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
