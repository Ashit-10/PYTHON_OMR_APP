# === Step 12: Draw final evaluation circles, pink dot, and tick/cross marks ===

final_visual = original.copy()

column_contours = {i+1: columns[i] for i in range(len(columns))}

for col_num in range(1, 6):
    points = locations[str(col_num)]

    for q_idx in range(0, len(points), 4):
        question_number = (col_num - 1) * (len(points) // 4) + (q_idx // 4) + 1
        q_no_str = str(question_number)

        detected = filtered_data.get(q_no_str, [])
        actual = answer_key.get(q_no_str, [])

        # Transformation matrix for this column
        src_pts = np.array([
            [0, 0],
            [186 - 1, 0],
            [186 - 1, 450 - 1],
            [0, 450 - 1]
        ], dtype="float32")
        dst_pts = order_points(column_contours[col_num])
        M = cv2.getPerspectiveTransform(src_pts, dst_pts)

        # Draw circles
        for j in range(4):
            idx = q_idx + j
            if idx >= len(points):
                break
            x, y = points[idx]
            pts = np.array([[[x, y]]], dtype="float32")
            transformed = cv2.perspectiveTransform(pts, M)
            x_orig, y_orig = transformed[0][0]
            x_orig, y_orig = int(x_orig), int(y_orig)

            option_label = ["A", "B", "C", "D"][j]

            if not detected:
                circle_color = (255, 0, 0)  # Blue
                cv2.circle(final_visual, (x_orig, y_orig), 15, circle_color, thickness=4)

            elif len(detected) > 1:
                if option_label in detected:
                    circle_color = (0, 0, 255)  # Red
                    cv2.circle(final_visual, (x_orig, y_orig), 15, circle_color, thickness=4)

            else:
                if option_label == detected[0]:
                    if detected[0] in actual:
                        circle_color = (0, 255, 0)  # Green
                    else:
                        circle_color = (0, 0, 255)  # Red
                    cv2.circle(final_visual, (x_orig, y_orig), 15, circle_color, thickness=4)

        # Draw pink dot on correct option
        if actual:
            for correct_option in actual:
                correct_idx = ["A", "B", "C", "D"].index(correct_option)
                correct_x, correct_y = points[q_idx + correct_idx]
                pts = np.array([[[correct_x, correct_y]]], dtype="float32")
                transformed = cv2.perspectiveTransform(pts, M)
                cx, cy = transformed[0][0]
                cx, cy = int(cx), int(cy)
                cv2.circle(final_visual, (cx, cy), 5, (255, 0, 255), thickness=-1)  # Pink dot

        # Draw Tick or Cross at small rectangle (right of D)
        d_idx = q_idx + 3  # D option
        if d_idx < len(points):
            x_d, y_d = points[d_idx]
            pts = np.array([[[x_d, y_d]]], dtype="float32")
            transformed = cv2.perspectiveTransform(pts, M)
            x_d_orig, y_d_orig = transformed[0][0]
            x_d_orig, y_d_orig = int(x_d_orig), int(y_d_orig)

            # Shift to right to reach rectangle box
            x_box, y_box = x_d_orig + 30, y_d_orig

            # Decide Tick or Cross
            if not detected:
                # No attempt -> no tick or cross
                pass
            elif len(detected) > 1:
                # Multiple answers selected -> Cross
                cv2.putText(final_visual, "✗", (x_box, y_box), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            else:
                if detected[0] in actual:
                    # Correct -> Tick
                    cv2.putText(final_visual, "✓", (x_box, y_box), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 200, 0), 3)
                else:
                    # Wrong -> Cross
                    cv2.putText(final_visual, "✗", (x_box, y_box), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)

# Save final visual
cv2.imwrite("final_result.jpg", final_visual)
print("\nSaved final evaluated image -> final_result.jpg")
