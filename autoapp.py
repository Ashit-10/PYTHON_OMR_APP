"""OMR engine runner.

Processes one uploaded sheet and writes the evaluated result to an output
directory supplied by the caller. Each run gets its own output directory and
its own input file, so the result is unambiguous even when several scans are
queued.

The web app writes a small ``scan_config.json`` next to the task output. When
present, this process never connects to MongoDB: the answer key and settings
are already in the file. That removes a TLS/Mongo handshake from every scan.
The database is still used as a fallback for standalone/CLI use.

Usage (as invoked by run_web.process_omr_task):
    python3 autoapp.py <input_file> <output_dir>
"""
import json
import os
import shutil
import sys
import time

import scan50 as s50
import scan100 as s100

CONFIG_NAME = "scan_config.json"
ERR_DIR = "error_images"


def normalize_answer_key(answer_key):
    """Return the answer key as a dict.

    The web form stores the key as a JSON string while the seed path stores a
    dict, so sizing or iterating a raw string misroutes 50-question sheets into
    the 100-question engine.
    """
    if isinstance(answer_key, (bytes, str)):
        answer_key = json.loads(answer_key)
    return answer_key


def load_scan_config(output_dir):
    """Load the per-task config written by run_web, if it exists."""
    path = os.path.join(output_dir, CONFIG_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Could not read scan config {path}: {e}")
        return None
    if not isinstance(data, dict) or not data.get("answer_key"):
        return None
    return data


def apply_config(config):
    """Inject settings into the engines so they never query Mongo."""
    settings = config.get("settings") or {}
    s50.configure(settings)
    s100.configure(settings)


def evaluate(image_file, out_put_path, answer_key, caption, has_darkness, allow_partial_mark):
    answer_key = normalize_answer_key(answer_key)
    if len(answer_key) < 51:
        return s50.find_and_draw_squares(
            image_file, out_put_path, answer_key, caption, has_darkness,
            allow_partial_mark,
        )
    return s100.find_and_draw_squares(
        image_file, out_put_path, answer_key, caption, has_darkness,
        allow_partial_mark,
    )


def _copy_error(photo, source):
    try:
        dest = os.path.join(ERR_DIR, photo)
        if os.path.exists(dest):
            base, ext = os.path.splitext(photo)
            i = 1
            while os.path.exists(os.path.join(ERR_DIR, f"{base}_{i}{ext}")):
                i += 1
            dest = os.path.join(ERR_DIR, f"{base}_{i}{ext}")
        shutil.copy(source, dest)
    except OSError as copy_error:
        print(f"Could not copy {photo} to {ERR_DIR}: {copy_error}")


def main():
    start_time = time.time()

    if len(sys.argv) > 1:
        photos = [os.path.basename(sys.argv[1])]
        input_dir = os.path.dirname(os.path.abspath(sys.argv[1]))
    else:
        input_dir = "temp_input"
        photos = sorted(os.listdir(input_dir)) if os.path.isdir(input_dir) else []

    output_dir = sys.argv[2] if len(sys.argv) > 2 else "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(ERR_DIR, exist_ok=True)

    config = load_scan_config(output_dir)
    if config:
        answer_key = config["answer_key"]
        apply_config(config)
        # The web app discards this scratch directory; a standalone run may
        # reuse temp_output, so remove the frozen config to avoid grading a
        # later sheet with an older answer key.
        try:
            os.remove(os.path.join(output_dir, CONFIG_NAME))
        except OSError:
            pass
    else:
        # Standalone/CLI fallback. The web path always supplies a config file.
        import db
        db.init_db()
        answer_key = db.get(db.ANSWER_KEY)
        if not answer_key:
            print("No answer key found in MongoDB.")
            return 1
        try:
            s50.configure(db.get_settings())
            s100.configure(db.get_settings())
        except Exception as e:
            print(f"Could not load settings from MongoDB: {e}")

    failures = 0
    for photo in photos:
        if not photo.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        source = os.path.join(input_dir, photo)
        if not os.path.isfile(source):
            print(f"Skipping missing input: {source}")
            continue

        caption = None
        if "_roll_" in photo:
            caption = photo.split("_roll_")[1].split("_")[0]

        print()
        print("-----------------------------------")
        print(f"Evaluating {source} -> {output_dir}")

        try:
            eval_data = evaluate(source, output_dir, answer_key, caption, None, None)
        except Exception as e:
            failures += 1
            print(f"❌❌ Failed to evaluate {photo}: {e}")
            _copy_error(photo, source)
            continue

        # Engine failures return a short (None, message) tuple. Treating that
        # as a score tuple used to raise IndexError and mask the real reason.
        if not eval_data:
            failures += 1
            print(f"❌❌ Failed to evaluate {photo}: no result")
            _copy_error(photo, source)
            continue
        if eval_data[0] is None:
            failures += 1
            message = eval_data[1] if len(eval_data) > 1 else "unknown engine error"
            print(f"❌❌ Failed to evaluate {photo}: {message}")
            _copy_error(photo, source)
            continue

        roll = eval_data[4] if len(eval_data) > 4 else None
        if roll:
            print(f"Roll: {roll}")

    print()
    print(f"Time taken: {time.time() - start_time:.1f} seconds")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
