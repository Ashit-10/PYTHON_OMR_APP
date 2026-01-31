import os
import re
import json
import requests
import base64
from tqdm import tqdm

# --- CONFIGURATION ---
GITHUB_TOKEN = "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"
REPO_OWNER = "Ashit-10"
REPO_NAME = "omr_exams"
YEAR = "2026"

# --- CONFIGURATION ---

# Capture arguments from the Web UI
if len(sys.argv) > 3:
    tuition = sys.argv[1]
    cls = sys.argv[2]
    subject = sys.argv[3]
else:
    tuition = "unknown"
    cls = "unknown"
    subject = "unknown"

print(f"--- STARTING SYNC ---")
print(f"Tuition: {tuition.upper()} | Class: {cls} | Subject: {subject}")

def get_total_marks():
    filename = "answer_key.txt"
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return len(data)
            except:
                return 0
    return 0

def get_student_names(tuition, cls):
    filename = f"{tuition}_class-{cls}_rolls.txt"
    name_map = {}
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            matches = re.findall(r'"(\d+)":\s*"([^"]+)"', content)
            for roll, name in matches:
                name_map[int(roll)] = name
    return name_map

def upload_to_github(session, local_path, github_path):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{github_path}"
    try:
        with open(local_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        
        get_file = session.get(url)
        data = {"message": f"Upload {github_path}", "content": content}
        if get_file.status_code == 200:
            data["sha"] = get_file.json()["sha"]
        
        res = session.put(url, json=data)
        return res.status_code in [200, 201]
    except Exception as e:
        print(f"Error uploading {local_path}: {e}")
        return False

def run():
    raw_subject = subject.strip()
    exam_no = 1
    clean_subject = raw_subject.replace(" ", "").lower()
    folder_path = f"class-{cls}_{clean_subject}_{exam_no}"
    
    github_tuition = tuition.upper()
    github_base = f"{github_tuition}/{YEAR}/class-{cls}"
    github_img_folder = f"{github_base}/{folder_path}/eval_files"
    
    output_folder = "./output"
    names_db = get_student_names(tuition, cls)
    
    if not os.path.exists(output_folder):
        print(f"❌ Error: Folder '{output_folder}' not found!")
        return

    # 2. Process Data
    raw_files = [f for f in os.listdir(output_folder) if "_" in f and f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    student_list = []
    for file_name in raw_files:
        match = re.search(r"(\d+)_(\d+)", file_name)
        if match:
            roll, mark = int(match.group(1)), int(match.group(2))
            student_list.append({
                "roll": roll, "mark": mark, "file": file_name,
                "name": names_db.get(roll, f"Student {roll}"),
                "path": f"eval_files/{file_name}" 
            })

    ranked_students = sorted(student_list, key=lambda x: x['mark'], reverse=True)
    for i, s in enumerate(ranked_students): s['rank'] = i + 1
    total_m = get_total_marks()

    # 3. HTML Generation
    html_content = f"""<!DOCTYPE html>...[Omitted for brevity, keep your HTML code here]...</html>"""

    # 4. Save Locally
    output_filename = f"class-{cls}_{clean_subject}_test_{exam_no}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ Created: {output_filename}")

    # 5. Upload to GitHub
    session = requests.Session()
    session.headers.update({"Authorization": f"token {GITHUB_TOKEN}"})
    
    print(f"📤 Uploading HTML...")
    html_success = upload_to_github(session, output_filename, f"{github_base}/{output_filename}")
    
    if html_success:
        print(f"🚀 Uploading {len(student_list)} images...")
        count = 0
        total = len(student_list)
        
        for s in student_list:
            success = upload_to_github(session, f"{output_folder}/{s['file']}", f"{github_img_folder}/{s['file']}")
            count += 1
            if success:
                # Simple text progress that looks good in the web box
                print(f"[{count}/{total}] Uploaded: {s['name']}")
            else:
                print(f"[{count}/{total}] ❌ Failed: {s['name']}")
            
            # Flush stdout so the browser sees the line immediately
            sys.stdout.flush()

        os.remove(output_filename)
        print(f"\n✅ SUCCESS! All files synced to GitHub.")
    else:
        print("❌ HTML upload failed. Aborting image sync.")

if __name__ == "__main__":
    run()
