import os
import sys
import time
import shutil
import subprocess
import signal
import threading
import glob
import re
import json
import logging
import zipfile
import configparser
import base64
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from flask import (
    Flask, render_template, render_template_string, jsonify, 
    request, send_file, send_from_directory, Response
)

# --- ENVIRONMENT & CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

app = Flask(__name__)
BASE = os.path.abspath(os.getcwd())

INPUT_FOLDER = os.path.join(BASE, "temp_input")
OUTPUT_FOLDER = os.path.join(BASE, "temp_output")
FINAL_OUTPUT_FOLDER = os.path.join(BASE, "output")
EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
STATIC_FOLDERS = ["input", "output", "duplicates", "error_images"]

# Ensure essential directories exist
for folder in [INPUT_FOLDER, OUTPUT_FOLDER, FINAL_OUTPUT_FOLDER] + [os.path.join(BASE, f) for f in STATIC_FOLDERS]:
    os.makedirs(folder, exist_ok=True)

# Async processing state
executor = ThreadPoolExecutor(max_workers=4)
tasks = {}  # Format: { task_id: { "status": "processing"|"completed"|"failed", "input": "", "output": "", "error": "" } }

# --- LOGGING FILTER ---
class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())

# --- HELPER FUNCTIONS ---
def get_safe_path(req_path):
    """Prevents directory traversal attacks."""
    if not req_path:
        return BASE
    normalized = os.path.normpath(req_path).lstrip("/\\")
    target = os.path.abspath(os.path.join(BASE, normalized))
    if not target.startswith(BASE):
        raise PermissionError("Access denied: Path outside root directory.")
    return target

def get_project_folders():
    out = []
    if not os.path.exists(BASE): return out
    for f in os.listdir(BASE):
        full_path = os.path.join(BASE, f)
        if os.path.isdir(full_path) and (f.startswith("class") or f in STATIC_FOLDERS):
            out.append(f)
    return sorted(out)

# --- BACKGROUND TASK WORKER ---
def process_omr_task(task_id, input_filepath, original_filename):
    """Executes autoapp.py asynchronously without blocking Flask."""
    try:
        tasks[task_id]["status"] = "processing"
        
        # Run OMR engine
        process = subprocess.Popen(
            ["python3", "autoapp.py"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            cwd=BASE
        )
        stdout, stderr = process.communicate()

        # Check output directory for new images
        files = [f for f in os.listdir(OUTPUT_FOLDER) if f.lower().endswith(EXTENSIONS)]
        
        if files:
            files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_FOLDER, x)))
            newest_file = files[-1]
            
            src_path = os.path.join(OUTPUT_FOLDER, newest_file)
            dest_path = os.path.join(FINAL_OUTPUT_FOLDER, newest_file)
            
            # Handle filename collision
            if os.path.exists(dest_path):
                name_part, ext_part = os.path.splitext(newest_file)
                count = 1
                while os.path.exists(os.path.join(FINAL_OUTPUT_FOLDER, f"{name_part}_{count}{ext_part}")):
                    count += 1
                newest_file = f"{name_part}_{count}{ext_part}"
                dest_path = os.path.join(FINAL_OUTPUT_FOLDER, newest_file)

            shutil.copy(src_path, dest_path)
            
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["output_filename"] = newest_file
        else:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = stderr.decode() if stderr else "No output file produced by OMR engine."

    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)

# --- ROUTES ---

