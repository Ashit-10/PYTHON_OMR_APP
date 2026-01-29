import os
import re
import json
import requests
import base64
from tqdm import tqdm

# --- CONFIGURATION ---
GITHUB_TOKEN = "your_fine_grained_token"
REPO_OWNER = "your_username"
REPO_NAME = "your_repo"
YEAR = "2026"

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
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    
    get_file = session.get(url)
    data = {"message": f"Upload {github_path}", "content": content}
    if get_file.status_code == 200:
        data["sha"] = get_file.json()["sha"]
    
    res = session.put(url, json=data)
    return res.status_code in [200, 201]

def run():
    # 1. Inputs & Marks
    total_marks = get_total_marks()
    
    print("\n--- Select Tuition ---")
    print("[1] wsc\n[2] mvm")
    choice = input("Enter choice (1 or 2): ").strip()
    tuition = "wsc" if choice == "1" else "mvm"
    
    cls = input("Enter Class: ").strip()
    raw_subject = input("Enter Subject Name: ").strip()
    exam_no = input("Enter Exam Number: ").strip()

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
                "path": f"{folder_path}/eval_files/{file_name}" 
            })

    gallery_students = sorted(student_list, key=lambda x: x['roll'])
    ranked_students = sorted(student_list, key=lambda x: x['mark'], reverse=True)
    for i, s in enumerate(ranked_students): s['rank'] = i + 1

    # 3. HTML Generation
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
        #not-found {{ display: none; color: red; font-weight: bold; }}
        a {{ text-decoration: none !important; color: blue; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1 id="heading">{clean_subject.upper()} [unit test - {exam_no}]</h1>
    <nav class="navbar bg-body-tertiary px-3 mb-3">
        <ul class="nav nav-pills">
            <li class="nav-item me-2">
                <button class="btn btn-outline-warning" onclick="document.location='{folder_path}/{folder_path}_question.pdf'">View question paper</button>
            </li>
            <li class="nav-item">
                <button class="btn btn-outline-success" onclick="document.location='{folder_path}/{folder_path}_question.pdf'">Download question paper</button>
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
                <td>{total_marks}</td>
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
        <a class="imgs">
            <img src="{s['path']}" alt="{s['name']}" width="380"> 
        </a>
        <br><br><br><br><br>"""

    html_content += """
    </div>
    <script>
        const searchBar = document.getElementById('search-bar');
        searchBar.addEventListener('input', () => {
            const filter = searchBar.value.trim().toLowerCase();
            document.querySelectorAll('#name-table tbody tr').forEach(row => {
                row.style.display = row.cells[0].textContent.toLowerCase().includes(filter) ? '' : 'none';
            });
            document.querySelectorAll('.imgs').forEach(a => {
                a.style.display = a.querySelector('img').alt.toLowerCase().includes(filter) ? '' : 'none';
            });
        });
    </script>
</body>
</html>"""

    # 4. Save Locally with Class Name
    output_filename = f"class-{cls}_{clean_subject}_test_{exam_no}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n✅ HTML Generated Locally: {output_filename}")

    # 5. Upload to GitHub
    up_choice = input("\nDo you want to upload to GitHub? (y/n): ").strip().lower()
    if up_choice == 'y':
        session = requests.Session()
        session.headers.update({"Authorization": f"token {GITHUB_TOKEN}"})
        
        # Upload HTML
        html_success = upload_to_github(session, output_filename, f"{github_base}/{output_filename}")
        
        # Progress Bar Fix: Fixed width (80) and steady format
        custom_format = "|{bar:40}| {n_fmt}/{total_fmt} Files [ETA: {remaining}]"
        
        print(f"\n🚀 Uploading {len(student_list)} images...")
        pbar = tqdm(total=len(student_list), bar_format=custom_format, ascii=" #", colour="green")
        
        for s in student_list:
            upload_to_github(session, f"{output_folder}/{s['file']}", f"{github_img_folder}/{s['file']}")
            pbar.update(1)
        pbar.close()

        # Delete file after successful upload
        if html_success:
            os.remove(output_filename)
            print(f"\n🗑️ Local HTML file deleted after upload.")
        
        print(f"\n✅ SUCCESS! All files uploaded.")

if __name__ == "__main__":
    run()
