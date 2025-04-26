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

# Loop over various blur values for experimentation
blur_values = [(1, 1), (3, 3), (5, 5), (7, 7), (9, 9), (11, 11)]
contours_all_blurs = []

# List to hold detected columns
columns = []

for blur_value in blur_values:
    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, blur_value, 0)

    # Adaptive thresholding for binary conversion
    blockSize = 27  # Adjustable block size
    C = 5  # Adjustable constant for thresholding
    thresh1 = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, blockSize, C)

    # Morphological operations to enhance square/rectangular features
    kernel_size = 3  # Kernel size for morphological operations
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    thresh1 = cv2.morphologyEx(thresh1, cv2.MORPH_CLOSE, kernel)

    # Find contours after thresholding and morphological operations
    contours, _ = cv2.findContours(thresh1, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours_all_blurs.append(contours)

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

            # Filters: Area and Aspect Ratio tuned for OMR columns
            if 28000 < area < 300000 and 1.4 < aspect_ratio < 4.0:
                columns.append((x, y, w, h))

    if len(columns) == 5:  # We want only 5 columns detected
        break

# Save the detected columns as separate images
column_images = []
for i, (x, y, w, h) in enumerate(columns):
    column_image = original[y:y + h, x:x + w]  # Crop the image to get the column
    column_image_path = f"column_{i + 1}.jpeg"
    cv2.imwrite(column_image_path, column_image)  # Save the image
    column_images.append(column_image_path)

# Now loop through the saved images (detected columns) and detect bubbles
bubble_coordinates = []

for i, column_image_path in enumerate(column_images):
    column_image = cv2.imread(column_image_path)
    gray_column = cv2.cvtColor(column_image, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian Blur to reduce noise
    blurred_column = cv2.GaussianBlur(gray_column, (5, 5), 0)

    # Threshold to get binary image
    _, thresh_column = cv2.threshold(blurred_column, 127, 255, cv2.THRESH_BINARY_INV)

    # Find contours for bubbles
    contours_bubbles, _ = cv2.findContours(thresh_column, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Loop through contours to detect bubbles and print coordinates
    for cnt in contours_bubbles:
        # Get the bounding box of each contour
        x_bubble, y_bubble, w_bubble, h_bubble = cv2.boundingRect(cnt)
        
        # Filtering by size (adjust as necessary)
        if 100 < cv2.contourArea(cnt) < 500:  # Example size filter, adjust accordingly
            bubble_coordinates.append((x_bubble + x, y_bubble + y))  # Add original offset to the coordinates
            cv2.rectangle(column_image, (x_bubble, y_bubble), (x_bubble + w_bubble, y_bubble + h_bubble), (0, 255, 0), 2)

    # Show the image with detected bubbles
    plt.imshow(cv2.cvtColor(column_image, cv2.COLOR_BGR2RGB))
    plt.title(f"Bubbles Detected in Column {i + 1}")
    plt.axis('off')
    plt.show()

    # Print bubble coordinates
    print(f"Bubbles detected in Column {i + 1}:")
    for coord in bubble_coordinates:
        print(coord)

