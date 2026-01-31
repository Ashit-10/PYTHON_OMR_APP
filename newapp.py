import os
import time
import shutil
import subprocess
import signal
import sys
import threading
import glob
import re
import json
import logging
from flask import Flask, send_from_directory, render_template, render_template_string, jsonify, request, send_file
from datetime import datetime
from flask import Flask, render_template, render_template_string, jsonify, request, send_file, Response

# --- LOGGING FILTER ---
class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())

# --- CONFIGURATION ---
app = Flask(__name__)
BASE = os.getcwd()
download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
extensions = ('.jpg', '.jpeg', '.png')
STATIC_FOLDERS = ["input", "output", "duplicates", "error_images"]

# --- GLOBAL STATE ---
processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False


# --- OMR BACKGROUND PROCESSING ---
def open_chrome():
    os.system("am start -n com.android.chrome/com.google.android.apps.chrome.Main -a android.intent.action.VIEW -d https://127.0.0.1:7860")


def move_and_process(file_path):
    global processing, current_filename, latest_output_filename, error_occurred
    processing = True
    error_occurred = False

    # Ensure directories exist
    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs("output", exist_ok=True)

    # Clean previous temp files
    shutil.rmtree(input_folder, ignore_errors=True)
    shutil.rmtree(output_folder, ignore_errors=True)
    os.makedirs(input_folder)
    os.makedirs(output_folder)

    current_filename = os.path.basename(file_path)
    shutil.move(file_path, os.path.join(input_folder, current_filename))

    # Trigger OMR Logic
    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stdout: print(stdout.decode())
    if stderr:
        print(stderr.decode(), file=sys.stderr)
        error_occurred = True

    # Identify output
    files = [f for f in os.listdir(output_folder) if f.endswith(extensions)]
    if files:
        latest_output_filename = files[-1]
        src_path = os.path.join(output_folder, latest_output_filename)
        
        # Handle duplicate filenames in the permanent output folder
        dest_path = os.path.join("output", latest_output_filename)
        if os.path.exists(dest_path):
            count = 1
            while True:
                new_name = f"dup{count}_{latest_output_filename}"
                dest_path = os.path.join("output", new_name)
                if not os.path.exists(dest_path): break
                count += 1
            latest_output_filename = new_name
        
        shutil.copy(src_path, os.path.join("output", latest_output_filename))
    else:
        latest_output_filename = ""

    processing = False

def watch_folder():
    """Background loop for file automation."""
    while True:
        # 1. Sync Answer Keys
        for f in glob.glob(os.path.join(download_folder, '*ans*_key*.txt*')):
            try:
                shutil.move(f, os.path.join(BASE, os.path.basename(f)))
                print(f"Moved answer key: {f}")
            except: pass

        # 2. Sync OMR Scans
        files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.endswith(extensions)]
        for f in files:
            path = os.path.join(download_folder, f)
            move_and_process(path)
        time.sleep(1)

# --- PROJECT MANAGEMENT LOGIC ---

def get_project_folders():
    out = []
    if not os.path.exists(BASE): return out
    for f in os.listdir(BASE):
        full_path = os.path.join(BASE, f)
        if os.path.isdir(full_path) and (f.startswith("class") or f in STATIC_FOLDERS):
            out.append(f)
    return sorted(out)

# --- MAIN ROUTES ---
import json
import os



@app.route("/edit_rolls")
def edit_rolls():
    filename = request.args.get('file')
    file_path = os.path.join(BASE, filename)
    students = []
    
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)  # Read as JSON dictionary
                # Convert dictionary to a sorted list for the UI
                for roll in sorted(data.keys(), key=lambda x: int(x)):
                    students.append({'roll': roll, 'name': data[roll]})
        except Exception as e:
            print(f"Error loading JSON: {e}")
            
    return render_template("rolls_editor.html", students=students, filename=filename)

@app.route("/save_rolls", methods=["POST"])
def save_rolls():
    data = request.json
    filename = data.get('filename')
    student_list = data.get('students')
    file_path = os.path.join(BASE, filename)
    
    # Convert list back into the JSON dictionary format: {"1": "Name"}
    json_data = {str(s['roll']): s['name'] for s in student_list}
    
    try:
        with open(file_path, 'w') as f:
            json.dump(json_data, f, indent=4) # Save as pretty JSON
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/update_config", methods=["POST"])
def update_config():
    data = request.json
    new_sign = data.get("signature")
    
    # Read existing lines, change the signature line, and write back
    lines = []
    try:
        with open("config.cfg", "r") as f:
            lines = f.readlines()
            
        with open("config.cfg", "w") as f:
            for line in lines:
                if line.startswith("signature="):
                    f.write(f"signature={new_sign}\n")
                else:
                    f.write(line)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/")
def dashboard():
    """Main landing page with folder manager and roll lists."""
    # Find all files ending with _rolls.txt in the current directory
    all_files = os.listdir(BASE)
    rolls_files = [f for f in all_files if f.endswith('_rolls.txt')]
    
    return render_template("index.html", 
                           folders=get_project_folders(), 
                           rolls_files=rolls_files)

import subprocess

