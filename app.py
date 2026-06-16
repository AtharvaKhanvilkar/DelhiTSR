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

    # Clean up stale unmarked result files. Anything that isn't a
    # properly-marked parse result gets removed on workspace load,
    # so the user only ever sees data they explicitly parsed.
    for f in os.listdir(project_path):
        if not f.endswith("_result.json"):
            continue
        fpath = os.path.join(project_path, f)
        try:
            with open(fpath) as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            try:
                os.remove(fpath)
            except OSError:
                pass
            continue
        if not (isinstance(raw, dict) and raw.get("parsed") is True):
            try:
                os.remove(fpath)
            except OSError:
                pass

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
        # Save result to disk WITH a "parsed" marker so we can
        # distinguish freshly-parsed results from stale files on disk.
        result_filename = os.path.splitext(filename)[0] + "_result.json"
        result_path = os.path.join(project_path, result_filename)
        with open(result_path, "w") as f:
            json.dump({"parsed": True, "data": result}, f, indent=2)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})


# Rename a file within a project
@app.route("/rename_file/<project_name>/<path:filename>", methods=["POST"])
def rename_file(project_name, filename):
    from flask import jsonify
    from urllib.parse import unquote
    filename = unquote(filename)
    new_name = request.get_json(silent=True) or {}
    new_name = new_name.get("new_name", "").strip()

    if not new_name:
        return jsonify({"ok": False, "error": "No new name provided"}), 400

    # Ensure .pdf extension is preserved
    if not new_name.lower().endswith(".pdf"):
        new_name = new_name + ".pdf"

    project_path = os.path.join(PROJECT_FOLDER, project_name)
    old_path = os.path.join(project_path, filename)
    new_path = os.path.join(project_path, new_name)

    if not os.path.exists(old_path):
        return jsonify({"ok": False, "error": "File not found"}), 404
    if os.path.exists(new_path):
        return jsonify({"ok": False, "error": "A file with that name already exists"}), 409

    # Rename the PDF
    os.rename(old_path, new_path)

    # Rename the result JSON too so it stays linked
    old_result = os.path.join(project_path, os.path.splitext(filename)[0] + "_result.json")
    new_result = os.path.join(project_path, os.path.splitext(new_name)[0] + "_result.json")
    if os.path.exists(old_result):
        os.rename(old_result, new_result)

    return jsonify({"ok": True, "new_name": new_name})


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
    """Load all result JSON files that have a matching PDF
    AND carry the {"parsed": true} marker. Files without the
    marker are stale (from before the parse-marker system) and
    are silently ignored — they will be cleaned up on the next
    workspace load."""
    all_files = os.listdir(project_path)
    pdfs = [f for f in all_files if f.lower().endswith(".pdf")]
    pdf_basenames = set(os.path.splitext(p)[0] for p in pdfs)
    result_files = [f for f in all_files if f.endswith("_result.json")
                    and f.replace("_result.json", "") in pdf_basenames]
    results = []
    for rf in result_files:
        try:
            with open(os.path.join(project_path, rf)) as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        # Only accept marked results. Unwrap the inner data field
        # so callers continue to receive the flat dict shape.
        if isinstance(raw, dict) and raw.get("parsed") is True and isinstance(raw.get("data"), dict):
            results.append((rf, raw["data"]))
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

# Titles/prefixes to strip before fuzzy comparison
_STRIP_TITLES = {"mr", "mrs", "ms", "dr", "shri", "smt", "late", "sr", "jr",
                 "kumari", "km", "prof", "advocate", "adv"}

def _name_tokens(name):
    """Return a set of meaningful tokens from a name, stripping titles and initials."""
    import re
    tokens = re.split(r"[\s\.\-\/]+", _normalize(name))
    result = set()
    for t in tokens:
        t = t.strip(".,")
        if not t:
            continue
        if t in _STRIP_TITLES:
            continue
        if len(t) == 1:          # single initial — skip
            continue
        result.add(t)
    return result

def _fuzzy_match(name_a, name_b, threshold=0.92):
    """
    Return True if two name strings likely refer to the same person.
    Uses token overlap: intersection / union >= threshold.
    """
    if not name_a or not name_b:
        return False
    ta = _name_tokens(name_a)
    tb = _name_tokens(name_b)
    if not ta or not tb:
        return _normalize(name_a) == _normalize(name_b)
    intersection = ta & tb
    union = ta | tb
    score = len(intersection) / len(union)
    return score >= threshold

def _find_fuzzy_match(name, name_set, threshold=0.92):
    """
    Given a name and a set of canonical names, return the best matching
    canonical name if any exceed threshold, else None.
    """
    best_match = None
    best_score = 0.0
    import re
    ta = _name_tokens(name)
    if not ta:
        return None
    for candidate in name_set:
        tb = _name_tokens(candidate)
        if not tb:
            continue
        intersection = ta & tb
        union = ta | tb
        score = len(intersection) / len(union) if union else 0
        if score >= threshold and score > best_score:
            best_score = score
            best_match = candidate
    return best_match

