import os
import sys
import time
import shutil
import subprocess
import threading
import re
import json
import logging
import base64
import uuid
import atexit
import fcntl
import tempfile
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor

import db
import telegram

try:  # Pillow is optional; without it /thumb falls back to the full image.
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 50_000_000
except ImportError:  # pragma: no cover - exercised only on minimal installs
    Image = None

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

# Images are uploaded in batches by a background worker. The UI never waits
# for Telegram, and the free instance no longer spends CPU on TLS during the
# OpenCV scan.
SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL", "1800"))
SYNC_ON_START = os.environ.get("SYNC_ON_START", "1").lower() not in ("0", "false", "no")
RESTORE_ON_BOOT = os.environ.get("RESTORE_ON_BOOT", "1").lower() not in ("0", "false", "no")
SCAN_TIMEOUT = int(os.environ.get("SCAN_TIMEOUT", "180"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))

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


def claim_boot_side_effects():
    """Return True in exactly one process per container.

    Gunicorn imports this module in every worker, so unguarded boot work
    (Telegram pings, reconciling uploads left over from the previous deploy)
    would run once per worker. An exclusive file lock gives a single winner
    across processes without extra infrastructure; the lock is held for the
    life of the process by keeping the descriptor open.
    """
    if os.environ.get("DISABLE_SINGLETON_BOOT"):
        return True

    path = os.path.join(tempfile.gettempdir(), "omr_boot.lock")
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        logger.warning("Could not open boot lock %s: %s", path, e)
        return True

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Another worker already claimed it.
        os.close(fd)
        return False

    # Keep the descriptor open for the process lifetime so the lock persists.
    global _BOOT_LOCK_FD
    _BOOT_LOCK_FD = fd
    return True


@atexit.register
def shutdown_notification():
    if not globals().get("IS_PRIMARY_WORKER"):
        return
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

# One process per container runs the boot side effects. Every worker must
# still reach this point, so only the guarded work is skipped elsewhere.
IS_PRIMARY_WORKER = claim_boot_side_effects()

if IS_PRIMARY_WORKER:
    try:
        stats = db.startup_maintenance()
        logger.info("Startup maintenance: %s", stats)
    except Exception as e:
        logger.error(f"Startup maintenance failed: {e}")

    try:
        send_telegram_notification("Hi, I've been started")
    except Exception as e:
        logger.error(f"Startup message error: {e}")
else:
    logger.info("Secondary worker; skipping boot side effects.")

app = Flask(__name__)
APP_PASSWORD = os.environ.get("PASSWORD", "")
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    # Deterministic across gunicorn workers, unlike a random per-process key,
    # and not the old public default that allowed session forgery. Set
    # SECRET_KEY explicitly to decouple it from the database URL.
    _secret = hashlib.sha256(
        f"{APP_PASSWORD}|{os.environ.get('MONGO_URL', '')}|omr-session".encode("utf-8")
    ).hexdigest()
    logger.warning("SECRET_KEY is not set; deriving one from PASSWORD and MONGO_URL.")
app.secret_key = _secret
app.config.update(
    MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
)

@app.before_request
def require_login():
    if not APP_PASSWORD:
        return
    # Only the login page, static assets and the liveness probe are reachable
    # without a session. Image routes used to be whitelisted here, which made
    # every answer sheet world-readable to anyone who could guess a filename.
    allowed_endpoints = {'login', 'static', 'healthz'}
    if request.endpoint in allowed_endpoints or request.path.startswith('/static'):
        return
    if session.get('authenticated') != True:
        return redirect(url_for('login'))

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": f"Image is larger than {MAX_UPLOAD_MB} MB."}), 413


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
        if hmac.compare_digest(pwd, APP_PASSWORD):
            session.clear()
            session['authenticated'] = True
            app.logger.info("User successfully logged in.")
            return redirect(url_for('dashboard'))
        else:
            # Small fixed delay blunts trivial online guessing without adding
            # a dependency or per-IP state.
            time.sleep(0.4)
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
THUMB_FOLDER = os.path.join(BASE, "thumbnails")
EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
STATIC_FOLDERS = ["input", "output", "duplicates", "error_images"]
MANAGED_CONFIG_FILES = {"answer_key.txt", "config.cfg"}

# Ensure essential directories exist
for folder in [INPUT_FOLDER, OUTPUT_FOLDER, FINAL_OUTPUT_FOLDER, THUMB_FOLDER] + [os.path.join(BASE, f) for f in STATIC_FOLDERS]:
    os.makedirs(folder, exist_ok=True)

# Answer key + settings cache. Every scan needs both; reading them from Atlas
# for every sheet was one of the largest sources of latency.
_config_cache = {"value": None, "expires": 0.0}
_config_lock = threading.Lock()
CONFIG_CACHE_TTL = float(os.environ.get("CONFIG_CACHE_TTL", "60"))


def invalidate_scan_config():
    with _config_lock:
        _config_cache["value"] = None
        _config_cache["expires"] = 0.0
    db.invalidate_settings()


def get_scan_config(force=False):
    """Return {"answer_key", "settings"} once per TTL instead of per scan."""
    now = time.time()
    with _config_lock:
        cached = _config_cache["value"]
        if not force and cached is not None and _config_cache["expires"] > now:
            return cached
        answer_key = db.get(db.ANSWER_KEY)
        settings = db.get_settings()
        value = {"answer_key": answer_key, "settings": settings}
        _config_cache["value"] = value
        _config_cache["expires"] = now + CONFIG_CACHE_TTL
        return value

# Keep CPU-bound scans separate from network-bound Telegram uploads. A slow
# upload/retry must not occupy every worker and leave new scans queued.
scan_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omr-scan")
image_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="omr-image")

def set_task(task_id, **fields):
    """Update one task without reading it first (halves Atlas round trips)."""
    defaults = {
        "input_filename": "",
        "output_filename": "",
        "error": "",
        "status": "queued",
    }
    return db.update_task(task_id, fields, defaults=defaults)

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
    """Resolve a user path and prove it is inside BASE.

    startswith() was not enough: /workspace and /workspace_evil share a prefix,
    so "../workspace_evil/x" passed. realpath also blocks symlink escapes.
    """
    if not req_path:
        return BASE
    normalized = str(req_path).replace("\\", "/").lstrip("/")
    target = os.path.realpath(os.path.join(BASE, normalized))
    root = os.path.realpath(BASE)
    try:
        inside = os.path.commonpath([root, target]) == root
    except ValueError:
        inside = False
    if not inside:
        raise PermissionError("Access denied: Path outside root directory.")
    return target