@app.route("/")
def dashboard():
    all_files = os.listdir(BASE)
    rolls_files = [f for f in all_files if f.endswith('_rolls.txt')]
    folders = get_project_folders()
    
    folder_counts = {}
    for folder in folders:
        folder_path = os.path.join(BASE, folder)
        if os.path.isdir(folder_path):
            count = len([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
            folder_counts[folder] = count
        else:
            folder_counts[folder] = 0

    return render_template("index.html", folders=folders, folder_counts=folder_counts, rolls_files=rolls_files)

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({"error": "No image file uploaded"}), 400
        
    file = request.files['image']
    roll = request.form.get('roll', '').strip()
    timestamp = int(time.time())
    
    filename = f"OMR_sheet_roll_{roll}_{timestamp}.jpg" if roll else f"OMR_sheet_{timestamp}.jpg"
    input_filepath = os.path.join(INPUT_FOLDER, filename)
    file.save(input_filepath)

    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "queued",
        "input_filename": filename,
        "output_filename": "",
        "error": ""
    }

    executor.submit(process_omr_task, task_id, input_filepath, filename)
    return jsonify({"message": "OK", "task_id": task_id, "filename": filename})

@app.route('/status')
def status():
    task_id = request.args.get('task_id')
    if task_id and task_id in tasks:
        t = tasks[task_id]
        return jsonify({
            "processing": t["status"] in ["queued", "processing"],
            "status": t["status"],
            "filename": t["output_filename"],
            "input_filename": t["input_filename"],
            "error": t["status"] == "failed",
            "message": t["error"]
        })
    
    # Fallback to returning latest global status
    latest_task = list(tasks.values())[-1] if tasks else None
    if latest_task:
        return jsonify({
            "processing": latest_task["status"] in ["queued", "processing"],
            "status": latest_task["status"],
            "filename": latest_task["output_filename"],
            "input_filename": latest_task["input_filename"],
            "error": latest_task["status"] == "failed",
            "message": latest_task["error"]
        })
    
    return jsonify({"processing": False, "filename": "", "input_filename": "", "error": False, "message": ""})

@app.route("/scan")
def scan_ui():
    if os.path.exists("templates/camera_ui.html"):
        return render_template("camera_ui.html")
    return "Camera UI Template Missing", 404

@app.route("/results")
def results_page():
    return render_template_string(RESULTS_HTML)

@app.route("/send-telegram", methods=["POST"])
def send_telegram():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return jsonify({"error": "Telegram environment variables missing"}), 500

    data = request.json or {}
    folder_name = data.get("path", "")
    
    try:
        target_folder = get_safe_path(folder_name)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    zip_filename = f"{os.path.basename(target_folder)}_transfer.zip"

    if not os.path.exists(target_folder):
        return jsonify({"error": "Folder not found"}), 404

    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(target_folder):
                for file in files:
                    if file.lower().endswith(EXTENSIONS):
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, arcname=file)

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        with open(zip_filename, 'rb') as f:
            files = {'document': (zip_filename, f)}
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"📂 Folder: {folder_name}"}
            response = requests.post(url, data=payload, files=files, timeout=60)
        
        if os.path.exists(zip_filename):
            os.remove(zip_filename)

        if response.ok:
            return jsonify({"status": "success"})
        return jsonify({"error": response.json().get("description", "Telegram Error")}), 500

    except Exception as e:
        if os.path.exists(zip_filename):
            os.remove(zip_filename)
        return jsonify({"error": str(e)}), 500

