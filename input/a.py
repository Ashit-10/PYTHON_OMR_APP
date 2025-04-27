# === Step 7: Print Final JSON ===
print("\n\n=== Detailed Final Data (with white pixel counts) ===\n")
print(json.dumps(final_data, indent=2))

# === Step 8: Filter options based on white pixel threshold ===

filtered_data = {}

for q_no, options in final_data.items():
    selected_options = []
    for opt in options:
        label, x, y, white_pixel_value = opt
        if white_pixel_value > 200:
            selected_options.append(label)
    filtered_data[q_no] = selected_options

print("\n\n=== Filtered Data (options with white pixels > 200) ===\n")
print(json.dumps(filtered_data, indent=2))
