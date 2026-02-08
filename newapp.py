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
# Add this to track if the current scan has a finished result
scan_ready = False 



# --- OMR BACKGROUND PROCESSING ---
def open_chrome():
    os.system("am start -n com.android.chrome/com.google.android.apps.chrome.Main -a android.intent.action.VIEW -d https://127.0.0.1:7860")


def move_and_process(file_path):
    global processing, current_filename, latest_output_filename, error_occurred, scan_ready
    
    # Reset states for the new scan
    processing = True
    scan_ready = False
    error_occurred = False
    latest_output_filename = "" # Clear old filename so UI doesn't grab it

    # Ensure directories exist
    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs("output", exist_ok=True)

    # 1. CLEANUP: Remove old files so the system doesn't get confused by previous results
    for folder in [input_folder, output_folder]:
        for f in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, f))
            except:
                pass

    # 2. PREPARE INPUT: Move the uploaded file into the temp_input folder
    current_filename = os.path.basename(file_path)
    try:
        shutil.move(file_path, os.path.join(input_folder, current_filename))
    except Exception as e:
        print(f"Move Error: {e}")
        error_occurred = True
        processing = False
        return

    # 3. RUN OMR: Trigger the autoapp.py worker
    print(f"Starting OMR analysis for: {current_filename}")
    process = subprocess.Popen(["python3", "autoapp.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    if stdout: print(f"Worker Output: {stdout.decode()}")
    if stderr: print(f"Worker Error: {stderr.decode()}", file=sys.stderr)

    # 4. IDENTIFY OUTPUT: Check if autoapp.py actually produced a result image
    files = [f for f in os.listdir(output_folder) if f.lower().endswith(extensions)]
    
    if files:
        # Sort by time to get the absolute newest result
        files.sort(key=lambda x: os.path.getmtime(os.path.join(output_folder, x)))
        newest_file = files[-1]
        
        src_path = os.path.join(output_folder, newest_file)
        dest_path = os.path.join("output", newest_file)
        
        # Prevent filename collisions in the permanent 'output' folder
        if os.path.exists(dest_path):
            name_part, ext_part = os.path.splitext(newest_file)
            count = 1
            while os.path.exists(os.path.join("output", f"{name_part}_{count}{ext_part}")):
                count += 1
            newest_file = f"{name_part}_{count}{ext_part}"
            dest_path = os.path.join("output", newest_file)
        
        # Finalize the result
        shutil.copy(src_path, dest_path)
        latest_output_filename = newest_file
        scan_ready = True
        error_occurred = False
     #   print(f"Success! Result saved as: {latest_output_filename}")
    else:
        # ROOT FAILURE: autoapp.py finished but the output folder is empty
        latest_output_filename = ""
        scan_ready = False
        error_occurred = True
      #  print("!! ROOT FAILURE: autoapp.py finished but no output image was found !!")

    # Final state: processing is done
    processing = False



def watch_folder():
    """Background loop for file automation."""
    while True:
        try:
            # 1. Sync Answer Keys
            for f in glob.glob(os.path.join(download_folder, '*ans*_key*.txt*')):
                try:
                    dest = os.path.join(BASE, os.path.basename(f))
                    if not os.path.exists(dest):
                        shutil.move(f, dest)
                        print(f"Moved answer key: {f}")
                except: pass

            # 2. Sync OMR Scans
            # Check 'processing' flag so we don't interfere with the Camera UI
            if not processing:
                files = [f for f in os.listdir(download_folder) if f.startswith("OMR_") and f.endswith(extensions)]
                for f in files:
                    path = os.path.join(download_folder, f)
                    
                    # CRITICAL: Check if file exists before trying to move it
                    # This prevents the crash if /upload already moved the file
                    if os.path.exists(path):
                        print(f"Background worker processing: {f}")
                        move_and_process(path)
        
        except Exception as e:
            # This prevents the thread from dying if an error occurs
            print(f"Watch folder loop error: {e}")

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


import configparser

@app.route('/clear_project_folders', methods=['POST'])
def clear_project_folders():
    target_folders = ['input', 'output', 'error_images', 'duplicates']
    try:
        for folder in target_folders:
            folder_path = os.path.join(os.getcwd(), folder) # Adjust path as needed
            if os.path.exists(folder_path):
                for filename in os.listdir(folder_path):
                    file_path = os.path.join(folder_path, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f'Failed to delete {file_path}. Reason: {e}')
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_config')
def get_config():
    config = configparser.ConfigParser()
    config.read('config.cfg')
    
    # Extract values from the [settings] section
    pixel = config.get('settings', 'pixel_value', fallback='200')
    sign = config.get('settings', 'signature', fallback='')
    
    return {
        "pixel_value": pixel,
        "signature": sign
    }

@app.route('/update_config', methods=['POST'])
def update_config():
    data = request.get_json()
    config = configparser.ConfigParser()
    config.read('config.cfg')

    # Ensure the [settings] section exists
    if not config.has_section('settings'):
        config.add_section('settings')

    # Check which value is being sent and update it
    if 'signature' in data:
        config.set('settings', 'signature', data['signature'])
    
    if 'pixel_value' in data:
        config.set('settings', 'pixel_value', str(data['pixel_value']))

    # Save the changes back to the file
    with open('config.cfg', 'w') as configfile:
        config.write(configfile)

    return {"status": "success"}

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

@app.route("/update_config2", methods=["POST"])
def update_config2():
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
    all_files = os.listdir(BASE)
    rolls_files = [f for f in all_files if f.endswith('_rolls.txt')]
    
    # Get the list of project folders
    folders = get_project_folders()
    
    # Calculate file counts for each folder
    folder_counts = {}
    for folder in folders:
        folder_path = os.path.join(BASE, folder)
        if os.path.isdir(folder_path):
            # Counts only files, ignoring sub-folders
            count = len([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])
            folder_counts[folder] = count
        else:
            folder_counts[folder] = 0

    return render_template("index.html", 
                           folders=folders, 
                           folder_counts=folder_counts, # Pass the dictionary here
                           rolls_files=rolls_files)


import subprocess

import base64
import requests

@app.route('/sync_roll_github')
def sync_roll_github():
    filename = request.args.get('file')
    file_path = os.path.join(BASE, filename)

    # --- CONFIGURATION ---
    TOKEN = "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"
    OWNER = "Ashit-10"
    REPO = "PYTHON_OMR_APP"
    BRANCH = "main" # or 'master'
    
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    try:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")

        # 1. Get the file SHA (required by GitHub to update existing files)
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{filename}"
        headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
        
        get_res = requests.get(url, headers=headers)
        sha = get_res.json().get("sha") if get_res.status_code == 200 else None

        # 2. Upload/Update the file
        data = {
            "message": f"Update {filename} via OMR Dashboard",
            "content": content,
            "branch": BRANCH
        }
        if sha: data["sha"] = sha

        put_res = requests.put(url, headers=headers, json=data)
        
        if put_res.status_code in [200, 201]:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": put_res.json()}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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

@app.route('/rename', methods=['POST'])
def rename():
    data = request.json
    old_path = data.get('old')
    new_path = data.get('new')

    # 1. Check if the target filename already exists
    if os.path.exists(new_path):
        # Return 409 Conflict status
        return jsonify({"error": "File already exists"}), 409

    try:
        os.rename(old_path, new_path)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    
    # We set processing to True immediately to tell the UI to wait
    processing = True 
    
    roll = request.form.get('roll', '').strip()
    timestamp = int(time.time())

    if roll:
        current_filename = f"OMR_sheet_roll_{roll}_{timestamp}.jpg"
    else:
        current_filename = f"OMR_sheet_{timestamp}.jpg"
    
    path = os.path.join(download_folder, current_filename)
    file.save(path)
    
    # Trigger the background process immediately in a new thread
    threading.Thread(target=move_and_process, args=(path,)).start()
    
    return jsonify({"message": "OK", "filename": current_filename})

@app.route('/status')
def status():
    return jsonify({
        "processing": processing,
        "filename": latest_output_filename if scan_ready else "",
        "input_filename": current_filename,
        "error": error_occurred,  # Sends 'true' if the root step failed
        "message": "OMR Analysis Failed" if error_occurred else ""
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





@app.route('/run-recheck', methods=['POST'])
def trigger_recheck():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "app.py")

        # .run() waits for the script to finish
        # You can add your arguments inside the list here
        result = subprocess.run(["python", "-u", script_path, "y"], check=True)
        
        if result.returncode == 0:
            return jsonify({"message": "Success"}), 200
        else:
            return jsonify({"error": result.stderr}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/browse")
def browse():
    path = request.args.get("path")
    full_path = os.path.join(BASE, path)
    items = []
    if os.path.exists(full_path):
        for f in os.listdir(full_path):
            fp = os.path.join(full_path, f)
            # Get modification time (mtime)
            mtime = os.path.getmtime(fp) if os.path.exists(fp) else 0
            items.append({
                "name": f, 
                "is_dir": os.path.isdir(fp),
                "mtime": mtime  # Added this line
            })
    
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

# if __name__ == '__main__':
#    threading.Thread(target=watch_folder, daemon=True).start()
#    threading.Timer(0.1, open_chrome).start()
#    app.run(host='0.0.0.0', port=7860, ssl_context=('certs/cert.pem', 'certs/key.pem'), threaded=True)



def kill_port_process(port):
    try:
        # Finds the Process ID (PID) using the specified port
        # -t: silent/terse mode, -k: kill (we'll do it manually for safety)
        pid = subprocess.check_output(["lsof", "-t", f"-i:{port}"]).decode().strip()
        
        if pid:
            print(f"Port {port} is in use by PID {pid}. Terminating...")
            # Convert string of PIDs (if multiple) to integers and kill them
            for p in pid.split('\n'):
                os.kill(int(p), signal.SIGKILL)
            
            # Give the OS a split second to actually release the socket
            time.sleep(1) 
    except subprocess.CalledProcessError:
        # This error triggers if lsof finds nothing, which means port is free
        pass
    except Exception as e:
        print(f"Error clearing port: {e}")

if __name__ == '__main__':
    PORT = 7860
    
    # 1. Clear the port first
    kill_port_process(PORT)
    
    # 2. Start your threads
    threading.Thread(target=watch_folder, daemon=True).start()
    threading.Timer(0.1, open_chrome).start()
    
    # 3. Run app
    app.run(host='0.0.0.0', port=PORT, ssl_context=('certs/cert.pem', 'certs/key.pem'), threaded=True)
