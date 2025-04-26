import cv2
import numpy as np
import matplotlib.pyplot as plt
import json

# Load the image
image_path = '/mnt/data/IMG_9842.jpeg'  # Your uploaded image path
image = cv2.imread(image_path)

# Resize for faster processing (optional, remove if you want original size)
image = cv2.resize(image, (1200, 550))

original = image.copy()

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Apply Gaussian Blur
blurred = cv2.GaussianBlur(gray, (5, 5), 0)

# Edge Detection
edges = cv2.Canny(blurred, 50, 150)

# Find Contours
contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

columns = []

for cnt in contours:
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

    if len(approx) == 4:  # We are looking for rectangles (4 sides)
        x, y, w, h = cv2.boundingRect(approx)
        area = cv2.contourArea(cnt)
        aspect_ratio = h / float(w) if w != 0 else 0

        if 20000 < area < 300000 and 1.3 < aspect_ratio < 4.5:
            columns.append(approx)

# Sort columns left to right
columns = sorted(columns, key=lambda c: cv2.boundingRect(c)[0])

# Limit to 5
columns = columns[:5]

# Warp each column
def order_points(pts):
    pts = pts.reshape(4, 2)
    rect = np.zeros((4, 2), dtype="float32")

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]     # top-left
    rect[2] = pts[np.argmax(s)]     # bottom-right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left

    return rect

# Destination size for each column
dst_width = 200
dst_height = 500

column_images = []

for i, box in enumerate(columns):
    rect = order_points(box)

    dst = np.array([
        [0, 0],
        [dst_width - 1, 0],
        [dst_width - 1, dst_height - 1],
        [0, dst_height - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(original, M, (dst_width, dst_height))

    column_image_path = f"column_{i+1}.jpeg"
    cv2.imwrite(column_image_path, warped)
    column_images.append((column_image_path, warped))

# ------------------ Bubble Detection ------------------

final_result = {}

for i, (column_image_path, column_img) in enumerate(column_images):
    gray_col = cv2.cvtColor(column_img, cv2.COLOR_BGR2GRAY)
    blurred_col = cv2.GaussianBlur(gray_col, (3, 3), 0)
    _, thresh_col = cv2.threshold(blurred_col, 127, 255, cv2.THRESH_BINARY_INV)

    contours_bubbles, _ = cv2.findContours(thresh_col, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    bubbles_in_column = []

    for cnt in contours_bubbles:
        x_bubble, y_bubble, w_bubble, h_bubble = cv2.boundingRect(cnt)

        if 30 < cv2.contourArea(cnt) < 500:
            bubbles_in_column.append({
                "x": int(x_bubble),
                "y": int(y_bubble)
            })
            cv2.rectangle(column_img, (x_bubble, y_bubble),
                          (x_bubble + w_bubble, y_bubble + h_bubble),
                          (0, 255, 0), 1)

    final_result[f"Column_{i + 1}"] = bubbles_in_column

    plt.imshow(cv2.cvtColor(column_img, cv2.COLOR_BGR2RGB))
    plt.title(f"Bubbles Detected in Column {i + 1}")
    plt.axis('off')
    plt.show()

# ------------------ Final Result ------------------

print(json.dumps(final_result, indent=4))
