import cv2
import numpy as np
import json
import datetime
import os
import configparser

config = configparser.ConfigParser()
config.read('config.cfg')

roll_first_column = [[250, 20], [250, 52], [250, 86], [250, 118], [250, 152], [250, 185],[250, 219], [250, 251],[250, 285],[250, 317]]
roll_second_column = [[287, 20], [287, 52], [287, 86], [287, 119], [287, 152], [287, 185], [287, 219], [287, 251],[287, 285],[287, 317] ]
location_file = "omr_50_locations.txt"


def add_sign(base_image, dst_pts, rect, x, y, r = 0):
    try:
        sign_file = config.get('settings', 'signature')
        signature_image = cv2.imread(sign_file, cv2.IMREAD_UNCHANGED)

        # Resize the signature image to width 100 while maintaining the aspect ratio
        new_width = 85
        aspect_ratio = new_width / signature_image.shape[1]
        new_height = int(signature_image.shape[0] * aspect_ratio)
        # print(new_height)
        y = y - (new_height)
        
        resized_signature_image = cv2.resize(signature_image, (new_width, new_height), interpolation=cv2.INTER_AREA)

        if len(dst_pts) > 0:
            # Transform the circle coordintes back to the original perspective
            circle_pts = np.array([[x-r, y-r], [x+r, y-r], [x+r, y+r], [x-r, y+r]], dtype="float32")
            M_inv = cv2.getPerspectiveTransform(dst_pts, rect)
            original_circle_pts = cv2.perspectiveTransform(np.array([circle_pts]), M_inv)[0]
            original_center = np.mean(original_circle_pts, axis=0).astype(int)
            (x, y) = tuple(original_center)

        # Get the dimensions of the signature image
        sig_height, sig_width = resized_signature_image.shape[:2]

        # Ensure the signature fits within the base image boundaries
        if x + sig_width > base_image.shape[1] or y + sig_height > base_image.shape[0]:
            raise ValueError("The signature image does not fit within the base image boundaries at the specified position.")
        # Separate the color and alpha channels
        sig_bgr = resized_signature_image[:, :, :3]
        alpha_mask = resized_signature_image[:, :, 3] / 255.0

        # Get the region of interest (ROI) in the base image where the signature will be placed
        roi = base_image[y:y+sig_height, x:x+sig_width]

        # Blend the signature with the ROI
        for c in range(0, 3):
            roi[:, :, c] = roi[:, :, c] * (1 - alpha_mask) + sig_bgr[:, :, c] * alpha_mask

        # Replace the ROI in the base image with the blended result
        base_image[y:y+sig_height, x:x+sig_width] = roi
    except Exception as e:
        print(e)

def draw_color(original_with_contours, dst_pts, rect, x, y, color, r=8, thickness=2):
    if len(dst_pts) > 0:
        # Transform the circle coordintes back to the original perspective
        circle_pts = np.array([[x-r, y-r], [x+r, y-r], [x+r, y+r], [x-r, y+r]], dtype="float32")
        M_inv = cv2.getPerspectiveTransform(dst_pts, rect)
        original_circle_pts = cv2.perspectiveTransform(np.array([circle_pts]), M_inv)[0]
        original_center = tuple(np.mean(original_circle_pts, axis=0).astype(int))
    else:
        original_center = (x, y)
    # Draw the circle in the original image
    cv2.circle(original_with_contours, original_center, r, color, thickness, cv2.LINE_AA)

def write_text(original_with_contours, dst_pts, rect, x, y, date, color_code = 0, largeness=0.5, thickness = 2, r = 0):
    if len(dst_pts) > 0:
        # Transform the circle coordintes back to the original perspective
        circle_pts = np.array([[x-r, y-r], [x+r, y-r], [x+r, y+r], [x-r, y+r]], dtype="float32")
        M_inv = cv2.getPerspectiveTransform(dst_pts, rect)
        original_circle_pts = cv2.perspectiveTransform(np.array([circle_pts]), M_inv)[0]
        original_center = tuple(np.mean(original_circle_pts, axis=0).astype(int))
        # print(original_center)
    
    else:
        original_center = (x, y)
    if not color_code:
        color_code = (0, 0, 200)  # red
    # else:
    #     color_code = (100, 0, 0)  # blue
    
    # Draw the circle in the original image
    cv2.putText(original_with_contours, date, original_center, cv2.FONT_HERSHEY_SIMPLEX, largeness, color_code, thickness, cv2.LINE_AA)
    return list(original_center)

