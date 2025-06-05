import scan50 as s50
import scan100 as s100
import os
import json
import time

def evaluate(image_file, photo, out_put_path, answer_key_file, caption, has_darkness, allow_partial_mark):
    with open(answer_key_file, 'r') as readd:
        answers = json.load(readd)
    if len(answers) < 51:
        return s50.find_and_draw_squares(image_file, out_put_path, 
                                  answer_key_file, caption, has_darkness, allow_partial_mark)
    else:
        print("Error in answer key")

# evaluate('images/n18.jpg', 'output/', "answer_key.txt", "", None, None)   



        
        
start_time = time.time()

ppath = "temp_input/"
#os.system(f"rm -f {ppath}/*")
photos = os.listdir(ppath)
rolls = []
dup_rolls = []
ret = None
for photo in photos:
    if photo.endswith(".jpg") or photo.endswith(".jpeg"):
        cap = None
        try:
            if "_roll_" in photo:
                cap = photo.split("_roll_")[1]
        except:
            cap = None
        print()
        print("-----------------------------------")
        os.system(f"cp -f {ppath}/{photo} input/")
        eval_data = evaluate(f"{ppath}/{photo}", photo, "temp_output/", "answer_key.txt", cap, None, None)
        # print(eval_data)
        try:
         if eval_data[4]:
            #  print(eval_data[4])
             ret = eval_data[4]
        except:
            pass
           
    
end_time = time.time()
print()
#print("Duplicate photos found and copied them to duplicate folder.")
#print(dup_rolls)
print()

os.system("rm -rf *.jpg")
