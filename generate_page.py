import os
import re

def get_student_names(tuition, cls):
    filename = f"{tuition}_class-{cls}_rolls.txt"
    name_map = {}
    
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            # Extracts "1": "Name" from your txt file
            matches = re.findall(r'"(\d+)":\s*"([^"]+)"', content)
            for roll, name in matches:
                name_map[int(roll)] = name
        print(f"✅ Loaded names from {filename}")
    else:
        print(f"⚠️ {filename} not found. Defaulting to 'Student [Roll]'")
    
    return name_map

def generate_html():
    # 1. Tuition Selection Menu
    print("\n--- Select Tuition ---")
    print("[1] wsc")
    print("[2] mvm")
    choice = input("Enter choice (1 or 2): ").strip()
    tuition = "wsc" if choice == "1" else "mvm"
    
    # 2. Input and Subject Cleaning
    cls = input("Enter Class (e.g. 10): ").strip()
    raw_subject = input("Enter Subject Name: ").strip()
    exam_no = input("Enter Exam Number: ").strip()

    # Clean Subject: lowercase and remove all spaces
    clean_subject = raw_subject.replace(" ", "").lower()
    
    # Path format: class-10_english_2
    folder_path = f"class-{cls}_{clean_subject}_{exam_no}"
    
    output_folder = "./output"
    names_db = get_student_names(tuition, cls)
    
    if not os.path.exists(output_folder):
        print(f"❌ Error: Folder '{output_folder}' not found!")
        return

    # 3. Process Images from /output
    raw_files = [f for f in os.listdir(output_folder) if "_" in f and f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    student_list = []
    for file_name in raw_files:
        match = re.search(r"(\d+)_(\d+)", file_name)
        if match:
            roll = int(match.group(1))
            mark = int(match.group(2))
            display_name = names_db.get(roll, f"Student {roll}")
            
            student_list.append({
                "roll": roll,
                "mark": mark,
                "file": file_name,
                "name": display_name,
                "path": f"{folder_path}/eval_files/{file_name}" 
            })

    # --- SERIAL SORTING ---
    # Sort for the Gallery (Roll 1, 2, 3...)
    gallery_students = sorted(student_list, key=lambda x: x['roll'])

    # Sort for the Table (High Mark to Low Mark)
    ranked_students = sorted(student_list, key=lambda x: x['mark'], reverse=True)
    for i, s in enumerate(ranked_students):
        s['rank'] = i + 1

    # 4. HTML Generation
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
    <p id="not-found">Not found</p>

    <table id="name-table">
        <thead>
            <tr>
                <th>Name</th>
                <th>Total mark</th>
                <th>Secured mark</th>
                <th>Rank</th>
            </tr> 
        </thead>
        <tbody>"""

    # Add ranked rows to Table
    for s in ranked_students:
        html_content += f"""
            <tr>
                <td><a href="{s['path']}">{s['name']}</a></td>
                <td>40</td>
                <td>{s['mark']}</td>
                <td>{s['rank']}</td>
            </tr>"""

    html_content += f"""
        </tbody>
    </table>

    <br><br>
    <h2 id="heading2">&nbsp;&nbsp;&nbsp;All student's answer sheets (Roll number wise).</h2>
    <div id="gallery-container">"""

    # Add images in SERIAL order (Roll 1, 2, 3...)
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
        const rows = document.querySelectorAll('#name-table tbody tr');
        const images = document.querySelectorAll('img');
        const heading2 = document.getElementById('heading2');
        const notFound = document.getElementById('not-found');

        searchBar.addEventListener('input', () => {
            const filter = searchBar.value.trim().toLowerCase();
            let matchFound = false;

            heading2.style.display = filter === "" ? "block" : "none";

            rows.forEach(row => {
                const name = row.cells[0].textContent.toLowerCase();
                if (name.includes(filter)) {
                    row.style.display = '';
                    matchFound = true;
                } else {
                    row.style.display = 'none';
                }
            });

            images.forEach(img => {
                const altText = img.alt.toLowerCase();
                if (altText.includes(filter)) {
                    img.style.display = '';
                    img.parentElement.style.display = '';
                } else {
                    img.style.display = 'none';
                    img.parentElement.style.display = 'none';
                }
            });

            notFound.style.display = matchFound ? 'none' : 'block';
        });
    </script>
</body>
</html>"""

    # 5. Save
    output_filename = f"{tuition}_{clean_subject}_test_{exam_no}.html"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\n🚀 Success! File generated: {output_filename}")
    print(f"Gallery sorted by Roll Number, Table sorted by Rank.")

if __name__ == "__main__":
    generate_html()
