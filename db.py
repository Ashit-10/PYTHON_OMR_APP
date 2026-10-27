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

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

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

# A task that has not moved for this long is considered abandoned. Covers a
# worker killed by a redeploy or a subprocess that hung.
STALE_TASK_SECONDS = 30 * 60

# Settings are read by every scan and every config request. A short TTL keeps
# the read off Mongo's hot path without making the dashboard feel stale.
SETTINGS_CACHE_TTL = float(os.environ.get("SETTINGS_CACHE_TTL", "30"))

_client = None
_lock = threading.Lock()
_settings_cache = {"value": None, "expires": 0.0}

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
    if not user and parsed.hostname not in ("localhost", "127.0.0.1", "::1", "mongo"):
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
        client = MongoClient(
            MONGO_URL,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            maxPoolSize=20,
            appname="omr",
        )
        client.admin.command("ping")
    except PyMongoError as e:
        raise RuntimeError(f"MongoDB at MONGO_URL is unreachable: {_connection_error(e)}") from e

    with _lock:
        _client = client
        _settings_cache["value"] = None
        _settings_cache["expires"] = 0.0

    collection = get_collection()
    collection.create_index([("key", ASCENDING)], unique=True)
    # Supports the retention sweeps and newest-task lookup.
    collection.create_index([("created_at", DESCENDING)])
    # New documents carry a type so listings can be indexed rather than
    # scanning every key with a regex. Existing prefix-keyed documents still
    # work through the key index.
    collection.create_index([("type", ASCENDING), ("created_at", DESCENDING)])
    collection.create_index([("type", ASCENDING), ("folder", ASCENDING)])


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
    if key == SETTINGS_KEY:
        invalidate_settings()
    return value


def delete(key):
    get_collection().delete_one({"key": key})


def get_settings():
    now = time.time()
    cached = _settings_cache["value"]
    if cached is not None and _settings_cache["expires"] > now:
        return dict(cached)

    merged = {**DEFAULT_SETTINGS, **(get(SETTINGS_KEY) or {})}
    _settings_cache["value"] = merged
    _settings_cache["expires"] = now + SETTINGS_CACHE_TTL
    return dict(merged)


def invalidate_settings():
    _settings_cache["value"] = None
    _settings_cache["expires"] = 0.0


def set_settings(patch):
    """Merge settings without losing a concurrent worker's change.

    Optimistic compare-and-set: the update only succeeds while "value" still
    has the exact contents that were read. A concurrent write causes one retry
    instead of silently dropping the other key.
    """
    for _ in range(5):
        current = get(SETTINGS_KEY)
        base = dict(current) if isinstance(current, dict) else {}
        merged = {**base, **patch}
        if current is None:
            try:
                get_collection().insert_one({"key": SETTINGS_KEY, "value": merged})
            except DuplicateKeyError:
                continue
            invalidate_settings()
            return merged
        result = get_collection().update_one(
            {"key": SETTINGS_KEY, "value": current},
            {"$set": {"value": merged}},
        )
        if result.matched_count:
            invalidate_settings()
            return merged
    # Extremely unlikely, but do not leave the caller with an exception after
    # a read they can retry from the UI.
    invalidate_settings()
    return get_settings()


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


def _mutate_folder_list(mutator):
    """Atomically apply mutator(list) -> list to the folder singleton."""
    for _ in range(5):
        current = get(FOLDERS_KEY)
        folders = list(current) if isinstance(current, list) else []
        updated = mutator(list(folders))
        if updated == folders:
            return sorted(updated)
        if current is None:
            try:
                get_collection().insert_one({"key": FOLDERS_KEY, "value": updated})
            except DuplicateKeyError:
                continue
            return sorted(updated)
        result = get_collection().update_one(
            {"key": FOLDERS_KEY, "value": current},
            {"$set": {"value": updated}},
        )
        if result.modified_count:
            return sorted(updated)
    return sorted(get_folders())


def add_folder(name):
    def add(folders):
        if name not in folders:
            folders.append(name)
        return folders

    return _mutate_folder_list(add)


def remove_folder(name):
    return _mutate_folder_list(lambda folders: [f for f in folders if f != name])


def get_task(task_id):
    return get(TASK_PREFIX + task_id)


