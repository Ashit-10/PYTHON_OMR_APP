import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the image
image_path = 'input/test6.jpeg'
image = cv2.imread(image_path)

# Resize image to 1200x550
image = cv2.resize(image, (1200, 550))

# Copy original image for later use
original = image.copy()

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
cv2.imshow("Grayscale", gray)
cv2.waitKey(0)

# Blur values to experiment
blur_values = [(1, 1), (3, 3), (5, 5), (7, 7), (9, 9), (11, 11)]

for blur_value in blur_values:
    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, blur_value, 0)

    # Adaptive thresholding
    blockSize = 27
    C = 5
    thresh1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, blockSize, C)
    cv2.imshow("Threshold", thresh1)
    cv2.waitKey(0)

    # Morphological operations
    kernel_size = 3
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    thresh1 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(thresh1, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    columns = []

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(approx)
            area = cv2.contourArea(cnt)
            aspect_ratio = h / float(w) if w != 0 else 0

            if 28000 < area < 300000 and 1.4 < aspect_ratio < 4.0:
                columns.append((x, y, w, h))

    # If too many columns, merge nearby ones
    if len(columns) > 5:
        print("More than 5 columns detected, merging nearby ones...")

        merged_columns = []
        columns = sorted(columns, key=lambda b: b[0])
        skip = [False] * len(columns)

        for i in range(len(columns)):
            if skip[i]:
                continue
            x1, y1, w1, h1 = columns[i]
            box1 = np.array([x1, y1, x1 + w1, y1 + h1])

            for j in range(i + 1, len(columns)):
                if skip[j]:
                    continue
                x2, y2, w2, h2 = columns[j]
                box2 = np.array([x2, y2, x2 + w2, y2 + h2])

                # Merge if x positions are close (10 pixels)
                if abs(x1 - x2) < 10 or abs((x1 + w1) - (x2 + w2)) < 10:
                    new_x_min = min(box1[0], box2[0])
                    new_y_min = min(box1[1], box2[1])
                    new_x_max = max(box1[2], box2[2])
                    new_y_max = max(box1[3], box2[3])

                    merged_box = (new_x_min, new_y_min, new_x_max - new_x_min, new_y_max - new_y_min)
                    merged_columns.append(merged_box)

                    skip[j] = True
                    skip[i] = True
                    break

            if not skip[i]:
                merged_columns.append((x1, y1, w1, h1))

        columns = merged_columns

        print(f"After merging, {len(columns)} columns remain.")

    # After merging, if exactly 5 columns, break
    if len(columns) == 5:
        print("Exactly 5 columns found after merging. Breaking loop.")
        break

# Sort final columns
columns = sorted(columns, key=lambda b: b[0])

# Draw rectangles using minAreaRect
for (x, y, w, h) in columns:
    roi = thresh1[y:y+h, x:x+w]
    roi_cnts, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if roi_cnts:
        c = max(roi_cnts, key=cv2.contourArea)
        rect = cv2.minAreaRect(c)
        box = cv2.boxPoints(rect)
        box = np.int0(box)

        # Offset box back to full image
        box[:, 0] += x
        box[:, 1] += y

        cv2.polylines(original, [box], isClosed=True, color=(0, 255, 0), thickness=5)

# Convert BGR to RGB for matplotlib
original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)

# Display the final image
plt.figure(figsize=(12, 18))
plt.imshow(original_rgb)
plt.axis('off')
plt.title('Detected and Merged OMR Columns')
plt.show()
