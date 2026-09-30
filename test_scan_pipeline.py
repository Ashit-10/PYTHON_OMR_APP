"""Exercise process_omr_task without the OpenCV engine.

numpy/opencv are not installed in every environment, and the point of this
test is the plumbing around the engine: that a scan writes its result to
MongoDB, that it claims only its own output, that a filename collision is
resolved, and that a scan never deletes files in the repo root.

scan50/scan100 are replaced with a stub that writes a predictable result
image, so the assertions do not depend on OCV detection.
"""
import os
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mongomock

# Stand in for the OpenCV-dependent engine. The point of this test is the
# plumbing around the engine, not the detection itself.
RESULT_NAME = "42_17.jpg"


def make_stub_engine():
    def find_and_draw_squares(image_file, out_put_path, answer_key, caption,
                              has_darkness, allow_partial_mark):
        path = os.path.join(out_put_path, RESULT_NAME)
        if os.path.exists(path):
            base, ext = os.path.splitext(path)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            path = f"{base}_{i}{ext}"
        with open(path, "wb") as f:
            f.write(b"fake-jpeg")
        return [50, 17, 5, 28, 42, "", path]

    mod = types.ModuleType("engine_stub")
    mod.find_and_draw_squares = find_and_draw_squares
    return mod


stub = make_stub_engine()
sys.modules["scan50"] = stub
sys.modules["scan100"] = stub

# run_web calls db.init_db() at import time and refuses to start without a
# reachable Mongo, so point it at a syntactically valid dummy URL and hand it
# the in-process mongomock client via _install_mock_db().
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "omr_smoke")
os.environ.setdefault("DISABLE_SINGLETON_BOOT", "1")
os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("TELEGRAM_CHAT_ID", None)

import db


def _install_mock_db():
    db._client = mongomock.MongoClient()
    db.DB_NAME = "omr_smoke"
    return db


# run_web calls db.init_db() during import, which would swap the mock client
# for a real connection attempt. Neutralise it; the client installed by
# _install_mock_db() is what the rest of the test uses.
db.init_db = _install_mock_db


_install_mock_db()

workdir = tempfile.mkdtemp(prefix="omr_smoke_")
os.chdir(workdir)

import run_web

# run_web derives BASE from the CWD, so its folders live under workdir. The
# engine stub is reached through sys.modules, but process_omr_task still
# invokes the real `python3 autoapp.py` in a subprocess, so this test stubs
# the subprocess rather than running the engine.
db.set(db.ANSWER_KEY, {"1": "A"})

failures = []


def check(label, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(label)


check("parse_result_filename reads roll and marks",
      run_web.parse_result_filename("42_17.jpg") == {"roll": 42, "marks": 17},
      run_web.parse_result_filename("42_17.jpg"))
check("parse_result_filename ignores non-results",
      run_web.parse_result_filename("OMR_sheet_roll_42.jpg") is None,
      run_web.parse_result_filename("OMR_sheet_roll_42.jpg"))

try:
    run_web.get_safe_path("../../etc/passwd")
    traversal_blocked = False
except PermissionError:
    traversal_blocked = True
check("get_safe_path blocks traversal", traversal_blocked)

# --- the durable-result guarantee ---
os.makedirs(run_web.INPUT_FOLDER, exist_ok=True)
input_path = os.path.join(run_web.INPUT_FOLDER, "OMR_sheet_roll_42_1700000000.jpg")
with open(input_path, "wb") as f:
    f.write(b"fake-input")

db.set(db.ANSWER_KEY, {"1": "A"})

# run_web shells out to `python3 autoapp.py`, which cannot see the in-process
# engine stub, so stand in for that subprocess and write the expected result
# into the task's own output directory (argv[2]).
def _stub_popen(*args, **kwargs):
    """Stand in for the autoapp.py subprocess, writing the expected result into
    the task's own output directory (the last argv entry). Pass _fail=True to
    simulate an engine error."""
    argv = args[0] if args else kwargs.get("args")
    out_dir = argv[-1]
    fail = kwargs.get("_fail", False)

    class _Proc:
        def communicate(self):
            if fail:
                return b"", b"engine exploded"
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, RESULT_NAME), "wb") as f:
                f.write(b"fake-jpeg")
            return b"", b""

    return _Proc()

def _run_task(task_id, input_path, fail=False):
    real_popen = run_web.subprocess.Popen
    run_web.subprocess.Popen = lambda *a, **k: _stub_popen(*a, _fail=fail, **k)
    try:
        run_web.process_omr_task(task_id, input_path, os.path.basename(input_path))
    finally:
        run_web.subprocess.Popen = real_popen


_run_task("t1", input_path)

task = db.get_task("t1")
print(f"  task: {task}")
check("task completed", task and task.get("status") == "completed", task)
check("result persisted to MongoDB", db.get_result("t1") is not None, db.get_result("t1"))
res = db.get_result("t1") or {}
check("result carries roll and marks", res.get("roll") == 42 and res.get("marks") == 17, res)
check("result names the input sheet",
      res.get("input_filename") == os.path.basename(input_path), res)
out_name = (task or {}).get("output_filename", "")
check("output moved into output/",
      os.path.isfile(os.path.join(run_web.FINAL_OUTPUT_FOLDER, out_name)), out_name)
check("per-task scratch dir cleaned up",
      not os.path.isdir(os.path.join(run_web.OUTPUT_FOLDER, "t1")))

# --- a second scan of the same student/marks must not overwrite ---
_run_task("t2", input_path)

second = (db.get_task("t2") or {}).get("output_filename", "")
check("colliding result gets a distinct name", second != out_name, (out_name, second))
check("both results still on disk",
      os.path.isfile(os.path.join(run_web.FINAL_OUTPUT_FOLDER, out_name))
      and os.path.isfile(os.path.join(run_web.FINAL_OUTPUT_FOLDER, second)),
      (out_name, second))
check("second result persisted too", db.get_result("t2") is not None)

# --- a scan must never delete committed files in the repo root ---
canary = os.path.join(workdir, "omr_sheet_50_questions.jpg")
with open(canary, "wb") as f:
    f.write(b"committed")
_run_task("t3", input_path)
check("repo-root image survives a scan", os.path.isfile(canary), "canary was deleted")

# --- a failing engine must not report success ---
_run_task("t4", input_path, fail=True)
failed = db.get_task("t4") or {}
check("engine failure is reported as failed", failed.get("status") == "failed", failed)
check("failure reason is captured", "exploded" in str(failed.get("error", "")), failed)
check("no result written for a failed scan", db.get_result("t4") is None)

os.chdir("/")
shutil.rmtree(workdir, ignore_errors=True)

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
