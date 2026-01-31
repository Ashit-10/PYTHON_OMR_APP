from flask import Flask, render_template, request, jsonify
import os

BASE_DIR = os.getcwd()

app = Flask(__name__)

@app.route("/")
def index():
    folders = ["input", "output", "error_images", "duplicates"]
    existing = [f for f in folders if os.path.isdir(f)]
    return render_template("index.html", folders=existing)

@app.route("/create_folder", methods=["POST"])
def create_folder():
    data = request.json
    cls = data.get("class")
    subject = data.get("subject")
    setno = data.get("set", "1")

    folder_name = f"class-{cls}_{subject}_{setno}"
    path = os.path.join(BASE_DIR, folder_name)

    if not os.path.exists(path):
        os.makedirs(path)
        return jsonify({"status": "ok", "folder": folder_name})
    else:
        return jsonify({"status": "exists"})

@app.route("/camera")
def camera():
    return app.send_static_file("../camera_ui.html")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
