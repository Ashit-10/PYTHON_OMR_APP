FROM python:3.10-slim

# Install system dependencies required by OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# One worker claims the boot lock; extra workers share the Mongo connection
# pool. The scan itself runs in a subprocess, so a long OpenCV job cannot block
# the request threads. The timeout covers streaming gallery publishing.
CMD ["sh", "-c", "gunicorn -w 2 --threads 4 -b 0.0.0.0:${PORT:-8000} --timeout 300 --graceful-timeout 30 --keep-alive 5 run_web:app"]
