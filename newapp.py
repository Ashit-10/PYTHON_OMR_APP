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

# --- LOGGING FILTER ---
class FilterRequests(logging.Filter):
    def filter(self, record):
        return "GET /" not in record.getMessage() and "POST /" not in record.getMessage()

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)
log.addFilter(FilterRequests())

# --- CONFIGURATION & GLOBALS ---
app = Flask(__name__)
BASE = os.getcwd()
download_folder = "/sdcard/Download"
input_folder = "temp_input"
output_folder = "temp_output"
extensions = ('.jpg', '.jpeg', '.png')
STATIC_FOLDERS = ["input", "output", "duplicates", "error_images", "temp_input", "temp_output"]

processing = False
current_filename = ""
latest_output_filename = ""
error_occurred = False

# --- OMR PROCESSING LOGIC (From Old App) ---

def move_and_process(file_path):
    global processing, current_filename, latest_output_filename, error_occurred
    processing = True
    error_occurred = False

    for folder in [input_folder, output_folder, "output"]:
        os.makedirs(folder, exist_ok=True)

    # Clean temp folders for new scan
    shutil.rmtree(input_folder, ignore_errors=True)
    shutil.rmtree(output_folder, ignore_errors=True)
    os.makedirs(input_folder)
    os.makedirs(output_folder)

    current_filename = os.path.basename(file_path)
    shutil.move(file_path, os.path.join(input_folder, current_filename))

    # Run the OMR core
    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    files = [f for f in os.listdir(output_folder) if f.endswith(extensions)]
    if files:
        latest_output_filename = files[-1]
        src_path = os.path.join(output_folder, latest_output_filename)
        dest_path = os.path.join("output", latest_output_filename)
        shutil.copy(src_path, dest_path)
    
    processing = False

def watch_folder():
    """Background thread to watch for new images and answer keys."""
    while True:
        # Move answer keys from Download to project root
        for f in glob.glob(os.path.join(download_folder, '*ans*_key*.txt*')):
            try:
                shutil.move(f, os.path.join(BASE, os.path.basename(f)))
            except: pass

        # Watch for OMR images
        files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.endswith(extensions)]
        for f in files:
            path = os.path.join(download_folder, f)
            move_and_process(path)
        time.sleep(1)

# --- FILE MANAGER LOGIC (From New App) ---

def get_project_folders():
    out = []
    if not os.path.exists(BASE): return out
    for f in os.listdir(BASE):
        full_path = os.path.join(BASE, f)
        if os.path.isdir(full_path) and (f.startswith("class") or f in STATIC_FOLDERS):
            out.append(f)
    return sorted(out)

# --- ROUTES ---

@app.route("/")
def index():
    """The main Dashboard."""
    return render_template("index.html", folders=get_project_folders())

@app.route("/scan_page")
def scan_page():
    """The Camera/Scanning UI."""
    with open("camera_ui.html") as f:
        return f.read()

@app.route("/results")
def results():
    """The old results viewing page."""
    # Note: Use the HTML string from your original app.py results() function
    return render_template_string(RESULTS_HTML_STRING) # Defined below

@app.route('/status')
def status():
    return jsonify({
        "processing": processing,
        "filename": latest_output_filename,
        "input_filename": current_filename
    })

@app.route('/upload', methods=['POST'])
def upload():
    global current_filename
    file = request.files['image']
    current_filename = f"OMR_{int(time.time())}.jpg"
    path = os.path.join(download_folder, current_filename)
    file.save(path)
    return jsonify({"message": "OK"})

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
def file():
    target = os.path.join(BASE, request.args.get("path", ""))
    return send_file(target) if os.path.exists(target) else ("Not Found", 404)

@app.route("/answer_key")
def answer_key():
    file_path = os.path.join(BASE, "answer_key.txt")
    content = ""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()
    return render_template("50.html", content=content, folder=".")

@app.route("/save_answer_key", methods=["POST"])
def save_answer_key():
    data = request.json
    try:
        with open(os.path.join(BASE, "answer_key.txt"), "w") as f:
            f.write(data.get("content"))
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# Helper routes for images
@app.route('/temp_output/<path:filename>')
def get_output(filename):
    return send_from_directory("output", filename)

@app.route('/temp_input/<path:filename>')
def get_input(filename):
    return send_from_directory("temp_input", filename)

# Put your massive HTML string for the results page here
RESULTS_HTML_STRING = """... (Copy the HTML from Old App Results function) ..."""

if __name__ == '__main__':
    threading.Thread(target=watch_folder, daemon=True).start()
    # Port 7860 to match your old setup
    app.run(host='0.0.0.0', port=7860, ssl_context=('certs/cert.pem', 'certs/key.pem'), threaded=True)
