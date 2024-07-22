import scan50 as s50
import scan100 as s100

import json

def evaluate(image_file, out_put_path, answer_key_file, has_darkness, allow_partial_mark):
    with open(answer_key_file, 'r') as readd:
        answers = json.load(readd)
    if len(answers) < 51:
        s50.find_and_draw_squares(image_file, out_put_path, answer_key_file, has_darkness, allow_partial_mark)
    elif len(answers) > 50:
        s100.find_and_draw_squares(image_file, out_put_path, answer_key_file, has_darkness, allow_partial_mark)



evaluate('images/test.jpg', 'output/', "answer_key.txt", None, None)    
