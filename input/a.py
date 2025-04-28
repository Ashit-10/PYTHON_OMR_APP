if not detected_columns:
    # Draw rectangles found so far for visualization
    visual = original.copy()
    for i, points in enumerate(columns):
        points = points.reshape((-1,1,2)).astype(np.int32)
        cv2.polylines(visual, [points], isClosed=True, color=(0,0,255), thickness=5)  # RED for error

    # Add error message text at bottom
    h, w = visual.shape[:2]
    new_image = np.ones((h + 180, w, 3), dtype=np.uint8) * 255  # white background
    new_image[:h, :w] = visual

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1
    thickness = 2
    y_start = h + 40

    cv2.putText(new_image, f"ERROR: Columns not detected", (50, y_start), font, font_scale, (0, 0, 255), thickness)
    cv2.putText(new_image, f"FILE: {photo_name}", (50, y_start + 40), font, font_scale, (0, 0, 0), thickness)

    # Save to error folder
    import os
    os.makedirs("error", exist_ok=True)
    error_filename = f"error/{photo_name}_error.jpg"
    cv2.imwrite(error_filename, new_image)

    print(f"Saved {error_filename} due to column detection failure.")

    # Skip further processing for this image
    return 0, 0, 0, 0, "00", "Column Detection Failed"
