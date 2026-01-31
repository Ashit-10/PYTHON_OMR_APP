from flask import Flask, render_template, request, jsonify, send_file
import os
import shutil

app = Flask(__name__)
BASE = os.getcwd()

@app.route("/")
def index():
    folders = [f for f in os.listdir(BASE) if os.path.isdir(f)]
    return render_template("index.html", folders=folders)

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json
    cls = data.get("class")
    subject = data.get("subject")

    if not cls or not subject:
        return jsonify({"error": "Class and subject required"}), 400

    name = f"class-{cls}_{subject}_1"
    os.makedirs(name, exist_ok=True)
    return jsonify({"folder": name})

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
    path = request.args.get("path")
    return send_file(os.path.join(BASE, path))

@app.route("/rename", methods=["POST"])
def rename():
    data = request.json
    old = os.path.join(BASE, data["old"])
    new = os.path.join(BASE, data["new"])
    os.rename(old, new)
    return jsonify({"ok": True})

@app.route("/delete", methods=["POST"])
def delete():
    path = os.path.join(BASE, request.json["path"])
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
