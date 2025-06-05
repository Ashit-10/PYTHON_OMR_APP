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

moved = [shutil.move(f, '.') for f in glob.glob('/sdcard/Download/answer_key*.txt')]
print("Moved files:", moved)

if_in_output = os.listdir("output/")
if len(if_in_output) > 0:
    print(f"{len(if_in_output)} photos found in output folder. Delete all ? [y/n]")
    y_or_n = input()
    if y_or_n.lower() == "y":
        os.system("rm output/*")
        os.system("rm duplicates/*")
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
            os.system(f"cp {ppath}/{photo} duplicates/")
        else:
            rolls.append(eval_data[4])
    
end_time = time.time()
print()
print("Duplicate photos found and copied them to duplicate folder.")
print(dup_rolls)
print()
print("Time taken:", int(end_time - start_time), "seconds")
print("Total OMR sheets:", len(os.listdir("output/")))

