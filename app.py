import uuid
import os
import json
import shutil
from flask import Flask, render_template, request, redirect
from main import extract_text_from_PDF
from google import genai

client = genai.Client(api_key="AIzaSyBzK1Z_dlGKQoiUq-spmWiwbh0uRUIrZUQ")

app = Flask(__name__)

# Folders
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PROJECT_FOLDER = "workspaces"
os.makedirs(PROJECT_FOLDER, exist_ok=True)

# Home page
@app.route("/")
def home():
    return render_template("index.html")

# Projects list
@app.route("/projects")
def projects():
    projects_list = []
    for folder in os.listdir(PROJECT_FOLDER):
        id_info_path = os.path.join(PROJECT_FOLDER, folder, "id_info.json")
        id_type, id_value = None, None
        if os.path.exists(id_info_path):
            with open(id_info_path) as f:
                info = json.load(f)
                id_type = info.get("id_type")
                id_value = info.get("id_value")
        projects_list.append({
            "folder": folder,
            "name": folder.rsplit("_", 1)[0],
            "id_type": id_type,
            "id_value": id_value
        })
    return render_template("projects.html", projects=projects_list)

# Create new project
@app.route("/create_project", methods=["POST"])
def create_project():
    project_name = request.form.get("project_name", "").strip()
    id_type = request.form.get("id_type", "").strip()
    id_value = request.form.get("id_value", "").strip()
    confirm = request.form.get("confirm")

    if not project_name or not id_type or not id_value or not confirm:
        return redirect("/projects")

    project_id = str(uuid.uuid4())[:8]
    folder_name = f"{project_name}_{project_id}"
    project_path = os.path.join(PROJECT_FOLDER, folder_name)
    os.makedirs(project_path, exist_ok=True)

    with open(os.path.join(project_path, "id_info.json"), "w") as f:
        json.dump({"id_type": id_type, "id_value": id_value}, f)

    return redirect("/projects")

# Delete project
@app.route("/delete_project/<project_name>", methods=["POST"])
def delete_project(project_name):
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    return redirect("/projects")

# Workspace page
@app.route("/workspace/<project_name>", methods=["GET", "POST"])
def workspace(project_name):
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    os.makedirs(project_path, exist_ok=True)

    if request.method == "POST":
        uploaded_file = request.files.get("index_ii")
        if uploaded_file:
            file_path = os.path.join(project_path, uploaded_file.filename)
            uploaded_file.save(file_path)

    index_iis = [f for f in os.listdir(project_path) if f.lower().endswith(".pdf")]

    id_type, id_value = None, None
    id_info_path = os.path.join(project_path, "id_info.json")
    if os.path.exists(id_info_path):
        with open(id_info_path) as f:
            info = json.load(f)
            id_type = info.get("id_type")
            id_value = info.get("id_value")

    return render_template(
        "workspace.html",
        project_name=project_name,
        index_iis=index_iis,
        id_type=id_type,
        id_value=id_value
    )

if __name__ == "__main__":
    app.run(debug=True)
