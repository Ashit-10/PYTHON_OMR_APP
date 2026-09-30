"""MongoDB-backed persistence for all durable OMR state.

Single source of truth for settings, answer key, roll->name maps, the project
folder list and scan task state. The container filesystem is ephemeral on
Koyeb, so nothing durable may live on disk.
"""
import os
import glob
import json
import re
import threading
import time

from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("MONGO_DB", "omr")
COLLECTION = "omr_state"

SETTINGS_KEY = "settings"
ANSWER_KEY = "answer_key"
FOLDERS_KEY = "folders"
ROLLS_PREFIX = "rolls:"

# Per-entity prefixes. Tasks, images and results are stored one document per
# entity rather than inside a single growing document: a read-modify-write of
# one shared dict loses concurrent writes, and a single document is capped at
# 16 MB by Mongo, which an unbounded task history would eventually hit.
TASK_PREFIX = "task:"
IMAGE_PREFIX = "image:"
RESULT_PREFIX = "result:"
UPLOAD_PREFIX = "upload:"

# Results and tasks older than this are pruned at boot, so the collections stay
# bounded on a long-lived deployment.
TASK_RETENTION_SECONDS = 7 * 24 * 60 * 60
RESULT_RETENTION_SECONDS = 365 * 24 * 60 * 60

_client = None
_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "signature": "",
    "pixel_value": "200",
    "roll_pixel": "200",
}


def get_collection():
    if _client is None:
        raise RuntimeError("db.init_db() must be called before using the database.")
    return _client[DB_NAME][COLLECTION]


def _validate_url(url):
    """Catch a malformed or placeholder URL before the driver does.

    Returns an error string, or None when the URL looks usable.
    """
    from urllib.parse import unquote, urlparse

    try:
        parsed = urlparse(url)
    except ValueError as e:
        return f"MONGO_URL could not be parsed: {e}"

    if not parsed.scheme:
        return "MONGO_URL is missing a scheme; it should start with mongodb:// or mongodb+srv://"
    if not parsed.hostname:
        return "MONGO_URL is missing a host name."

    user = unquote(parsed.username or "")
    if user.startswith("<") and user.endswith(">"):
        return (
            f"MONGO_URL still has the Atlas placeholder '{user}' as the username. "
            "Copy the connection string from Atlas > Database Access, which fills "
            "in your real username and password."
        )
    if not user:
        return "MONGO_URL has no username."

    if " " in url:
        return "MONGO_URL contains a space; it must be percent-encoded."
    return None


def _connection_error(e):
    """Turn a driver exception into something actionable.

    The raw pymongo message embeds a full topology dump, which buries the one
    line that matters.
    """
    from urllib.parse import unquote, urlparse

    text = str(e)

    try:
        user = unquote(urlparse(MONGO_URL).username or "")
    except ValueError:
        user = ""
    if user.startswith("<") and user.endswith(">"):
        return (
            "MONGO_URL still contains the Atlas placeholder "
            f"'{user}' as the username. Replace it with your real "
            "Database Access username, URL-encoded."
        )

    if "SSL handshake failed" in text or "TLSV1_ALERT_INTERNAL_ERROR" in text:
        return (
            "TLS handshake with MongoDB Atlas failed. Check that MONGO_URL uses "
            "mongodb+srv:// and that the cluster is not paused. The most common "
            "cause is a placeholder or misspelled username in the URL."
        )
    if "Authentication failed" in text:
        return "MongoDB rejected the credentials. Check the username and password in MONGO_URL."

    # Keep the first clause; the topology dump after it is noise.
    return text.split(",")[0][:300]


def init_db():
    """Connect, verify reachability and ensure indexes. Raises on failure."""
    global _client

    if not MONGO_URL:
        raise RuntimeError(
            "MONGO_URL environment variable is not set. "
            "Durable state cannot be stored; refusing to start."
        )

    invalid = _validate_url(MONGO_URL)
    if invalid:
        raise RuntimeError(invalid)

    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
    except PyMongoError as e:
        raise RuntimeError(f"MongoDB at MONGO_URL is unreachable: {_connection_error(e)}") from e

    with _lock:
        _client = client

    get_collection().create_index([("key", ASCENDING)], unique=True)
    # Supports the retention sweeps; not unique, and not a TTL index because
    # pruning runs at boot rather than in the background.
    get_collection().create_index([("created_at", ASCENDING)])


def get(key, default=None):
    """Read a stored value.

    Handles both document shapes in this collection: simple values written via
    set() live under "value", while per-entity documents (tasks, images,
    results) hold their fields at the top level.
    """
    doc = get_collection().find_one({"key": key})
    if not doc:
        return default
    if "value" in doc:
        return doc["value"]
    return _doc_value(doc)


