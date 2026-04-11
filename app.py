import uuid
import os
import json
import shutil
from flask import Flask, render_template, request, redirect
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


# ── Shared helper ──────────────────────────────────────────────────────────

def _load_results(project_path):
    """Load all result JSON files that have a matching PDF."""
    all_files = os.listdir(project_path)
    pdfs = [f for f in all_files if f.lower().endswith(".pdf")]
    pdf_basenames = set(os.path.splitext(p)[0] for p in pdfs)
    result_files = [f for f in all_files if f.endswith("_result.json")
                    and f.replace("_result.json", "") in pdf_basenames]
    results = []
    for rf in result_files:
        with open(os.path.join(project_path, rf)) as f:
            data = json.load(f)
        results.append((rf, data))
    return results

def _parse_date(d):
    from datetime import datetime
    if not d:
        return datetime(9999, 1, 1)
    for fmt in ["%d-%m-%Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(d, fmt)
        except:
            pass
    return datetime(9999, 1, 1)

def _normalize(name):
    """Lowercase + strip for name comparison."""
    if not name:
        return ""
    return str(name).strip().lower()

def _normalize_area(area_str):
    """Extract numeric area value for comparison."""
    import re
    if not area_str:
        return None
    m = re.search(r"[\d,\.]+", str(area_str).replace(",", ""))
    if m:
        try:
            return float(m.group().replace(",", ""))
        except:
            return None
    return None

def _build_events_and_errors(project_path):
    """
    Core logic: build events, entities, and all errors from result files.
    Returns (events, entities, errors)
    """
    results = _load_results(project_path)

    # Sort by date first
    results.sort(key=lambda x: _parse_date(x[1].get("date_of_execution")))

    events = []
    errors = []
    entities = []  # chronological ownership log

    # Reference values for consistency checks
    ref_area = None
    ref_area_src = None
    ref_society = None
    ref_society_src = None
    ref_id_val = None
    ref_id_field = None
    ref_id_src = None

    # Track current owners (set of normalised names)
    current_owners = set()
    first_ownership_set = False

    for rf, data in results:
        source = rf.replace("_result.json", ".pdf")
        txn = (data.get("txn_type") or "").upper()

        # ── Property type ──────────────────────────────────────────────
        flat_no      = data.get("flat_no")
        society_name = data.get("society_building_name")
        is_flat      = bool(flat_no or society_name)

        # ── ID field ───────────────────────────────────────────────────
        id_field, id_value = None, None
        for field in ["cts_no", "plot_no", "survey_no"]:
            val = data.get(field)
            if val and str(val).lower() != "null":
                id_field = field
                id_value = val
                break

        # ── Area ───────────────────────────────────────────────────────
        area     = data.get("area")
        area_num = _normalize_area(area)

        # ── Consistency checks ─────────────────────────────────────────
        if area_num is not None:
            if ref_area is None:
                ref_area = area_num
                ref_area_src = source
            elif abs(area_num - ref_area) > 0.01:
                errors.append({
                    "type": "AREA_MISMATCH",
                    "doc_no": data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source": source,
                    "message": f"Area mismatch: this document has area '{area}' but earlier document '{ref_area_src}' has a different area.",
                    "expected": str(ref_area),
                    "actual": str(area_num)
                })

        if is_flat and society_name:
            if ref_society is None:
                ref_society = _normalize(society_name)
                ref_society_src = source
            elif _normalize(society_name) != ref_society:
                errors.append({
                    "type": "SOCIETY_MISMATCH",
                    "doc_no": data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source": source,
                    "message": f"Society name mismatch: '{society_name}' vs expected from '{ref_society_src}'.",
                    "expected": ref_society,
                    "actual": _normalize(society_name)
                })

        if id_value:
            if ref_id_val is None:
                ref_id_val   = _normalize(id_value)
                ref_id_field = id_field
                ref_id_src   = source
            elif _normalize(id_value) != ref_id_val:
                errors.append({
                    "type": "ID_MISMATCH",
                    "doc_no": data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source": source,
                    "message": f"Property ID mismatch: '{id_field}={id_value}' vs expected '{ref_id_field}={ref_id_val}' from '{ref_id_src}'.",
                    "expected": ref_id_val,
                    "actual": _normalize(id_value)
                })

        # ── Build event ────────────────────────────────────────────────
        event = {
            "source_file":   source,
            "event_type":    txn,
            "event_date":    data.get("date_of_execution"),
            "event_reg_date":data.get("date_of_registration"),
            "event_doc_no":  data.get("doc_no"),
            "area":          area,
            "id_field":      id_field,
            "id_value":      id_value,
            "property_type": "FLAT" if is_flat else "PLOT",
        }

        # Only attach society/flat info for flats
        if is_flat:
            event["society_building_name"]    = society_name
            event["society_building_address"] = data.get("society_building_address")
            event["flat_no"]                  = flat_no

        # ── Parties + ownership chain ──────────────────────────────────
        transferors = []
        transferees = []

        if "SALE" in txn or "AGREEMENT" in txn:
            raw_sellers = data.get("seller_names") or []
            raw_buyers  = data.get("buyer_names")  or []
            transferors = raw_sellers if isinstance(raw_sellers, list) else [raw_sellers]
            transferees = raw_buyers  if isinstance(raw_buyers,  list) else [raw_buyers]
            event["seller_names"]  = raw_sellers
            event["buyer_names"]   = raw_buyers
            event["consideration"] = data.get("consideration")

        elif "GIFT" in txn:
            dn = data.get("donor_name")
            de = data.get("donee_name")
            transferors = [dn] if dn else []
            transferees = [de] if de else []
            event["donor_name"] = dn
            event["donee_name"] = de

        elif "MORTGAGE" in txn or "INTIMATION" in txn:
            event["mortgagor_name"] = data.get("mortgagor_name")
            event["mortgagee_name"] = data.get("mortgagee_name")
            # Mortgage does NOT transfer ownership — skip chain update

        elif "RELEASE" in txn:
            raw_rel = data.get("seller_names") or []
            raw_ree = data.get("buyer_names")  or []
            transferors = raw_rel if isinstance(raw_rel, list) else [raw_rel]
            transferees = raw_ree if isinstance(raw_ree, list) else [raw_ree]
            event["releasor_names"] = raw_rel
            event["releasee_names"] = raw_ree

        elif "LEAVE" in txn or "LICENSE" in txn:
            event["licensor_name"] = data.get("licensor_name")
            event["licensee_name"] = data.get("licensee_name")

        events.append(event)

        # ── Ownership chain validation (only for transfer events) ──────
        if transferors or transferees:
            norm_transferors = set(_normalize(n) for n in transferors if n)
            norm_transferees = set(_normalize(n) for n in transferees if n)

            if not first_ownership_set:
                # First transfer — establish initial owners
                current_owners = norm_transferors | norm_transferees
                # Add first owners to entities
                for name in norm_transferors:
                    entities.append({
                        "name": name,
                        "role": "initial_owner",
                        "area": area,
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source
                    })
                first_ownership_set = True
            else:
                # Check if transferors are current owners
                if norm_transferors and not norm_transferors.intersection(current_owners):
                    errors.append({
                        "type": "CHAIN_ERROR",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": "Ownership mismatch: the transferor in this deed does not match the current owner on record.",
                        "expected": list(current_owners),
                        "actual": list(norm_transferors)
                    })
                else:
                    # Check area — transferors can only transfer what they own
                    # (simplified: if area in this doc != reference area, already caught above)
                    # Remove transferors, add transferees
                    current_owners -= norm_transferors
                    current_owners |= norm_transferees

            # Log to entities
            for name in norm_transferees:
                entities.append({
                    "name": name,
                    "role": "acquired",
                    "area": area,
                    "doc_no": data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source": source,
                    "txn_type": txn
                })

    # ── Unresolved mortgage check ──────────────────────────────────────
    mortgage_events = [e for e in events if "MORTGAGE" in e.get("event_type","") or "INTIMATION" in e.get("event_type","")]
    release_events  = [e for e in events if "RELEASE"  in e.get("event_type","")]
    unresolved_mortgages = []

    for m in mortgage_events:
        has_release = any(
            _parse_date(r.get("event_date")) > _parse_date(m.get("event_date"))
            for r in release_events
        )
        if not has_release:
            unresolved_mortgages.append(m.get("event_doc_no") or "unknown")
            errors.append({
                "type": "UNRESOLVED_MORTGAGE",
                "doc_no": m.get("event_doc_no"),
                "event_date": m.get("event_date"),
                "source": m.get("source_file"),
                "message": "Unresolved mortgage: no matching Release Deed found for this mortgage.",
                "expected": "A Release Deed",
                "actual": "None found"
            })

    return events, entities, errors, unresolved_mortgages


# Build events for a project
@app.route("/events/<project_name>")
def get_events(project_name):
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)
    # Pull out only consistency errors for the events tab warnings
    consistency_errors = [e["message"] for e in errors if e["type"] in ("AREA_MISMATCH","SOCIETY_MISMATCH","ID_MISMATCH")]
    return jsonify({
        "events": events,
        "consistency_errors": consistency_errors,
        "unresolved_mortgages": unresolved_mortgages
    })


# Build errors for a project
@app.route("/errors/<project_name>")
def get_errors(project_name):
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)
    return jsonify({"chain_errors": errors})


# Build entities for a project
@app.route("/entities/<project_name>")
def get_entities(project_name):
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)
    return jsonify({"entities": entities})


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="127.0.0.1", port=5000)