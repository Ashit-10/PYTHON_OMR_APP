import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the image
image_path = '/mnt/data/IMG_9839.jpeg'
image = cv2.imread(image_path)

# Resize image
image = cv2.resize(image, (900, 440))

# Copy original
original = image.copy()

# Grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Apply Gaussian Blur
blurred = cv2.GaussianBlur(gray, (5, 5), 0)

# Adaptive threshold
thresh = cv2.adaptiveThreshold(blurred, 255, 
                               cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                               cv2.THRESH_BINARY_INV, 
                               blockSize=15, C=4)

# Morphological close (fill small holes)
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

# Find contours
contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

columns = []

for cnt in contours:
    area = cv2.contourArea(cnt)
    if area > 10000:  # Only large rectangles
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) == 4:  # Rectangle check
            x, y, w, h = cv2.boundingRect(approx)
            aspect_ratio = h / float(w)
            if 1.5 < aspect_ratio < 3.5:  # Tune this if needed
                columns.append((x, y, w, h))

# Sort columns left to right
columns = sorted(columns, key=lambda x: x[0])

# Draw rectangles
for (x, y, w, h) in columns:
    cv2.rectangle(original, (x, y), (x + w, y + h), (0, 255, 0), 5)

# Display
original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
plt.figure(figsize=(12, 8))
plt.imshow(original_rgb)
plt.axis('off')
plt.title('Detected 5 OMR Columns')
plt.show()
