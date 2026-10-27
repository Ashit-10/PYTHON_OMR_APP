"""Telegram Bot API client used as durable image storage.

Each image is uploaded as its own document so it can be restored on its own.
Only the message/file ids are persisted (in Mongo); Telegram holds the bytes.

Note: a bot can only fetch a file while it still has access to the chat holding
it, so the bot must stay a member of TELEGRAM_CHAT_ID and that chat must not be
cleared. Deleting an image in the UI therefore only drops the Mongo entry and
never touches Telegram.
"""
import os
import logging
import time
import uuid

import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

API_ROOT = "https://api.telegram.org"
REQUEST_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 300

logger = logging.getLogger("omr.telegram")


def is_configured():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _require_config():
    if not is_configured():
        raise RuntimeError(
            "Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )


def _api_url(method):
    return f"{API_ROOT}/bot{TELEGRAM_BOT_TOKEN}/{method}"


def send_image(file_path, caption=""):
    """Upload one image and return its storage metadata.

    Returns {"msg_id", "file_id", "chat_id", "size"} or None on failure.
    """
    _require_config()

    response = None
    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                payload = {"chat_id": TELEGRAM_CHAT_ID}
                if caption:
                    payload["caption"] = caption
                files = {"document": (os.path.basename(file_path), f)}
                response = requests.post(
                    _api_url("sendDocument"),
                    data=payload,
                    files=files,
                    timeout=REQUEST_TIMEOUT,
                )
        except Exception as e:
            logger.error(f"Telegram upload failed for {file_path}: {e}")
            return None

        if response.ok:
            break
        if response.status_code == 429 or response.status_code >= 500:
            try:
                retry_after = int(response.json().get("parameters", {}).get("retry_after", 2))
            except ValueError:
                retry_after = 2
            logger.warning("Telegram upload throttled; retrying in %ss", retry_after)
            time.sleep(min(retry_after, 30))
            continue

        logger.error(
            f"Telegram upload failed for {file_path} "
            f"({response.status_code}): {response.text[:200]}"
        )
        return None

    if response is None or not response.ok:
        logger.error(f"Telegram upload failed for {file_path} after retries")
        return None

    try:
        message = response.json()["result"]
        document = message["document"]
        return {
            "msg_id": message["message_id"],
            "file_id": document["file_id"],
            "chat_id": str(message["chat"]["id"]),
            "size": document.get("file_size", os.path.getsize(file_path)),
        }
    except (ValueError, KeyError) as e:
        logger.error(f"Unexpected Telegram upload response: {e}")
        return None


def get_file(file_id):
    """Resolve a file_id to {"file_id", "file_unique_id", "file_path"}.

    The resolved file_path is only valid for about an hour, so callers must
    re-resolve rather than cache the resulting URL.
    """
    _require_config()

    try:
        response = requests.get(
            _api_url("getFile"), params={"file_id": file_id}, timeout=REQUEST_TIMEOUT
        )
    except Exception as e:
        logger.error(f"Telegram getFile failed: {e}")
        return None

    if not response.ok:
        logger.error(f"Telegram getFile failed ({response.status_code}): {response.text[:200]}")
        return None

    try:
        return response.json()["result"]
    except (ValueError, KeyError) as e:
        logger.error(f"Unexpected Telegram getFile response: {e}")
        return None


def file_url(file_id):
    """Return a temporary download URL, or None if the file is unreachable."""
    info = get_file(file_id)
    if not info or not info.get("file_path"):
        return None
    return f"{API_ROOT}/file/bot{TELEGRAM_BOT_TOKEN}/{info['file_path']}"


def download(file_id, dest_path):
    """Download a file_id to dest_path atomically. Returns True on success.

    Writing straight to dest_path meant a timeout left a truncated image that
    looked valid to every later request. A sibling .part file is only renamed
    into place after the complete body has arrived.
    """
    url = file_url(file_id)
    if not url:
        return False

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    # Unique per attempt: the boot restore thread and an on-demand /file
    # request can otherwise write the same .part file at the same time.
    part_path = f"{dest_path}.{uuid.uuid4().hex}.part"
    try:
        with requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True) as response:
            response.raise_for_status()
            with open(part_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        os.replace(part_path, dest_path)
    except Exception as e:
        logger.error(f"Telegram download failed for {dest_path}: {e}")
        try:
            os.remove(part_path)
        except OSError:
            pass
        return False

    return True