@app.route("/api/files")
def list_files_for_count():
    folder_name = request.args.get("path", "input")
    try:
        target_folder = get_safe_path(folder_name)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    if not os.path.exists(target_folder) or not os.path.isdir(target_folder):
        return jsonify({"items": []})

    try:
        files = os.listdir(target_folder)
        image_items = [{"name": f, "is_dir": False} for f in files if f.lower().endswith(EXTENSIONS)]
        return jsonify({"items": image_items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/clear_project_folders', methods=['POST'])
def clear_project_folders():
    target_folders = ['input', 'output', 'error_images', 'duplicates', 'temp_input', 'temp_output']
    try:
        for folder in target_folders:
            folder_path = os.path.join(BASE, folder)
            if os.path.exists(folder_path):
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_config')
def get_config():
    config = configparser.ConfigParser()
    config.read('config.cfg')
    return {
        "pixel_value": config.get('settings', 'pixel_value', fallback='200'),
        "signature": config.get('settings', 'signature', fallback=''),
        "roll_pixel": config.get('settings', 'roll_pixel', fallback='200')
    }

@app.route('/update_config', methods=['POST'])
def update_config():
    data = request.get_json() or {}
    config = configparser.ConfigParser()
    config.read('config.cfg')

    if not config.has_section('settings'):
        config.add_section('settings')

    for key in ['signature', 'pixel_value', 'roll_pixel']:
        if key in data:
            config.set('settings', key, str(data[key]))
        
    with open('config.cfg', 'w') as configfile:
        config.write(configfile)

    return {"status": "success"}

@app.route("/edit_rolls")
def edit_rolls():
    filename = request.args.get('file', '')
    try:
        file_path = get_safe_path(filename)
    except PermissionError:
        return "Access denied", 403

    students = []
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                for roll in sorted(data.keys(), key=lambda x: int(x) if x.isdigit() else x):
                    students.append({'roll': roll, 'name': data[roll]})
        except Exception as e:
            print(f"Error loading JSON: {e}")
            
    return render_template("rolls_editor.html", students=students, filename=filename)

@app.route("/save_rolls", methods=["POST"])
def save_rolls():
    data = request.json or {}
    filename = data.get('filename', '')
    try:
        file_path = get_safe_path(filename)
    except PermissionError:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    student_list = data.get('students', [])
    json_data = {str(s['roll']): s['name'] for s in student_list}
    
    try:
        with open(file_path, 'w') as f:
            json.dump(json_data, f, indent=4)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/sync_roll_github')
def sync_roll_github():
    if not GITHUB_TOKEN:
        return jsonify({"status": "error", "message": "GitHub token environment variable missing"}), 500

    filename = request.args.get('file', '')
    try:
        file_path = get_safe_path(filename)
    except PermissionError:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    OWNER = "Ashit-10"
    REPO = "PYTHON_OMR_APP"
    BRANCH = "main"
    
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    try:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")

        url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        
        get_res = requests.get(url, headers=headers)
        sha = get_res.json().get("sha") if get_res.status_code == 200 else None

        data = {
            "message": f"Update {filename} via OMR Server Dashboard",
            "content": content,
            "branch": BRANCH
        }
        if sha: data["sha"] = sha

        put_res = requests.put(url, headers=headers, json=data)
        if put_res.status_code in [200, 201]:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": put_res.json()}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/run_gitup')
def run_gitup():
    tution = request.args.get('tution', '')
    cls = request.args.get('class', '')
    sub = request.args.get('subject', '')

    def generate():
        process = subprocess.Popen(
            ['python3', 'gitup.py', tution, cls, sub],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=BASE
        )
        for line in process.stdout:
            yield line
        process.wait()

    return Response(generate(), mimetype='text/plain')

@app.route('/rename', methods=['POST'])
def rename():
    data = request.json or {}
    try:
        old_path = get_safe_path(data.get('old', ''))
        new_path = get_safe_path(data.get('new', ''))
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    if os.path.exists(new_path):
        return jsonify({"error": "File already exists"}), 409

    try:
        os.rename(old_path, new_path)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json or {}
    cls = re.sub(r'[^a-zA-Z0-9]', '-', data.get("class", "NA"))
    sub = re.sub(r'[^a-zA-Z0-9]', '-', data.get("subject", "NA"))
    counter = 1
    while True:
        folder_name = f"class-{cls}_{sub}_{counter}".lower()
        full_path = os.path.join(BASE, folder_name)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
            break
        counter += 1
    return jsonify(folders=get_project_folders())

@app.route('/run-recheck', methods=['POST'])
def trigger_recheck():
    try:
        script_path = os.path.join(BASE, "app.py")
        result = subprocess.run(["python3", "-u", script_path, "y"], check=True, capture_output=True, text=True)
        return jsonify({"message": "Success", "output": result.stdout}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/browse")
def browse():
    path = request.args.get("path", "")
    try:
        full_path = get_safe_path(path)
    except PermissionError:
        return "Access denied", 403

    items = []
    if os.path.exists(full_path) and os.path.isdir(full_path):
        for f in os.listdir(full_path):
            fp = os.path.join(full_path, f)
            mtime = os.path.getmtime(fp) if os.path.exists(fp) else 0
            items.append({"name": f, "is_dir": os.path.isdir(fp), "mtime": mtime})
    
    def sort_key(x):
        if x["is_dir"]: return (0, x["name"])
        m = re.search(r"(\d+)", x["name"])
        return (1, int(m.group(1)) if m else 999999)
        
    items.sort(key=sort_key)
    return render_template("browser.html", items=items, path=path)

@app.route("/file")
def get_file():
    try:
        target = get_safe_path(request.args.get("path", ""))
    except PermissionError:
        return "Access denied", 403
    return send_file(target) if os.path.exists(target) and os.path.isfile(target) else ("Not Found", 404)

@app.route("/delete", methods=["POST"])
def delete_item():
    data = request.json or {}
    try:
        path = get_safe_path(data.get("path", ""))
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    if os.path.isdir(path): 
        shutil.rmtree(path)
    elif os.path.exists(path): 
        os.remove(path)
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
    data = request.json or {}
    try:
        with open(os.path.join(BASE, "answer_key.txt"), "w") as f:
            f.write(data.get("content", ""))
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@app.route('/temp_output/<path:filename>')
def serve_output(filename):
    return send_from_directory(FINAL_OUTPUT_FOLDER, filename)

@app.route('/temp_input/<path:filename>')
def serve_input(filename):
    return send_from_directory(INPUT_FOLDER, filename)

# --- RESULTS HTML TEMPLATE ---
RESULTS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>OMR Result Viewer</title>
  <style>
    body { margin: 0; background: #121212; color: white; text-align: center; font-family: sans-serif; }
    #status { margin-top: 20px; font-size: 22px; }
    img { max-height: 75vh; width: auto; display: block; margin: 20px auto; border: 2px solid #333; border-radius: 8px; }
    #timestamp { font-size: 32px; font-weight: bold; color: #00ffcc; margin-top: 10px; }
    .btn { padding: 12px 24px; font-size: 16px; background: #5451f0; color: white; border: none; border-radius: 6px; cursor: pointer; }
  </style>
  <script>
    let activeTaskId = "";
    let lastInput = ""; let lastOutput = "";

    async function pollStatus() {
      try {
        const url = activeTaskId ? `/status?task_id=${activeTaskId}` : '/status';
        const response = await fetch(url);
        const data = await response.json();
        
        const statusDiv = document.getElementById("status");
        const imgTag = document.getElementById("result-img");
        const ts = document.getElementById("timestamp");

        if (data.input_filename && data.input_filename !== lastInput) {
            lastInput = data.input_filename;
            statusDiv.textContent = "🟡 Processing New Image...";
            imgTag.src = "/temp_input/" + data.input_filename + "?t=" + Date.now();
            imgTag.style.display = "block";
            ts.textContent = new Date().toLocaleTimeString();
        }

        if (!data.processing && data.filename && data.filename !== lastOutput) {
            lastOutput = data.filename;
            statusDiv.textContent = "✅ Processing Complete!";
            imgTag.src = "/temp_output/" + data.filename + "?t=" + Date.now();
        } else if (data.error) {
            statusDiv.textContent = "❌ " + (data.message || "OMR Analysis Failed");
        }
      } catch (err) { console.error(err); }
    }
    setInterval(pollStatus, 1200);
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
    port = int(os.environ.get("PORT", 7860))
    app.run(host='0.0.0.0', port=port, threaded=True)
