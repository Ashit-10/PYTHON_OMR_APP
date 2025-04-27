# === Step 12: Draw final evaluation circles ===

final_visual = original.copy()

# Map each column number to its corresponding contour
column_contours = {i+1: columns[i] for i in range(len(columns))}

# Load all column images and prepare for mapping
for col_num in range(1, 6):
    points = locations[str(col_num)]  # Points for this column

    for q_idx in range(0, len(points), 4):  # Each set of 4 options (A, B, C, D)
        question_number = (col_num - 1) * (len(points) // 4) + (q_idx // 4) + 1
        q_no_str = str(question_number)

        detected = filtered_data.get(q_no_str, [])
        actual = answer_key.get(q_no_str, [])

        for j in range(4):
            idx = q_idx + j
            if idx >= len(points):
                break
            x, y = points[idx]

            # Transform (x, y) back to original image space
            # Map points from column image to original
            src_pts = np.array([
                [0, 0],
                [186 - 1, 0],
                [186 - 1, 450 - 1],
                [0, 450 - 1]
            ], dtype="float32")
            dst_pts = order_points(column_contours[col_num])

            M = cv2.getPerspectiveTransform(src_pts, dst_pts)
            pts = np.array([[[x, y]]], dtype="float32")
            transformed = cv2.perspectiveTransform(pts, M)
            x_orig, y_orig = transformed[0][0]
            x_orig, y_orig = int(x_orig), int(y_orig)

            # Decide color
            option_label = ["A", "B", "C", "D"][j]
            if not detected:
                circle_color = (255, 0, 0)  # Blue for unattempted
            elif option_label in detected and option_label in actual:
                circle_color = (0, 255, 0)  # Green for correct
            elif option_label in detected and option_label not in actual:
                circle_color = (0, 0, 255)  # Red for wrong
            else:
                continue  # No need to draw on unselected correct options

            # Draw circle
            cv2.circle(final_visual, (x_orig, y_orig), 15, circle_color, thickness=4)

# Save the final image
cv2.imwrite("final_result.jpg", final_visual)
print("\nSaved final evaluated image -> final_result.jpg")