def set(key, value):
    get_collection().update_one(
        {"key": key}, {"$set": {"value": value}}, upsert=True
    )
    return value


def delete(key):
    get_collection().delete_one({"key": key})


def get_settings():
    return {**DEFAULT_SETTINGS, **(get(SETTINGS_KEY) or {})}


def set_settings(patch):
    with _lock:
        merged = get_settings()
        merged.update(patch)
        set(SETTINGS_KEY, merged)
    return merged


def get_rolls(filename):
    return get(ROLLS_PREFIX + filename, {}) or {}


def list_rolls_names():
    """Names (without the rolls: prefix) of every stored rolls file."""
    prefix = "^" + re.escape(ROLLS_PREFIX)
    keys = get_collection().distinct("key", {"key": {"$regex": prefix}})
    return [k[len(ROLLS_PREFIX):] for k in keys]


def set_rolls(filename, mapping):
    return set(ROLLS_PREFIX + filename, mapping)


def get_folders():
    return get(FOLDERS_KEY, []) or []


def add_folder(name):
    with _lock:
        folders = get_folders()
        if name not in folders:
            folders.append(name)
            folders.sort()
            set(FOLDERS_KEY, folders)
    return folders


def remove_folder(name):
    with _lock:
        folders = [f for f in get_folders() if f != name]
        set(FOLDERS_KEY, folders)
    return folders


def get_task(task_id):
    return get(TASK_PREFIX + task_id)


def set_task(task_id, data):
    """Upsert one task document atomically.

    run_web.set_task() merges a full task dict, so a whole-document $set keeps
    the write a single atomic operation instead of a read-modify-write.
    """
    data = dict(data)
    data["updated_at"] = time.time()
    data.setdefault("created_at", data["updated_at"])
    get_collection().update_one(
        {"key": TASK_PREFIX + task_id},
        {"$set": data},
        upsert=True,
    )
    return data


def all_tasks():
    """Every task, newest first. Scans by prefix so the small settings/folder
    documents in the same collection are never loaded."""
    cursor = get_collection().find(
        {"key": {"$regex": "^" + re.escape(TASK_PREFIX)}}
    )
    tasks = {}
    for doc in cursor:
        tasks[doc["key"][len(TASK_PREFIX):]] = _doc_value(doc)
    return tasks


def _doc_value(doc):
    """Flatten a stored document back into a plain dict.

    Entities are written with $set at the top level, so a document holds the
    fields directly rather than under "value".
    """
    doc.pop("_id", None)
    return doc


def prune_tasks(max_age=TASK_RETENTION_SECONDS):
    """Drop tasks older than max_age. Returns the number removed."""
    cutoff = time.time() - max_age
    result = get_collection().delete_many(
        {
            "key": {"$regex": "^" + re.escape(TASK_PREFIX)},
            "created_at": {"$lt": cutoff},
        }
    )
    return result.deleted_count


def put_result(task_id, data):
    """Persist a scan's verdict.

    This is the durable record of the score: the image itself may live only on
    ephemeral disk or in Telegram, but {roll, marks} must never depend on
    either surviving.
    """
    data = dict(data)
    data["task_id"] = task_id
    data["created_at"] = time.time()
    get_collection().update_one(
        {"key": RESULT_PREFIX + task_id}, {"$set": data}, upsert=True
    )
    return data


def get_result(task_id):
    return get(RESULT_PREFIX + task_id)


def list_results():
    """Every persisted scan result, newest first."""
    cursor = get_collection().find(
        {"key": {"$regex": "^" + re.escape(RESULT_PREFIX)}}
    )
    results = [_doc_value(doc) for doc in cursor]
    results.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return results


def prune_results(max_age=RESULT_RETENTION_SECONDS):
    cutoff = time.time() - max_age
    result = get_collection().delete_many(
        {
            "key": {"$regex": "^" + re.escape(RESULT_PREFIX)},
            "created_at": {"$lt": cutoff},
        }
    )
    return result.deleted_count


IMAGES_KEY = "images"


def image_key(folder, filename):
    """Single place the image identifier is built, so uploads and lookups
    cannot drift apart."""
    return f"{folder}/{filename}".strip("/")


def get_image(folder, filename):
    return get(IMAGE_PREFIX + image_key(folder, filename))


def put_image(folder, filename, meta):
    """Index one image. A single upsert is atomic, so concurrent uploads from
    different workers cannot overwrite each other's entries."""
    get_collection().update_one(
        {"key": IMAGE_PREFIX + image_key(folder, filename)},
        {"$set": dict(meta)},
        upsert=True,
    )
    return meta


