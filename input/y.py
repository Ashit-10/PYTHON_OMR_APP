import cv2
import numpy as np
import json

# ----------------- Step 1: Detect and Crop 5 Columns -----------------

# Load the image
image_path = 'input/test8.jpeg'
image = cv2.imread(image_path)

# Resize image to 1200x550
image = cv2.resize(image, (1200, 550))

# Copy original image
original = image.copy()

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# List to hold detected columns
columns = []

# Different blurs to try
blur_values = [(1, 1), (3, 3), (5, 5), (7, 7), (9, 9), (11, 11)]

for blur_value in blur_values:
    blurred = cv2.GaussianBlur(gray, blur_value, 0)
    blockSize = 27
    C = 5
    thresh1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, blockSize, C)

    kernel = np.ones((3, 3), np.uint8)
    thresh1 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(thresh1, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(approx)
            area = cv2.contourArea(cnt)
            aspect_ratio = h / float(w) if w != 0 else 0
            if 28000 < area < 300000 and 1.4 < aspect_ratio < 4.0:
                columns.append((x, y, w, h))

# Sort columns by x coordinate
columns = sorted(columns, key=lambda b: b[0])

# Merge close columns (distance < 15 pixels)
merged_columns = []

while columns:
    base = columns.pop(0)
    x_base, y_base, w_base, h_base = base
    x_end_base = x_base + w_base

    close = [base]
    to_remove = []

    for i, other in enumerate(columns):
        x_other, y_other, w_other, h_other = other
        x_end_other = x_other + w_other

        if abs(x_other - x_base) <= 15 or abs(x_end_other - x_end_base) <= 15:
            close.append(other)
            to_remove.append(i)

    for index in sorted(to_remove, reverse=True):
        columns.pop(index)

    xs = [item[0] for item in close]
    ys = [item[1] for item in close]
    ws = [item[0] + item[2] for item in close]
    hs = [item[1] + item[3] for item in close]

    new_x = min(xs)
    new_y = min(ys)
    new_w = max(ws) - new_x
    new_h = max(hs) - new_y

    merged_columns.append((new_x, new_y, new_w, new_h))

# Sort again
columns = sorted(merged_columns, key=lambda b: b[0])

# Take first 5 only
if len(columns) > 5:
    columns = columns[:5]

# Save cropped column images
column_images = []
for i, (x, y, w, h) in enumerate(columns):
    column_image = original[y:y + h, x:x + w]
    column_image_path = f"column_{i + 1}.jpeg"
    cv2.imwrite(column_image_path, column_image)
    column_images.append((column_image_path, x, y))

# ----------------- Step 2: Read locations.txt, Draw Circles, and Print x, y Values -----------------

# Load bubble locations from locations.txt
with open('locations.txt', 'r') as f:
    locations = json.load(f)

# Process each column and draw circles for the x, y coordinates
final_data = {}
question_number = 1

for i in range(5):
    column_image_path = f"column_{i + 1}.jpeg"
    column_image = cv2.imread(column_image_path)

    # Get the x, y locations for the current column
    column_locations = locations[str(i + 1)]

    # List to hold bubble data for this column
    question_bubbles = []

    # Draw circles and print x, y values for each bubble location
    for (x, y) in column_locations:
        # Convert to integers for proper drawing
        x, y = int(x), int(y)

        # Draw a circle at each location (radius=5, color=green, thickness=-1)
        cv2.circle(column_image, (x, y), 5, (0, 255, 0), -1)  # Green circles

        # Count white pixels around the bubble
        half_size = 7  # For 15x15 area
        roi = column_image[max(0, y - half_size): y + half_size + 1,
                           max(0, x - half_size): x + half_size + 1]

        white_pixel_count = cv2.countNonZero(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY))

        # Store bubble data
        question_bubbles.append([x, y, white_pixel_count])

        # Print x, y and white pixel values
        print(f"Question {question_number}, Bubble {len(question_bubbles)}: x = {x}, y = {y}, white pixel count = {white_pixel_count}")

    # Save the column image with the drawn circles
    column_image_with_circles_path = f"column_{i + 1}_with_circles.jpeg"
    cv2.imwrite(column_image_with_circles_path, column_image)

    # Store final data for this column
    final_data[str(question_number)] = question_bubbles
    question_number += 1

    print(f"Saved {column_image_with_circles_path}")

# Save JSON to file
with open('white_pixel_data.txt', 'w') as f:
    json.dump(final_data, f, indent=4)

print("\nAll images with circles saved successfully and white pixel data printed.")
