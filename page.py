from flask import Flask, render_template, request, jsonify, send_file
import os, shutil, re

app = Flask(__name__)
BASE = os.getcwd()

# Folders always present
STATIC_FOLDERS = ["input", "output", "duplicates", "error_images"]

def get_project_folders():
    out = []
    for f in os.listdir(BASE):
        if os.path.isdir(f) and (f.startswith("class") or f in STATIC_FOLDERS):
            out.append(f)
    return sorted(out)

@app.route("/")
def index():
    return render_template("index.html", folders=get_project_folders())

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json
    cls = data.get("class", "").strip()
    sub = data.get("subject", "").strip()
    if not cls or not sub:
        return jsonify({"error":"Class and Subject required"}), 400
    folder_name = f"class-{cls}_{sub}_1".lower()
    os.makedirs(folder_name, exist_ok=True)
    return jsonify(folders=get_project_folders())

@app.route("/browse")
def browse():
    path = request.args.get("path")
    full_path = os.path.join(BASE, path)

    items = []
    for f in os.listdir(full_path):
        fp = os.path.join(full_path, f)
        items.append({
            "name": f,
            "is_dir": os.path.isdir(fp)
        })

    # Sort jpg files by roll number (number before _)
    def sort_key(x):
        m = re.match(r"(\d+)_", x["name"])
        return int(m.group(1)) if m else 999999

    items.sort(key=sort_key)
    return render_template("browser.html", items=items, path=path)

@app.route("/file")
def file():
    return send_file(os.path.join(BASE, request.args["path"]))

@app.route("/rename", methods=["POST"])
def rename():
    data = request.json
    old = os.path.join(BASE, data["old"])
    new = os.path.join(BASE, data["new"])
    os.rename(old, new)
    return jsonify(ok=True)

@app.route("/delete", methods=["POST"])
def delete():
    path = os.path.join(BASE, request.json["path"])
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
