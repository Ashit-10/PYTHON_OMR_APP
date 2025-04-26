import cv2
import numpy as np
import matplotlib.pyplot as plt
import json

# Load the image
image_path = 'input/test8.jpeg'
image = cv2.imread(image_path)

# Resize image to 1200x550
image = cv2.resize(image, (1200, 550))

# Copy original image for later use
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

# ----------------- Merge similar columns if more than 5 detected -----------------

# Sort columns by x-coordinate
columns = sorted(columns, key=lambda col: col[0])

# Merge close columns (threshold = 15 pixels)
merged_columns = []
skip = False

for i in range(len(columns)):
    if skip:
        skip = False
        continue

    x1, y1, w1, h1 = columns[i]

    if i + 1 < len(columns):
        x2, y2, w2, h2 = columns[i + 1]
        if abs(x2 - x1) < 15:  # If two columns are very close, merge them
            # Take min x, min y, max right-x, max bottom-y
            new_x = min(x1, x2)
            new_y = min(y1, y2)
            new_w = max(x1 + w1, x2 + w2) - new_x
            new_h = max(y1 + h1, y2 + h2) - new_y
            merged_columns.append((new_x, new_y, new_w, new_h))
            skip = True
        else:
            merged_columns.append((x1, y1, w1, h1))
    else:
        merged_columns.append((x1, y1, w1, h1))

# Use merged columns
columns = merged_columns

# After merging, again take only first 5 columns if more
if len(columns) > 5:
    columns = columns[:5]

# ----------------- Save the detected columns -----------------
column_images = []
for i, (x, y, w, h) in enumerate(columns):
    column_image = original[y:y + h, x:x + w]
    column_image_path = f"column_{i + 1}.jpeg"
    cv2.imwrite(column_image_path, column_image)
    column_images.append((column_image_path, x, y))

# ----------------- Detect Bubbles and Save Coords -----------------
final_result = {}

for i, (column_image_path, offset_x, offset_y) in enumerate(column_images):
    column_image = cv2.imread(column_image_path)
    gray_column = cv2.cvtColor(column_image, cv2.COLOR_BGR2GRAY)

    blurred_column = cv2.GaussianBlur(gray_column, (1, 1), 0)

    _, thresh_column = cv2.threshold(blurred_column, 127, 255, cv2.THRESH_BINARY_INV)

    contours_bubbles, _ = cv2.findContours(thresh_column, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bubbles_in_column = []

    for cnt in contours_bubbles:
        x_bubble, y_bubble, w_bubble, h_bubble = cv2.boundingRect(cnt)

        if 70 < cv2.contourArea(cnt) < 500:  # Filtering bubbles
            bubbles_in_column.append({
                "x": int(x_bubble + offset_x),
                "y": int(y_bubble + offset_y)
            })
            cv2.rectangle(column_image, (x_bubble, y_bubble),
                          (x_bubble + w_bubble, y_bubble + h_bubble),
                          (0, 255, 0), 2)

    final_result[f"Column_{i + 1}"] = bubbles_in_column

    # Show the image
    plt.imshow(cv2.cvtColor(column_image, cv2.COLOR_BGR2RGB))
    plt.title(f"Bubbles Detected in Column {i + 1}")
    plt.axis('off')
    plt.show()

# ----------------- Print final result in JSON -----------------
print(json.dumps(final_result, indent=4))
