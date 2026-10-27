"""End-to-end checks for the refreshed dashboard and image serving.

These use Flask's test client and mongomock, so they exercise template
rendering, task-scoped status, pagination, the safe image path gate and the
managed delete path without OpenCV or a live server.
"""
import os
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
os.environ["MONGO_DB"] = "omr_web_ui_test"
os.environ["PASSWORD"] = ""
os.environ["SECRET_KEY"] = "web-ui-test"
os.environ["DISABLE_SINGLETON_BOOT"] = "1"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)

import db


def _install_mock_db():
    db._client = mongomock.MongoClient()
    db.DB_NAME = "omr_web_ui_test"


db.init_db = _install_mock_db
_install_mock_db()

workdir = tempfile.mkdtemp(prefix="omr_web_ui_")
os.chdir(workdir)

import run_web

failures = []


def check(label, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(label)


client = run_web.app.test_client()

# Fake image bytes are enough for /file; /thumb falls back to the original
# when Pillow cannot decode them.
out_name = "42_17.jpg"
out_path = os.path.join(run_web.FINAL_OUTPUT_FOLDER, out_name)
with open(out_path, "wb") as f:
    f.write(b"fake-jpeg-output")
in_name = "OMR_sheet_roll_42_1.jpg"
with open(os.path.join(run_web.INPUT_FOLDER, in_name), "wb") as f:
    f.write(b"fake-jpeg-input")
with open(os.path.join(workdir, ".env"), "w", encoding="utf-8") as f:
    f.write("SECRET_SHOULD_NOT_LEAK=1\n")

db.add_folder("output")
db.put_image("output", out_name, {"file_id": "fid", "mtime": os.path.getmtime(out_path)})
db.put_result("task-old", {"output_filename": out_name, "roll": 42, "marks": 17})
db.update_task(
    "task-old",
    {"status": "completed", "input_filename": in_name, "output_filename": out_name,
     "roll": 42, "marks": 17},
    defaults={"status": "queued"},
)
db.update_task(
    "task-new",
    {"status": "completed", "input_filename": "other.jpg", "output_filename": "7_9.jpg",
     "roll": 7, "marks": 9},
    defaults={"status": "queued"},
)

# --- pages render ---
r = client.get("/")
check("dashboard renders", r.status_code == 200 and b"Project folders" in r.data, r.status_code)
check("folder cards carry a JS-safe target",
      b'data-folder="input"' in r.data and b'onclick="openFolder' not in r.data,
      r.status_code)
r = client.get("/browse?path=output")
check("browser renders an image", r.status_code == 200 and out_name.encode() in r.data, r.status_code)
check("browser links the thumbnail", b"/thumb?path=" in r.data, r.status_code)
r = client.get("/browse?path=output&page=1")
check("browse pagination parameter accepted", r.status_code == 200, r.status_code)
r = client.get("/results")
check("live results page renders", r.status_code == 200 and b"Live results" in r.data, r.status_code)
r = client.get("/answer_key")
check("answer-key editor renders", r.status_code == 200, r.status_code)

# --- task-scoped status, not whichever task happens to be newest ---
r = client.get("/status?task_id=task-old")
data = r.get_json()
check("status is scoped to the requested task", data.get("roll") == 42 and data.get("marks") == 17, data)
r = client.get("/status?task_id=does-not-exist")
data = r.get_json()
check("unknown task is an error, not another student's result", data.get("error") is True, data)

# --- image serving is restricted to managed image folders ---
r = client.get(f"/file?path=output/{out_name}")
check("managed output image is served", r.status_code == 200 and r.data == b"fake-jpeg-output", r.status_code)
r = client.get(f"/thumb?path=output/{out_name}")
check("thumbnail route falls back to the original", r.status_code == 200, r.status_code)
for blocked in (".env", "run_web.py", "certs/key.pem"):
    r = client.get(f"/file?path={blocked}")
    check(f"/file refuses {blocked}", r.status_code == 403, r.status_code)

# --- delete is limited to managed paths and removes the index entry ---
r = client.post("/delete", json={"path": ".env"})
check("delete refuses an unmanaged path", r.status_code == 403, r.status_code)
r = client.post("/delete", json={"path": f"output/{out_name}"})
check("delete removes a managed image", r.status_code == 200, r.status_code)
check("deleted image is gone from disk", not os.path.exists(out_path))
check("deleted image is gone from the index", db.get_image("output", out_name) is None)

# --- input validation on roll saves ---
r = client.post("/save_rolls", json={"filename": "mvm_class-10_rolls.txt", "students": "nope"})
check("invalid roll payload is rejected", r.status_code == 400, r.status_code)

r = client.get("/recheck_status")
check("recheck status returns JSON", r.status_code == 200 and "running" in r.get_json(), r.status_code)

if failures:
    print(f"\n{len(failures)} check(s) failed")
    sys.exit(1)
print("\nall checks passed")
