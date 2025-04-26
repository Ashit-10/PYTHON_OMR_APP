import cv2
import numpy as np
import matplotlib.pyplot as plt

# Load the image
image_path = 'input/test6.jpeg'
image = cv2.imread(image_path)

# Resize image to 1200x800
image = cv2.resize(image, (1200, 550))

# Copy original image for later use
original = image.copy()

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
cv2.imshow("hh", gray)
cv2.waitKey(0)
# Loop over various blur values for experimentation
blur_values = [(1, 1), (3, 3), (5, 5), (7, 7), (9, 9), (11, 11)]
contours_all_blurs = []

for blur_value in blur_values:
    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, blur_value, 0)

    ##################################################### New #############################################################
    # Adaptive thresholding for binary conversion
    blockSize = 27  # Adjustable block size
    C = 5  # Adjustable constant for thresholding
    thresh1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, blockSize, C)
    cv2.imshow("hh", thresh1)
    cv2.waitKey(0)
    # Morphological operations to enhance square/rectangular features
    kernel_size = 3  # Kernel size for morphological operations
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    thresh1 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)

    # Find contours after thresholding and morphological operations
    contours, _ = cv2.findContours(thresh1, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours_all_blurs.append(contours)

        # List to hold detected columns
    columns = []

    # Loop through contours and apply filtering based on area and aspect ratio
    for cnt in contours:
        # Approximate the contour to a polygon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # Check if the shape has 4 vertices (rectangular shape)
        if len(approx) >= 4:
            x, y, w, h = cv2.boundingRect(approx)
            area = cv2.contourArea(cnt)
            aspect_ratio = h / float(w) if w != 0 else 0
            # if 18000 < area:
                # print(area, aspect_ratio, w, h,         x, y)

            # Filters: Area and Aspect Ratio tuned for OMR columns
            if 28000 < area < 300000 and 1.4 < aspect_ratio < 4.0:
                print(area, aspect_ratio)
                columns.append((x, y, w, h))

    # print(columns)
    if len(columns) > 5:
         print("Done")
            # print("gone to choose", len(square_contours))
            # square_contours = choose_8(thresh1, square_contours)
            # print(len(square_contours))

    if len(columns) == 5:
            break

    # Optional: Show each processed step for debugging
    # cv2.imshow(f"Blurred with {blur_value}", blurred)
    # cv2.imshow(f"Thresholded with {blur_value}", thresh1)
    # cv2.waitKey(0)

# Optionally, you can examine different contours detected with different blurs to find the best one.
# Select contours from a specific blur (example: using the third blur)
# contours = contours_all_blurs[2]  # Change the index based on your desired blur value


# # Sort columns by their x-coordinate (left to right)
# columns = sorted(columns, key=lambda b: b[0])

# Draw rectangles around detected columns
for (x, y, w, h) in columns:
    # print(x, y)
    cv2.rectangle(original, (x, y), (x + w, y + h), (255, 0, 0), 5)

# Convert BGR to RGB for displaying with matplotlib
original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)

# Display the final image with detected columns
plt.figure(figsize=(12, 18))
plt.imshow(original_rgb)
plt.axis('off')
plt.title('Detected OMR Columns')
plt.show()
