"""Run the real scan50/scan100 engines against the committed sample sheets.

test_scan_pipeline stubs the engine out, which is right for testing the
plumbing but means the OCV path is never exercised. That is how a run of
regressions survived the MongoDB migration, including one where every web
scan wrote its result outside the task directory and the task was then
reported as failed.

This test drives find_and_draw_squares for real and asserts the contract the
web pipeline depends on: the graded image lands *inside* the directory it was
given, and the score in the filename matches the returned tuple.

Skipped automatically when OpenCV or the sample sheets are unavailable.
"""
import glob
import json
import os
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import mongomock
except ImportError:
    print("SKIP  mongomock is not installed (pip install -r requirements.txt)")
    sys.exit(0)

try:
    import cv2  # noqa: F401
except ImportError:
    print("SKIP  OpenCV is not installed (pip install opencv-python-headless)")
    sys.exit(0)

# scan50/scan100 read db.get_settings() at call time for the pixel thresholds.
# A stub keeps this test off a live Mongo without importing run_web, which would
# call db.init_db() as a side effect of import.
_settings_stub = types.ModuleType("db")
_settings_stub.get_settings = lambda: {}
sys.modules["db"] = _settings_stub

import scan50
import scan100

# The engines open their bubble-coordinate files by bare relative name, so the
# scan has to run with the repo root as the working directory.
os.chdir(HERE)

SHEET_50 = "omr_sheet_50_questions.jpg"
SHEET_100 = "omr_sheet_100_questions.jpg"

failures = []
skipped = []


def check(label, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {label}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(label)


def skip(label, why):
    print(f"SKIP  {label}  <- {why}")
    skipped.append(label)


def run_engine(engine, sheet, answer_key, out_dir):
    """Call the engine and return its result tuple."""
    return engine.find_and_draw_squares(
        sheet, out_dir, answer_key, "", None, None
    )


def check_engine(label, engine, sheet, answer_key_path):
    """Assert one engine grades a sheet into the directory it was handed.

    The output-location assertion is the regression guard: the engine used to
    concatenate the path, so passing a directory without a trailing slash
    (exactly what run_web does) wrote the image outside it.
    """
    if not os.path.isfile(sheet):
        skip(f"{label} sheet present", f"{sheet} not found")
        return
    if not os.path.isfile(answer_key_path):
        skip(f"{label} answer key present", f"{answer_key_path} not found")
        return

    with open(answer_key_path, "r", encoding="utf-8") as f:
        answer_key = json.load(f)

    workdir = tempfile.mkdtemp(prefix="omr_engine_")
    try:
        # Deliberately no trailing slash: this is the shape run_web passes.
        out_dir = os.path.join(workdir, "task-out")
        os.makedirs(out_dir, exist_ok=True)

        try:
            result = run_engine(engine, sheet, answer_key, out_dir)
        except Exception as e:
            check(f"{label} engine runs without raising", False, repr(e))
            return
        check(f"{label} engine runs without raising", True)

        produced = os.listdir(out_dir)
        check(
            f"{label} writes inside the given directory",
            len(produced) == 1,
            f"expected 1 file in {out_dir}, found {produced}",
        )
        if not produced:
            return

        out_file = produced[0]
        out_path = os.path.join(out_dir, out_file)
        check(f"{label} output file is non-empty",
              os.path.getsize(out_path) > 0, out_path)

        # The web pipeline recovers roll and marks by parsing this filename, so
        # it must stay "<roll>_<marks>.jpg".
        total, correct, blank, wrong, roll, _err, returned_name = result
        stem = os.path.splitext(out_file)[0]
        parts = stem.split("_")
        check(
            f"{label} filename encodes roll and marks",
            len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit(),
            f"{out_file} (roll={roll!r} correct={correct})",
        )
        check(
            f"{label} filename matches the returned score",
            len(parts) >= 2 and int(parts[1]) == correct,
            f"{out_file} vs correct={correct}",
        )
        check(
            f"{label} filename matches the returned roll",
            len(parts) >= 1 and parts[0] == str(roll),
            f"{out_file} vs roll={roll}",
        )
        check(
            f"{label} returned path is the written file",
            returned_name and os.path.abspath(returned_name) == os.path.abspath(out_path),
            f"returned={returned_name} actual={out_path}",
        )
        check(
            f"{label} score components sum to the total",
            correct + wrong + blank == total,
            f"correct={correct} wrong={wrong} blank={blank} total={total}",
        )
        print(f"      -> {label}: roll={roll} correct={correct}/{total} "
              f"wrong={wrong} blank={blank}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


print()
print("--- real engine, 50-question sheet ---")
check_engine("scan50", scan50, SHEET_50, "answer_key.txt")

print()
print("--- real engine, 100-question sheet ---")
check_engine("scan100", scan100, SHEET_100, "answer_key.txt")

# The answer key can arrive from Mongo as either a dict or a JSON string (the
# web form posts JSON.stringify output). Both must evaluate identically; the
# string form used to be opened as a file path and raise FileNotFoundError.
print()
print("--- answer key stored as a JSON string ---")
if os.path.isfile(SHEET_50) and os.path.isfile("answer_key.txt"):
    with open("answer_key.txt", "r", encoding="utf-8") as f:
        dict_key = json.load(f)
    json_key = json.dumps(dict_key, indent=2)

    workdir = tempfile.mkdtemp(prefix="omr_engine_key_")
    try:
        results = {}
        for label, key in (("dict", dict_key), ("string", json_key)):
            out_dir = os.path.join(workdir, f"out-{label}")
            os.makedirs(out_dir, exist_ok=True)
            try:
                results[label] = run_engine(scan50, SHEET_50, key, out_dir)
            except Exception as e:
                check(f"string answer key evaluates like a dict ({label})",
                      False, repr(e))
                results[label] = None
        if results.get("dict") and results.get("string"):
            check(
                "string answer key evaluates like a dict",
                results["string"][:5] == results["dict"][:5],
                f"{results['string'][:5]} vs {results['dict'][:5]}",
            )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
else:
    skip("string answer key parity", "sample sheet or answer key missing")

# A directory that already holds a result must not clobber it: concurrent
# scans share the output folder, and safe_imwrite disambiguates the name.
print()
print("--- output directory collision ---")
if os.path.isfile(SHEET_50) and os.path.isfile("answer_key.txt"):
    with open("answer_key.txt", "r", encoding="utf-8") as f:
        dict_key = json.load(f)
    workdir = tempfile.mkdtemp(prefix="omr_engine_clash_")
    try:
        names = []
        for _ in range(2):
            out_dir = os.path.join(workdir, "shared")
            os.makedirs(out_dir, exist_ok=True)
            try:
                result = run_engine(scan50, SHEET_50, dict_key, out_dir)
                names.append(os.path.basename(result[6]))
            except Exception as e:
                check("second scan into the same dir does not clobber",
                      False, repr(e))
                break
        if len(names) == 2:
            check("second scan into the same dir does not clobber",
                  len(set(names)) == 2, names)
            check("both results remain on disk",
                  len(os.listdir(os.path.join(workdir, "shared"))) == 2,
                  os.listdir(os.path.join(workdir, "shared")))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
else:
    skip("collision handling", "sample sheet or answer key missing")

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
if skipped:
    print(f"({len(skipped)} skipped)")
