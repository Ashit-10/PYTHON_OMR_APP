import scan50 as s50
import scan100 as s100
import os
import json
import time
import glob
import shutil

def evaluate(image_file, out_put_path, answer_key_file, caption, has_darkness, allow_partial_mark):
    with open(answer_key_file, 'r') as readd:
        answers = json.load(readd)
    if len(answers) < 51:
        return s50.find_and_draw_squares(image_file, out_put_path, 
                                  answer_key_file, caption, has_darkness, allow_partial_mark)
    elif len(answers) > 50:
        return s100.find_and_draw_squares(image_file, out_put_path, 
                                   answer_key_file, caption, has_darkness, allow_partial_mark)


# evaluate('images/n18.jpg', 'output/', "answer_key.txt", "", None, None)   
moved = []
for f in glob.glob('/sdcard/Download/*ans*_key*.txt*'):
    try:
        shutil.move(f, f'./{os.path.basename(f)}')
        moved.append(os.path.basename(f))
    except: pass
print("Moved files:", moved)
# ---- Check Download folder for OMR images (safe move, no overwrite) ----
download_path = "/sdcard/Download"
target_input_path = "../PYTHON_OMR_APP/input"

image_exts = (".jpg", ".jpeg", ".png")
omr_images = []

for f in os.listdir(download_path):
    fname = f.lower()
    if fname.startswith("omr_sheet") and fname.endswith(image_exts):
        omr_images.append(f)

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
    print(f"{len(if_in_output)} photos found in output folder. Delete all ? [y/n]")
    y_or_n = input()
    if y_or_n.lower() == "y":
        os.system("rm -f output/*")
        os.system("rm -f duplicates/*")
        print("Deleted all photos in output folder .")
    else:
        print("Proceeding without deleting ...")

start_time = time.time()

ppath = "input/"
photos = os.listdir(ppath)
rolls = []
dup_rolls = []
for photo in photos:
    if photo.endswith(".jpg"):
        cap = None
        try:
            if "_roll_" in photo:
                cap = photo.split("_roll_")[1]
        except:
            cap = None
        print()
        print("-----------------------------------")
        eval_data = evaluate(f"{ppath}/{photo}", "output/", "answer_key.txt", cap, None, None)
        if eval_data[4] in rolls:
            dup_rolls.append(photo)
            os.system(f"cp '{ppath}/{photo}' duplicates/")
        else:
            rolls.append(eval_data[4])
    
end_time = time.time()
print()
print("Duplicate photos found and copied them to duplicate folder.")
print(dup_rolls)
print()
print("Time taken:", int(end_time - start_time), "seconds")
print("Total OMR sheets:", len(os.listdir("output/")))