def is_managed_path(raw):
    """True for paths the UI is allowed to delete or rename."""
    if not raw:
        return False
    normalized = str(raw).replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("."):
        return False
    parts = normalized.split("/")
    first = parts[0]
    if first in STATIC_FOLDERS or first in get_project_folders():
        return True
    return len(parts) == 1 and (first in MANAGED_CONFIG_FILES or first.endswith("_rolls.txt"))

_folders_cache = {"value": None, "expires": 0.0}
FOLDERS_CACHE_TTL = float(os.environ.get("FOLDERS_CACHE_TTL", "30"))


def invalidate_folders():
    _folders_cache["value"] = None
    _folders_cache["expires"] = 0.0


def get_project_folders(force=False):
    """Folders known to MongoDB, plus any image folder present on disk.

    The disk half keeps folders visible on a fresh deploy before any folder
    metadata has been written; the Mongo half is what survives redeploys.
    Cached briefly because every thumbnail request checks this list.
    """
    now = time.time()
    if not force and _folders_cache["value"] is not None and _folders_cache["expires"] > now:
        return _folders_cache["value"]
    out = set(db.get_folders())
    if os.path.exists(BASE):
        for f in os.listdir(BASE):
            full_path = os.path.join(BASE, f)
            if os.path.isdir(full_path) and (f.startswith("class") or f in STATIC_FOLDERS):
                out.add(f)
    value = sorted(out)
    _folders_cache["value"] = value
    _folders_cache["expires"] = now + FOLDERS_CACHE_TTL
    return value

# --- LOCAL IMAGE CACHE / THUMBNAILS ---
def is_servable_image(raw):
    """Only image files inside managed folders may be streamed.

    /file previously accepted any path under BASE, which made .env, the Flask
    source and certs/key.pem downloadable by anyone with a login. Keep the
    image routes broad enough for temp uploads and class folders, but never
    serve arbitrary repository files.
    """
    if not raw:
        return False
    normalized = str(raw).replace("\\", "/").strip("/")
    if not normalized or ".." in normalized.split("/"):
        return False
    parts = normalized.split("/")
    first = parts[0]
    if first not in STATIC_FOLDERS and first not in ("temp_input", "temp_output"):
        try:
            if first not in get_project_folders():
                return False
        except Exception:
            return False
    return parts[-1].lower().endswith(EXTENSIONS)


def thumb_path_for(folder, filename):
    digest = hashlib.sha1(f"{folder}/{filename}".encode("utf-8")).hexdigest()
    return os.path.join(THUMB_FOLDER, digest + ".jpg")


def make_thumbnail(source, folder, filename):
    """Create a small listing image. Missing Pillow is not fatal: /thumb will
    simply serve the original file."""
    if Image is None:
        return None
    dest = thumb_path_for(folder, filename)
    try:
        if os.path.exists(dest) and os.path.getmtime(dest) >= os.path.getmtime(source):
            return dest
        os.makedirs(THUMB_FOLDER, exist_ok=True)
        with Image.open(source) as img:
            img = img.convert("RGB")
            img.thumbnail((420, 420), Image.Resampling.LANCZOS)
            img.save(dest, "JPEG", quality=78, optimize=True)
        return dest
    except Exception as e:
        logger.debug("Could not thumbnail %s/%s: %s", folder, filename, e)
        return None


def queue_image(folder, filename, file_path=None):
    """Record an image for the next Telegram batch and build its thumbnail."""
    if file_path is None:
        file_path = os.path.join(BASE, folder, filename)
    if not os.path.isfile(file_path):
        return None
    make_thumbnail(file_path, folder, filename)
    try:
        return db.queue_upload(folder, filename, file_path)
    except Exception as e:
        logger.error("Could not queue %s/%s: %s", folder, filename, e)
        return None


# --- TELEGRAM IMAGE STORAGE ---
# Batching means a scan queues its images instantly and the network work is
# done later by the sync worker. Lower retry counts keep a bad batch from
# occupying the worker for minutes.
UPLOAD_ATTEMPTS = int(os.environ.get("UPLOAD_ATTEMPTS", "2"))
UPLOAD_RETRY_DELAY = int(os.environ.get("UPLOAD_RETRY_DELAY", "2"))
_sync_lock = threading.Lock()
# Set while OpenCV is running. Telegram traffic is deliberately paused then so
# background downloads/uploads cannot steal CPU/TLS time from a live scan.
_scan_busy = threading.Event()


def _wait_for_scan_idle():
    while _scan_busy.is_set():
        time.sleep(0.25)


def store_image(folder, filename, file_path=None, _attempts=None):
    """Upload one image to Telegram and index it in MongoDB.

    Retries a few times, then records the failure in the upload queue so a
    later attempt (or the next deploy) can pick it up. Never raises: a failed
    upload must not fail the OMR scan that produced it.
    """
    if _attempts is None:
        _attempts = UPLOAD_ATTEMPTS

    if file_path is None:
        file_path = os.path.join(BASE, folder, filename)

    if not os.path.isfile(file_path):
        logger.warning("Cannot store %s/%s: %s is missing", folder, filename, file_path)
        return None
    if not telegram.is_configured():
        logger.warning("Telegram not configured; queueing %s/%s", folder, filename)
        db.queue_upload(folder, filename, file_path)
        return None

    meta = None
    for attempt in range(1, _attempts + 1):
        meta = telegram.send_image(file_path, caption=f"{folder}/{filename}")
        if meta:
            break
        if attempt < _attempts:
            logger.warning(
                "Upload of %s/%s failed (attempt %d/%d); retrying",
                folder, filename, attempt, _attempts,
            )
            time.sleep(UPLOAD_RETRY_DELAY)

    if not meta:
        logger.error("Giving up on %s/%s; leaving it queued for the next batch", folder, filename)
        try:
            db.queue_upload(folder, filename, file_path)
            db.bump_upload_attempts(folder, filename)
        except Exception as e:
            logger.error(f"Could not queue %s/%s for retry: {e}", folder, filename)
        return None

    try:
        meta["mtime"] = os.path.getmtime(file_path)
    except OSError:
        meta["mtime"] = time.time()
    try:
        # Index first, clear the queue second: an index failure must leave the
        # file queued so a later batch can still attach its Telegram id.
        db.put_image(folder, filename, meta)
        db.clear_upload(folder, filename)
        make_thumbnail(file_path, folder, filename)
    except Exception as e:
        logger.error(f"Could not index {folder}/{filename} in MongoDB: {e}")
    logger.info("Stored %s/%s on Telegram (msg_id=%s)", folder, filename, meta["msg_id"])
    return meta