def _canonical_name(name):
    """Return a lowercase stripped key for use as dict key."""
    return _normalize(name)

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


def _parse_money(value):
    """
    Parse an Indian-format money string into a float (rupees).
    Handles: '94,00,000/-', 'Rs. 1,28,00,000', '₹50,00,000',
             '50 Lakhs', '1.5 Crore', '2 Cr', etc.
    Returns None if it cannot be parsed (caller must skip silently).
    """
    import re
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None

    # Detect lakh / crore multipliers stated as words
    multiplier = 1.0
    if re.search(r"\bcr(ore)?s?\b", s):
        multiplier = 1e7          # 1 crore = 10,000,000
    elif re.search(r"\bl(akh|ac|ak)h?s?\b", s):
        multiplier = 1e5          # 1 lakh = 100,000

    # Remove currency words/symbols FIRST so their letters/dots
    # (e.g. the "." in "Rs.") don't contaminate the number.
    s = re.sub(r"(rs\.?|inr|\u20b9|/-)", " ", s)
    # Remove the lakh/crore words themselves.
    s = re.sub(r"\b(cr(ore)?s?|l(akh|ac|ak)h?s?)\b", " ", s)
    # Remove grouping commas.
    s = s.replace(",", "")
    # Keep only digits and decimal points.
    cleaned = re.sub(r"[^\d.]", "", s)
    # If multiple dots survived, keep only the first as the decimal point.
    if cleaned.count(".") > 1:
        first = cleaned.find(".")
        cleaned = cleaned[:first + 1] + cleaned[first + 1:].replace(".", "")
    cleaned = cleaned.strip(".")
    if not cleaned:
        return None
    try:
        num = float(cleaned)
    except ValueError:
        return None

    # If a word multiplier was present, the digits are the "50" in "50 lakhs"
    if multiplier > 1.0:
        return num * multiplier
    return num


def _char_similarity(a, b):
    """
    Character-level similarity ratio (0.0–1.0) between two strings,
    using difflib (standard library — no external dependency).
    Used to detect SPELLING drift within names, which token-overlap
    matching cannot see. 1.0 = identical, lower = more different.
    """
    from difflib import SequenceMatcher
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _name_spelling_drift(a, b):
    """
    Return the character-similarity ratio if two names are 'probably the
    same person but spelled differently' — i.e. close but not identical.
    Returns None if they are identical, or so different they are not a
    spelling-drift case. Caller decides whether to flag.

    Threshold band (tunable):
      ratio == 1.0          → identical, no finding
      SPELL_LOW..0.999      → spelling drift, FLAG for review
      below SPELL_LOW       → too different, not a 'drift' (handled elsewhere)
    """
    SPELL_LOW = 0.80
    ratio = _char_similarity(a, b)
    if ratio >= 1.0:
        return None
    if ratio >= SPELL_LOW:
        return ratio
    return None

