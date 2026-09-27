import scan50 as s50
import scan100 as s100
import db
import os
import time

def evaluate(image_file, photo, out_put_path, answer_key, caption, has_darkness, allow_partial_mark):
    if len(answer_key) < 51:
        return s50.find_and_draw_squares(image_file, out_put_path, 
                                  answer_key, caption, has_darkness, allow_partial_mark)
    else:
        
        return s100.find_and_draw_squares(image_file, out_put_path, 
                                   answer_key, caption, has_darkness, allow_partial_mark)
                                   
    #    print("Error in answer key")

# evaluate('images/n18.jpg', 'output/', "answer_key.txt", "", None, None)   



        
        
start_time = time.time()

db.init_db()
answer_key = db.get(db.ANSWER_KEY)
if not answer_key:
    raise SystemExit("No answer key found in MongoDB.")

ppath = "temp_input/"
err_dir = "error_images"
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
                cap = (photo.split("_roll_")[1]).split("_")[0]
        except:
            cap = None
        print()
        print("-----------------------------------")
        os.system(f"cp -f {ppath}/{photo} input/")
        eval_data = evaluate(f"{ppath}/{photo}", photo, "temp_output/", answer_key, cap, None, None)
        # print(eval_data)
        try:
         if eval_data[4]:
            #  print(eval_data[4])
             ret = eval_data[4]
        except:
            os.system(f"mv -f input/{photo} {err_dir}/")
            print("❌❌", eval_data)
            pass
           
    
end_time = time.time()
time_diff= (end_time) - (start_time)
print(f"Time taken: {time_diff:.1f} seconds")
#print("Duplicate photos found and copied them to duplicate folder.")
#print(dup_rolls)
print()

os.system("rm -rf *.jpg")
