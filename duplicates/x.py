import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the image
image_path = '/mnt/data/078bdbd9-0504-4d3a-83b2-54b130c8f273.jpeg'
image = cv2.imread(image_path)
original = image.copy()

# Preprocessing
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)

# Edge detection
edges = cv2.Canny(blurred, 30, 120)

# Find contours
contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

columns = []

for cnt in contours:
    # Approximate the contour
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    
    if len(approx) == 4:
        x, y, w, h = cv2.boundingRect(approx)
        area = cv2.contourArea(cnt)
        aspect_ratio = h / float(w) if w != 0 else 0
        
        # Filters: Area and Aspect Ratio tuned for OMR columns
        if 50000 < area < 300000 and 2.0 < aspect_ratio < 6.0:
            columns.append((x, y, w, h))

# Sort by x-coordinate (left to right)
columns = sorted(columns, key=lambda b: b[0])

# Draw rectangles on detected columns
for (x, y, w, h) in columns:
    cv2.rectangle(original, (x, y), (x + w, y + h), (255, 0, 0), 5)

# Convert BGR to RGB
original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)

# Display
plt.figure(figsize=(12, 18))
plt.imshow(original_rgb)
plt.axis('off')
plt.title('Detected 5 OMR Columns')
plt.show()
