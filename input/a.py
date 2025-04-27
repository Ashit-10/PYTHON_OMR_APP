import cv2
import numpy as np

# === Utilities ===

def order_points(pts):
    """Order points: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # Top-left
    rect[2] = pts[np.argmax(s)]  # Bottom-right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # Top-right
    rect[3] = pts[np.argmax(diff)]  # Bottom-left
    return rect

def four_point_transform(image, pts):
    """Apply perspective warp."""
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

# === Step 1: Read and preprocess ===

# Use your uploaded image
image_path = 'input/test9.jpeg'  # Your uploaded file path
image = cv2.imread(image_path)
image = cv2.resize(image, (1200, 550))  # Resize for faster processing
original = image.copy()

gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                cv2.THRESH_BINARY_INV, 27, 5)

# Find contours
contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

columns = []

# === Step 2: Detect rectangles ===
for cnt in contours:
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    if len(approx) == 4:  # Only quadrilaterals
        area = cv2.contourArea(cnt)
        x, y, w, h = cv2.boundingRect(approx)
        aspect_ratio = h / float(w) if w != 0 else 0

        # Filter based on size and aspect ratio
        if 20000 < area < 300000 and 1.3 < aspect_ratio < 5.0:
            columns.append(approx.reshape(4, 2))

# Sort left to right
columns = sorted(columns, key=lambda c: np.min(c[:, 0]))

print(f"Detected {len(columns)} columns.")

# === Step 3: Draw rectangles for visualization ===

visual = original.copy()

for i, points in enumerate(columns):
    points = points.reshape((-1,1,2)).astype(np.int32)
    cv2.polylines(visual, [points], isClosed=True, color=(0,255,0), thickness=5)
    cv2.putText(visual, f"Col {i+1}", tuple(points[0][0]), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)


cv2.imwrite("with_rectangles.jpg", visual)
print("Saved visualization with rectangles -> with_rectangles.jpg")

# === Step 4: Warp each column separately ===

for i, corner_points in enumerate(columns):
    warped = four_point_transform(original, corner_points)
    warped = cv2.resize(warped, (186, 450))  # Resize for faster processing

    cv2.imwrite(f"column_{i+1}.jpg", warped)
    print(f"Saved warped column -> column_{i+1}.jpg")

print("\nAll Done! Now you can see the results.")
import json

# === Step 5: Draw green unfilled circles based on locations.txt ===

# Load locations.txt
with open('locations.txt', 'r') as f:
    locations = json.load(f)

# Draw circles on each column image
for i in range(1, 6):  # For columns 1 to 5
    img = cv2.imread(f"column_{i}.jpg")
    points = locations[str(i)]  # Get points for this column

    for (x, y) in points:
        cv2.circle(img, (x, y), 10, (0, 255, 0), thickness=2)  # Green, unfilled circle

    cv2.imwrite(f"column_{i}_with_circles.jpg", img)
    print(f"Saved -> column_{i}_with_circles.jpg with circles.")

print("\nAll circles drawn successfully!")
