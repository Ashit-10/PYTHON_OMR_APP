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
   - `PASSWORD` (Optional): Set a secure password to protect your dashboard access.
   - `TELEGRAM_BOT_TOKEN` (Optional): For Telegram result sharing.
   - `TELEGRAM_CHAT_ID` (Optional): Chat ID for Telegram notifications.
   - `GITHUB_TOKEN` (Optional): For GitHub rolls synchronization.
6. Click **Deploy**. Once running, access your app via your Koyeb public URL!

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