def remove_image(folder, filename):
    get_collection().delete_one({"key": IMAGE_PREFIX + image_key(folder, filename)})


def remove_images_in_folder(folder):
    """Drop every image entry for a folder. Returns the number removed."""
    result = get_collection().delete_many(
        {
            "key": {
                "$regex": "^"
                + re.escape(IMAGE_PREFIX)
                + re.escape(folder)
                + "/"
            }
        }
    )
    return result.deleted_count


def list_images(folder=None):
    """Stored image metadata keyed by "folder/filename", optionally limited to
    one folder."""
    query = {"key": {"$regex": "^" + re.escape(IMAGE_PREFIX)}}
    images = {}
    for doc in get_collection().find(query, {"_id": 0}):
        full_key = doc["key"][len(IMAGE_PREFIX):]
        images[full_key] = _doc_value(doc)
    if folder is None:
        return images
    prefix = f"{folder}/"
    return {k[len(prefix):]: v for k, v in images.items() if k.startswith(prefix)}


def migrate_legacy_images():
    """Convert the old single-document image index into per-image documents.

    The previous schema kept every entry inside one "images" document, which
    meant any concurrent write could drop an unrelated entry. Idempotent: it
    is a no-op once the legacy document is gone.
    """
    legacy = get(IMAGES_KEY)
    if not isinstance(legacy, dict) or not legacy:
        return 0

    for key, meta in legacy.items():
        if not isinstance(meta, dict):
            continue
        get_collection().update_one(
            {"key": IMAGE_PREFIX + key},
            {"$set": dict(meta)},
            upsert=True,
        )
    delete(IMAGES_KEY)
    return len(legacy)


# --- PENDING UPLOAD QUEUE ---
# An image that failed to reach Telegram is recorded here so a later attempt
# can retry it. Without this the only copy lived on ephemeral disk and was lost
# on the next deploy, with nothing left to reconcile against.


def queue_upload(folder, filename, file_path):
    """Record an upload that still needs to happen. Returns the entry.

    $setOnInsert keeps created_at and attempts intact across repeated queueing,
    so a file that keeps failing shows a growing attempt count rather than
    resetting to zero every time.
    """
    get_collection().update_one(
        {"key": UPLOAD_PREFIX + image_key(folder, filename)},
        {
            "$set": {"folder": folder, "filename": filename, "file_path": file_path},
            "$setOnInsert": {"attempts": 0, "created_at": time.time()},
        },
        upsert=True,
    )
    return get(UPLOAD_PREFIX + image_key(folder, filename))


def get_uploads():
    """Every queued upload."""
    cursor = get_collection().find({"key": {"$regex": "^" + re.escape(UPLOAD_PREFIX)}})
    uploads = []
    for doc in cursor:
        entry = _doc_value(doc)
        uploads.append(entry)
    uploads.sort(key=lambda u: u.get("created_at", 0))
    return uploads


def clear_upload(folder, filename):
    get_collection().delete_one({"key": UPLOAD_PREFIX + image_key(folder, filename)})


def bump_upload_attempts(folder, filename):
    get_collection().update_one(
        {"key": UPLOAD_PREFIX + image_key(folder, filename)},
        {"$inc": {"attempts": 1}},
    )


def seed_from_disk(base_dir="."):
    """Bootstrap an empty database from the files committed to the repo.

    No-op once the collection has any document, so live Mongo data always
    wins over the on-disk defaults.
    """
    if get_collection().count_documents({}, limit=1):
        return False

    def read_json(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if os.path.exists(os.path.join(base_dir, "answer_key.txt")):
        try:
            set(ANSWER_KEY, read_json(os.path.join(base_dir, "answer_key.txt")))
        except (ValueError, OSError):
            pass

    config_path = os.path.join(base_dir, "config.cfg")
    if os.path.exists(config_path):
        settings = get_settings()
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("["):
                    k, v = line.split("=", 1)
                    settings[k.strip()] = v.strip()
        set(SETTINGS_KEY, settings)

    for path in glob.glob(os.path.join(base_dir, "*_rolls.txt")):
        name = os.path.basename(path)[: -len(".txt")]
        try:
            set_rolls(name, read_json(path))
        except (ValueError, OSError):
            pass

    return True


def startup_maintenance():
    """Bring persisted state up to date on boot.

    Runs the image-index schema migration and the retention sweeps. Safe to
    call on every start: each step is idempotent.
    """
    migrated = migrate_legacy_images()
    pruned_tasks = prune_tasks()
    pruned_results = prune_results()
    return {
        "migrated_images": migrated,
        "pruned_tasks": pruned_tasks,
        "pruned_results": pruned_results,
    }