def sync_pending_uploads(limit=None):
    """Upload queued local images to Telegram in one batch.

    Local disk is authoritative while the container lives. Telegram is the
    durable copy used after a redeploy, so it does not need to be updated on
    every single scan.
    """
    if not telegram.is_configured():
        return 0
    # A manual "Sync now" click must not overlap the background batch and
    # upload/clear the same queue rows twice.
    if not _sync_lock.acquire(blocking=False):
        return 0

    recovered = 0
    lost = 0
    try:
        entries = db.get_uploads()
        if limit:
            entries = entries[:limit]
        for entry in entries:
            _wait_for_scan_idle()
            folder = entry.get("folder", "")
            filename = entry.get("filename", "")
            path = entry.get("file_path") or os.path.join(BASE, folder, filename)
            if not os.path.isfile(path):
                # The local copy disappeared. If the image index already has it,
                # just clear the stale queue row; otherwise there is nothing left
                # to upload from this container.
                logger.warning(
                    "Queued upload %s/%s has no local copy; dropping it", folder, filename
                )
                db.clear_upload(folder, filename)
                lost += 1
                continue
            db.bump_upload_attempts(folder, filename)
            if store_image(folder, filename, path):
                recovered += 1
    finally:
        _sync_lock.release()
    if recovered or lost:
        logger.info("Telegram sync: %d uploaded, %d dropped", recovered, lost)
    return recovered


def reconcile_uploads():
    """Backwards-compatible alias used by tests and boot code."""
    return sync_pending_uploads()


def restore_missing_images(limit=None):
    """Download Telegram-backed images that are absent from this container.

    Runs in the background after boot, so the first page load does not pay for
    thousands of sequential downloads. The on-demand /file path remains the
    fallback for anything not restored yet.
    """
    if not telegram.is_configured():
        return 0

    images = db.list_images()
    restored = 0
    for full_key, meta in images.items():
        if limit and restored >= limit:
            break
        if not meta.get("file_id"):
            continue
        _wait_for_scan_idle()
        folder, _, filename = full_key.partition("/")
        if not folder or not filename:
            continue
        try:
            dest = get_safe_path(f"{folder}/{filename}")
        except PermissionError:
            logger.warning("Skipping unsafe indexed image path %s", full_key)
            continue
        if os.path.isfile(dest):
            make_thumbnail(dest, folder, filename)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if telegram.download(meta["file_id"], dest):
            restored += 1
            make_thumbnail(dest, folder, filename)
    if restored:
        logger.info("Restored %d image(s) from Telegram", restored)
    return restored


def _background_sync_loop():
    """Batch uploads every SYNC_INTERVAL seconds, forever."""
    if SYNC_ON_START:
        try:
            # Queue any pre-existing on-disk images (first local boot, or a
            # partially completed previous batch) before flushing the queue.
            backfill_images()
            sync_pending_uploads()
        except Exception as e:
            logger.error("Initial Telegram sync failed: %s", e)
    while True:
        time.sleep(SYNC_INTERVAL)
        try:
            backfill_images()
            sync_pending_uploads()
        except Exception as e:
            logger.error("Telegram sync failed: %s", e)

def store_folder_images(folder, limit=None):
    """Queue every new image in one folder for the next Telegram batch."""
    folder_path = os.path.join(BASE, folder)
    if not os.path.isdir(folder_path):
        return 0

    known = db.list_images(folder)
    stored = 0
    for name in sorted(os.listdir(folder_path)):
        if not name.lower().endswith(EXTENSIONS) or name in known:
            continue
        if queue_image(folder, name, os.path.join(folder_path, name)):
            stored += 1
        if limit and stored >= limit:
            break
    return stored

def backfill_images():
    """Queue on-disk images that are not yet recorded in MongoDB.

    Only managed folders are considered: static signatures and template assets
    must never be uploaded as if they were answer sheets.
    """
    for folder in get_project_folders():
        try:
            count = store_folder_images(folder)
            if count:
                logger.info("Queued %d image(s) from %s", count, folder)
        except Exception as e:
            logger.error(f"Backfill failed for {folder}: {e}")

def fetch_image_from_telegram(folder, filename, dest_path):
    """Re-download an image from Telegram into the local cache."""
    meta = db.get_image(folder, filename)
    if not meta or not meta.get("file_id"):
        return False

    if telegram.download(meta["file_id"], dest_path):
        make_thumbnail(dest_path, folder, filename)
        return True

    logger.warning("Could not download Telegram image %s/%s", folder, filename)
    return False

# --- BACKGROUND TASK WORKER ---
# autoapp.py reads and writes the shared temp_input/ and temp_output/ folders,
# and the filesystem here is not shared between gunicorn workers or containers.
# A process-wide lock serialises scans within a worker; a lock file serialises
# them across workers on the same filesystem.
_SCAN_LOCK = threading.Lock()
SCAN_LOCK_PATH = os.path.join(tempfile.gettempdir(), "omr_scan.lock")


