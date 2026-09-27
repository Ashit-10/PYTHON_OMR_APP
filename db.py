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

from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("MONGO_DB", "omr")
COLLECTION = "omr_state"

SETTINGS_KEY = "settings"
ANSWER_KEY = "answer_key"
FOLDERS_KEY = "folders"
TASKS_KEY = "tasks"
ROLLS_PREFIX = "rolls:"

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


def init_db():
    """Connect, verify reachability and ensure indexes. Raises on failure."""
    global _client

    if not MONGO_URL:
        raise RuntimeError(
            "MONGO_URL environment variable is not set. "
            "Durable state cannot be stored; refusing to start."
        )

    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except PyMongoError as e:
        raise RuntimeError(f"MongoDB at MONGO_URL is unreachable: {e}") from e

    with _lock:
        _client = client

    get_collection().create_index([("key", ASCENDING)], unique=True)


def get(key, default=None):
    doc = get_collection().find_one({"key": key})
    return doc["value"] if doc else default


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
    return (get(TASKS_KEY) or {}).get(task_id)


def set_task(task_id, data):
    with _lock:
        tasks = get(TASKS_KEY) or {}
        tasks[task_id] = data
        set(TASKS_KEY, tasks)
    return data


def all_tasks():
    return get(TASKS_KEY) or {}


IMAGES_KEY = "images"

# Mongo caps a single document at 16 MB. ~200 bytes per entry means this is
# roughly 70k images; the guard just makes sure we notice before Mongo does.
IMAGES_MAX_ENTRIES = 60000


def image_key(folder, filename):
    """Single place the image identifier is built, so uploads and lookups
    cannot drift apart."""
    return f"{folder}/{filename}".strip("/")


def get_images():
    return get(IMAGES_KEY) or {}


def get_image(folder, filename):
    return get_images().get(image_key(folder, filename))


def put_image(folder, filename, meta):
    with _lock:
        images = get_images()
        key = image_key(folder, filename)
        if key not in images and len(images) >= IMAGES_MAX_ENTRIES:
            raise RuntimeError(
                f"Image index is full ({len(images)} entries). "
                "Remove some images before uploading more."
            )
        images[key] = meta
        set(IMAGES_KEY, images)
    return meta


def remove_image(folder, filename):
    with _lock:
        images = get_images()
        images.pop(image_key(folder, filename), None)
        set(IMAGES_KEY, images)


def remove_images_in_folder(folder):
    """Drop every image entry for a folder. Returns the number removed."""
    prefix = f"{folder}/"
    with _lock:
        images = get_images()
        keys = [k for k in images if k.startswith(prefix)]
        for k in keys:
            del images[k]
        set(IMAGES_KEY, images)
    return len(keys)


def list_images(folder=None):
    """Stored image metadata, optionally limited to one folder."""
    images = get_images()
    if folder is None:
        return images
    prefix = f"{folder}/"
    return {
        k[len(prefix):]: v for k, v in images.items() if k.startswith(prefix)
    }


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
