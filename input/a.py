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

# === Step 6: Canny and Measure White Pixels at Circle Locations ===

final_data = {}

question_counter = 1  # Start question number from 1

for col_num in range(1, 6):
    img = cv2.imread(f"column_{col_num}_with_circles.jpg", cv2.IMREAD_GRAYSCALE)

    # Apply Canny edge detection
    edges = cv2.Canny(img, threshold1=50, threshold2=150)

    points = locations[str(col_num)]  # Get corresponding points

    for i in range(0, len(points), 4):  # Every 4 points (A, B, C, D)
        question_data = []
        option_labels = ["A", "B", "C", "D"]
        
        for j in range(4):
            idx = i + j
            if idx >= len(points):
                break
            x, y = points[idx]

            # Define a small ROI around the (x, y)
            roi_size = 10  # 10x10 square
            x1, y1 = max(0, x - roi_size), max(0, y - roi_size)
            x2, y2 = min(edges.shape[1], x + roi_size), min(edges.shape[0], y + roi_size)
            roi = edges[y1:y2, x1:x2]

            white_pixels = cv2.countNonZero(roi)

            question_data.append([option_labels[j], x, y, white_pixels])

        final_data[str(question_counter)] = question_data
        question_counter += 1

# === Step 7: Print Final JSON ===
print("\n\n=== Final Data ===\n")
print(json.dumps(final_data, indent=2))
