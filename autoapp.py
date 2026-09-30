"""OMR engine.

Processes one uploaded sheet and writes the evaluated result to an output
directory supplied by the caller. The previous version swept every file in
temp_input/ into a shared temp_output/, which meant two concurrent runs could
claim each other's results and lose them. Each run now gets its own output
directory and its own input file, so the result is unambiguous.

Usage (as invoked by run_web.process_omr_task):
    python3 autoapp.py <input_file> <output_dir>

Both arguments are optional; the defaults preserve standalone use.
"""
import os
import shutil
import sys
import time

import db
import scan50 as s50
import scan100 as s100

ERR_DIR = "error_images"


def evaluate(image_file, photo, out_put_path, answer_key, caption, has_darkness, allow_partial_mark):
    if len(answer_key) < 51:
        return s50.find_and_draw_squares(image_file, out_put_path,
                                         answer_key, caption, has_darkness, allow_partial_mark)
    return s100.find_and_draw_squares(image_file, out_put_path,
                                      answer_key, caption, has_darkness, allow_partial_mark)


def main():
    start_time = time.time()

    db.init_db()
    answer_key = db.get(db.ANSWER_KEY)
    if not answer_key:
        raise SystemExit("No answer key found in MongoDB.")

    # A single explicit file keeps concurrent scans from claiming each other's
    # sheets. Falling back to the whole folder preserves manual CLI use.
    if len(sys.argv) > 1:
        photos = [os.path.basename(sys.argv[1])]
        input_dir = os.path.dirname(sys.argv[1]) or "temp_input"
    else:
        input_dir = "temp_input"
        photos = sorted(os.listdir(input_dir))

    output_dir = sys.argv[2] if len(sys.argv) > 2 else "temp_output"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(ERR_DIR, exist_ok=True)

    for photo in photos:
        if not photo.lower().endswith((".jpg", ".jpeg")):
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
            eval_data = evaluate(source, photo, output_dir, answer_key, caption, None, None)
            if eval_data[4]:
                print(f"Roll: {eval_data[4]}")
        except Exception as e:
            # Keep the unparseable sheet for inspection rather than losing it.
            print(f"❌❌ Failed to evaluate {photo}: {e}")
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

    print()
    print(f"Time taken: {time.time() - start_time:.1f} seconds")


if __name__ == "__main__":
    main()
