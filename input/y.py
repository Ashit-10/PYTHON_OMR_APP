import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the image
image_path = 'input/test7.jpeg'
image = cv2.imread(image_path)

# Resize image to 900x440
image = cv2.resize(image, (900, 440))

# Copy original image for later use
original = image.copy()

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
cv2.imshow("Grayscale", gray)
cv2.waitKey(0)

# Loop over various blur values for experimentation
blur_values = [(5, 5)]  # Only one good blur needed, not multiple
contours_all_blurs = []

for blur_value in blur_values:
    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, blur_value, 0)

    # Adaptive thresholding
    blockSize = 19  # Smaller block size works better here
    C = 8
    thresh1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, blockSize, C)
    cv2.imshow("Threshold", thresh1)
    cv2.waitKey(0)

    # Morphological closing to fill small gaps
    kernel_size = 9
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    thresh1 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(thresh1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours_all_blurs.append(contours)

    # List to hold detected columns
    columns = []

    for cnt in contours:
        # Approximate the contour to a polygon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # Check if rectangular
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            area = cv2.contourArea(cnt)
            aspect_ratio = h / float(w) if w != 0 else 0

            if 50000 < area < 300000 and 1.2 < aspect_ratio < 2.5:  # Tight filters
                print("Detected:", area, aspect_ratio, w, h, x, y)
                columns.append((x, y, w, h))

    print("Columns found:", len(columns))
    if len(columns) == 5:
        print("Found 5 Columns!")
        break  # Exit loop once found

# Sort columns by x position (left to right)
columns = sorted(columns, key=lambda b: b[0])

# Draw rectangles around detected columns
for (x, y, w, h) in columns:
    cv2.rectangle(original, (x, y), (x + w, y + h), (255, 0, 0), 5)

# Convert BGR to RGB for matplotlib
original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)

# Show result
plt.figure(figsize=(12, 18))
plt.imshow(original_rgb)
plt.axis('off')
plt.title('Detected OMR Columns')
plt.show()