def opposite_pattern(img_no):
    if img_no == 3:
        start = (img_no - 1) * 20 + 1
        end = start + 10
        combined_set = list(range(start, end))
    else:
        start1 = (img_no - 1) * 20 + 1
        start2 = start1 + 10

        first_set = list(range(start1, start1 + 10))
        second_set = list(range(start2, start2 + 10))

        combined_set = []
        for i in range(10):
            combined_set.append(first_set[i])
            combined_set.append(second_set[i])

    return combined_set

def rm_empty_opts(lst):
    return [item for item in lst if item != '']

def choose_8(thresh1, square_contours):
    # Calculate white pixel values for each square contour
    white_pixel_counts = []
    for contour in square_contours:
        mask = np.zeros_like(thresh1)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        white_pixels = cv2.countNonZero(cv2.bitwise_and(thresh1, thresh1, mask=mask))
        white_pixel_counts.append((contour, white_pixels))

    # Sort contours by white pixel values and select the top 8 with the most similar values
    white_pixel_counts.sort(key=lambda x: x[1])

    # Select the 8 contours with the most similar white pixel values
    selected_contours = white_pixel_counts[:8]

    # Find the 8 contours with the smallest range of white pixel values
    best_contours = selected_contours
    min_diff = float('inf')
    for i in range(len(white_pixel_counts) - 7):
        current_contours = white_pixel_counts[i:i+8]
        diff = current_contours[-1][1] - current_contours[0][1]
        if diff < min_diff:
            min_diff = diff
            best_contours = current_contours

    square_contours = [contour for contour, _ in best_contours]
    # print(square_contours)
    if len(square_contours) == 8:
        # print("Chose 8 among the list.")
        return square_contours
    else:
        return []
    
def get_roll_cods(cap_given, roll_first_column, roll_second_column):
    roll = []
    cap = cap_given.strip()
    if len(cap) == 1:
        cap = f"0{cap_given}"
    p = 0
    for roll_column in [roll_first_column, roll_second_column]:
        cap_int = int(cap[p])
        if cap_int == 0:
            cap_index = 9
        else:
            cap_index = cap_int - 1
        roll.append(roll_column[cap_index])
        p += 1
    return roll
def find_extremes(coords):
    if not coords:
        return None, None, None, None  # Return None if the input list is empty

    # Initialize the smallest and largest values
    smallest_x = float('inf')
    largest_x = float('-inf')
    smallest_y = float('inf')
    largest_y = float('-inf')

    # Iterate through the list to find the smallest and largest x and y values
    for x, y in coords:
        if x < smallest_x:
            smallest_x = x
        if x > largest_x:
            largest_x = x
        if y < smallest_y:
            smallest_y = y
        if y > largest_y:
            largest_y = y

    return smallest_x, largest_x, smallest_y, largest_y


