# 📊 Python OMR Evaluation Web App (Koyeb Ready)

A fast, web-based **OMR (Optical Mark Recognition) Scanner & Evaluation System** built with Flask and OpenCV. Designed for automated exam grading, instant feedback, and multi-device access via cloud deployment (Koyeb).

---

## ✨ Features

- **Fast & Lightweight**: Powered by Gunicorn, OpenCV headless, and NumPy.
- **Multi-Device Cloud Access**: Host on Koyeb and access from any device anywhere.
- **Password Protection**: Secure your dashboard with a custom password (`PASSWORD` environment variable).
- **Flexible Question Support**: Supports 50 and 100-question OMR sheets.
- **Roll Number Detection**: Accurate student roll number recognition.
- **Answer Key & Signature Customization**: Easily update answer keys and signature stamps on evaluated sheets.
- **Terminal Logging**: Complete application logs streamed directly to your Koyeb terminal.

---

## 🚀 Deploying on Koyeb

1. Push this repository to your GitHub account.
2. Go to the [Koyeb Dashboard](https://app.koyeb.com/) and click **Create Web Service**.
3. Select **GitHub** as your deployment source and choose your repository.
4. Keep the builder as **Dockerfile** (the repository includes a pre-configured `Dockerfile` with OpenCV system dependencies).
5. Add the following **Environment Variables** in Koyeb:
   - `MONGO_URL` (**Required**): MongoDB connection string. The app refuses to
     start without it, since the durable index lives there.
   - `TELEGRAM_BOT_TOKEN` (**Recommended**): Bot token used to back up and
     restore images.
   - `TELEGRAM_CHAT_ID` (**Recommended**): The chat holding the stored images.
     **The bot must stay a member of this chat and its history must not be
     cleared**, otherwise every stored image becomes unrecoverable.
   - `PASSWORD` (Optional): Set a secure password to protect the dashboard.
   - `SECRET_KEY` (**Recommended**): Long random string for Flask sessions.
   - `GITHUB_TOKEN` (Optional): For gallery and roll-list publishing.
   - `SELF_PING_URL` (Optional): Your public URL plus `/healthz`, e.g.
     `https://your-app.koyeb.app/healthz`. `SELF_PING_INTERVAL` (default
     `300`) and `DISABLE_SELF_PING=1` are also supported.
   - `SYNC_INTERVAL` (default `1800`): Seconds between Telegram upload batches.
     `SYNC_ON_START=0` disables the initial flush, `RESTORE_ON_BOOT=0` disables
     the background download of Telegram-backed images.
   - `SCAN_TIMEOUT` (default `180`): Hard limit for one OpenCV subprocess.
   - `MAX_UPLOAD_MB` (default `25`): Maximum accepted camera upload.
   - `COOKIE_SECURE=1`: Mark the login cookie Secure when serving over HTTPS.
   - `CONFIG_CACHE_TTL` / `SETTINGS_CACHE_TTL` (default `60` / `30`): Seconds
     to cache the answer key/settings read by scans.
   - `FOLDERS_CACHE_TTL` (default `30`): Folder-list cache used by browse and
     thumbnail requests.
   - `UPLOAD_ATTEMPTS` / `UPLOAD_RETRY_DELAY` (default `2` / `2s`): Immediate
     Telegram retry budget before an image waits for the next batch.
6. Click **Deploy**. Once running, access your app via your Koyeb public URL!

### Where your data lives

| Data | Stored in |
| --- | --- |
| Settings, answer key, roll lists, folder list, scan tasks/results | MongoDB |
| Image metadata (`file_id`, folder, mtime) | MongoDB |
| Image bytes | Local disk cache first; Telegram backup in 30-minute batches |

The container filesystem is ephemeral. The app therefore serves local files
while they exist and falls back to downloading the Telegram copy (or a
thumbnail) on demand. At boot, a background worker restores missing images
and queues any new on-disk files. On first boot, missing keys are seeded
per-key from `config.cfg`, `answer_key.txt` and `*_rolls.txt`.

Each scan runs in its own subprocess and receives the answer key and settings
in a small `scan_config.json`, so the OpenCV process does not connect to
MongoDB at all. A scan commits its score to MongoDB before the image upload is
queued.

---

## 💻 Local Development & Testing

If you want to run the app locally:

```bash
git clone https://github.com/Ashit-10/PYTHON_OMR_APP
cd PYTHON_OMR_APP
pip install -r requirements-dev.txt
export MONGO_URL='mongodb://localhost:27017'
export MONGO_DB='omr'
python3 run_web.py
```

Open `http://localhost:8000` in your browser. Localhost Mongo URLs may omit a
username; remote URLs must include one. The test suite uses `mongomock`:

```bash
python3 test_persistence.py
python3 test_scan_pipeline.py
python3 test_auth_and_uploads.py
python3 test_reconcile.py
python3 test_web_ui.py
python3 test_engine_eval.py   # skipped automatically without OpenCV
```

### Background work

- Telegram uploads are queued locally and flushed every 30 minutes (or from
  **Sync Telegram now** in the dashboard).
- Missing images are restored from Telegram in the background after boot.
- Recheck runs in the background and reports progress through
  `/recheck_status`; it no longer blocks the request for the whole batch.
- `/status?task_id=...` is a single indexed lookup. The live camera UI always
  passes its own task id, so a new scan cannot show the previous student's
  result.
