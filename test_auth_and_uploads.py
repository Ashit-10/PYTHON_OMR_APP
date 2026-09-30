"""Verify the auth gate and the Telegram upload fallback.

Two guarantees:
  1. Image routes require a session when PASSWORD is set. They used to be
     whitelisted in before_request, making every answer sheet public.
  2. A failed Telegram upload is queued durably rather than silently dropped.
"""
import os
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mongomock

stub = types.ModuleType("engine_stub")
stub.find_and_draw_squares = lambda *a, **k: None
sys.modules["scan50"] = stub
sys.modules["scan100"] = stub

os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["MONGO_DB"] = "omr_auth_test"
os.environ["PASSWORD"] = "letmein"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DISABLE_SINGLETON_BOOT"] = "1"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)

import db


def _install_mock_db():
    db._client = mongomock.MongoClient()
    db.DB_NAME = "omr_auth_test"


db.init_db = _install_mock_db
_install_mock_db()

workdir = tempfile.mkdtemp(prefix="omr_auth_")
os.chdir(workdir)

import run_web
import telegram

failures = []


def check(label, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(label)


client = run_web.app.test_client()

# Seed an image so the protected routes have something to serve.
out_name = "42_17.jpg"
with open(os.path.join(run_web.FINAL_OUTPUT_FOLDER, out_name), "wb") as f:
    f.write(b"fake-jpeg")
in_name = "OMR_sheet_roll_42_1.jpg"
with open(os.path.join(run_web.INPUT_FOLDER, in_name), "wb") as f:
    f.write(b"fake-input")

# --- 1. image routes must not be public ---
for label, url in [
    ("/file", f"/file?path=output/{out_name}"),
    ("/temp_output", f"/temp_output/{out_name}"),
    ("/temp_input", f"/temp_input/{in_name}"),
]:
    r = client.get(url)
    check(f"{label} blocked without login", r.status_code in (301, 302, 401, 403), r.status_code)

r = client.get("/browse?path=output")
check("/browse blocked without login", r.status_code in (301, 302, 401, 403), r.status_code)

# The liveness probe and static assets must stay reachable.
r = client.get("/healthz")
check("/healthz stays public", r.status_code == 200, r.status_code)

# --- 2. after logging in, the image is served ---
r = client.post("/login", data={"password": "letmein"}, follow_redirects=False)
check("login succeeds with the right password", r.status_code in (301, 302), r.status_code)

r = client.get(f"/file?path=output/{out_name}")
check("/file serves the image once authenticated", r.status_code == 200, r.status_code)
check("served bytes match", r.data == b"fake-jpeg", r.data[:20])

r = client.get(f"/temp_output/{out_name}")
check("/temp_output serves once authenticated", r.status_code == 200, r.status_code)

# A wrong password must not grant access.
client2 = run_web.app.test_client()
client2.post("/login", data={"password": "wrong"})
r = client2.get(f"/file?path=output/{out_name}")
check("wrong password grants no access", r.status_code in (301, 302, 401, 403), r.status_code)

# --- 3. a failed Telegram upload is queued, not dropped ---
os.environ["TELEGRAM_BOT_TOKEN"] = "123:fake"
os.environ["TELEGRAM_CHAT_ID"] = "999"
telegram.TELEGRAM_BOT_TOKEN = "123:fake"
telegram.TELEGRAM_CHAT_ID = "999"

calls = {"n": 0}


def always_fail(*a, **k):
    calls["n"] += 1
    return None


telegram.send_image = always_fail
run_web.UPLOAD_ATTEMPTS = 2
run_web.UPLOAD_RETRY_DELAY = 0

before = len(db.get_uploads())
# store_image() skips a file that is not on disk, so create the targets.
for name in ("99_5.jpg", "88_4.jpg"):
    with open(os.path.join(run_web.FINAL_OUTPUT_FOLDER, name), "wb") as f:
        f.write(b"fake-jpeg")

run_web.store_image("output", "99_5.jpg")
queued = db.get_uploads()
check("failed upload is queued", len(queued) == before + 1, queued)
check("upload was retried", calls["n"] == 2, calls["n"])

entry = next((u for u in queued if u["filename"] == "99_5.jpg"), None)
check("queue entry records the folder", entry and entry["folder"] == "output", entry)
check("queue entry records the path", entry and entry["file_path"].endswith("99_5.jpg"), entry)

# A succeeding upload must clear the queue entry.
telegram.send_image = lambda *a, **k: {"msg_id": 1, "file_id": "f1", "chat_id": "999", "size": 9}
run_web.store_image("output", "99_5.jpg")
check("successful upload clears the queue",
      not any(u["filename"] == "99_5.jpg" for u in db.get_uploads()),
      db.get_uploads())
check("successful upload is indexed",
      db.get_image("output", "99_5.jpg") is not None)

# With Telegram unconfigured the image must still be queued, not discarded.
telegram.TELEGRAM_BOT_TOKEN = ""
telegram.TELEGRAM_CHAT_ID = ""
run_web.store_image("output", "88_4.jpg")
check("unconfigured Telegram still queues",
      any(u["filename"] == "88_4.jpg" for u in db.get_uploads()),
      db.get_uploads())

# A missing local file must not create a phantom queue entry.
before = len(db.get_uploads())
run_web.store_image("output", "does_not_exist.jpg")
check("missing file is not queued", len(db.get_uploads()) == before, db.get_uploads())

os.chdir("/")
shutil.rmtree(workdir, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
