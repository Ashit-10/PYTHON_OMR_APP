from flask import Flask, render_template, request, jsonify, send_file
import os, shutil, re

app = Flask(__name__)
BASE = os.getcwd()
STATIC_FOLDERS = ["input", "output", "duplicates", "error_images"]

def get_project_folders():
    # Only show folders that exist in the BASE directory
    out = []
    if not os.path.exists(BASE): return out
    for f in os.listdir(BASE):
        full_path = os.path.join(BASE, f)
        if os.path.isdir(full_path) and (f.startswith("class") or f in STATIC_FOLDERS):
            out.append(f)
    return sorted(out)

@app.route("/")
def index():
    return render_template("index.html", folders=get_project_folders())

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json
    # Clean up name: remove spaces/special chars
    cls = re.sub(r'[^a-zA-Z0-9]', '-', data.get("class", "NA"))
    sub = re.sub(r'[^a-zA-Z0-9]', '-', data.get("subject", "NA"))
    
    # Logic to prevent overwriting: find the next available number
    counter = 1
    while True:
        folder_name = f"class-{cls}_{sub}_{counter}".lower()
        if not os.path.exists(os.path.join(BASE, folder_name)):
            os.makedirs(os.path.join(BASE, folder_name))
            break
        counter += 1
        
    return jsonify(folders=get_project_folders())

@app.route("/browse")
def browse():
    path = request.args.get("path")
    if not path:
        return "No path provided", 400
        
    full_path = os.path.join(BASE, path)
    if not os.path.exists(full_path):
        return f"Folder '{path}' not found", 404

    items = []
    for f in os.listdir(full_path):
        fp = os.path.join(full_path, f)
        items.append({"name": f, "is_dir": os.path.isdir(fp)})

    # Robust sorting: handles '123_name.jpg' or just 'name.jpg'
    def sort_key(x):
        if x["is_dir"]: return (0, x["name"])
        m = re.search(r"(\d+)", x["name"])
        return (1, int(m.group(1)) if m else 999999)

    items.sort(key=sort_key)
    return render_template("browser.html", items=items, path=path)

@app.route("/file")
def file():
    target = os.path.join(BASE, request.args.get("path", ""))
    if os.path.exists(target):
        return send_file(target)
    return "File not found", 404

@app.route("/rename", methods=["POST"])
def rename():
    data = request.json
    old = os.path.join(BASE, data["old"])
    new = os.path.join(BASE, data["new"])
    if os.path.exists(old):
        os.rename(old, new)
        return jsonify(ok=True)
    return jsonify(ok=False), 404

@app.route("/delete", methods=["POST"])
def delete():
    path = os.path.join(BASE, request.json["path"])
    if not os.path.exists(path): return jsonify(ok=False), 404
    
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return jsonify(ok=True)

@app.route("/answer_key")
def answer_key():
    # 1. Figure out which folder we are in
    folder = request.args.get("folder", "input") 
    
    # 2. Find the file answer_key.txt inside that folder
    file_path = os.path.join(BASE, folder, "answer_key.txt")
    
    # 3. Read the text inside that file
    content = ""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()
            
    # 4. Open 50.html and "STAMP" the text into it
    return render_template("50.html", content=content, folder=folder)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
