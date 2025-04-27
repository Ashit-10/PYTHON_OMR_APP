# === Step 9: Load correct answers ===

with open('answer_key.txt', 'r') as f:
    answer_key = json.load(f)

# === Step 10: Compare answers ===

correct = 0
incorrect = 0
unattempted = 0

for q_no in range(1, 51):
    q_no_str = str(q_no)
    detected = filtered_data.get(q_no_str, [])
    actual = answer_key.get(q_no_str, [])

    if not detected:
        unattempted += 1
    elif sorted(detected) == sorted(actual):
        correct += 1
    else:
        incorrect += 1

# === Step 11: Print result ===

print("\n\n=== Result Summary ===")
print(f"Correct answers: {correct}")
print(f"Incorrect answers: {incorrect}")
print(f"Unattempted questions: {unattempted}")
