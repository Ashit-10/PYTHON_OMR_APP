import cv2
import numpy as np

# Load the image
image = cv2.imread('input_image.jpg')

# Convert to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Apply edge detection
edges = cv2.Canny(gray, 50, 150)

# Find contours
contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

# Iterate through contours and detect rectangles
rectangles = []
for contour in contours:
    # Approximate contour to polygon
    epsilon = 0.04 * cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, epsilon, True)

    # If the polygon has 4 vertices, it's a rectangle
    if len(approx) == 4:
        rectangles.append(approx)

# Now we have the detected rectangles, we need to warp each of them
for rect in rectangles:
    # Get the corner points of the rectangle
    points = rect.reshape(4, 2)

    # Sort the points in a consistent order (top-left, top-right, bottom-right, bottom-left)
    points = sorted(points, key=lambda x: x[0])
    if points[0][1] > points[1][1]:
        points[0], points[1] = points[1], points[0]
    if points[2][1] > points[3][1]:
        points[2], points[3] = points[3], points[2]

    # Create the target points for perspective transformation (a perfect rectangle)
    width = int(np.linalg.norm(points[0] - points[1]))
    height = int(np.linalg.norm(points[0] - points[3]))
    target_points = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype="float32")

    # Perform perspective warp for each rectangle
    M = cv2.getPerspectiveTransform(np.float32(points), target_points)
    warped = cv2.warpPerspective(image, M, (width, height))

    # Show or save the warped rectangle
    cv2.imshow("Warped Rectangle", warped)
    cv2.waitKey(0)

cv2.destroyAllWindows()
