from flask import Flask, render_template, request, jsonify, send_file
import os, shutil

app = Flask(__name__)
BASE = os.getcwd()

ALLOWED_STATIC = ["input", "output", "duplicates", "error_images"]

def get_project_folders():
    folders = []
    for f in os.listdir(BASE):
        if not os.path.isdir(f):
            continue
        if f.startswith("class") or f in ALLOWED_STATIC:
            folders.append(f)
    return sorted(folders)

@app.route("/")
def index():
    return render_template("index.html", folders=get_project_folders())

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json
    cls = data.get("class")
    subject = data.get("subject")

    if not cls or not subject:
        return jsonify({"error": "required"}), 400

    name = f"class-{cls}_{subject}_1".lower()
    os.makedirs(name, exist_ok=True)

    return jsonify({
        "folder": name,
        "folders": get_project_folders()
    })

@app.route("/browse")
def browse():
    path = request.args.get("path", "")
    full = os.path.join(BASE, path)

    items = []
    for f in os.listdir(full):
        fp = os.path.join(full, f)
        items.append({
            "name": f,
            "is_dir": os.path.isdir(fp)
        })

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
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
