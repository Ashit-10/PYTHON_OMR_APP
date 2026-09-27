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
import base64
import uuid
import atexit
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import db
import telegram

# Configure logging to output to stdout for Koyeb terminal
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

import requests
from flask import (
    Flask, render_template, render_template_string, jsonify, 
    request, send_file, send_from_directory, Response, session, redirect, url_for
)

# --- ENVIRONMENT & CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

logger = logging.getLogger("omr")

def send_telegram_notification(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram bot token or chat ID not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        res = requests.post(url, json=payload, timeout=10)
        if not res.ok:
            logger.error(f"Telegram notification error ({res.status_code}): {res.text}")
    except Exception as e:
        logger.error(f"Telegram notification exception: {e}")

try:
    send_telegram_notification("Hi, I've been started")
except Exception as e:
    logger.error(f"Startup message error: {e}")

@atexit.register
def shutdown_notification():
    try:
        send_telegram_notification("I have been disabled")
    except Exception as e:
        logger.error(f"Shutdown message error: {e}")

# Connect to MongoDB and bootstrap it from the repo defaults if empty.
# init_db() raises when MONGO_URL is missing or unreachable, which is
# intentional: the container filesystem is ephemeral, so serving with
# on-disk-only state would silently lose data on the next redeploy.
try:
    db.init_db()
    if db.seed_from_disk(os.path.abspath(os.getcwd())):
        logger.info("Seeded MongoDB from on-disk defaults.")
    logger.info("MongoDB connected.")
except Exception as e:
    logger.error(f"Fatal: could not initialise MongoDB: {e}")
    try:
        send_telegram_notification(f"❌ Fatal: could not initialise MongoDB: {e}")
    except Exception:
        pass
    raise

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "omr_app_default_secret_key_12345")
APP_PASSWORD = os.environ.get("PASSWORD", "")

@app.before_request
def require_login():
    if not APP_PASSWORD:
        return
    allowed_endpoints = ['login', 'static', 'get_file', 'serve_output', 'serve_input', 'healthz']
    if request.endpoint in allowed_endpoints or request.path.startswith('/static') or request.path.startswith('/temp_output') or request.path.startswith('/temp_input'):
        return
    if session.get('authenticated') != True:
        return redirect(url_for('login'))