def find_and_draw_squares(image_path, output_path, answer_key_file, cap_given, has_shadow, allow_parcial_marking, new_cods_=[]):
    roll_pixel = 220
    white_pixel_value = int(config.get('settings', 'pixel_value')) #230 # 170
    m_area = 150
    shadow_pixel_value = 280


    if has_shadow:
        white_pixel_value = shadow_pixel_value
    err_msg = ""
    # Read the image
    image = cv2.imread(image_path)
    if image is None:
        print(f"Failed to load image at {image_path}")
        return None, f"Failed to load image at {image_path}"

    file_height = image.shape[0]
    file_width = image.shape[1]
    # print(file_height, file_width)

    new_width = 960 #   height 2560
    if file_width < file_height:
        img2 = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        image = img2
        # print("Rotated the image.")
    if image.shape[1] != new_width:
        file_height = image.shape[0]
        file_width = image.shape[1]
        a_ratio = file_height / file_width
        new_height = int(new_width * a_ratio)
        resized_img = cv2.resize(image, (new_width, new_height))
        image = resized_img
        # print("Resized the image.", image.shape[0], image.shape[1])
    image_height = image.shape[0]
    # Define min and max area for filtering
    max_area = 400
    min_area = m_area

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    for blur_value in [(1, 1), (3, 3), (5, 5), (7, 7), (9, 9), (11, 11)]:
        # Apply Gaussian blur to smooth edges
        blurred = cv2.GaussianBlur(gray, blur_value, 0)

    #####################################################new#############################################################
        # Adaptive thresholding
        blockSize = 27  # Try increasing to 15, 19, 23, etc.
        C = 5  # Try adjusting to different values like 5, 10, etc.
        thresh1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, blockSize, C)

        # Morphological operations to enhance square features
        kernel_size = 3  # Try adjusting to 5, 7, etc.
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        thresh1 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)

        # cv2.imshow("Binary Image", thresh1)
        # cv2.waitKey(0)
        contours, _ = cv2.findContours(thresh1, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        # Filter and store square-like contours
        square_contours = []
        for contour in contours:
            approx = cv2.approxPolyDP(contour, 0.03 * cv2.arcLength(contour, True), True)
            if len(approx) == 4:
                (x, y, w, h) = cv2.boundingRect(approx)
                aspect_ratio = w / float(h)
                area = cv2.contourArea(contour)
                # Additional check for convexity and aspect ratio closer to 1
                if 0.7 <= aspect_ratio <= 1.3 and area >= min_area and area < max_area and cv2.isContourConvex(approx):
                    # print("Area of square boxes:", area)
                    square_contours.append(approx)

        if len(square_contours) > 8:
            # print("gone to choose", len(square_contours))
            square_contours = choose_8(thresh1, square_contours)
            # print(len(square_contours))

        if len(square_contours) == 8:
            break

    if len(square_contours) != 8:
        return None, "Could not find 8 square boxes."
    # Extract top-left corner points from the square contours
    top_left_points = []
    x_y_w_h = []
    for approx in square_contours:

        # top-left points
        top_left = min(approx, key=lambda point: point[0][0] + point[0][1])
        top_left_coord = tuple(top_left[0])

        # Extract the bottom-left corner point
        bottom_left = min(approx, key=lambda point: point[0][0] - point[0][1])
        bottom_left_coord = tuple(bottom_left[0])

        (x, y, w, h) = cv2.boundingRect(approx)
        if top_left_coord[1] > image_height / 2:
            top_left_coord = (bottom_left_coord[0], bottom_left_coord[1])
      
        top_left_points.append(top_left_coord)
        x_y_w_h.append([list(top_left_coord), [w, h]])


    # print(top_left_points, "top left")
    # Sort points by x and then by y
    top_left_points.sort(key=lambda point: (point[0], point[1]))

    # Print the sorted top-left coordinates of all square contours
    all_cods = []
    # print("Sorted top-left coordinates of all square contours:")
    for point in top_left_points:
        all_cods.append([point[0], point[1]])

    # print(all_cods)

    # Define the destination points for perspective transform
    width, height = 400, 340
    dst_pts = np.float32([[0, 0], [width, 0], [width, height], [0, height]])

    # Store the original image with contours
    original_with_contours = image.copy()

    # with open("new_omr_loc.txt", 'r') as red:
    with open(location_file, 'r') as red:
        all_circle_cods = json.load(red)

    all_options_selected = {}    
    stored_dst_rect = []
    all_numbers_coods = {}
    unselected = {}
    # Perform perspective transform for each overlapping set of four coordinates
    for i in range(0, len(all_cods) - 3, 2):

        # print(x_y_w_h)
        per_image_coods = []
        range_cods = all_cods[i:i + 4]

        # Sort the coordinates based on the x-value
        sorted_coordss = sorted(range_cods, key=lambda point: point[0])

        # Extract the two coordinates with the lowest x-values
        lowest_x_coords = sorted_coordss[:2]
        per_image_coods = sorted_coordss[2:]
        # print(per_image_coods, "per image coods")
        for cod in lowest_x_coords:
            per_image_w = 0
            for an_cod in x_y_w_h:
                if cod in an_cod:
                    per_image_w = an_cod[1][0]
            per_image_coods.append([cod[0] + per_image_w, cod[1]])
            
        src_pts = np.float32(per_image_coods)


        # src_pts = np.float32(all_cods[i:i + 4])
        # Sort the points to match the expected order: top-left, top-right, bottom-right, bottom-left
        rect = np.zeros((4, 2), dtype="float32")
        s = np.sum(src_pts, axis=1)
        rect[0] = src_pts[np.argmin(s)]  # top-left
        rect[2] = src_pts[np.argmax(s)]  # bottom-right

        diff = np.diff(src_pts, axis=1)
        rect[1] = src_pts[np.argmin(diff)]  # top-right
        rect[3] = src_pts[np.argmax(diff)]  # bottom-left

        # Perform perspective transform
        M = cv2.getPerspectiveTransform(rect, dst_pts)
        warped = cv2.warpPerspective(image, M, (width, height))

        # Save the transformed image
        # transformed_output_path = f"{output_path.split('.')[0]}_transformed_{i // 2 + 1}.jpg"
        # cv2.imwrite(transformed_output_path, warped)
        # print(f"Transformed image {i // 2 + 1} saved at {transformed_output_path}")

        # Detect circular contours in the transformed image
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        # circles = cv2.HoughCircles(warped_gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30, param1=50, param2=30, minRadius=8, maxRadius=19)
        

        stored_dst_rect.append([dst_pts, rect])

        img_no = i // 2 + 1
        try:
            circles = all_circle_cods[str(img_no)]
        except KeyError as e:
            print("key Error", e)
            break
        opts = {}
        un_opts = {}
        correct_numbers = 0
        wrong_numbers = 0
        roll_number = ""
        roll_number_coods = []
        if img_no == 3:
            for roll_column in [roll_first_column, roll_second_column]:
                for fi in roll_column:
                    [xr, yr] = fi
                    r = 10
                    x_start_r, y_start_r = max(xr-r, 0), max(yr-r, 0)
                    x_end_r, y_end_r = min(xr+r, width), min(yr+r, height)
                    small_square_r = warped_gray[y_start_r:y_end_r, x_start_r:x_end_r]
                    _, binary_square_r = cv2.threshold(small_square_r, 120, 255, cv2.THRESH_BINARY_INV)
                    white_pixel_count_r = cv2.countNonZero(binary_square_r)
                    
                    if white_pixel_count_r > roll_pixel:   # white pixel for roll number
                     #   print(white_pixel_count_r)
                        f_roll_num = roll_column.index(fi) + 1
                        if f_roll_num == 10:
                            f_roll_num = "0"
                        roll_number += str(f_roll_num)
                        roll_number_coods.append([xr, yr])


            # top max 2 ta pixel ku naba #todo
            roll_number = roll_number.strip()
            if (len(str(roll_number)) > 2) or (not roll_number):
                roll_number = "0"
                roll_number_coods = [roll_first_column[9], roll_second_column[9]]

            if cap_given:
                roll_number_coods = get_roll_cods(cap_given,roll_first_column, roll_second_column)
                roll_number = cap_given.strip()

            if (len(roll_number) == 2) and (str(roll_number).startswith("0")):
                roll_number = str(roll_number)[1:]

            if int(roll_number) == 0:
                err_msg += "Error finding roll number, but omr sheet evaluated correctly ✅!"
                roll_number = "0"
        if circles is not None:
            # circles = np.round(circles[0, :]).astype("int")
            n = 0
            # circle_cods = []
            for (x, y) in circles:
            # for (x, y, r) in circles:
                r = 11
                # circle_cods.append([x,y])
                x_start, y_start = max(x-r, 0), max(y-r, 0)
                x_end, y_end = min(x+r, width), min(y+r, height)
                small_square = warped_gray[y_start:y_end, x_start:x_end]
                
                # Convert to binary (black and white)
                _, binary_square = cv2.threshold(small_square, 120, 255, cv2.THRESH_BINARY_INV)
                # cv2.imshow("Final Output", binary_square)
                # cv2.waitKey(0)
                white_pixel_count = cv2.countNonZero(binary_square)
                # white_pixel_counts.append(white_pixel_count)
                # print(f"Circle at ({x}, {y}): White pixel count = {white_pixel_count}")
                un_opt = ""
                if white_pixel_count > white_pixel_value:  # white pixel for options
                    print("For options", white_pixel_count)
                    # cv2.imshow("ok", binary_square)
                    # cv2.waitKey(0)
                    if n == 0 or (n % 4) == 0:
                        opt = ["A", [x, y]]
                    elif n == 1 or (n % 4) == 1:
                        opt = ["B", [x, y]]
                    elif n == 2 or (n % 4) == 2:
                        opt = ["C", [x, y]]
                    elif n == 3 or (n % 4) == 3:
                        opt = ["D", [x, y]]
                    # print(opt, [x,y])
                else:
                    opt = ''
                    un_opt = [x, y]
                opts.update({n + 1 : opt})
                un_opts.update({n + 1 : un_opt})
                n += 1
                

                # Draw the circle in the transformed image
                cv2.circle(warped, (x, y), r, (255, 0, 0), 2)

             
            o = 0
            selected_opts = {}
            opposite_number_list = opposite_pattern(img_no)
            # print(opposite_number_list)
            for i in range(0, len(opts), 4):
                chunk = rm_empty_opts(list(opts.values())[i:i+4])

                selected_opts.update({str(opposite_number_list[o]) : chunk})
                all_options_selected.update({str(opposite_number_list[o]) : chunk})
                o += 1

            o = 0
            for i in range(0, len(un_opts), 4):
                chunkk = list(un_opts.values())[i:i+4]
                # print(chunkk)
                if "" not in chunkk:
                    unselected.update({str(opposite_number_list[o]) : chunkk})
                o += 1

            # print(len(circles))
            o = 0
            for i in range(0, len(circles), 4):
                chunk = circles[i:i+4]
                # print(chunk)
                all_numbers_coods.update({str(opposite_number_list[o]) : chunk})
                o += 1

            #### start coloring the correct and wrong answers #####

            # Get all keys and sort them
            sorted_keys = sorted(selected_opts.keys(), key=lambda x: int(x))
            # Create a new dictionary with sorted keys
            sorted_data = {key: selected_opts[key] for key in sorted_keys}

            # print(sorted_data)


    # Get all keys and sort them
    all_sorted_keys = sorted(all_options_selected.keys(), key=lambda x: int(x))
    # Create a new dictionary with sorted keys
    all_sorted_data = {key: all_options_selected[key] for key in all_sorted_keys}

    # Get all keys and sort them
    all_sorted_number_keys = sorted(all_numbers_coods.keys(), key=lambda x: int(x))
    # Create a new dictionary with sorted keys
    all_sorted_number_data = {key: all_numbers_coods[key] for key in all_sorted_number_keys}

    # print(all_numbers_coods)
    # print(all_sorted_data)
    # print("Unselected", unselected)
    #### start coloring the correct and wrong answers #####

    with open(answer_key_file, "r") as red:
        answer_key = json.load(red)
    total_numbers = len(answer_key)
        
    for answer in answer_key:
        # print(answer)
        if int(answer) < 21:
            [all_dst_pts, all_rect] = stored_dst_rect[0]
        elif int(answer) < 41:
            [all_dst_pts, all_rect] = stored_dst_rect[1]
        elif int(answer) < 51:
            [all_dst_pts, all_rect] = stored_dst_rect[2]

        to_draw = all_sorted_data.get(answer)
        # print(to_draw)

        # allow_parcial_marking = True
        if allow_parcial_marking:   ######## illegal 
            all_chosen = []
            if len(to_draw) > 0:
                for draw in to_draw:
                    all_chosen.append(draw[0])
                if all_chosen == answer_key.get(answer):     
                        for to_color in to_draw:
                            [xx, yy] = to_color[1]        #### correct answer  #green
                            draw_color(original_with_contours, all_dst_pts, all_rect, xx, yy, (0, 255, 0), 8)
                        correct_numbers += 1      
                else:           
                    for to_color_r in to_draw:
                        [xx, yy] = to_color_r[1]    ############# wrong answer red
                        draw_color(original_with_contours, all_dst_pts, all_rect, xx, yy, (0, 0, 255), 8)  
                    wrong_numbers += 1 
            else:
                pass  ################ add circle for unattempted numbers

        else:   ####### this should , omr sheet 
            if len(to_draw) > 1:
                for d in to_draw:
                    [xx, yy] = d[1]        ### wrong answer   #red
                    draw_color(original_with_contours, all_dst_pts, all_rect, xx, yy, (0, 0, 255), 8)  
                wrong_numbers += 1 
            elif len(to_draw) == 1:
                if to_draw[0][0] in answer_key.get(answer):
                    [xx, yy] = to_draw[0][1]        #### correct answer  #green
                    draw_color(original_with_contours, all_dst_pts, all_rect, xx, yy, (0, 255, 0), 8)
                    correct_numbers += 1
                else:
                    [xx, yy] = to_draw[0][1]  
                    draw_color(original_with_contours, all_dst_pts, all_rect, xx, yy, (0, 0, 255), 8)  
                    wrong_numbers += 1 

        is_unselected = unselected.get(answer)
        if is_unselected:
            for u in is_unselected:
                [unx , uny] = u               ###### blue color for unattempted numbers
                draw_color(original_with_contours, all_dst_pts, all_rect, unx, uny, (255, 0, 0), 8)  

    
            
        
        ##### Draw pink dot on correct nswer as per answer key ######
        coods = all_sorted_number_data.get(answer)
        option = answer_key.get(answer)
        for op in option:
            if op == "A":
                op_index = 0
            if op == "B":
                op_index = 1
            if op == "C":
                op_index = 2
            if op == "D":
                op_index = 3

            [ax, ay] = coods[op_index]        ###### Draw pink dot
            draw_color(original_with_contours, all_dst_pts, all_rect, ax, ay, (100, 100, 255), 1)



                ###### Color roll number coords #####

    # print(len(roll_number_coods))
    [roll_dst_pts, roll_rect] = stored_dst_rect[2]    # for roll number the last image data
    for roll_cod in roll_number_coods:
        [xx, yy] = roll_cod     
        draw_color(original_with_contours, roll_dst_pts, roll_rect, xx, yy, (0, 0, 0), 8, cv2.FILLED)
        draw_color(original_with_contours, roll_dst_pts, roll_rect, xx, yy, (0, 100, 200), 8)


        #### add sign , date , marks   ######
    end_x = roll_second_column[5][0] + 12
    end_y = 130
    c_date = datetime.datetime.now()
    exam_date = c_date.strftime("%d/%m/%Y")
    safe_coods = write_text(original_with_contours, roll_dst_pts, roll_rect, end_x + 4, end_y, exam_date, '', 0.4, 1)

    add_sign(original_with_contours, [], [], safe_coods[0] + 4, safe_coods[1] - 15)
    # add_sign(original_with_contours, roll_dst_pts, roll_rect, end_x, end_y - 15)
    draw_color(original_with_contours, [], [], safe_coods[0] + 42, safe_coods[1] + 55, (0, 0, 200), 38)
    # draw_color(original_with_contours, roll_dst_pts, roll_rect, end_x + 68, end_y + 100, (0, 0, 200), 48)
    write_text(original_with_contours, [], [], safe_coods[0] + 17, safe_coods[1] + 53, "______", (100, 0, 0))
    # write_text(original_with_contours, roll_dst_pts, roll_rect, end_x + 25, end_y + 100, "_______")

    if len(str(correct_numbers)) == 1:
        safe_coods[0] += 10
        write_text(original_with_contours, [], [], safe_coods[0] + 22, safe_coods[1] + 45, str(correct_numbers), '', 1)
        if len(str(total_numbers)) != 1:
            safe_coods[0] -= 10
    else:
        write_text(original_with_contours, [],[], safe_coods[0] + 19, safe_coods[1] + 45, str(correct_numbers), '', 1)

    write_text(original_with_contours, [], [], safe_coods[0] + 22, safe_coods[1] + 85, str(total_numbers), '', 1)

    # Draw the selected square contours on the original image
    for contour in square_contours:
        cv2.drawContours(original_with_contours, [contour], -1, (170, 51, 106), thickness=cv2.FILLED)

    print("Input image:", image_path)
    print("Roll number:", roll_number)
    print("total numbers:", total_numbers)
    print("correct:", correct_numbers)
    print("wrong:", wrong_numbers)

    try:
        height, width = original_with_contours.shape[:2]

        exts = find_extremes(all_cods)
        sx = exts[0]
        lx = exts[1]
        sy = exts[2]
        ly = exts[3]
        
        for v in [30, 25, 20, 15, 10, 5, 0]:
            if (sx - v) >= 0:
                sx = sx - v
                break

        for v in [55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0]:
            if (sy - v) >= 0:
                sy = sy - v
                break

        for v in [50, 25, 20, 15, 10, 5, 0]:
            if (lx + v) <= width:
                lx = lx + v
                break

        for v in [40, 35, 30, 25, 20, 15, 10, 5, 0]:
            if (ly + v) <= height:
                ly = ly + v
                break

        crop_box = (sx, sy, lx, ly)

        cropped_image = original_with_contours[crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
        original_with_contours = cropped_image
    except Exception as e:
        print(e)

    # Save the output image with drawn contours and circles
    out_put_name = f"{roll_number}_{correct_numbers}.jpg"
    out_put_path_name = output_path + out_put_name
    cv2.imwrite(out_put_path_name, original_with_contours)


    print(f"Output image saved at {out_put_path_name}")

    return total_numbers, correct_numbers, total_numbers - (correct_numbers + wrong_numbers), wrong_numbers, roll_number, err_msg

    # Display the final output image with drawn contours and circles
    # cv2.imshow("Final Output", original_with_contours)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()

# # Example usageTrue
# find_and_draw_squares('images/ex1.jpg', 'output_image.jpg', "answer_key.txt", "", True, None)

