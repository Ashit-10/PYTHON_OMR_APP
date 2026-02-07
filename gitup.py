

# --- CONFIGURATION ---
GITHUB_TOKEN = "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"
REPO_OWNER = "Ashit-10"
REPO_NAME = "omr_exams"
YEAR = "2026"
site_link = "https://theomr.shop"
import os
import re
import json
import requests
import base64
import sys



# Capture arguments from the Web UI (passed via subprocess)
if len(sys.argv) > 3:
    tuition = sys.argv[1]
    cls = sys.argv[2]
    subject = sys.argv[3]
else:
    tuition = "unknown"
    cls = "unknown"
    subject = "unknown"

print(f"--- INITIALIZING GITHUB SYNC ---")
print(f"Target: {tuition.upper()} | Class: {cls} | Subject: {subject}")
def get_next_exam_no(session, github_base, cls, clean_subject):
    """Checks GitHub to see how many exams exist and returns the next number."""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{github_base}"
    res = session.get(url)
    
    exam_no = 1
    if res.status_code == 200:
        contents = res.json()
        # Look for folders like "class-10_math_1", "class-10_math_2"
        pattern = f"class-{cls}_{clean_subject}_"
        existing_exams = [
            item['name'] for item in contents 
            if item['type'] == 'dir' and item['name'].startswith(pattern)
        ]
        
        if existing_exams:
            # Find the highest number currently in use
            numbers = []
            for name in existing_exams:
                try:
                    num = int(name.split('_')[-1])
                    numbers.append(num)
                except ValueError:
                    continue
            if numbers:
                exam_no = max(numbers) + 1
    
    return exam_no
def get_total_marks():
    """Parses answer_key.txt as JSON and returns the count of items."""
    filename = "answer_key.txt"
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return len(data)
            except json.JSONDecodeError:
                content = f.read()
                items = re.findall(r'"[^"]+"\s*:\s*"[^"]+"', content)
                return len(items)
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
        print(f"Error: {e}")
        return False

def run():
    raw_subject = subject.strip()
    exam_no = 1
    clean_subject = raw_subject.replace(" ", "").lower()
    
    github_tuition = tuition.upper()
    github_base = f"{github_tuition}/{YEAR}/class-{cls}"
    
    session = requests.Session()
    session.headers.update({"Authorization": f"token {GITHUB_TOKEN}"})
    exam_no = get_next_exam_no(session, github_base, cls, clean_subject)
    print(f"📈 Setting Exam Number to: {exam_no}")
    
    folder_path = f"class-{cls}_{clean_subject}_{exam_no}"
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
                "path": f"{folder_path}/eval_files/{file_name}" 
            })

    gallery_students = sorted(student_list, key=lambda x: x['roll'])
    ranked_students = sorted(student_list, key=lambda x: x['mark'], reverse=True)
    for i, s in enumerate(ranked_students): s['rank'] = i + 1
    
    total_possible_marks = get_total_marks()

    # 3. HTML Generation (With New Button Added)
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Answer sheets</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        #heading{{ display: flex; justify-content: center; padding-top: 20px; padding-right: 10%; }}
        body {{ font-family: Arial, sans-serif; padding: 5px; }}
        #search-bar {{ margin-bottom: 20px; width: 100%; padding: 10px; font-size: 16px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 8px; vertical-align: middle; }}
        tr:nth-child(even) {{ background-color: #eee9e9; }}
        a {{ text-decoration: none !important; color: blue; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1 id="heading">{clean_subject.upper()} [unit test - {exam_no}]</h1>
    <nav class="navbar bg-body-tertiary px-3 mb-3">
        <ul class="nav nav-pills">
            <li class="nav-item me-2">
               <a href="class-{cls}_{clean_subject.lower()}_{exam_no}/question.pdf" class="btn btn-outline-warning" target="_blank">
                  View question paper
               </a>
            </li>
            <li class="nav-item">
               <a href="{site_link}/50?user=student&filename={github_base}/class-{cls}_{clean_subject.lower()}_{exam_no}/answer_key.txt" class="btn btn-outline-primary" target="_blank">
                  View Answer Key
               </a>
            </li>
        </ul>
    </nav>
    <input type="text" id="search-bar" placeholder="Search for names...">
    <table id="name-table">
        <thead><tr><th>Name</th><th>Total mark</th><th>Secured mark</th><th>Rank</th></tr></thead>
        <tbody>"""

    for s in ranked_students:
        html_content += f"""
            <tr>
                <td><a href="{s['path']}">{s['name']}</a></td>
                <td>{total_possible_marks}</td>
                <td>{s['mark']}</td>
                <td>{s['rank']}</td>
            </tr>"""

    html_content += f"""
        </tbody>
    </table>
    <br><br>
    <h2 id="heading2">&nbsp;&nbsp;&nbsp;All student's answer sheets (Roll number wise).</h2>
    <div id="gallery-container">"""

    for s in gallery_students:
        html_content += f"""
        <div class="imgs" style="text-align:center; margin-bottom:40px;">
            <img src="{s['path']}" alt="{s['name']}" style="max-width:98%; height:auto; border:1px solid #ccc;"> 
            <p>{s['name']} (Roll: {s['roll']})</p>
        </div>"""

    html_content += """
    </div>
    <script>
        const searchBar = document.getElementById('search-bar');
        searchBar.addEventListener('input', () => {
            const filter = searchBar.value.trim().toLowerCase();
            document.querySelectorAll('#name-table tbody tr').forEach(row => {
                row.style.display = row.cells[0].textContent.toLowerCase().includes(filter) ? '' : 'none';
            });
            document.querySelectorAll('.imgs').forEach(div => {
                div.style.display = div.querySelector('img').alt.toLowerCase().includes(filter) ? '' : 'none';
            });
        });
    </script>
</body>
</html>"""

    # 4. Save Locally
    output_filename = f"class-{cls}_{clean_subject}_{exam_no}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print()
    print(f"✅ HTML Generated:\n {output_filename}")
    print()

    # 5. Upload to GitHub (Automatic)
    session = requests.Session()
    session.headers.update({"Authorization": f"token {GITHUB_TOKEN}"})
    
    print(f"📤 Uploading HTML to GitHub...")
    html_success = upload_to_github(session, output_filename, f"{github_base}/{output_filename}")
    
    # NEW: Upload answer_key.txt to the same directory as the HTML
    if os.path.exists("answer_key.txt"):
        print(f"📤 Uploading answer_key.txt to GitHub...")
        upload_to_github(session, "answer_key.txt", f"{github_base}/class-{cls}_{clean_subject.lower()}_{exam_no}/answer_key.txt")
    
    if html_success:
        print(f"🚀 Uploading {len(student_list)} images...")
        count = 0
        for s in student_list:
            img_success = upload_to_github(session, f"{output_folder}/{s['file']}", f"{github_img_folder}/{s['file']}")
            count += 1
            status = "✅" if img_success else "❌"
            print(f"[{count}/{len(student_list)}] {status} {s['name']}")
            sys.stdout.flush() 

        os.remove(output_filename)
        print(f"\n✅ SYNC COMPLETE")
        print()
        print(f"The webpage will be available in 5 minutes: {site_link}/{github_base}/{output_filename}")
        print()
    else:
        print("❌ FAILED: Could not upload HTML file to GitHub.")
        print()

if __name__ == "__main__":
    run()