@app.route('/sync_roll_github')
def sync_roll_github():
    filename = request.args.get('file')
    def generate():
        # Using 'python3' to be safe, adjust to 'python' if on Windows
        process = subprocess.Popen(
            ['python3', 'gitup.py', 'sync_file', filename], 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in process.stdout:
            yield line
        process.wait()
    return Response(generate(), mimetype='text/plain')


@app.route('/run_gitup')
def run_gitup():
    # Get parameters from the URL
    tution = request.args.get('tution')
    cls = request.args.get('class')
    sub = request.args.get('subject')

    def generate():
        # Passing parameters to gitup.py
        # This is like running: python gitup.py mvm 10 Physics
        process = subprocess.Popen(
            ['python', 'gitup.py', tution, cls, sub],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        for line in process.stdout:
            yield line
        process.wait()

    return Response(generate(), mimetype='text/plain')

@app.route("/scan")
def scan_ui():
    """Camera interface for scanning."""
    with open("camera_ui.html") as f:
        return f.read()

@app.route("/results")
def results_page():
    """Real-time OMR result viewer."""
    return render_template_string(RESULTS_HTML)

# --- API ENDPOINTS ---

@app.route('/upload', methods=['POST'])
def upload():
    global current_filename, processing
    file = request.files['image']
    
    # Force a unique name that the watch_folder WILL recognize
    current_filename = f"OMR_sheet_{int(time.time())}.jpg"
    path = os.path.join(download_folder, current_filename)
    file.save(path)
    
    # OPTIONAL: Trigger processing immediately instead of waiting for the thread
    # threading.Thread(target=move_and_process, args=(path,)).start()
    
    return jsonify({"message": "OK", "filename": current_filename})

@app.route('/status')
def status():
    return jsonify({
        "processing": processing,
        "filename": latest_output_filename,
        "input_filename": current_filename
    })

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json
    cls = re.sub(r'[^a-zA-Z0-9]', '-', data.get("class", "NA"))
    sub = re.sub(r'[^a-zA-Z0-9]', '-', data.get("subject", "NA"))
    counter = 1
    while True:
        folder_name = f"class-{cls}_{sub}_{counter}".lower()
        if not os.path.exists(os.path.join(BASE, folder_name)):
            os.makedirs(os.path.join(BASE, folder_name))
            break
        counter += 1
    return jsonify(folders=get_project_folders())

@app.route("/browse")
def browse():
    path = request.args.get("path")
    full_path = os.path.join(BASE, path)
    items = []
    if os.path.exists(full_path):
        for f in os.listdir(full_path):
            fp = os.path.join(full_path, f)
            items.append({"name": f, "is_dir": os.path.isdir(fp)})
    
    def sort_key(x):
        if x["is_dir"]: return (0, x["name"])
        m = re.search(r"(\d+)", x["name"])
        return (1, int(m.group(1)) if m else 999999)
    items.sort(key=sort_key)
    return render_template("browser.html", items=items, path=path)

@app.route("/file")
def get_file():
    target = os.path.join(BASE, request.args.get("path", ""))
    return send_file(target) if os.path.exists(target) else ("Not Found", 404)

@app.route("/delete", methods=["POST"])
def delete_item():
    path = os.path.join(BASE, request.json["path"])
    if os.path.isdir(path): shutil.rmtree(path)
    else: os.remove(path)
    return jsonify(ok=True)

@app.route("/answer_key")
def answer_key_route():
    file_path = os.path.join(BASE, "answer_key.txt")
    content = ""
    if os.path.exists(file_path):
        with open(file_path, "r") as f: content = f.read()
    return render_template("50.html", content=content, folder=".")

@app.route("/save_answer_key", methods=["POST"])
def save_key():
    data = request.json
    try:
        with open(os.path.join(BASE, "answer_key.txt"), "w") as f:
            f.write(data.get("content"))
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# Static file serving for OMR images
@app.route('/temp_output/<path:filename>')
def serve_output(filename):
    return send_from_directory("output", filename)

@app.route('/temp_input/<path:filename>')
def serve_input(filename):
    return send_from_directory("temp_input", filename)

# --- RESULTS HTML TEMPLATE ---

RESULTS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>OMR Result Viewer</title>
  <style>
    body { margin: 0; background: black; color: white; text-align: center; font-family: sans-serif; }
    #status { margin-top: 20px; font-size: 22px; }
    img { max-height: 80vh; width: auto; display: block; margin: 20px auto; border: 3px solid white; }
    #timestamp { font-size: 150px; font-weight: bold; color: #00ffcc; }
    .btn { padding: 10px 20px; font-size: 16px; background: #5451f0; color: white; border: none; cursor: pointer; }
  </style>
  <script>
    let lastInput = ""; let lastOutput = "";
    async function pollStatus() {
      try {
        const response = await fetch('/status');
        const data = await response.json();
        const statusDiv = document.getElementById("status");
        const imgTag = document.getElementById("result-img");
        const ts = document.getElementById("timestamp");

        if (data.input_filename && data.input_filename !== lastInput) {
            lastInput = data.input_filename;
            statusDiv.textContent = "🟡 Processing New Image...";
            imgTag.src = "/temp_input/" + data.input_filename + "?t=" + Date.now();
            imgTag.style.display = "block";
            ts.textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }
        if (!data.processing && data.filename && data.filename !== lastOutput) {
            lastOutput = data.filename;
            statusDiv.textContent = "✅ Success!";
            imgTag.src = "/temp_output/" + data.filename + "?t=" + Date.now();
        }
      } catch (err) { console.error(err); }
    }
    setInterval(pollStatus, 800);
  </script>
</head>
<body>
  <h2>📸 OMR LIVE FEED</h2>
  <div id="status">⏳ Waiting for scan...</div>
  <div id="timestamp"></div>
  <img id="result-img" style="display:none;" />
  <button class="btn" onclick="window.location.href='/'">🔙 Back to Dashboard</button>
</body>
</html>
"""

if __name__ == '__main__':
    threading.Thread(target=watch_folder, daemon=True).start()
    threading.Timer(0.1, open_chrome).start()
    app.run(host='0.0.0.0', port=7860, ssl_context=('certs/cert.pem', 'certs/key.pem'), threaded=True)