def set_task(task_id, data):
    """Upsert one task document atomically.

    Kept for callers that already hold a merged task dict. New code should
    prefer update_task(), which changes only the fields it is given.
    """
    data = dict(data)
    data["updated_at"] = time.time()
    data.setdefault("created_at", data["updated_at"])
    data.setdefault("type", "task")
    get_collection().update_one(
        {"key": TASK_PREFIX + task_id},
        {"$set": data},
        upsert=True,
    )
    return data


def update_task(task_id, fields, defaults=None):
    """Update only the supplied task fields, without a preceding read.

    $setOnInsert writes created_at/defaults on the first write and is ignored
    afterwards, so the common "processing" and "completed" updates are one
    round trip each.
    """
    now = time.time()
    fields = dict(fields)
    fields["updated_at"] = now
    on_insert = {"created_at": now, "type": "task"}
    if defaults:
        on_insert.update(defaults)
    # Mongo rejects a field that appears in both $set and $setOnInsert.
    for key in fields:
        on_insert.pop(key, None)
    get_collection().update_one(
        {"key": TASK_PREFIX + task_id},
        {"$set": fields, "$setOnInsert": on_insert},
        upsert=True,
    )
    return fields


def latest_task():
    """Most recently created task, or None. One indexed document, not a scan."""
    doc = get_collection().find_one(
        {"type": "task"},
        sort=[("created_at", DESCENDING)],
    )
    if doc is None:
        # Tasks created before the type field was introduced.
        doc = get_collection().find_one(
            {"key": {"$regex": "^" + re.escape(TASK_PREFIX)}},
            sort=[("created_at", DESCENDING)],
        )
    return _doc_value(doc) if doc else None


def all_tasks():
    """Every task. Only used by maintenance/tests now; request paths use
    get_task() or latest_task()."""
    cursor = get_collection().find(
        {"key": {"$regex": "^" + re.escape(TASK_PREFIX)}},
        {"_id": 0},
    )
    tasks = {}
    for doc in cursor:
        key = doc.get("key", "")
        tasks[key[len(TASK_PREFIX):]] = _doc_value(doc)
    return tasks


def _doc_value(doc):
    """Flatten a stored document back into a plain dict.

    Entities are written with $set at the top level, so a document holds the
    fields directly rather than under "value". Storage-only fields (the _id
    and the key prefix) are stripped so callers cannot accidentally write them
    back during a copy/rename.
    """
    doc.pop("_id", None)
    doc.pop("key", None)
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


def fail_stale_tasks(max_age=STALE_TASK_SECONDS):
    """Mark tasks abandoned by a dying worker as failed.

    Without this a redeploy during a scan leaves the row at "processing"
    forever, and the live view waits on it indefinitely.
    """
    cutoff = time.time() - max_age
    result = get_collection().update_many(
        {
            "key": {"$regex": "^" + re.escape(TASK_PREFIX)},
            "status": {"$in": ["queued", "processing"]},
            "$or": [
                {"updated_at": {"$lt": cutoff}},
                {"updated_at": {"$exists": False}, "created_at": {"$lt": cutoff}},
            ],
        },
        {
            "$set": {
                "status": "failed",
                "error": "Scan was interrupted by a restart.",
                "updated_at": time.time(),
            }
        },
    )
    return result.modified_count


def put_result(task_id, data):
    """Persist a scan's verdict.

    This is the durable record of the score: the image itself may live only on
    ephemeral disk or in Telegram, but {roll, marks} must never depend on
    either surviving.
    """
    data = dict(data)
    data["task_id"] = task_id
    data["created_at"] = time.time()
    data["type"] = "result"
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
    meta = dict(meta)
    meta.pop("key", None)
    meta.pop("_id", None)
    meta["type"] = "image"
    meta["folder"] = folder
    meta["filename"] = filename
    meta["updated_at"] = time.time()
    get_collection().update_one(
        {"key": IMAGE_PREFIX + image_key(folder, filename)},
        {"$set": meta},
        upsert=True,
    )
    return meta