class _CrossProcessLock:
    """Exclusive lock backed by a file, so concurrent gunicorn workers in one
    container do not run two scans at once."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
        return False


def parse_result_filename(filename):
    """Pull {roll, marks} out of a "<roll>_<marks>.jpg" result name.

    The score is encoded in the filename by scan50/scan100, which makes the
    image the only record of it. Returns None when the name does not match.
    """
    match = re.match(r"^(\d+)_(\d+)(?:_\d+)?\.", os.path.basename(filename or ""))
    if not match:
        return None
    return {"roll": int(match.group(1)), "marks": int(match.group(2))}


def _write_scan_config(task_output_dir):
    """Freeze the answer key/settings for this task.

    The engine subprocess reads this file, so it does not need Mongo, DNS, TLS
    or the settings collection before it can start working.
    """
    config = get_scan_config()
    if not config.get("answer_key"):
        raise RuntimeError("No answer key found. Save an answer key before scanning.")
    path = os.path.join(task_output_dir, "scan_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, separators=(",", ":"))
    return path


def process_omr_task(task_id, input_filepath, original_filename):
    """Evaluate one sheet, then persist the verdict.

    The score is written to MongoDB synchronously, before any Telegram batch,
    so the result survives a redeploy even if the image upload is still queued.
    """
    task_output_dir = os.path.join(OUTPUT_FOLDER, task_id)
    os.makedirs(task_output_dir, exist_ok=True)
    process = None

    try:
        _write_scan_config(task_output_dir)

        with _SCAN_LOCK, _CrossProcessLock(SCAN_LOCK_PATH):
            # Start the engine first, then record the status while it runs.
            # The scan no longer waits for an Atlas write before importing cv2.
            _scan_busy.set()
            process = subprocess.Popen(
                ["python3", "autoapp.py", input_filepath, task_output_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=BASE,
            )
            set_task(task_id, status="processing", input_filename=original_filename or "")
            try:
                stdout, stderr = process.communicate(timeout=SCAN_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise RuntimeError(f"OMR engine timed out after {SCAN_TIMEOUT}s.")
            except TypeError:
                # Test doubles / old wrappers may not accept timeout.
                stdout, stderr = process.communicate()

            # Only this task's own output directory, never a shared folder: the
            # previous "newest file in temp_output/" could pick up a different
            # task's image and drop this task's result entirely.
            files = sorted(
                f for f in os.listdir(task_output_dir) if f.lower().endswith(EXTENSIONS)
            )

        if not files:
            detail = (stdout or b"").decode(errors="replace").strip()
            err_detail = (stderr or b"").decode(errors="replace").strip()
            if err_detail:
                detail = f"{detail}\n{err_detail}" if detail else err_detail
            set_task(
                task_id,
                status="failed",
                error=detail or "No output file produced by OMR engine.",
            )
            shutil.rmtree(task_output_dir, ignore_errors=True)
            return

        newest_file = files[0]
        src_path = os.path.join(task_output_dir, newest_file)
        name_part, ext_part = os.path.splitext(newest_file)
        dest_path = os.path.join(FINAL_OUTPUT_FOLDER, newest_file)
        count = 1
        while os.path.exists(dest_path):
            newest_file = f"{name_part}_{count}{ext_part}"
            dest_path = os.path.join(FINAL_OUTPUT_FOLDER, newest_file)
            count += 1

        shutil.move(src_path, dest_path)
        shutil.rmtree(task_output_dir, ignore_errors=True)

        # The durable record. Everything below this line is best-effort.
        verdict = parse_result_filename(newest_file) or {}
        try:
            db.put_result(
                task_id,
                {
                    "input_filename": original_filename or "",
                    "output_filename": newest_file,
                    "roll": verdict.get("roll"),
                    "marks": verdict.get("marks"),
                },
            )
        except Exception as e:
            logger.error(f"Could not persist result for task {task_id}: {e}")

        set_task(
            task_id,
            status="completed",
            output_filename=newest_file,
            roll=verdict.get("roll"),
            marks=verdict.get("marks"),
        )

        # Local-first but off the critical path: the next scan can start while
        # thumbnails are generated and uploads are queued.
        image_executor.submit(queue_image, "output", newest_file, dest_path)

    except Exception as e:
        logger.error(f"OMR task {task_id} failed: {e}")
        try:
            set_task(task_id, status="failed", error=str(e))
        except Exception as db_error:
            logger.error("Could not record task failure: %s", db_error)
        shutil.rmtree(task_output_dir, ignore_errors=True)
        if process is not None:
            poll = getattr(process, "poll", None)
            kill = getattr(process, "kill", None)
            if poll and kill and poll() is None:
                kill()
    finally:
        _scan_busy.clear()

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
        disk_count = 0
        if os.path.isdir(folder_path):
            disk_count = len([
                f for f in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, f))
                and not f.startswith('.')
                and f.lower().endswith(EXTENSIONS)
            ])
        try:
            indexed = db.count_images(folder)
        except Exception:
            indexed = 0
        # After a redeploy the disk is empty but Telegram still has the image;
        # show the larger of the two so the dashboard is not misleading.
        folder_counts[folder] = max(disk_count, indexed)

    pending = 0
    try:
        pending = db.count_uploads()
    except Exception:
        pass
    return render_template(
        "index.html",
        folders=folders,
        folder_counts=folder_counts,
        total_images=sum(folder_counts.values()),
        rolls_files=rolls_files,
        pending_uploads=pending,
        telegram_configured=telegram.is_configured(),
    )

def _save_upload(file_obj, dest_path):
    """Normalise a camera image to a sane size and a real JPEG.

    Phone cameras produce 12MP+ files; decoding those wastes most of the
    engine's CPU. Pillow is optional so the app still works without it.
    """
    if Image is None:
        file_obj.save(dest_path)
        return
    try:
        file_obj.stream.seek(0)
        with Image.open(file_obj.stream) as img:
            # The browser already sends a 1600px JPEG. Copying those bytes
            # avoids a full decode + JPEG re-encode on every upload (which also
            # throws away quality for no benefit).
            if img.format == "JPEG" and max(img.size) <= 1600:
                file_obj.stream.seek(0)
                with open(dest_path, "wb") as out:
                    shutil.copyfileobj(file_obj.stream, out)
                return
            # Decode JPEGs at a reduced DCT scale instead of fully expanding a
            # 12MP phone photo only to feed the engine, which resizes to 960px
            # wide anyway. This cuts upload latency and disk usage a lot.
            img.draft("RGB", (1600, 1600))
            img = img.convert("RGB")
            img.thumbnail((1600, 1600), Image.Resampling.BILINEAR)
            img.save(dest_path, "JPEG", quality=88, optimize=True)
    except Exception:
        # Not a composable image (or a HEIC-only upload): keep the original
        # bytes so the engine can produce its normal error instead of a 500.
        file_obj.stream.seek(0)
        file_obj.save(dest_path)


@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({"error": "No image file uploaded"}), 400

    file = request.files['image']
    roll = re.sub(r"[^0-9]", "", request.form.get('roll', ''))[:6]
    stamp = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    filename = f"OMR_sheet_roll_{roll}_{stamp}.jpg" if roll else f"OMR_sheet_{stamp}.jpg"
    input_filepath = os.path.join(INPUT_FOLDER, filename)
    try:
        _save_upload(file, input_filepath)
    except Exception as e:
        logger.error("Could not save upload: %s", e)
        return jsonify({"error": "Could not save upload"}), 500

    # The response and the scan must not wait for a thumbnail and a Mongo
    # queue write; the batch worker only needs the file to exist.
    image_executor.submit(queue_image, "temp_input", filename, input_filepath)

    task_id = str(uuid.uuid4())
    set_task(task_id, status="queued", input_filename=filename)

    scan_executor.submit(process_omr_task, task_id, input_filepath, filename)
    return jsonify({"message": "OK", "task_id": task_id, "filename": filename})

@app.route('/status')
def status():
    task_id = request.args.get('task_id', '').strip()
    if task_id:
        # A specific task must never fall back to somebody else's result. One
        # indexed point lookup, not a scan of every task ever created.
        t = get_task(task_id)
    else:
        # Legacy clients (and the live page before an upload) may omit the id;
        # one newest document is still O(1).
        t = db.latest_task()

    if t:
        return jsonify({
            "processing": t.get("status") in ["queued", "processing"],
            "status": t.get("status", ""),
            "filename": t.get("output_filename", ""),
            "input_filename": t.get("input_filename", ""),
            "roll": t.get("roll"),
            "marks": t.get("marks"),
            "error": t.get("status") == "failed",
            "message": t.get("error", "")
        })

    return jsonify({
        "processing": False, "filename": "", "input_filename": "",
        "roll": None, "marks": None, "error": bool(task_id),
        "message": "Task not found." if task_id else "",
    })

@app.route("/scan")
def scan_ui():
    if os.path.exists(os.path.join(BASE, "templates", "camera_ui.html")):
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

    items = []
    if os.path.exists(target_folder) and os.path.isdir(target_folder):
        try:
            items = [
                {"name": f, "is_dir": False}
                for f in os.listdir(target_folder)
                if f.lower().endswith(EXTENSIONS)
            ]
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # After a redeploy the folder is empty on disk but the images still exist
    # in MongoDB/Telegram. Report the larger count so recheck progress is not
    # stuck at zero.
    try:
        indexed = db.count_images(folder_name)
    except Exception:
        indexed = 0
    return jsonify({"items": items, "count": max(len(items), indexed)})

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
            # Drop the MongoDB index and pending queue too, otherwise the
            # images would still be listed/retried after being cleared.
            db.remove_images_in_folder(folder)
            db.remove_uploads_in_folder(folder)
        # Thumbnails are keyed by path, not folder; rebuild after a clear.
        try:
            for thumb in os.listdir(THUMB_FOLDER):
                os.remove(os.path.join(THUMB_FOLDER, thumb))
        except OSError:
            pass
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/get_config')
def get_config():
    config = db.get_settings()
    return {
        "pixel_value": config.get('pixel_value', '200'),
        "signature": config.get('signature', ''),
        "roll_pixel": config.get('roll_pixel', '200'),
        "pending_uploads": db.count_uploads(),
        "telegram_configured": telegram.is_configured(),
    }

@app.route('/update_config', methods=['POST'])
def update_config():
    data = request.get_json() or {}
    patch = {}
    for key in ('signature', 'pixel_value', 'roll_pixel'):
        if key not in data:
            continue
        value = str(data[key]).strip()
        if key == 'signature':
            if value and (value != os.path.basename(value) or '/' in value or '\\' in value):
                return jsonify({"status": "error", "message": "Invalid signature"}), 400
            patch[key] = value
        else:
            if not value.isdigit() or not (0 <= int(value) <= 5000):
                return jsonify({"status": "error", "message": "Value must be 0-5000"}), 400
            patch[key] = value
    if patch:
        db.set_settings(patch)
        invalidate_scan_config()
    return {"status": "success"}


@app.route('/sync_telegram', methods=['POST'])
def sync_telegram():
    """Optional manual flush; the background worker normally does this."""
    if not telegram.is_configured():
        return jsonify({"status": "error", "message": "Telegram is not configured"}), 400
    if _sync_lock.locked():
        return jsonify({"status": "running", "message": "A sync is already running."}), 202
    threading.Thread(target=sync_pending_uploads, daemon=True, name="telegram-manual-sync").start()
    return jsonify({"status": "success"})

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
        # Keep non-numeric keys comparable with numeric ones; returning a bare
        # int for some rows and a str for others made sorted() raise TypeError
        # and the page rendered empty.
        for roll in sorted(data.keys(), key=lambda x: (0, int(x), "") if str(x).isdigit() else (1, 0, str(x))):
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
    if not isinstance(student_list, list) or len(student_list) > 5000:
        return jsonify({"status": "error", "message": "Invalid student list"}), 400
    json_data = {}
    for student in student_list:
        if not isinstance(student, dict) or 'roll' not in student or 'name' not in student:
            return jsonify({"status": "error", "message": "Invalid student entry"}), 400
        roll = str(student['roll']).strip()
        name = str(student['name']).strip()
        if not roll or not name:
            continue
        json_data[roll] = name[:120]

    try:
        db.set_rolls(name, json_data)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/sync_roll_github', methods=['POST'])
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

        from urllib.parse import quote
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{quote(filename)}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        
        get_res = requests.get(url, headers=headers, timeout=20)
        sha = get_res.json().get("sha") if get_res.status_code == 200 else None

        data = {
            "message": f"Update {filename} via OMR Server Dashboard",
            "content": content,
            "branch": BRANCH
        }
        if sha: data["sha"] = sha

        put_res = requests.put(url, headers=headers, json=data, timeout=30)
        if put_res.status_code in [200, 201]:
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": put_res.json()}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/run_gitup', methods=['POST'])
def run_gitup():
    """Stream gitup.py output to the dashboard.

    POST only: a GET could be triggered by any cross-site image/link and would
    then push the user's gallery to GitHub.
    """
    tution = request.form.get('tution') or request.args.get('tution', '')
    cls = request.form.get('class') or request.args.get('class', '')
    sub = request.form.get('subject') or request.args.get('subject', '')
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", tution or ""):
        return "Invalid tuition", 400
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", cls or ""):
        return "Invalid class", 400
    if not re.fullmatch(r"[A-Za-z0-9 _-]{1,40}", sub or ""):
        return "Invalid subject", 400

    def generate():
        try:
            process = subprocess.Popen(
                ['python3', '-u', 'gitup.py', tution, cls, sub],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=BASE
            )
            for line in process.stdout:
                yield line
            process.wait()
            if process.returncode:
                yield f"\n[gitup exited with {process.returncode}]\n"
        except Exception as e:
            yield f"\n[gitup failed: {e}]\n"

    return Response(generate(), mimetype='text/plain')

@app.route('/rename', methods=['POST'])
def rename():
    data = request.json or {}
    raw_old, raw_new = data.get('old', ''), data.get('new', '')
    if not is_managed_path(raw_old) or not is_managed_path(raw_new):
        return jsonify({"error": "Access denied"}), 403
    try:
        old_path = get_safe_path(raw_old)
        new_path = get_safe_path(raw_new)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    if os.path.exists(new_path):
        return jsonify({"error": "File already exists"}), 409

    try:
        os.rename(old_path, new_path)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Move the image index entry too. db.move_image strips storage-only
    # fields, otherwise the new document inherits the old key and violates the
    # unique index.
    old_folder, _, old_name = raw_old.rpartition("/")
    new_folder, _, new_name = raw_new.rpartition("/")
    if (old_folder and new_folder and old_name and new_name
            and old_name != new_name):
        try:
            db.move_image(old_folder, old_name, new_folder, new_name)
            if os.path.isfile(new_path):
                make_thumbnail(new_path, new_folder, new_name)
            # If the image had not reached Telegram yet, move its queue entry
            # too; otherwise the batch worker would look for the old path and
            # drop the only pending backup.
            queued = db.get(db.UPLOAD_PREFIX + db.image_key(old_folder, old_name))
            if queued and os.path.isfile(new_path):
                db.clear_upload(old_folder, old_name)
                db.queue_upload(new_folder, new_name, new_path)
        except Exception as e:
            logger.error(f"Could not move image index entry for {old_name}: {e}")

    return jsonify({"success": True}), 200

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json or {}
    cls = re.sub(r'[^a-zA-Z0-9]', '-', str(data.get("class", "NA"))[:30]) or "NA"
    sub = re.sub(r'[^a-zA-Z0-9]', '-', str(data.get("subject", "NA"))[:30]) or "NA"
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
    invalidate_folders()
    return jsonify(folders=get_project_folders(force=True))

RECHECK_KEY = "recheck_state"
_recheck_lock = threading.Lock()
_recheck_fd = None
RECHECK_LOCK_PATH = os.path.join(tempfile.gettempdir(), "omr_recheck.lock")


def _recheck_worker():
    """Evaluate every sheet in input/ through the normal task pipeline.

    The old implementation ran app.py inside the request and only wrote files,
    so results were neither durable in Mongo nor queued for Telegram and a
    realistic batch exceeded gunicorn's timeout.
    """
    files = sorted(
        f for f in os.listdir(os.path.join(BASE, "input"))
        if f.lower().endswith(EXTENSIONS)
        and os.path.isfile(os.path.join(BASE, "input", f))
    )
    state = {
        "running": True,
        "total": len(files),
        "done": 0,
        "failed": 0,
        "started_at": time.time(),
        "finished_at": None,
        "message": "",
    }
    db.set(RECHECK_KEY, state)
    for name in files:
        task_id = str(uuid.uuid4())
        path = os.path.join(BASE, "input", name)
        try:
            set_task(task_id, status="queued", input_filename=name)
            process_omr_task(task_id, path, name)
            task = get_task(task_id) or {}
            if task.get("status") == "completed":
                state["done"] += 1
            else:
                state["failed"] += 1
        except Exception as e:
            logger.error("Recheck failed for %s: %s", name, e)
            state["failed"] += 1
        state["updated_at"] = time.time()
        db.set(RECHECK_KEY, state)
    state["running"] = False
    state["finished_at"] = time.time()
    state["message"] = f"{state['done']} completed, {state['failed']} failed"
    db.set(RECHECK_KEY, state)


@app.route('/run-recheck', methods=['POST'])
def trigger_recheck():
    global _recheck_fd
    if not _recheck_lock.acquire(blocking=False):
        return jsonify({"status": "running", "message": "A recheck is already running."}), 202
    try:
        fd = os.open(RECHECK_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _recheck_fd = fd
    except OSError:
        _recheck_lock.release()
        return jsonify({"status": "running", "message": "A recheck is already running."}), 202
    try:
        db.set(RECHECK_KEY, {
            "running": True, "total": 0, "done": 0, "failed": 0,
            "started_at": time.time(), "finished_at": None,
            "message": "Starting…",
        })
        threading.Thread(target=_run_recheck_locked, daemon=True, name="omr-recheck").start()
    except Exception as e:
        _recheck_lock.release()
        os.close(_recheck_fd)
        _recheck_fd = None
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "started"}), 202

def _run_recheck_locked():
    global _recheck_fd
    try:
        _recheck_worker()
    except Exception as e:
        logger.error("Recheck worker failed: %s", e)
        db.set(RECHECK_KEY, {
            "running": False,
            "total": 0, "done": 0, "failed": 1,
            "finished_at": time.time(),
            "message": str(e),
        })
    finally:
        _recheck_lock.release()
        try:
            fcntl.flock(_recheck_fd, fcntl.LOCK_UN)
            os.close(_recheck_fd)
        except Exception:
            pass
        _recheck_fd = None


@app.route('/recheck_status')
def recheck_status():
    state = db.get(RECHECK_KEY) or {
        "running": False, "total": 0, "done": 0, "failed": 0, "message": ""
    }
    return jsonify(state)

@app.route("/browse")
def browse():
    path = request.args.get("path", "")
    try:
        full_path = get_safe_path(path)
    except PermissionError:
        return "Access denied", 403
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    page_size = 60

    items = []
    seen = set()
    if os.path.exists(full_path) and os.path.isdir(full_path):
        for f in os.listdir(full_path):
            if f.startswith('.'):
                continue
            fp = os.path.join(full_path, f)
            try:
                mtime = os.path.getmtime(fp)
            except OSError:
                mtime = 0
            items.append({"name": f, "is_dir": os.path.isdir(fp), "mtime": mtime})
            seen.add(f)

    # Images held in Telegram are absent from a fresh container, so merge in
    # the MongoDB index to keep the folder listing complete after a redeploy.
    if path:
        for name, meta in db.list_images(path).items():
            if name in seen or name.startswith('.'):
                continue
            items.append({"name": name, "is_dir": False, "mtime": meta.get("mtime", 0)})

    def sort_key(x):
        if x["is_dir"]:
            return (0, x["name"])
        m = re.search(r"(\d+)", x["name"])
        return (1, int(m.group(1)) if m else 999999)

    items.sort(key=sort_key)
    dirs = [i for i in items if i["is_dir"]]
    files = [i for i in items if not i["is_dir"]]
    total_pages = max(1, (len(files) + page_size - 1) // page_size)
    page = min(page, total_pages)
    page_files = files[(page - 1) * page_size: page * page_size]

    # Duplicate roll detection across the whole folder, not just this page.
    roll_counts = {}
    for item in files:
        match = re.match(r"^(\d+)_", item["name"])
        if match:
            item["roll"] = match.group(1)
            roll_counts[item["roll"]] = roll_counts.get(item["roll"], 0) + 1
    duplicate_rolls = {roll for roll, count in roll_counts.items() if count > 1}

    return render_template(
        "browser.html",
        items=dirs + page_files,
        path=path,
        page=page,
        total_pages=total_pages,
        total_files=len(files),
        page_size=page_size,
        duplicate_rolls=duplicate_rolls,
    )

@app.route("/file")
def get_file():
    raw = request.args.get("path", "")
    if not is_servable_image(raw):
        return "Access denied", 403
    try:
        target = get_safe_path(raw)
    except PermissionError:
        return "Access denied", 403

    if not (os.path.exists(target) and os.path.isfile(target)):
        # Not on this container: restore it from Telegram. The first view
        # after a redeploy pays the download; after that it is local.
        folder, _, name = raw.rpartition("/")
        if not (folder and name and fetch_image_from_telegram(folder, name, target)):
            return "Not Found", 404

    response = send_file(target, conditional=True, max_age=86400)
    response.cache_control.private = True
    return response


@app.route("/thumb")
def get_thumb():
    """Serve a small listing image instead of a multi-megabyte scan."""
    raw = request.args.get("path", "")
    if not is_servable_image(raw):
        return "Access denied", 403
    try:
        target = get_safe_path(raw)
    except PermissionError:
        return "Access denied", 403

    folder, _, name = raw.rpartition("/")
    if not (folder and name):
        return "Not Found", 404

    thumb = thumb_path_for(folder, name)
    if not os.path.isfile(thumb):
        if not os.path.isfile(target):
            if not fetch_image_from_telegram(folder, name, target):
                return "Not Found", 404
        thumb = make_thumbnail(target, folder, name)
    if not thumb or not os.path.isfile(thumb):
        # Pillow unavailable or the image is not decodable: the original is
        # still better than a broken tile.
        response = send_file(target, conditional=True, max_age=86400)
        response.cache_control.private = True
        return response

    response = send_file(thumb, conditional=True, max_age=604800)
    response.cache_control.private = True
    return response

@app.route("/delete", methods=["POST"])
def delete_item():
    """Forget an item: drop its MongoDB entry and its local cache file.

    Nothing is ever removed from Telegram - the bytes stay there, only the
    pointer is dropped. The local file must go too, otherwise /browse would
    keep listing it from disk and the delete would look like a no-op.
    """
    data = request.json or {}
    raw = data.get("path", "")
    if not is_managed_path(raw):
        return jsonify({"error": "Access denied"}), 403
    try:
        path = get_safe_path(raw)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403

    normalized = str(raw).replace("\\", "/").strip("/")
    folder, _, name = normalized.rpartition("/")
    if os.path.isdir(path):
        # A top-level project folder has folder metadata; nested folders only
        # need their image/upload prefix removed. Delete by the full relative
        # path so a folder created on disk but not yet in Mongo is not missed.
        if "/" not in normalized and (
            normalized in get_project_folders() or normalized in STATIC_FOLDERS
        ):
            db.remove_folder(normalized)
            invalidate_folders()
        db.remove_images_in_folder(normalized)
        db.remove_uploads_in_folder(normalized)
    elif name.lower().endswith(EXTENSIONS):
        db.remove_image(folder, name)
        db.clear_upload(folder, name)
        try:
            os.remove(thumb_path_for(folder, name))
        except OSError:
            pass
    elif name.endswith("_rolls.txt"):
        db.delete(db.ROLLS_PREFIX + name[: -len(".txt")])
    elif name == "answer_key.txt":
        db.delete(db.ANSWER_KEY)
        invalidate_scan_config()
    elif name == "config.cfg":
        db.set(db.SETTINGS_KEY, db.DEFAULT_SETTINGS)
        invalidate_scan_config()

    # Drop the local cache copy so it stops being listed and served.
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        # A folder delete must remove its thumbnails as well, otherwise they
        # linger and count against the small container disk.
        try:
            for thumb in os.listdir(THUMB_FOLDER):
                os.remove(os.path.join(THUMB_FOLDER, thumb))
        except OSError:
            pass
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


@app.route("/50")
def answer_key_alias():
    """Legacy public URL used by older published galleries."""
    return answer_key_route()

@app.route("/save_answer_key", methods=['POST'])
def save_key():
    data = request.json or {}
    try:
        content = data.get("content", "")
        # The form posts JSON as a string. Store the parsed dict so the scan
        # engines see the same shape regardless of how the key was saved.
        if isinstance(content, (str, bytes)):
            content = json.loads(content or "{}")
        if not isinstance(content, dict) or not content:
            raise ValueError("Answer key must be a non-empty JSON object.")
        cleaned = {}
        for question, options in content.items():
            if not str(question).isdigit():
                raise ValueError(f"Invalid question number: {question}")
            number = int(question)
            if not (1 <= number <= 100):
                raise ValueError(f"Question out of range: {question}")
            if not isinstance(options, (list, tuple)):
                raise ValueError(f"Question {question} must be a list of options.")
            answer = []
            for option in options:
                letter = str(option).strip().upper()
                if letter not in ("A", "B", "C", "D"):
                    raise ValueError(f"Invalid option {option!r} for question {question}.")
                if letter not in answer:
                    answer.append(letter)
            if not answer:
                raise ValueError(f"Question {question} has no answer.")
            cleaned[str(number)] = answer
        db.set(db.ANSWER_KEY, cleaned)
        invalidate_scan_config()
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

@app.route('/temp_output/<path:filename>')
def serve_output(filename):
    # The task scratch directory contains scan_config.json, which includes the
    # answer key; only image files from it are ever served.
    if not filename.lower().endswith(EXTENSIONS):
        return "Not Found", 404
    return send_from_directory(FINAL_OUTPUT_FOLDER, filename)

@app.route('/temp_input/<path:filename>')
def serve_input(filename):
    if not filename.lower().endswith(EXTENSIONS):
        return "Not Found", 404
    return send_from_directory(INPUT_FOLDER, filename)

# --- RESULTS HTML TEMPLATE ---
RESULTS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live OMR Results</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <div class="brand">
        <div class="brand-mark">◉</div>
        <div><h1 class="brand-title">Live results</h1><p class="brand-sub">Updates automatically</p></div>
      </div>
      <a class="btn btn-ghost" href="/">Dashboard</a>
    </div>
  </header>
  <main class="app-main">
    <div class="panel">
      <div class="section-head">
        <div>
          <h2 id="status">⏳ Waiting for scan…</h2>
          <p id="timestamp" class="muted"></p>
        </div>
        <span id="pill" class="badge badge-warn">Live</span>
      </div>
      <div style="display:flex;justify-content:center;">
        <img id="result-img" style="display:none;max-width:100%;max-height:72vh;border-radius:14px;border:1px solid var(--line);" alt="Marked OMR result">
      </div>
      <div id="meta" class="stats-grid" style="margin-bottom:0;margin-top:18px;"></div>
    </div>
  </main>
  <script>
    const params = new URLSearchParams(location.search);
    const requestedTask = (params.get('task_id') || '').trim();
    let lastTask = requestedTask;
    let lastInput = ""; let lastOutput = ""; let stopped = false;

    function setPill(text, cls) {
      const pill = document.getElementById('pill');
      pill.textContent = text;
      pill.className = 'badge ' + (cls || 'badge-warn');
    }

    async function pollStatus() {
      if (stopped) return;
      try {
        const url = requestedTask ? `/status?task_id=${encodeURIComponent(requestedTask)}` : '/status';
        const response = await fetch(url, {cache: 'no-store'});
        const data = await response.json();
        const failed = data.error && !data.filename;
        if (failed) {
          document.getElementById('status').textContent = '❌ ' + (data.message || 'Scan failed');
          setPill('Failed', 'badge-danger');
          // A live page must recover when the next sheet is scanned; only a
          // page pinned to one task id stops on that task's failure.
          if (requestedTask) return;
        }

        if (!failed && !requestedTask && data.input_filename && data.input_filename !== lastInput) {
          lastInput = data.input_filename;
          document.getElementById('status').textContent = '🟡 Processing new sheet…';
          setPill('Processing', 'badge-warn');
          const input = document.getElementById('result-img');
          input.style.display = 'block';
          input.src = '/file?path=' + encodeURIComponent('temp_input/' + data.input_filename) + '&v=' + Date.now();
          document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();
        }

        if (!failed && !data.processing && data.filename && data.filename !== lastOutput) {
          lastOutput = data.filename;
          document.getElementById('status').textContent = '✅ Marked result';
          setPill('Complete', 'badge-warn');
          const img = document.getElementById('result-img');
          img.style.display = 'block';
          img.src = '/file?path=' + encodeURIComponent('output/' + data.filename) + '&v=' + Date.now();
          document.getElementById('timestamp').textContent = new Date().toLocaleTimeString();
          document.getElementById('meta').innerHTML =
            `<div class="stat-card"><div class="stat-label">Roll</div><div class="stat-value">${data.roll ?? '—'}</div></div>` +
            `<div class="stat-card"><div class="stat-label">Marks</div><div class="stat-value">${data.marks ?? '—'}</div></div>`;
          if (requestedTask) stopped = true;
        } else if (!failed && data.processing) {
          document.getElementById('status').textContent = '🟡 Processing…';
          setPill('Processing', 'badge-warn');
        }
      } catch (err) {
        setPill('Offline', 'badge-danger');
      }
    }
    pollStatus();
    setInterval(pollStatus, 1200);
  </script>
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
# __main__ (which only runs under `python3 run_web.py`). Gated on the boot lock
# so a second worker does not double the request rate.
if (
    IS_PRIMARY_WORKER
    and os.environ.get("DISABLE_SELF_PING", "").lower() not in ("1", "true", "yes")
):
    _start_self_ping()

# Warm the caches in every worker before the first camera upload so its scan
# does not pay for two Atlas reads (answer key + settings) or a folder listing.
try:
    if not get_scan_config(force=True).get("answer_key"):
        invalidate_scan_config()
    get_project_folders(force=True)
except Exception as e:
    logger.warning("Could not warm startup caches: %s", e)

# Telegram work is batched. The sync thread queues any on-disk images and
# flushes the upload queue; the restore thread repopulates the local cache so
# browsing is fast after a redeploy. Both are single-winner per container.
if IS_PRIMARY_WORKER and telegram.is_configured():
    threading.Thread(
        target=_background_sync_loop, daemon=True, name="telegram-sync"
    ).start()
    if RESTORE_ON_BOOT and os.environ.get("DISABLE_RESTORE", "").lower() not in ("1", "true", "yes"):
        threading.Thread(
            target=restore_missing_images, daemon=True, name="telegram-restore"
        ).start()
    logger.info("Telegram batch sync enabled (interval %ds).", SYNC_INTERVAL)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port, threaded=True)
