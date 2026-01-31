from flask import Flask, render_template, request, jsonify, send_file
import os, shutil, re

app = Flask(__name__)
BASE = os.getcwd()

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
    d = request.json
    name = f"class-{d['class']}_{d['subject']}_1".lower()
    os.makedirs(name, exist_ok=True)
    return jsonify(folders=get_project_folders())

@app.route("/browse")
def browse():
    path = request.args.get("path")
    full = os.path.join(BASE, path)

    items = []
    for f in os.listdir(full):
        fp = os.path.join(full, f)
        items.append({
            "name": f,
            "is_dir": os.path.isdir(fp)
        })

    # sort jpg by roll number
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
    d = request.json
    os.rename(os.path.join(BASE, d["old"]),
              os.path.join(BASE, d["new"]))
    return jsonify(ok=True)

@app.route("/delete", methods=["POST"])
def delete():
    p = os.path.join(BASE, request.json["path"])
    if os.path.isdir(p):
        shutil.rmtree(p)
    else:
        os.remove(p)
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
