import cv2
import numpy as np

# Suppose final_visual is your final output
h, w = final_visual.shape[:2]

# Create a new image: add 150px extra height
new_image = np.ones((h + 150, w, 3), dtype=np.uint8) * 255  # white background

# Paste the original image on top
new_image[:h, :w] = final_visual

# Now, write the result summary at bottom
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 1
thickness = 2
y_start = h + 40

cv2.putText(new_image, f"CORRECT: {correct}", (50, y_start), font, font_scale, (0, 200, 0), thickness)
cv2.putText(new_image, f"INCORRECT: {incorrect}", (50, y_start + 40), font, font_scale, (0, 0, 255), thickness)
cv2.putText(new_image, f"NOT ATTEMPTED: {unattempted}", (50, y_start + 80), font, font_scale, (255, 0, 0), thickness)
cv2.putText(new_image, f"TOTAL: {correct + incorrect + unattempted}", (50, y_start + 120), font, font_scale, (0, 0, 0), thickness)

# Save final image
cv2.imwrite("final_result_with_summary.jpg", new_image)
print("Saved final image with summary -> final_result_with_summary.jpg")