def _clean_id(v):
    """Normalize a single PAN/PIN value; return None if empty/null."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in ("null", "none", ""):
        return None
    return s.upper()


def _person_ids(data, side, name):
    """
    Return (pan, pin) for ONE specific person on a given side, by matching
    their name against the structured party objects. This binds each
    identity number to the correct individual — PAN/PIN are unique per
    person and must never be shared across parties.

    side = 'transferor' (giving) or 'transferee' (receiving).
    Falls back to (None, None) if no per-person match is found — we would
    rather show nothing than attribute the wrong number to someone.
    """
    parties = data.get(f"{side}_parties")
    if isinstance(parties, list):
        # Find the party object whose name matches this person (fuzzy).
        for p in parties:
            if not isinstance(p, dict):
                continue
            pname = p.get("name")
            if pname and _fuzzy_match(pname, name):
                return _clean_id(p.get("pan")), _clean_id(p.get("pin"))
    # No structured party objects, or no match → no IDs.
    # We deliberately do NOT fall back to the flat side-lists here,
    # because those are not bound to individuals and caused mis-attribution.
    return None, None


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

    # Reference values for consistency checks.
    # *_src  = PDF filename (for human-readable messages)
    # *_doc  = parsed doc_no from that file (for the finding's ref_doc_no field)
    ref_area = None
    ref_area_src = None
    ref_area_doc = None
    ref_society = None
    ref_society_src = None
    ref_society_doc = None
    ref_id_val = None
    ref_id_field = None
    ref_id_src = None
    ref_id_doc = None

    # Track current owners (set of canonical keys)
    current_owners = set()
    first_ownership_set = False

    # Structured entity ledger
    claimants = {}       # canonical_key -> claimant dict
    encumbrances = []    # list of encumbrance dicts

    # Track prior sale considerations chronologically, for the
    # consideration-anomaly check (later sale far below an earlier one).
    # Each entry: (numeric_value, doc_no, date_str)
    prior_sale_values = []

    # Threshold: flag a later sale priced below this fraction of the
    # highest prior sale (tunable). 0.50 = flag drops to under half.
    CONSIDERATION_DROP_FRACTION = 0.50

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

        # area field
        area     = data.get("area")
        area_num = _normalize_area(area)

        # area vs area
        if area_num is not None:
            if ref_area is None:
                ref_area     = area_num
                ref_area_src = source
                ref_area_doc = data.get("doc_no")

            elif area_num != ref_area:  # any deviation, no matter how small

                errors.append({
                    "type":       "AREA_MISMATCH",
                    "doc_no":     data.get("doc_no"),
                    "ref_doc_no": ref_area_doc,
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"Area differs from first recorded value ({ref_area} sq ft in Doc {ref_area_doc or ref_area_src}). Investigate even minor deviations.",
                    "expected":   str(ref_area) + " sq ft",
                    "actual":     str(area_num) + " sq ft" })

        if is_flat and society_name:
            if ref_society is None:
                ref_society     = _normalize(society_name)
                ref_society_src = source
                ref_society_doc = data.get("doc_no")
            elif _normalize(society_name) != ref_society:
                errors.append({
                    "type":       "SOCIETY_MISMATCH",
                    "doc_no":     data.get("doc_no"),
                    "ref_doc_no": ref_society_doc,
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"Society name '{society_name}' doesn't match first recorded name (Doc {ref_society_doc or ref_society_src}).",
                    "expected":   ref_society,
                    "actual":     _normalize(society_name)
                })

        if id_value:
            if ref_id_val is None:
                ref_id_val   = _normalize(id_value)
                ref_id_field = id_field
                ref_id_src   = source
                ref_id_doc   = data.get("doc_no")
            elif _normalize(id_value) != ref_id_val:
                errors.append({
                    "type":       "ID_MISMATCH",
                    "doc_no":     data.get("doc_no"),
                    "ref_doc_no": ref_id_doc,
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"Property ID mismatch: {id_field}={id_value} here vs {ref_id_field}={ref_id_val} in Doc {ref_id_doc or ref_id_src}.",
                    "expected":   ref_id_val,
                    "actual":     _normalize(id_value)
                })

        # ── Check 1: Registration date predates Execution date ──────────
        exec_date = _parse_date(data.get("date_of_execution"))
        reg_date  = _parse_date(data.get("date_of_registration"))
        from datetime import datetime
        sentinel  = datetime(9999, 1, 1)
        if exec_date != sentinel and reg_date != sentinel and reg_date < exec_date:
            errors.append({
                "type":        "DATE_ORDER_ERROR",
                "doc_no":      data.get("doc_no"),
                "event_date":  data.get("date_of_execution"),
                "source":      source,
                "message":     f"Registration date ({data.get('date_of_registration')}) is before execution date ({data.get('date_of_execution')}). Legally invalid.",
                "expected":    f"Registration on or after {data.get('date_of_execution')}",
                "actual":      data.get("date_of_registration")
            })

        # ── Check 2 & 3: PAN/PIN format and transferor=transferee clash ─
        import re as _re

        PAN_RE = _re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$')
        PIN_RE = _re.compile(r'^\d{6}$')

        all_pans = []
        all_pins = []

        for field_key in ["transferor_pan", "transferee_pan"]:
            raw = data.get(field_key)
            if not raw:
                continue
            items = raw if isinstance(raw, list) else [raw]
            for val in items:
                if val and str(val).strip().lower() not in ("null", "none", ""):
                    all_pans.append((field_key, str(val).strip().upper()))

        for field_key in ["transferor_pin", "transferee_pin"]:
            raw = data.get(field_key)
            if not raw:
                continue
            items = raw if isinstance(raw, list) else [raw]
            for val in items:
                if val and str(val).strip().lower() not in ("null", "none", ""):
                    all_pins.append((field_key, str(val).strip()))

        # Check 2a: PAN format
        for field_key, pan_val in all_pans:
            if not PAN_RE.match(pan_val):
                errors.append({
                    "type":       "INVALID_PAN_FORMAT",
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"Invalid PAN '{pan_val}' in {field_key.replace('_', ' ')}. Expected format: AAAAA9999A.",
                    "expected":   "Format: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)",
                    "actual":     pan_val
                })

        # Check 2b: PIN format
        for field_key, pin_val in all_pins:
            if not PIN_RE.match(pin_val):
                errors.append({
                    "type":       "INVALID_PIN_FORMAT",
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"Invalid PIN '{pin_val}' in {field_key.replace('_', ' ')}. Expected 6-digit postal code.",
                    "expected":   "6-digit numeric PIN code",
                    "actual":     pin_val
                })

        # Check 3: Transferor PAN == Transferee PAN (same person on both sides)
        t_or_pans = set()
        t_ee_pans = set()
        for field_key, pan_val in all_pans:
            if PAN_RE.match(pan_val):  # only flag valid PANs
                if "transferor" in field_key:
                    t_or_pans.add(pan_val)
                else:
                    t_ee_pans.add(pan_val)

        overlap_pans = t_or_pans & t_ee_pans
        if overlap_pans:
            errors.append({
                "type":       "PAN_TRANSFEROR_TRANSFEREE_CLASH",
                "doc_no":     data.get("doc_no"),
                "event_date": data.get("date_of_execution"),
                "source":     source,
                "message":    f"PAN {', '.join(overlap_pans)} appears on both transferor and transferee sides — same person cannot be both parties.",
                "expected":   "Different PANs for transferor and transferee",
                "actual":     ', '.join(overlap_pans)
            })

        # Check 3b: Same for PIN
        t_or_pins = set()
        t_ee_pins = set()
        for field_key, pin_val in all_pins:
            if PIN_RE.match(pin_val):
                if "transferor" in field_key:
                    t_or_pins.add(pin_val)
                else:
                    t_ee_pins.add(pin_val)

        overlap_pins = t_or_pins & t_ee_pins
        if overlap_pins:
            errors.append({
                "type":       "PIN_TRANSFEROR_TRANSFEREE_CLASH",
                "doc_no":     data.get("doc_no"),
                "event_date": data.get("date_of_execution"),
                "source":     source,
                "message":    f"PIN {', '.join(overlap_pins)} appears on both transferor and transferee sides — verify this is not the same person.",
                "expected":   "Different PINs for transferor and transferee",
                "actual":     ', '.join(overlap_pins)
            })

        # ── Check 4: Consideration anomalies (sale deeds only) ──────────
        # Two sub-checks, both ONLY for actual sales (never gifts/releases,
        # which legitimately have no/zero consideration):
        #   (a) zero or missing consideration on a sale
        #   (b) a sale priced far below the highest prior sale (undervaluation)
        is_sale = ("SALE" in txn or "AGREEMENT" in txn)
        if is_sale:
            cons_value = _parse_money(data.get("consideration"))

            # (a) Zero / missing consideration on a sale
            if cons_value is None or cons_value <= 0:
                errors.append({
                    "type":       "ZERO_CONSIDERATION",
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"No/zero consideration recorded ('{data.get('consideration')}'). A genuine sale must state a price — verify it's not an undervaluation or mislabelled gift.",
                    "expected":   "A positive sale price",
                    "actual":     str(data.get("consideration"))
                })
            else:
                # (b) Drastic drop versus the highest prior sale
                if prior_sale_values:
                    highest_prior = max(prior_sale_values, key=lambda x: x[0])
                    hp_value, hp_doc, hp_date = highest_prior
                    if hp_value > 0 and cons_value < hp_value * CONSIDERATION_DROP_FRACTION:
                        pct = round((cons_value / hp_value) * 100)
                        errors.append({
                            "type":       "CONSIDERATION_ANOMALY",
                            "doc_no":     data.get("doc_no"),
                            "ref_doc_no": hp_doc,
                            "event_date": data.get("date_of_execution"),
                            "source":     source,
                            "message":    f"Sale price is only {pct}% of Doc {hp_doc}. Possible undervaluation — verify against market value.",
                            "expected":   f"At least {int(CONSIDERATION_DROP_FRACTION*100)}% of prior sale (₹{int(hp_value):,})",
                            "actual":     f"₹{int(cons_value):,}"
                        })

                # Record this sale's value for future comparisons
                prior_sale_values.append((cons_value, data.get("doc_no"), data.get("date_of_execution")))

        # ── Build event ────────────────────────────────────────────────
        event = {
            "source_file":       source,
            "event_type":        txn,
            "event_date":        data.get("date_of_execution"),
            "event_reg_date":    data.get("date_of_registration"),
            "event_doc_no":      data.get("doc_no"),
            "area":              area,
            "id_field":          id_field,
            "id_value":          id_value,
            "property_type":     "FLAT" if is_flat else "PLOT",
            "sub_registrar_office": data.get("sub_registrar_office"),
            "village":           data.get("village"),
            "district":          data.get("district"),
            "stamp_duty":        data.get("stamp_duty"),
            "market_value":      data.get("market_value"),
            "plot_no":           data.get("plot_no"),
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

        # ── Ownership chain validation + entity ledger ──────────────
        #
        # Fix 3: current_owners is a SET — multiple simultaneous owners
        #         are all kept active and all must be accounted for.
        # Fix 4/5: Mortgage validity checked against current_owners at
        #          the time of the mortgage event (chronological order
        #          is already guaranteed by the sort at the top).
        #
        if transferors or transferees:
            if not first_ownership_set:
                # ── Seed: first transfer in the chain ─────────────────
                # Both transferors and transferees enter the ledger;
                # transferors are the initial sellers (historical owners
                # before our chain starts), transferees become first
                # active owners.
                for name in transferors:
                    if not name:
                        continue
                    key = _canonical_name(name)
                    _pan, _pin = _person_ids(data, "transferor", name)
                    claimants[key] = {
                        "display_name": name,
                        "role":         "owner",
                        "since_doc":    data.get("doc_no"),
                        "since_date":   data.get("date_of_execution"),
                        "basis":        txn,
                        "area":         area,
                        "status":       "active",
                        "encumbered":   False,
                        "entry_type":   "root_seller",
                        "pan":          _pan,
                        "pin":          _pin,
                    }
                    current_owners.add(key)

                for name in transferees:
                    if not name:
                        continue
                    key = _canonical_name(name)
                    _pan, _pin = _person_ids(data, "transferee", name)
                    claimants[key] = {
                        "display_name": name,
                        "role":         "owner",
                        "since_doc":    data.get("doc_no"),
                        "since_date":   data.get("date_of_execution"),
                        "basis":        txn,
                        "area":         area,
                        "status":       "active",
                        "encumbered":   False,
                        "pan":          _pan,
                        "pin":          _pin,
                    }
                    current_owners.add(key)

                # After seeding, only transferees are the active owners
                # (transferors were the prior sellers — retire them)
                for name in transferors:
                    if not name:
                        continue
                    key = _canonical_name(name)
                    current_owners.discard(key)
                    if key in claimants:
                        claimants[key]["status"]      = "transferred_out"
                        claimants[key]["exited_doc"]  = data.get("doc_no")
                        claimants[key]["exited_date"] = data.get("date_of_execution")
                        claimants[key]["exited_via"]  = txn

                first_ownership_set = True

            else:
                # ── Subsequent transfers ───────────────────────────────
                # Each transferor must fuzzy-match a CURRENTLY ACTIVE
                # owner. Former owners who already transferred away do
                # NOT count, even if their name appears in a later deed.

                matched_keys = []
                unmatched_names = []

                for name in transferors:
                    if not name:
                        continue
                    # Only search within ACTIVE current owners
                    matched_key = _find_fuzzy_match(name, current_owners)
                    if matched_key:
                        matched_keys.append(matched_key)

                        # Spelling-drift check: the transferor matched a
                        # current owner (so we accept them as the same person
                        # and the chain continues) — but if the spelling
                        # differs from the recorded owner's name, notify the
                        # reviewer so they can confirm it's truly the same person.
                        recorded_name = claimants.get(matched_key, {}).get("display_name", matched_key)
                        drift = _name_spelling_drift(name, recorded_name)
                        if drift is not None:
                            errors.append({
                                "type":       "NAME_SPELLING_VARIATION",
                                "doc_no":     data.get("doc_no"),
                                "ref_doc_no": claimants.get(matched_key, {}).get("since_doc"),
                                "event_date": data.get("date_of_execution"),
                                "source":     source,
                                "message":    f"Name spelling differs: '{name}' here vs '{recorded_name}' in chain. Accepted as same person — please confirm.",
                                "expected":   recorded_name,
                                "actual":     name
                            })
                    else:
                        unmatched_names.append(name)

                if transferors and not matched_keys:
                    # No transferor matched any active owner → chain break.
                    # Flag the error, but STILL record the parties in the
                    # ledger so the Entities tab shows the full picture.
                    # The error makes the broken link visible to the reviewer.
                    errors.append({
                        "type":       "CHAIN_ERROR",
                        "doc_no":     data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source":     source,
                        "message":    "Ownership chain break: transferor(s) in this deed don't match any current active owner on record.",
                        "expected":   list(current_owners),
                        "actual":     [_canonical_name(n) for n in transferors if n]
                    })

                    # Record the unmatched transferors as parties anyway —
                    # the deed names them, so they enter the ledger as former
                    # parties. The reviewer uses the Errors tab to judge
                    # whether the chain break is legitimate.
                    for name in transferors:
                        if not name:
                            continue
                        key = _canonical_name(name)
                        if key not in claimants:
                            _pan, _pin = _person_ids(data, "transferor", name)
                            claimants[key] = {
                                "display_name": name,
                                "role":         "owner",
                                "since_doc":    data.get("doc_no"),
                                "since_date":   data.get("date_of_execution"),
                                "basis":        txn,
                                "area":         area,
                                "status":       "transferred_out",
                                "exited_doc":   data.get("doc_no"),
                                "exited_date":  data.get("date_of_execution"),
                                "exited_via":   txn,
                                "encumbered":   False,
                                "entry_type":   "seller_only",
                                "pan":          _pan,
                                "pin":          _pin,
                            }

                    # The deed asserts an ownership transfer regardless of
                    # whether the chain is intact. Record what the deed says:
                    # retire the previous active owners and add the new
                    # transferees. Subsequent deeds will be checked against
                    # this new state.
                    for key in list(current_owners):
                        current_owners.discard(key)
                        if key in claimants and claimants[key]["status"] == "active":
                            claimants[key]["status"]      = "transferred_out"
                            claimants[key]["exited_doc"]  = data.get("doc_no")
                            claimants[key]["exited_date"] = data.get("date_of_execution")
                            claimants[key]["exited_via"]  = txn

                    for name in transferees:
                        if not name:
                            continue
                        key = _canonical_name(name)
                        _pan, _pin = _person_ids(data, "transferee", name)
                        claimants[key] = {
                            "display_name": name,
                            "role":         "owner",
                            "since_doc":    data.get("doc_no"),
                            "since_date":   data.get("date_of_execution"),
                            "basis":        txn,
                            "area":         area,
                            "status":       "active",
                            "encumbered":   False,
                            "pan":          _pan,
                            "pin":          _pin,
                        }
                        current_owners.add(key)

                else:
                    # Valid transfer — retire matched transferors
                    for key in matched_keys:
                        current_owners.discard(key)
                        if key in claimants:
                            claimants[key]["status"]      = "transferred_out"
                            claimants[key]["exited_doc"]  = data.get("doc_no")
                            claimants[key]["exited_date"] = data.get("date_of_execution")
                            claimants[key]["exited_via"]  = txn

                    # Add all transferees as new active owners (Fix 3:
                    # multiple transferees → multiple simultaneous owners)
                    for name in transferees:
                        if not name:
                            continue
                        # If this exact person is already active (e.g.
                        # partial release back to existing owner), just
                        # refresh their entry rather than duplicate.
                        existing_key = _find_fuzzy_match(name, current_owners)
                        if existing_key:
                            key = existing_key
                        else:
                            key = _canonical_name(name)
                        _pan, _pin = _person_ids(data, "transferee", name)
                        claimants[key] = {
                            "display_name": name,
                            "role":         "owner",
                            "since_doc":    data.get("doc_no"),
                            "since_date":   data.get("date_of_execution"),
                            "basis":        txn,
                            "area":         area,
                            "status":       "active",
                            "encumbered":   False,
                            "pan":          _pan,
                            "pin":          _pin,
                        }
                        current_owners.add(key)

        # ── Mortgages: validate against current owners, then encumber ─
        #
        # Fix 4/5: A mortgage is only valid if the mortgagor is a
        # CURRENT ACTIVE owner at the time this deed is processed.
        # If the mortgagor previously owned the property but has since
        # transferred it away, flag the mortgage as STALE_OWNERSHIP.
        #
        if "MORTGAGE" in txn or "INTIMATION" in txn:
            mortgagor = data.get("mortgagor_name")
            mortgagee = data.get("mortgagee_name")

            mortgagor_is_current = False
            mortgagor_matched_key = None

            if mortgagor and first_ownership_set:
                mortgagor_matched_key = _find_fuzzy_match(mortgagor, current_owners)
                mortgagor_is_current = mortgagor_matched_key is not None

            if not mortgagor_is_current and first_ownership_set:
                # Check if the mortgagor ever appeared in the chain
                # (former owner) vs completely unknown
                ever_owned = _find_fuzzy_match(mortgagor or "", set(claimants.keys())) if mortgagor else None
                if ever_owned:
                    err_msg = (
                        f"'{mortgagor}' is listed as mortgagor but previously transferred ownership away. "
                        f"Current owners: {list(current_owners)}."
                    )
                    err_type = "INVALID_MORTGAGOR"
                else:
                    err_msg = (
                        f"'{mortgagor}' is listed as mortgagor but doesn't appear in the ownership chain. "
                        f"Current owners: {list(current_owners)}."
                    )
                    err_type = "UNKNOWN_MORTGAGOR"

                errors.append({
                    "type":       err_type,
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    err_msg,
                    "expected":   list(current_owners),
                    "actual":     [_canonical_name(mortgagor)] if mortgagor else []
                })

            # Regardless of validity error, record the encumbrance so
            # it appears in the ledger (user needs to see it either way)
            enc = {
                "mortgagor":  mortgagor,
                "holder":     mortgagee,
                "type":       txn,
                "doc_no":     data.get("doc_no"),
                "since_date": data.get("date_of_execution"),
                "status":     "UNRESOLVED",
                "valid":      mortgagor_is_current,
            }
            encumbrances.append(enc)

            # Flag the mortgagor in claimants as encumbered (only if valid)
            if mortgagor_is_current and mortgagor_matched_key and mortgagor_matched_key in claimants:
                claimants[mortgagor_matched_key]["encumbered"] = True
                claimants[mortgagor_matched_key]["encumbrance_doc"] = data.get("doc_no")

    # ── Mortgage release matching (fuzzy mortgagor + mortgagee) ──────
    release_events_data = [(rf2, d2) for rf2, d2 in results
                           if ("RELEASE" in (d2.get("txn_type") or "").upper())]

    for enc in encumbrances:
        for rf2, d2 in release_events_data:
            rel_date = _parse_date(d2.get("date_of_execution"))
            enc_date = _parse_date(enc["since_date"])
            if rel_date <= enc_date:
                continue
            # Match mortgagor and mortgagee via fuzzy
            rel_sellers = d2.get("seller_names") or []
            rel_buyers  = d2.get("buyer_names")  or []
            if isinstance(rel_sellers, str):
                rel_sellers = [rel_sellers]
            if isinstance(rel_buyers, str):
                rel_buyers = [rel_buyers]

            mortgagor_match = enc["mortgagor"] and any(
                _fuzzy_match(enc["mortgagor"], n) for n in rel_sellers if n
            )
            mortgagee_match = enc["holder"] and any(
                _fuzzy_match(enc["holder"], n) for n in rel_buyers if n
            )

            if mortgagor_match and mortgagee_match:
                enc["status"] = "RESOLVED"
                enc["resolved_doc"] = d2.get("doc_no")
                enc["resolved_date"] = d2.get("date_of_execution")
                # Un-flag the mortgagor's encumbrance in claimants
                if enc["mortgagor"]:
                    matched_key = _find_fuzzy_match(enc["mortgagor"], set(claimants.keys()))
                    if matched_key and matched_key in claimants:
                        # Only clear if no other unresolved encumbrances remain
                        still_encumbered = any(
                            e["status"] == "UNRESOLVED" and
                            _fuzzy_match(enc["mortgagor"], e["mortgagor"] or "")
                            for e in encumbrances if e is not enc
                        )
                        if not still_encumbered:
                            claimants[matched_key]["encumbered"] = False
                break  # one release per mortgage

    # ── Build unresolved_mortgages list + errors ──────────────────────
    unresolved_mortgages = []
    for enc in encumbrances:
        if enc["status"] == "UNRESOLVED":
            unresolved_mortgages.append(enc["doc_no"] or "unknown")
            errors.append({
                "type":     "UNRESOLVED_MORTGAGE",
                "doc_no":   enc["doc_no"],
                "event_date": enc["since_date"],
                "source":   "",
                "message":  f"No matching Release Deed found. Mortgagor: {enc['mortgagor']}, Mortgagee: {enc['holder']}.",
                "expected": "A matching Release Deed (mortgagor + mortgagee names)",
                "actual":   "None found"
            })

    # ── Cross-party identity check: same PAN/PIN on DIFFERENT people ──
    # PAN is legally one-per-person; a PIN (here used as a personal ID)
    # likewise should not be shared by two distinct parties. The SAME
    # person reappearing across deeds with the same PAN is fine and must
    # NOT be flagged — so we only flag when one ID maps to two or more
    # claimants whose names do NOT fuzzy-match each other (i.e. the system
    # considers them different people).
    def _flag_shared_ids(id_field, id_label, error_type):
        # Build: id_value -> list of (canonical_key, display_name)
        buckets = {}
        for key, c in claimants.items():
            val = c.get(id_field)
            if not val:
                continue
            # Normalize to a flat list of clean string values
            vals = val if isinstance(val, list) else [val]
            for v in vals:
                if not v:
                    continue
                vv = str(v).strip().upper()
                if vv in ("", "NULL", "NONE"):
                    continue
                buckets.setdefault(vv, [])
                # Avoid listing the same canonical key twice
                if not any(k == key for k, _ in buckets[vv]):
                    buckets[vv].append((key, c.get("display_name", key)))

        for id_value, holders in buckets.items():
            if len(holders) < 2:
                continue
            # Among the holders, are there at least two who are genuinely
            # DIFFERENT people (names that do not fuzzy-match)?
            distinct_people = []
            for key, name in holders:
                already = False
                for seen_name in distinct_people:
                    if _fuzzy_match(name, seen_name):
                        already = True
                        break
                if not already:
                    distinct_people.append(name)

            if len(distinct_people) >= 2:
                errors.append({
                    "type":       error_type,
                    "doc_no":     None,
                    "event_date": None,
                    "source":     "cross-document identity check",
                    "message":    f"{id_label} {id_value} is shared by {len(distinct_people)} different parties: {', '.join(distinct_people)}. Verify this is not a transcription error or identity reuse.",
                    "expected":   f"A unique {id_label} per person",
                    "actual":     f"{id_value} shared by: {', '.join(distinct_people)}"
                })

    _flag_shared_ids("pan", "PAN", "SHARED_PAN")
    _flag_shared_ids("pin", "PIN", "SHARED_PIN")

    # ── Final entities snapshot — return EVERYONE, not just current ──
    # Frontend groups by status to render Current / Previous sections.
    owners_all = [
        {**v, "canonical": k}
        for k, v in claimants.items()
    ]
    # Encumbrances: surface all of them with their final status.
    # Frontend separates UNRESOLVED (active) from RESOLVED (historical).
    encumbrances_all = list(encumbrances)

    entities = {
        "owners":       owners_all,        # mixed: active + transferred_out
        "encumbrances": encumbrances_all,  # mixed: UNRESOLVED + RESOLVED
    }

    return events, entities, errors, unresolved_mortgages


# Build events for a project
# Clear all parse results for a project (does NOT delete PDFs)
@app.route("/clear_results/<project_name>", methods=["POST"])
def clear_results(project_name):
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    if not os.path.isdir(project_path):
        return jsonify({"ok": False, "removed": 0}), 404
    removed = 0
    for f in os.listdir(project_path):
        if f.endswith("_result.json"):
            try:
                os.remove(os.path.join(project_path, f))
                removed += 1
            except OSError:
                pass
    return jsonify({"ok": True, "removed": removed})


def _finding_id(err):
    """
    Build a STABLE, deterministic id for a finding so that a reviewer's
    dismissal survives re-parsing. Same finding → same id every time.
    Derived from the finding's type + the parties/values that define it,
    NOT from list order (which can change).
    """
    import hashlib
    parts = [
        str(err.get("type", "")),
        str(err.get("doc_no", "")),
        str(err.get("expected", "")),
        str(err.get("actual", "")),
    ]
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _dismissals_path(project_name):
    return os.path.join(PROJECT_FOLDER, project_name, "_dismissed.json")


def _load_dismissals(project_name):
    """Return the set of dismissed finding ids for a project."""
    path = _dismissals_path(project_name)
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            return set(json.load(f))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_dismissals(project_name, ids):
    path = _dismissals_path(project_name)
    try:
        with open(path, "w") as f:
            json.dump(sorted(ids), f, indent=2)
        return True
    except OSError:
        return False


@app.route("/events/<project_name>")
def get_events(project_name):
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)

    # Attach a stable id + dismissed flag to every finding so the reviewer
    # can dismiss/restore individual findings, and have it persist.
    dismissed_ids = _load_dismissals(project_name)
    for e in errors:
        fid = _finding_id(e)
        e["finding_id"] = fid
        e["dismissed"]  = fid in dismissed_ids

    # A dismissed finding is treated as resolved EVERYWHERE downstream —
    # it must not influence counts, summaries, or any derived signal.
    # Only the raw "chain_errors" list keeps dismissed items (so the UI
    # can still render them greyed); every other derived value below is
    # computed from ACTIVE findings only.
    active_errors = [e for e in errors if not e["dismissed"]]

    # Consistency warnings for the events tab — active only.
    consistency_errors = [
        e["message"] for e in active_errors
        if e["type"] in ("AREA_MISMATCH", "SOCIETY_MISMATCH", "ID_MISMATCH")
    ]

    # Findings count for the metadata/summary — active only.
    active_findings_count = len(active_errors)

    # Encumbrance counts for the metadata bar (total vs unresolved)
    encumbrances = (entities or {}).get("encumbrances", [])
    encumbrances_total      = len(encumbrances)
    encumbrances_unresolved = len([e for e in encumbrances if e.get("status") == "UNRESOLVED"])
    return jsonify({
        "events": events,
        "consistency_errors": consistency_errors,
        "unresolved_mortgages": unresolved_mortgages,
        # Full findings list (incl. dismissed) so the Events tab can render
        # them — but downstream logic uses active_findings_count / active only.
        "chain_errors": errors,
        "active_findings_count": active_findings_count,
        "encumbrances_total": encumbrances_total,
        "encumbrances_unresolved": encumbrances_unresolved,
    })


# Dismiss a finding (reviewer has verified it as a non-issue)
@app.route("/dismiss_finding/<project_name>/<finding_id>", methods=["POST"])
def dismiss_finding(project_name, finding_id):
    from flask import jsonify
    ids = _load_dismissals(project_name)
    ids.add(finding_id)
    ok = _save_dismissals(project_name, ids)
    return jsonify({"ok": ok, "dismissed": finding_id})


# Restore a previously dismissed finding (full reviewer control)
@app.route("/restore_finding/<project_name>/<finding_id>", methods=["POST"])
def restore_finding(project_name, finding_id):
    from flask import jsonify
    ids = _load_dismissals(project_name)
    ids.discard(finding_id)
    ok = _save_dismissals(project_name, ids)
    return jsonify({"ok": ok, "restored": finding_id})


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
    return jsonify(entities)  # already structured as {owners, encumbrances}


# ── AI Assistant chat endpoint ──────────────────────────────────────────────
@app.route("/chat/<project_name>", methods=["POST"])
def chat(project_name):
    from flask import jsonify
    from main import chat_about_property

    project_path = os.path.join(PROJECT_FOLDER, project_name)
    payload = request.get_json(silent=True) or {}
    history = payload.get("history", [])
    model   = payload.get("model", "gemini-2.5-flash")

    if not isinstance(history, list) or not history:
        return jsonify({"ok": False, "error": "No question provided"}), 400

    # Assemble the assistant's ENTIRE factual world for this property:
    # every per-document parsed field + the derived events/entities/findings.
    results = _load_results(project_path)
    per_document = [
        {"file": rf.replace("_result.json", ".pdf"), "fields": data}
        for rf, data in results
    ]

    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)

    # Drop dismissed findings from the assistant's view — a dismissed finding
    # is resolved, and the assistant shouldn't raise it as a live concern.
    dismissed_ids = _load_dismissals(project_name)
    active_findings = []
    for e in errors:
        fid = _finding_id(e)
        if fid not in dismissed_ids:
            active_findings.append(e)

    context = {
        "project": project_name.rsplit("_", 1)[0],
        "per_document_parsed_fields": per_document,
        "events": events,
        "entities": entities,                 # {owners, encumbrances}
        "findings": active_findings,
        "unresolved_mortgages": unresolved_mortgages,
    }

    try:
        context_json = json.dumps(context, indent=2, default=str)
    except (TypeError, ValueError):
        context_json = str(context)

    reply = chat_about_property(context_json, history, model=model)
    return jsonify({"ok": True, "reply": reply})


if __name__ == "__main__":
    app.run(debug=True, port=5000)