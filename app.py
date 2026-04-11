import uuid
import os
import json
import shutil
from flask import Flask, render_template, request, redirect
from flask import send_from_directory
from main import extract_text_from_PDF

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


# Parse a PDF
@app.route("/parse/<project_name>/<path:filename>")
def parse(project_name, filename):
    from flask import jsonify
    from main import parse_index_ii
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    file_path = os.path.join(project_path, filename)
    print("DEBUG looking for:", file_path)
    print("DEBUG files in folder:", os.listdir(project_path))
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found: " + file_path})
    try:
        result = parse_index_ii(file_path)
        if result is None:
            return jsonify({"error": "Could not parse document"})
        # Save result to disk
        result_filename = os.path.splitext(filename)[0] + "_result.json"
        result_path = os.path.join(project_path, result_filename)
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})


# Delete a file from a project
@app.route("/delete_file/<project_name>/<path:filename>", methods=["POST"])
def delete_file(project_name, filename):
    from urllib.parse import unquote
    filename = unquote(filename)
    file_path = os.path.join(PROJECT_FOLDER, project_name, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    # Also delete the saved result JSON if it exists
    result_filename = os.path.splitext(filename)[0] + "_result.json"
    result_path = os.path.join(PROJECT_FOLDER, project_name, result_filename)
    if os.path.exists(result_path):
        os.remove(result_path)
    return redirect(f"/workspace/{project_name}")


# Edit project
@app.route("/edit_project", methods=["POST"])
def edit_project():
    folder      = request.form.get("folder", "").strip()
    new_name    = request.form.get("project_name", "").strip()
    new_id_type = request.form.get("id_type", "").strip()
    new_id_value= request.form.get("id_value", "").strip()

    if not folder or not new_name or not new_id_type or not new_id_value:
        return redirect("/projects")

    old_path = os.path.join(PROJECT_FOLDER, folder)

    # Keep the same unique ID suffix, just change the name part
    suffix = folder.rsplit("_", 1)[-1]
    new_folder = f"{new_name}_{suffix}"
    new_path = os.path.join(PROJECT_FOLDER, new_folder)

    # Rename the folder
    if os.path.exists(old_path):
        os.rename(old_path, new_path)

    # Update id_info.json
    id_info_path = os.path.join(new_path, "id_info.json")
    with open(id_info_path, "w") as f:
        json.dump({"id_type": new_id_type, "id_value": new_id_value}, f)

    return redirect("/projects")


# Serve PDF file for viewer
@app.route("/pdf/<project_name>/<path:filename>")
def serve_pdf(project_name, filename):
    from flask import send_from_directory
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    return send_from_directory(project_path, filename)


# Load saved parse result for a file
@app.route("/result/<project_name>/<path:filename>")
def load_result(project_name, filename):
    from flask import jsonify
    result_filename = os.path.splitext(filename)[0] + "_result.json"
    result_path = os.path.join(PROJECT_FOLDER, project_name, result_filename)
    if not os.path.exists(result_path):
        return jsonify({"exists": False})
    with open(result_path) as f:
        data = json.load(f)
    return jsonify({"exists": True, "data": data})


# Build events for a project from all saved JSON results
@app.route("/events/<project_name>")
def get_events(project_name):
    from flask import jsonify
    from datetime import datetime

    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events = []
    consistency_errors = []

    # Only include result files that have a matching PDF still in the folder
    all_files = os.listdir(project_path)
    pdfs = [f for f in all_files if f.lower().endswith(".pdf")]
    pdf_basenames = set(os.path.splitext(p)[0] for p in pdfs)
    result_files = [f for f in all_files if f.endswith("_result.json") and f.replace("_result.json", "") in pdf_basenames]

    ref_society_name = None
    ref_society_address = None
    ref_id_field = None
    ref_id_value = None

    for rf in result_files:
        result_path = os.path.join(project_path, rf)
        with open(result_path) as f:
            data = json.load(f)

        txn = data.get("txn_type") or ""
        txn = txn.upper()

        # Determine property type
        flat_no = data.get("flat_no")
        society_name = data.get("society_building_name")
        is_flat = bool(flat_no or society_name)

        # Get the filled ID field
        id_field, id_value = None, None
        for field in ["cts_no", "plot_no", "survey_no"]:
            val = data.get(field)
            if val and val != "null":
                id_field = field
                id_value = val
                break

        # Consistency check
        if ref_society_name is None and is_flat and society_name:
            ref_society_name = society_name
            ref_society_address = data.get("society_building_address")
        elif is_flat and society_name and ref_society_name:
            if society_name.strip().lower() != ref_society_name.strip().lower():
                consistency_errors.append(f"Society name mismatch in {rf}: '{society_name}' vs expected '{ref_society_name}'")

        if ref_id_value is None and id_value:
            ref_id_field = id_field
            ref_id_value = id_value
        elif id_value and ref_id_value:
            if id_value.strip().lower() != ref_id_value.strip().lower():
                consistency_errors.append(f"ID number mismatch in {rf}: '{id_field}={id_value}' vs expected '{ref_id_field}={ref_id_value}'")

        # Build event
        event = {
            "source_file": rf.replace("_result.json", ".pdf"),
            "event_type": txn,
            "event_date": data.get("date_of_execution"),
            "event_reg_date": data.get("date_of_registration"),
            "event_doc_no": data.get("doc_no"),
            "area": data.get("area"),
            "id_field": id_field,
            "id_value": id_value,
        }

        # Property type
        event["property_type"] = "FLAT" if is_flat else "PLOT"
        if is_flat:
            event["society_building_name"] = society_name
            event["society_building_address"] = data.get("society_building_address")
            event["flat_no"] = flat_no

        # Parties based on txn type
        if "SALE" in txn or "AGREEMENT" in txn:
            event["seller_names"] = data.get("seller_names")
            event["buyer_names"] = data.get("buyer_names")
            event["consideration"] = data.get("consideration")
        elif "GIFT" in txn:
            event["donor_name"] = data.get("donor_name")
            event["donee_name"] = data.get("donee_name")
        elif "MORTGAGE" in txn or "INTIMATION" in txn:
            event["mortgagor_name"] = data.get("mortgagor_name")
            event["mortgagee_name"] = data.get("mortgagee_name")
        elif "RELEASE" in txn:
            event["releasor_names"] = data.get("seller_names")
            event["releasee_names"] = data.get("buyer_names")
        elif "LEAVE" in txn or "LICENSE" in txn:
            event["licensor_name"] = data.get("licensor_name")
            event["licensee_name"] = data.get("licensee_name")

        events.append(event)

    # Sort chronologically
    def parse_date(d):
        if not d:
            return datetime.max
        for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(d, fmt)
            except:
                pass
        return datetime.max

    events.sort(key=lambda e: parse_date(e.get("event_date")))

    # Mortgage check — every mortgage needs a release
    mortgage_events = [e for e in events if "MORTGAGE" in e.get("event_type","") or "INTIMATION" in e.get("event_type","")]
    release_events  = [e for e in events if "RELEASE" in e.get("event_type","")]
    unresolved_mortgages = []
    for m in mortgage_events:
        has_release = any(
            parse_date(r.get("event_date")) > parse_date(m.get("event_date"))
            for r in release_events
        )
        if not has_release:
            unresolved_mortgages.append(m.get("event_doc_no") or "unknown")

    return jsonify({
        "events": events,
        "consistency_errors": consistency_errors,
        "unresolved_mortgages": unresolved_mortgages
    })


# Build ownership chain errors for a project
@app.route("/errors/<project_name>")
def get_errors(project_name):
    from flask import jsonify
    from datetime import datetime

    project_path = os.path.join(PROJECT_FOLDER, project_name)
    all_files = os.listdir(project_path)
    pdfs = [f for f in all_files if f.lower().endswith(".pdf")]
    pdf_basenames = set(os.path.splitext(p)[0] for p in pdfs)
    result_files = [f for f in all_files if f.endswith("_result.json") and f.replace("_result.json", "") in pdf_basenames]

    events = []
    for rf in result_files:
        with open(os.path.join(project_path, rf)) as f:
            data = json.load(f)
        txn = (data.get("txn_type") or "").upper()

        # Get current owners (who received the property)
        if "SALE" in txn or "AGREEMENT" in txn:
            transferors = data.get("seller_names") or []
            transferees = data.get("buyer_names") or []
        elif "GIFT" in txn:
            transferors = [data.get("donor_name")] if data.get("donor_name") else []
            transferees = [data.get("donee_name")] if data.get("donee_name") else []
        elif "RELEASE" in txn:
            transferors = data.get("seller_names") or []
            transferees = data.get("buyer_names") or []
        else:
            continue  # Skip mortgage, L&L etc for chain check

        events.append({
            "doc_no": data.get("doc_no"),
            "txn_type": txn,
            "event_date": data.get("date_of_execution"),
            "transferors": [n.strip().lower() for n in (transferors if isinstance(transferors, list) else [transferors])],
            "transferees": [n.strip().lower() for n in (transferees if isinstance(transferees, list) else [transferees])],
        })

    def parse_date(d):
        if not d: return datetime(9999,1,1)
        for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
            try: return datetime.strptime(d, fmt)
            except: pass
        return datetime(9999,1,1)

    events.sort(key=lambda e: parse_date(e.get("event_date")))

    chain_errors = []
    current_owners = set(events[0]["transferees"]) if events else set()

    for i in range(1, len(events)):
        ev = events[i]
        transferors_set = set(ev["transferors"])

        # Check if transferors match current owners
        if not transferors_set.intersection(current_owners):
            chain_errors.append({
                "doc_no": ev["doc_no"],
                "txn_type": ev["txn_type"],
                "event_date": ev["event_date"],
                "expected_sellers": list(current_owners),
                "actual_sellers": list(transferors_set),
                "message": f"Ownership mismatch: sellers in this deed do not match buyers from previous deed."
            })

        # Update current owners to transferees of this deed
        current_owners = set(ev["transferees"])

    return jsonify({"chain_errors": chain_errors})

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json')


@app.route('/sw.js')
def service_worker():
    response = send_from_directory('.', 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    return response

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="127.0.0.1", port=5000)