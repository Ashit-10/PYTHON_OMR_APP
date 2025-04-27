import cv2
import numpy as np
import json

# ======= Utilities =======

def order_points(pts):
    """ Order the points: top-left, top-right, bottom-right, bottom-left """
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]      # top-left
    rect[2] = pts[np.argmax(s)]      # bottom-right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]   # top-right
    rect[3] = pts[np.argmax(diff)]   # bottom-left

    return rect

def four_point_transform(image, pts):
    """ Apply perspective transform """
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = max(int(heightA), int(heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))

    return warped

def is_bubble_filled(white_pixel_count, threshold=100):
    """ Return True if bubble is filled based on white pixel count """
    return white_pixel_count < threshold

# ======= Step 1: Deskew and Detect Columns =======

image_path = 'input/test8.jpeg'
image = cv2.imread(image_path)
image = cv2.resize(image, (1200, 550))
original = image.copy()

gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Deskew
edges = cv2.Canny(gray, 50, 150)
lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)

angle = 0
if lines is not None:
    for rho, theta in lines[:, 0]:
        angle += theta
    angle /= len(lines)
    angle = (angle - np.pi/2) * (180/np.pi)

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    image = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    original = image.copy()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    print(f"Deskewed image by {angle:.2f} degrees")

# Detect contours
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, 27, 5)

kernel = np.ones((3, 3), np.uint8)
thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

columns = []

for cnt in contours:
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    if len(approx) == 4:
        area = cv2.contourArea(cnt)
        x, y, w, h = cv2.boundingRect(approx)
        aspect_ratio = h / float(w) if w != 0 else 0
        if 28000 < area < 300000 and 1.4 < aspect_ratio < 4.0:
            columns.append(approx.reshape(4, 2))

# Sort columns left to right
columns = sorted(columns, key=lambda c: np.min(c[:, 0]))
columns = columns[:5]

# Warp each column
for i, corner_points in enumerate(columns):
    warped = four_point_transform(original, corner_points)
    cv2.imwrite(f"column_{i + 1}.jpeg", warped)

print("Warped and saved all 5 columns perfectly!")

# ======= Step 2: Read locations.txt, Analyze Bubbles =======

with open('locations.txt', 'r') as f:
    locations = json.load(f)

final_data = {}
question_number = 1

for i in range(5):
    column_image_path = f"column_{i + 1}.jpeg"
    column_image = cv2.imread(column_image_path)
    column_image_copy = column_image.copy()

    column_locations = locations[str(i + 1)]
    question_bubbles = []

    for (x, y) in column_locations:
        x, y = int(x), int(y)

        half_size = 7
        roi = column_image_copy[max(0, y - half_size): y + half_size + 1,
                                max(0, x - half_size): x + half_size + 1]

        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        white_pixel_count = cv2.countNonZero(gray_roi)

        filled = is_bubble_filled(white_pixel_count)

        # Draw
        color = (0, 255, 0) if filled else (0, 0, 255)  # Green if filled, Red if empty
        cv2.circle(column_image, (x, y), 12, color, -1)

        question_bubbles.append({
            "x": x,
            "y": y,
            "white_pixel_count": white_pixel_count,
            "filled": filled
        })

        print(f"Question {question_number}, Bubble {len(question_bubbles)}: x = {x}, y = {y}, white pixels = {white_pixel_count}, Filled: {filled}")

    column_image_with_circles_path = f"column_{i + 1}_with_circles.jpeg"
    cv2.imwrite(column_image_with_circles_path, column_image)

    final_data[str(question_number)] = question_bubbles
    question_number += 1

    print(f"Saved {column_image_with_circles_path}")

# Save JSON to file
with open('white_pixel_data.txt', 'w') as f:
    json.dump(final_data, f, indent=4)

print("\nAll images with circles saved successfully and white pixel data printed.")