def move_image(old_folder, old_name, new_folder, new_name):
    """Move an image's index entry, preserving only its storage metadata."""
    meta = get_image(old_folder, old_name)
    if not meta:
        return None
    meta = dict(meta)
    meta.pop("key", None)
    meta.pop("_id", None)
    put_image(new_folder, new_name, meta)
    remove_image(old_folder, old_name)
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
    one folder.

    Limiting happens in the query, not in Python: browsing one folder must not
    download every image record on the server.
    """
    if folder is None:
        query = {"key": {"$regex": "^" + re.escape(IMAGE_PREFIX)}}
    else:
        query = {
            "key": {
                "$regex": "^"
                + re.escape(IMAGE_PREFIX)
                + re.escape(folder)
                + "/"
            }
        }
    images = {}
    for doc in get_collection().find(query, {"_id": 0}):
        full_key = doc["key"][len(IMAGE_PREFIX):]
        images[full_key] = _doc_value(doc)
    if folder is None:
        return images
    prefix = f"{folder}/"
    return {k[len(prefix):]: v for k, v in images.items() if k.startswith(prefix)}


def count_images(folder):
    """Number of indexed images in one folder, without transferring them."""
    return get_collection().count_documents(
        {
            "key": {
                "$regex": "^"
                + re.escape(IMAGE_PREFIX)
                + re.escape(folder)
                + "/"
            }
        }
    )


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
        meta = dict(meta)
        meta.pop("_id", None)
        meta.pop("key", None)
        folder, _, filename = str(key).partition("/")
        meta["type"] = "image"
        meta["folder"] = folder
        meta["filename"] = filename
        get_collection().update_one(
            {"key": IMAGE_PREFIX + key},
            {"$set": meta},
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
            "$set": {
                "folder": folder,
                "filename": filename,
                "file_path": file_path,
                "type": "upload",
                "updated_at": time.time(),
            },
            "$setOnInsert": {"attempts": 0, "created_at": time.time()},
        },
        upsert=True,
    )
    return get(UPLOAD_PREFIX + image_key(folder, filename))


def count_uploads():
    return get_collection().count_documents(
        {"key": {"$regex": "^" + re.escape(UPLOAD_PREFIX)}}
    )


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


def remove_uploads_in_folder(folder):
    result = get_collection().delete_many(
        {
            "key": {
                "$regex": "^"
                + re.escape(UPLOAD_PREFIX)
                + re.escape(folder)
                + "/"
            }
        }
    )
    return result.deleted_count


def bump_upload_attempts(folder, filename):
    get_collection().update_one(
        {"key": UPLOAD_PREFIX + image_key(folder, filename)},
        {"$inc": {"attempts": 1}},
    )


def seed_from_disk(base_dir="."):
    """Bootstrap missing keys from the files committed to the repo.

    Per-key rather than all-or-nothing: a deployment that wrote settings but
    failed before the answer key must heal on the next boot instead of being
    permanently treated as already seeded.
    """
    def read_json(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    seeded = 0

    answer_path = os.path.join(base_dir, "answer_key.txt")
    if os.path.exists(answer_path) and not get(ANSWER_KEY):
        try:
            set(ANSWER_KEY, read_json(answer_path))
            seeded += 1
        except (ValueError, OSError):
            pass

    config_path = os.path.join(base_dir, "config.cfg")
    if os.path.exists(config_path) and not get(SETTINGS_KEY):
        settings = dict(DEFAULT_SETTINGS)
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("["):
                        k, v = line.split("=", 1)
                        settings[k.strip()] = v.strip()
            set(SETTINGS_KEY, settings)
            seeded += 1
        except OSError:
            pass

    for path in glob.glob(os.path.join(base_dir, "*_rolls.txt")):
        name = os.path.basename(path)[: -len(".txt")]
        if get(ROLLS_PREFIX + name):
            continue
        try:
            set_rolls(name, read_json(path))
            seeded += 1
        except (ValueError, OSError):
            pass

    return seeded > 0


def startup_maintenance():
    """Bring persisted state up to date on boot.

    Runs the image-index schema migration and the retention sweeps. Safe to
    call on every start: each step is idempotent.
    """
    migrated = migrate_legacy_images()
    stale_tasks = fail_stale_tasks()
    pruned_tasks = prune_tasks()
    pruned_results = prune_results()
    return {
        "migrated_images": migrated,
        "stale_tasks": stale_tasks,
        "pruned_tasks": pruned_tasks,
        "pruned_results": pruned_results,
    }