@app.route('/healthz')
def healthz():
    """Unauthenticated liveness probe, also used by the self-ping thread."""
    return jsonify(status="ok"), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not APP_PASSWORD:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        pwd = request.form.get('password', '')
        if pwd == APP_PASSWORD:
            session['authenticated'] = True
            app.logger.info("User successfully logged in.")
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid password. Please try again."
            app.logger.warning("Failed login attempt.")
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OMR Login</title>
<style>
    body { background: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
    .card { background: #1e293b; padding: 2.5rem; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); width: 100%; max-width: 380px; text-align: center; border: 1px solid #334155; }
    h2 { margin-bottom: 1.5rem; color: #38bdf8; font-size: 1.5rem; }
    input { width: 100%; padding: 12px 16px; margin-bottom: 1.2rem; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: white; font-size: 1rem; box-sizing: border-box; outline: none; transition: border-color 0.2s; }
    input:focus { border-color: #38bdf8; }
    button { width: 100%; padding: 12px; border-radius: 8px; border: none; background: #38bdf8; color: #0f172a; font-weight: bold; font-size: 1rem; cursor: pointer; transition: background 0.2s; }
    button:hover { background: #0ea5e9; }
    .error { color: #f87171; margin-bottom: 1rem; font-size: 0.9rem; background: rgba(248,113,113,0.1); padding: 8px; border-radius: 6px; }
</style>
</head>
<body>
<div class="card">
    <h2>🔐 OMR Scanner</h2>
    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}
    <form method="POST">
        <input type="password" name="password" placeholder="Enter Password" required autofocus>
        <button type="submit">Access Dashboard</button>
    </form>
</div>
</body>
</html>
"""

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

def set_task(task_id, **fields):
    task = dict(db.get_task(task_id) or {})
    task.update(fields)
    task.setdefault("input_filename", "")
    task.setdefault("output_filename", "")
    task.setdefault("error", "")
    return db.set_task(task_id, task)

def get_task(task_id):
    return db.get_task(task_id)

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
    """Folders known to MongoDB, plus any image folder present on disk.

    The disk half keeps folders visible on a fresh deploy before any folder
    metadata has been written; the Mongo half is what survives redeploys.
    """
    out = set(db.get_folders())
    if os.path.exists(BASE):
        for f in os.listdir(BASE):
            full_path = os.path.join(BASE, f)
            if os.path.isdir(full_path) and (f.startswith("class") or f in STATIC_FOLDERS):
                out.add(f)
    return sorted(out)

# --- TELEGRAM IMAGE STORAGE ---
def store_image(folder, filename, file_path=None):
    """Upload one image to Telegram and record it in MongoDB.

    Never raises: a failed upload must not fail the OMR scan that produced it.
    backfill_images() retries anything that is still missing.
    """
    if file_path is None:
        file_path = os.path.join(BASE, folder, filename)

    if not os.path.isfile(file_path):
        return None
    if not telegram.is_configured():
        logger.warning("Telegram not configured; skipping upload of %s/%s", folder, filename)
        return None

    meta = telegram.send_image(file_path, caption=f"{folder}/{filename}")
    if not meta:
        return None

    meta["mtime"] = os.path.getmtime(file_path)
    try:
        db.put_image(folder, filename, meta)
    except Exception as e:
        logger.error(f"Could not index {folder}/{filename} in MongoDB: {e}")
    logger.info("Stored %s/%s on Telegram (msg_id=%s)", folder, filename, meta["msg_id"])
    return meta

def store_folder_images(folder, limit=None):
    """Upload every image in a folder that is not already in MongoDB."""
    folder_path = os.path.join(BASE, folder)
    if not os.path.isdir(folder_path):
        return 0

    known = db.list_images(folder)
    stored = 0
    for name in sorted(os.listdir(folder_path)):
        if not name.lower().endswith(EXTENSIONS) or name in known:
            continue
        if store_image(folder, name):
            stored += 1
        if limit and stored >= limit:
            break
    return stored

def backfill_images():
    """Upload any on-disk image that is not yet recorded in MongoDB.

    Covers images that predate this change and repairs partial upload runs.
    """
    if not telegram.is_configured():
        return
    for folder in [f for f in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, f))]:
        try:
            count = store_folder_images(folder)
            if count:
                logger.info("Backfilled %d image(s) from %s", count, folder)
        except Exception as e:
            logger.error(f"Backfill failed for {folder}: {e}")

def fetch_image_from_telegram(folder, filename, dest_path):
    """Re-download an image from Telegram into the local cache."""
    meta = db.get_image(folder, filename)
    if not meta or not meta.get("file_id"):
        return False

    if telegram.download(meta["file_id"], dest_path):
        return True

    # A dead file_id would otherwise serve a broken image forever.
    logger.warning("Dropping unreachable Telegram entry %s/%s", folder, filename)
    db.remove_image(folder, filename)
    return False

# --- BACKGROUND TASK WORKER ---
def process_omr_task(task_id, input_filepath, original_filename):
    """Executes autoapp.py asynchronously without blocking Flask."""
    try:
        set_task(task_id, status="processing")
        
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

            # Persist the result and its input copy to Telegram.
            executor.submit(store_image, "output", newest_file, dest_path)
            if original_filename:
                executor.submit(
                    store_image, "input", original_filename,
                    os.path.join(INPUT_FOLDER, original_filename)
                )

            set_task(task_id, status="completed", output_filename=newest_file)
        else:
            set_task(task_id, status="failed", error=stderr.decode() if stderr else "No output file produced by OMR engine.")

    except Exception as e:
        set_task(task_id, status="failed", error=str(e))

# --- ROUTES ---

@app.route("/")
def dashboard():
    # Rolls now live in MongoDB, so list them from there rather than from disk.
    # list_rolls_names() already returns names without the "rolls:" prefix.
    rolls_files = sorted(name + ".txt" for name in db.list_rolls_names())
    folders = get_project_folders()
    
    folder_counts = {}
    for folder in folders:
        folder_path = os.path.join(BASE, folder)
        if os.path.isdir(folder_path):
            count = len([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and not f.startswith('.')])
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

    # Persist the original immediately, so the sheet survives even if the scan
    # itself fails.
    executor.submit(store_image, "temp_input", filename, input_filepath)

    task_id = str(uuid.uuid4())
    set_task(task_id, status="queued", input_filename=filename)

    executor.submit(process_omr_task, task_id, input_filepath, filename)
    return jsonify({"message": "OK", "task_id": task_id, "filename": filename})

@app.route('/status')
def status():
    task_id = request.args.get('task_id')
    t = get_task(task_id) if task_id else None
    if t is None:
        # Fallback to returning the most recent task
        all_tasks = db.all_tasks()
        t = all_tasks[list(all_tasks)[-1]] if all_tasks else None

    if t:
        return jsonify({
            "processing": t.get("status") in ["queued", "processing"],
            "status": t.get("status", ""),
            "filename": t.get("output_filename", ""),
            "input_filename": t.get("input_filename", ""),
            "error": t.get("status") == "failed",
            "message": t.get("error", "")
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
            # Drop the MongoDB index too, otherwise the images would still be
            # listed (and restorable from Telegram) after being cleared.
            db.remove_images_in_folder(folder)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_config')
def get_config():
    config = db.get_settings()
    return {
        "pixel_value": config.get('pixel_value', '200'),
        "signature": config.get('signature', ''),
        "roll_pixel": config.get('roll_pixel', '200')
    }

@app.route('/update_config', methods=['POST'])
def update_config():
    data = request.get_json() or {}
    patch = {k: str(data[k]) for k in ['signature', 'pixel_value', 'roll_pixel'] if k in data}
    db.set_settings(patch)
    return {"status": "success"}

def rolls_name(raw):
    """Validate a rolls filename and normalise it to the Mongo key suffix.

    Rolls are stored under "rolls:<name>" without the .txt extension, which is
    also how gitup.py and the dashboard refer to them.
    """
    name = raw or ''
    if not name or name != os.path.basename(name) or '/' in name or '\\' in name:
        raise PermissionError("Access denied")
    if name.endswith(".txt"):
        name = name[: -len(".txt")]
    if not name:
        raise PermissionError("Access denied")
    return name

@app.route("/edit_rolls")
def edit_rolls():
    filename = request.args.get('file', '')
    try:
        name = rolls_name(filename)
    except PermissionError:
        return "Access denied", 403

    students = []
    try:
        data = db.get_rolls(name)
        for roll in sorted(data.keys(), key=lambda x: int(x) if str(x).isdigit() else x):
            students.append({'roll': roll, 'name': data[roll]})
    except Exception as e:
        print(f"Error loading rolls: {e}")

    return render_template("rolls_editor.html", students=students, filename=filename)

@app.route("/save_rolls", methods=["POST"])
def save_rolls():
    data = request.json or {}
    filename = data.get('filename', '')
    try:
        name = rolls_name(filename)
    except PermissionError:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    student_list = data.get('students', [])
    json_data = {str(s['roll']): s['name'] for s in student_list}

    try:
        db.set_rolls(name, json_data)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/sync_roll_github')
def sync_roll_github():
    if not GITHUB_TOKEN:
        return jsonify({"status": "error", "message": "GitHub token environment variable missing"}), 500

    filename = request.args.get('file', '')
    try:
        name = rolls_name(filename)
    except PermissionError:
        return jsonify({"status": "error", "message": "Access denied"}), 403

    OWNER = "Ashit-10"
    REPO = "PYTHON_OMR_APP"
    BRANCH = "main"
    
    data = db.get_rolls(name)
    if not data:
        return jsonify({"status": "error", "message": "No rolls data found"}), 404

    try:
        content = base64.b64encode(json.dumps(data, indent=4).encode("utf-8")).decode("utf-8")

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
    existing = set(get_project_folders())
    counter = 1
    while True:
        folder_name = f"class-{cls}_{sub}_{counter}".lower()
        full_path = os.path.join(BASE, folder_name)
        if folder_name not in existing and not os.path.exists(full_path):
            os.makedirs(full_path, exist_ok=True)
            break
        counter += 1
    db.add_folder(folder_name)
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
    seen = set()
    if os.path.exists(full_path) and os.path.isdir(full_path):
        for f in os.listdir(full_path):
            if f.startswith('.'):
                continue
            fp = os.path.join(full_path, f)
            mtime = os.path.getmtime(fp) if os.path.exists(fp) else 0
            items.append({"name": f, "is_dir": os.path.isdir(fp), "mtime": mtime})
            seen.add(f)

    # Images held in Telegram are absent from a fresh container, so merge in
    # the MongoDB index to keep the folder listing complete after a redeploy.
    for name, meta in db.list_images(path).items():
        if name in seen or name.startswith('.'):
            continue
        items.append({"name": name, "is_dir": False, "mtime": meta.get("mtime", 0)})

    def sort_key(x):
        if x["is_dir"]: return (0, x["name"])
        m = re.search(r"(\d+)", x["name"])
        return (1, int(m.group(1)) if m else 999999)
        
    items.sort(key=sort_key)
    return render_template("browser.html", items=items, path=path)

@app.route("/file")
def get_file():
    raw = request.args.get("path", "")
    try:
        target = get_safe_path(raw)
    except PermissionError:
        return "Access denied", 403

    if os.path.exists(target) and os.path.isfile(target):
        return send_file(target)

    # Not on this container: restore it from Telegram. The first view after a
    # redeploy pays the download; after that it is served from local cache.
    folder, _, name = raw.rpartition("/")
    if folder and fetch_image_from_telegram(folder, name, target):
        return send_file(target)

    return "Not Found", 404

@app.route("/delete", methods=["POST"])
def delete_item():
    """Forget an item: drop its MongoDB entry and its local cache file.

    Nothing is ever removed from Telegram - the bytes stay there, only the
    pointer is dropped. The local file must go too, otherwise /browse would
    keep listing it from disk and the delete would look like a no-op.
    """
    data = request.json or {}
    raw = data.get("path", "")
    try:
        path = get_safe_path(raw)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    folder, _, name = raw.rpartition("/")
    if name in db.get_folders():
        db.remove_folder(name)
        db.remove_images_in_folder(name)
    elif name.lower().endswith(EXTENSIONS):
        db.remove_image(folder, name)
    elif name.endswith("_rolls.txt"):
        db.delete(db.ROLLS_PREFIX + name[: -len(".txt")])
    elif name == "answer_key.txt":
        db.delete(db.ANSWER_KEY)
    elif name == "config.cfg":
        db.set(db.SETTINGS_KEY, db.DEFAULT_SETTINGS)

    # Drop the local cache copy so it stops being listed and served.
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.warning(f"Could not remove local cache {raw}: {e}")

    return jsonify(ok=True)

@app.route("/answer_key")
def answer_key_route():
    content = db.get(db.ANSWER_KEY) or {}
    if not isinstance(content, str):
        content = json.dumps(content, indent=2)
    return render_template("50.html", content=content, folder=".")

@app.route("/save_answer_key", methods=['POST'])
def save_key():
    data = request.json or {}
    try:
        db.set(db.ANSWER_KEY, data.get("content", ""))
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

# --- SELF-PING (keeps the free instance awake) ---
SELF_PING_URL = os.environ.get("SELF_PING_URL", "").strip()
SELF_PING_INTERVAL = int(os.environ.get("SELF_PING_INTERVAL", "300"))

def _start_self_ping():
    """Hit our own URL periodically so the host does not sleep the instance.

    Uses a plain daemon thread rather than APScheduler: this is one fixed
    interval, so a scheduler would be a dependency with no benefit.
    """
    if not SELF_PING_URL:
        return

    def loop():
        while True:
            time.sleep(SELF_PING_INTERVAL)
            try:
                requests.get(SELF_PING_URL, timeout=15)
            except Exception:
                pass  # a missed ping is not worth crashing over

    threading.Thread(target=loop, daemon=True, name="self-ping").start()
    logger.info("Self-ping every %ds -> %s", SELF_PING_INTERVAL, SELF_PING_URL)

# The gunicorn CMD imports this module, so start it here rather than in
# __main__ (which only runs under `python3 run_web.py`).
if os.environ.get("DISABLE_SELF_PING", "").lower() not in ("1", "true", "yes"):
    _start_self_ping()

if __name__ == '__main__':
    # Images are uploaded to Telegram automatically, so catch up on anything
    # that never made it (pre-existing files, previously failed uploads).
    if telegram.is_configured():
        executor.submit(backfill_images)
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port, threaded=True)
