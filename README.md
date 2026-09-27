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
     start without it, since all durable state lives there.
   - `TELEGRAM_BOT_TOKEN` (**Required** for image storage): Bot token used to
     store and restore images.
   - `TELEGRAM_CHAT_ID` (**Required** for image storage): The chat holding the
     stored images. **The bot must stay a member of this chat and its history
     must not be cleared**, otherwise every stored image becomes unrecoverable.
   - `PASSWORD` (Optional): Set a secure password to protect your dashboard access.
   - `GITHUB_TOKEN` (Optional): For GitHub rolls synchronization.
   - `SELF_PING_URL` (Optional): Your public URL plus `/healthz`, e.g.
     `https://your-app.koyeb.app/healthz`. Keeps the instance awake by hitting
     it every 5 minutes. `SELF_PING_INTERVAL` (default `300`) and
     `DISABLE_SELF_PING=1` are also supported.
6. Click **Deploy**. Once running, access your app via your Koyeb public URL!

### Where your data lives

| Data | Stored in |
| --- | --- |
| Settings, answer key, roll lists, folder list, scan state | MongoDB |
| Images | Telegram (only the `file_id` is kept in MongoDB) |

Because the container filesystem is ephemeral, nothing durable is written to
disk. On first boot an empty database is seeded from the `config.cfg`,
`answer_key.txt` and `*_rolls.txt` files committed in this repo.

---

## 💻 Local Development & Testing

If you want to run the app locally:

```bash
git clone https://github.com/Ashit-10/PYTHON_OMR_APP
cd PYTHON_OMR_APP
pip install -r requirements.txt
python3 run_web.py
```

Open `http://localhost:8000` in your browser.
