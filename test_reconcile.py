"""Verify boot-time reconciliation and the single-worker boot lock.

reconcile_uploads() is the safety net for images whose upload failed before a
deploy. It used to run only under __main__, so gunicorn never called it and a
Telegram outage lost every image uploaded in that window.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import types

import fcntl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mongomock

stub = types.ModuleType("engine_stub")
stub.find_and_draw_squares = lambda *a, **k: None
sys.modules["scan50"] = stub
sys.modules["scan100"] = stub

os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["MONGO_DB"] = "omr_recon_test"
os.environ["DISABLE_SINGLETON_BOOT"] = "1"
os.environ.pop("PASSWORD", None)

import db


def _install_mock_db():
    db._client = mongomock.MongoClient()
    db.DB_NAME = "omr_recon_test"


db.init_db = _install_mock_db
_install_mock_db()

workdir = tempfile.mkdtemp(prefix="omr_recon_")
os.chdir(workdir)

import run_web
import telegram

failures = []


def check(label, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(label)


# Telegram must look configured or reconcile_uploads() returns early.
telegram.TELEGRAM_BOT_TOKEN = "123:fake"
telegram.TELEGRAM_CHAT_ID = "999"

# --- a file still on disk is recovered and indexed ---
recoverable = "11_5.jpg"
path = os.path.join(run_web.FINAL_OUTPUT_FOLDER, recoverable)
with open(path, "wb") as f:
    f.write(b"fake-jpeg")
db.queue_upload("output", recoverable, path)

sent = []


def fake_send(file_path, caption=""):
    sent.append(os.path.basename(file_path))
    return {"msg_id": len(sent), "file_id": f"f{len(sent)}", "chat_id": "999", "size": 9}


telegram.send_image = fake_send

recovered = run_web.reconcile_uploads()
check("queued upload is recovered", recovered == 1, recovered)
check("recovered file is indexed", db.get_image("output", recoverable) is not None)
check("recovered upload is dequeued",
      not any(u["filename"] == recoverable for u in db.get_uploads()),
      db.get_uploads())
check("recovery used the local copy", recoverable in sent, sent)

# --- an entry whose file is gone is dropped, not retried forever ---
db.queue_upload("output", "vanished.jpg", os.path.join(workdir, "gone", "vanished.jpg"))
lost = run_web.reconcile_uploads()
check("vanished entry does not count as recovered", lost == 0, lost)
check("vanished entry is cleaned up",
      not any(u["filename"] == "vanished.jpg" for u in db.get_uploads()),
      db.get_uploads())
check("vanished file is not indexed", db.get_image("output", "vanished.jpg") is None)

# --- an entry that still fails stays queued for the next attempt ---
retry = "12_6.jpg"
retry_path = os.path.join(run_web.FINAL_OUTPUT_FOLDER, retry)
with open(retry_path, "wb") as f:
    f.write(b"fake-jpeg")
db.queue_upload("output", retry, retry_path)
telegram.send_image = lambda *a, **k: None
run_web.UPLOAD_ATTEMPTS = 1
run_web.UPLOAD_RETRY_DELAY = 0
run_web.reconcile_uploads()
check("a still-failing entry stays queued",
      any(u["filename"] == retry for u in db.get_uploads()),
      db.get_uploads())
check("attempts are counted",
      next(u for u in db.get_uploads() if u["filename"] == retry)["attempts"] >= 1,
      db.get_uploads())

# --- with Telegram unconfigured, reconciliation is a no-op ---
telegram.TELEGRAM_BOT_TOKEN = ""
telegram.TELEGRAM_CHAT_ID = ""
check("unconfigured Telegram reconciles nothing", run_web.reconcile_uploads() == 0)

# --- the boot lock lets exactly one process win ---
# flock is per-process, so a child process has to hold the lock for this
# process to observe it as taken.
probe_dir = tempfile.mkdtemp(prefix="omr_lockprobe_")
lock_path = os.path.join(probe_dir, "omr_boot.lock")

holder_src = (
    "import fcntl, os, sys, time\n"
    "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o644)\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('HELD', flush=True)\n"
    "time.sleep(30)\n"
)
holder = subprocess.Popen(
    [sys.executable, "-c", holder_src, lock_path],
    stdout=subprocess.PIPE, text=True,
)
try:
    check("helper process acquired the lock", holder.stdout.readline().strip() == "HELD")

    # run_web reads the lock path from tempfile.gettempdir() at call time, so
    # point TMPDIR at the probe directory. DISABLE_SINGLETON_BOOT has to go,
    # since it is the documented bypass for single-process runs.
    old_tmp = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = probe_dir
    os.environ.pop("DISABLE_SINGLETON_BOOT", None)
    # gettempdir() memoises its result, so drop the cache for the new TMPDIR.
    import tempfile as _tempfile

    _tempfile.tempdir = None

    check("a held boot lock excludes a second claim",
          run_web.claim_boot_side_effects() is False)

    _tempfile.tempdir = None
    if old_tmp is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = old_tmp
    os.environ["DISABLE_SINGLETON_BOOT"] = "1"
finally:
    holder.kill()
    holder.wait(timeout=10)
    shutil.rmtree(probe_dir, ignore_errors=True)

# The env override must let a single-process run claim the lock.
check("DISABLE_SINGLETON_BOOT bypasses the lock",
      run_web.claim_boot_side_effects() is True)

os.chdir("/")
shutil.rmtree(workdir, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
