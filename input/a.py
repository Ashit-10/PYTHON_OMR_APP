import json

# === Step 5: Draw green unfilled circles based on locations.txt ===

# Load locations.txt
with open('/mnt/data/locations.txt', 'r') as f:
    locations = json.load(f)

# Draw circles on each column image
for i in range(1, 6):  # For columns 1 to 5
    img = cv2.imread(f"column_{i}.jpg")
    points = locations[str(i)]  # Get points for this column

    for (x, y) in points:
        cv2.circle(img, (x, y), 15, (0, 255, 0), thickness=2)  # Green, unfilled circle

    cv2.imwrite(f"column_{i}_with_circles.jpg", img)
    print(f"Saved -> column_{i}_with_circles.jpg with circles.")

print("\nAll circles drawn successfully!")
