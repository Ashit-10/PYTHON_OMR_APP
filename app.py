import scan50 as s50
import scan100 as s100
import db
import os
import time
import glob
import shutil
import sys

# Assigning the arguments to variables
try:
    auto_y_n = sys.argv[1]  # "argument1"
  #  arg2 = sys.argv[2]  # "argument2"
    print(f"Running recheck with: {auto_y_n}")
except:
    auto_y_n = None


def evaluate(image_file, out_put_path, answer_key, caption, has_darkness, allow_partial_mark):
    if len(answer_key) < 51:
        return s50.find_and_draw_squares(image_file, out_put_path, 
                                  answer_key, caption, has_darkness, allow_partial_mark)
    elif len(answer_key) > 50:
        return s100.find_and_draw_squares(image_file, out_put_path, 
                                   answer_key, caption, has_darkness, allow_partial_mark)


db.init_db()
answer_key = db.get(db.ANSWER_KEY)
if not answer_key:
    raise SystemExit("No answer key found in MongoDB.")

# evaluate('images/n18.jpg', 'output/', answer_key, "", None, None)   
moved = []
download_path = "/sdcard/Download"
target_input_path = "input"

if os.path.exists(download_path):
    image_exts = (".jpg", ".jpeg", ".png")
    omr_images = []

    for f in os.listdir(download_path):
        fname = f.lower()
        if fname.startswith("omr_sheet") and fname.endswith(image_exts):
            omr_images.append(f)
else:
    omr_images = []


def get_safe_name(dst_folder, filename):
    name, ext = os.path.splitext(filename)
    counter = 1
    new_name = filename
    while os.path.exists(os.path.join(dst_folder, new_name)):
        new_name = f"{name}_{counter}{ext}"
        counter += 1
    return new_name

if omr_images:
    print(f"{len(omr_images)} OMR image(s) found in Download folder.")
    if auto_y_n:
        choice = auto_y_n
    else:
        print("Move them to input folder? [y/n]")
        choice = input().strip().lower()

    if choice == "y":
        moved_imgs = []
        for img in omr_images:
            try:
                safe_name = get_safe_name(target_input_path, img)
                shutil.move(
                    os.path.join(download_path, img),
                    os.path.join(target_input_path, safe_name)
                )
                moved_imgs.append(safe_name)
            except Exception as e:
                print(f"Failed to move {img}: {e}")

        print("Moved OMR images:")
        for m in moved_imgs:
            print(" -", m)
    else:
        print("Skipping move operation.")

else:
    print("No OMR images found in Download folder.\nProceeding to input folder.")
# ---- End of pre-check ----

if_in_output = os.listdir("output/")
if len(if_in_output) > 0:
    # Existing results are never deleted automatically. This used to run
    # "rm -f output/*" whenever the caller passed "y", which silently destroyed
    # every stored result on a server deploy. Clearing is now an explicit,
    # separate action and off by default.
    print(f"{len(if_in_output)} photos already in output folder; keeping them.")
    if not auto_y_n:
        choice = input("Delete all existing results? [y/n] ").strip().lower()
    else:
        choice = "n"
    if choice == "y":
        os.system("rm -f output/*")
        os.system("rm -f duplicates/*")
        os.system("rm -f error_images/*")
        print("Deleted all photos in output folder .")
    else:
        print("Proceeding without deleting ...")

start_time = time.time()
print()
print("-----------------------------------")

ppath = "input/"
photos = os.listdir(ppath)
rolls = []
dup_rolls = []
for photo in photos:
    if photo.endswith(".jpg"):
        cap = None
        try:
            if "_roll_" in photo:
                cap = (photo.split("_roll_")[1]).split("_")[0]
        except:
            cap = None
        print()
        
        eval_data = evaluate(f"{ppath}/{photo}", "output/", answer_key, cap, None, None)
        try:
            print(f"{ppath}/{photo}")
            if eval_data[4] in rolls:
                dup_rolls.append(photo)
                os.system(f"cp '{ppath}/{photo}' duplicates/")
            else:
                rolls.append(eval_data[4])
              #  print(eval_data[6])              
                
          #  os.system(f"cp '{ppath}/{photo}' original_images/input/")
          #  os.system(f"cp '{eval_data[6]}' original_images/output/")
        except:            
          #  print(eval_data)
            print(f"\033[1;91m{eval_data}\033[0m")
            shutil.copy(f"{ppath}/{photo}", "error_images/")
        print()
        print("-----------------------------------")
        
        
    
end_time = time.time()
print()
print(f"{len(dup_rolls)} Duplicate photos found and copied them to duplicate folder.")
print(dup_rolls)
print()
print("Time taken:", int(end_time - start_time), "seconds")
print("Total OMR sheets input:", len(os.listdir("input/")))
print("Total OMR sheets output:", len(os.listdir("output/")))
print("Total OMR sheets Error:", len(os.listdir("error_images/")))
print("Total Duplicate Roll No:", len(os.listdir("duplicates/")))

