import cv2
import numpy as np
import matplotlib.pyplot as plt
import json

# ---------- Helper functions ----------

def order_points(pts):
    # Order points: top-left, top-right, bottom-right, bottom-left
    rect = np.zeros((4, 2), dtype="float32")

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left

    return rect

def four_point_transform(image, pts):
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    # Compute width and height
    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = max(int(heightA), int(heightB))

    # Destination coordinates
    dst = np.array([
        [0, 0],
        [maxWidth-1, 0],
        [maxWidth-1, maxHeight-1],
        [0, maxHeight-1]
    ], dtype="float32")

    # Perspective transform
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

    return warped

# ---------- Main Code ----------

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
            area = cv2.contourArea(cnt)
            if 28000 < area < 300000:
                if len(approx) > 4:
                    approx = cv2.convexHull(approx)

                if len(approx) >= 4:
                    pts = approx.reshape(-1, 2)
                    rect = cv2.boundingRect(approx)
                    x, y, w, h = rect
                    aspect_ratio = h / float(w) if w != 0 else 0
                    if 1.4 < aspect_ratio < 4.0:
                        columns.append(pts)

# ------------- Merge Close Columns -------------

# Sort columns by x-coordinate
columns = sorted(columns, key=lambda pts: np.min(pts[:, 0]))

merged_columns = []

while columns:
    base = columns.pop(0)
    base_x_min = np.min(base[:, 0])
    base_x_max = np.max(base[:, 0])

    close = [base]
    to_remove = []

    for i, other in enumerate(columns):
        other_x_min = np.min(other[:, 0])
        other_x_max = np.max(other[:, 0])

        if abs(other_x_min - base_x_min) <= 15 or abs(other_x_max - base_x_max) <= 15:
            close.append(other)
            to_remove.append(i)

    for index in sorted(to_remove, reverse=True):
        columns.pop(index)

    # Merge points
    merged_pts = np.vstack(close)
    merged_columns.append(merged_pts)

# Sort again by x
columns = sorted(merged_columns, key=lambda pts: np.min(pts[:, 0]))

# After full merging, if still more than 5, cut to first 5
if len(columns) > 5:
    columns = columns[:5]

# ------------- Save Detected Columns -------------

column_images = []
for i, pts in enumerate(columns):
    warped = four_point_transform(original, pts)
    column_image_path = f"column_{i + 1}.jpeg"
    cv2.imwrite(column_image_path, warped)
    column_images.append((column_image_path, 0, 0))  # Offset is (0,0) because warped

# ------------- Detect Bubbles and Save Coords -------------

final_result = {}

for i, (column_image_path, offset_x, offset_y) in enumerate(column_images):
    column_image = cv2.imread(column_image_path)
    gray_column = cv2.cvtColor(column_image, cv2.COLOR_BGR2GRAY)

    blurred_column = cv2.GaussianBlur(gray_column, (3, 3), 0)

    _, thresh_column = cv2.threshold(blurred_column, 127, 255, cv2.THRESH_BINARY_INV)

    contours_bubbles, _ = cv2.findContours(thresh_column, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bubbles_in_column = []

    for cnt in contours_bubbles:
        x_bubble, y_bubble, w_bubble, h_bubble = cv2.boundingRect(cnt)

        if 50 < cv2.contourArea(cnt) < 500:  # Filtering bubbles
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

# ------------- Print Final Result -------------
print(json.dumps(final_result, indent=4))
