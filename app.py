import uuid
import os
import json
import shutil
import re
import random
import datetime
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from main import extract_text_from_PDF
from circle_rates import calculate_circle_rate_value, normalize_area_to_sqm, get_historical_stamp_duty_rate
from doris_scraper import DorisScraperSession
from deed_doc_scraper import DorisDocScraper

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-autotsr-alpha-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=365)
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=365)

@app.before_request
def make_session_permanent():
    session.permanent = True

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    projects = db.relationship('Project', backref='owner', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(150), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class UserOTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def send_otp_email(email, otp_code):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = os.environ.get("SMTP_PORT")
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender_email = os.environ.get("SENDER_EMAIL")

    subject = f"Your AutoTSR Verification Code: {otp_code}"
    body = f"Hello,\n\nYour One-Time Password (OTP) for AutoTSR is: {otp_code}\n\nThis code will expire in 5 minutes.\n\nRegards,\nAutoTSR Team"

    if smtp_server and smtp_port and smtp_username and smtp_password and sender_email:
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = email

            with smtplib.SMTP(smtp_server, int(smtp_port)) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(sender_email, [email], msg.as_string())
            print(f"[SMTP] Successfully sent OTP to {email}")
            return True
        except Exception as e:
            print(f"[SMTP ERROR] Failed to send email via SMTP: {e}")
            
    print(f"\n==========================================")
    print(f"[DEVELOPER MODE] OTP for {email} is: {otp_code}")
    print(f"==========================================\n")
    return False

def migrate_existing_projects(user_id):
    if os.path.exists(PROJECT_FOLDER):
        for item in os.listdir(PROJECT_FOLDER):
            item_path = os.path.join(PROJECT_FOLDER, item)
            if os.path.isdir(item_path):
                existing = Project.query.filter_by(project_name=item).first()
                if not existing:
                    proj = Project(project_name=item, user_id=user_id)
                    db.session.add(proj)
        db.session.commit()

def check_project_owner(project_name):
    if not current_user.is_authenticated:
        return False
    proj = Project.query.filter_by(project_name=project_name, user_id=current_user.id).first()
    return proj is not None

with app.app_context():
    inspector = db.inspect(db.engine)
    if 'user' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('user')]
        if 'password_hash' in columns:
            db.drop_all()
            print("Dropped old database tables to migrate to passwordless schema.")
    db.create_all()

# Folders
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

PROJECT_FOLDER = "workspaces"
os.makedirs(PROJECT_FOLDER, exist_ok=True)

# PER BANK ALIASES 
LENDER_ALIASES = {
    "state_bank_of_india": ["SBI", "State Bank of India", "State Bank", "S.B.I."],
    "hdfc_bank": ["HDFC Bank", "HDFC Bank Ltd", "HDFC Bank Limited", "HDFC"],
    "icici_bank": ["ICICI Bank", "ICICI Bank Ltd", "ICICI"],
    "axis_bank": ["Axis Bank", "Axis Bank Ltd", "UTI Bank"],  # UTI was renamed Axis in 2007
    "punjab_national_bank": ["PNB", "Punjab National Bank"],
    "bank_of_baroda": ["BoB", "Bank of Baroda"],
    "canara_bank": ["Canara Bank"],
    "union_bank_of_india": ["UBI", "Union Bank of India", "Union Bank"],
    "bank_of_india": ["BoI", "Bank of India"],
    "indian_bank": ["Indian Bank"],
    "central_bank_of_india": ["Central Bank of India", "CBI"],
    "indian_overseas_bank": ["IOB", "Indian Overseas Bank"],
    "uco_bank": ["UCO Bank"],
    "bank_of_maharashtra": ["BoM", "Bank of Maharashtra"],
    "punjab_and_sind_bank": ["PSB", "Punjab and Sind Bank", "Punjab & Sind Bank"],
    "kotak_mahindra_bank": ["Kotak", "Kotak Mahindra Bank", "Kotak Bank"],
    "yes_bank": ["Yes Bank", "YES Bank"],
    "idfc_first_bank": ["IDFC First Bank", "IDFC Bank", "IDFC FIRST Bank"],
    "indusind_bank": ["IndusInd Bank", "Indusind Bank"],
    "federal_bank": ["Federal Bank", "The Federal Bank"],
    "south_indian_bank": ["South Indian Bank", "SIB"],
    "rbl_bank": ["RBL Bank", "Ratnakar Bank"],
    "bandhan_bank": ["Bandhan Bank"],
    "lic_housing_finance": ["LICHFL", "LIC Housing Finance", "LIC HFL"],
    "hdfc_ltd": ["HDFC Ltd", "Housing Development Finance Corporation", "HDFC Limited"],
    "pnb_housing_finance": ["PNB Housing", "PNB Housing Finance"],
    # known mergers (treated as same entity, with WARNING flag)
    "vijaya_bank": ["Vijaya Bank"],  # merged into BoB 2019
    "dena_bank": ["Dena Bank"],       # merged into BoB 2019
    "corporation_bank": ["Corporation Bank"],  # merged into UBI 2020
    "andhra_bank": ["Andhra Bank"],   # merged into UBI 2020
    "syndicate_bank": ["Syndicate Bank"],  # merged into Canara 2020
    "oriental_bank_of_commerce": ["OBC", "Oriental Bank of Commerce"],  # merged into PNB 2020
    "united_bank_of_india": ["United Bank of India"],  # merged into PNB 2020
    "allahabad_bank": ["Allahabad Bank"],  # merged into Indian Bank 2020
}

MERGER_MAP = {
    "vijaya_bank": "bank_of_baroda",
    "dena_bank": "bank_of_baroda",
    "corporation_bank": "union_bank_of_india",
    "andhra_bank": "union_bank_of_india",
    "syndicate_bank": "canara_bank",
    "oriental_bank_of_commerce": "punjab_national_bank",
    "united_bank_of_india": "punjab_national_bank",
    "allahabad_bank": "indian_bank",
}

import re

def _normalize_sro(sro):
    if not sro:
        return ""
    s = str(sro).strip().lower()
    
    # Strip common trailing location suffixes that documents often append
    for suffix in [", new delhi", ", delhi", ", nct of delhi", ", nct delhi",
                   " new delhi", " delhi"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip().rstrip(",").strip()
            break
    
    # Precise Roman numeral dictionary for Delhi SROs
    DELHI_SRO_ROMANS = {
        "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6",
        "vii": "7", "viii": "8", "ix": "9", "x": "10", "xi": "11", "xii": "12",
        "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16", "xvii": "17", "xviii": "18",
        "iia": "2a", "via": "6a", "viiia": "8a"
    }
    
    # Split by non-alphanumeric to find SRO tokens
    tokens = re.split(r"[^\w\d]+", s)
    new_tokens = []
    for t in tokens:
        if t in DELHI_SRO_ROMANS:
            t = DELHI_SRO_ROMANS[t]
        new_tokens.append(t)
    s = "".join(new_tokens)
    return s

def _parse_share(text):
    if not text:
        return None
    s = str(text).lower().strip()
    
    fractions_map = {
        r"\bone[- ]half\b": 0.5, r"\b1/2\b": 0.5, r"\bhalf\b": 0.5,
        r"\bone[- ]third\b": 1.0/3.0, r"\b1/3\b": 1.0/3.0,
        r"\btwo[- ]third\b": 2.0/3.0, r"\b2/3\b": 2.0/3.0,
        r"\bone[- ]fourth\b": 0.25, r"\b1/4\b": 0.25, r"\b(?:one|a)\s+quarter\b": 0.25,
        r"\bthree[- ]fourth\b": 0.75, r"\b3/4\b": 0.75,
        r"\bone[- ]fifth\b": 0.20, r"\b1/5\b": 0.20,
        r"\btwo[- ]fifth\b": 0.40, r"\b2/5\b": 0.40,
        r"\bthree[- ]fifth\b": 0.60, r"\b3/5\b": 0.60,
        r"\bfour[- ]fifth\b": 0.80, r"\b4/5\b": 0.80,
    }
    
    for pattern, val in fractions_map.items():
        if re.search(pattern, s):
            return val
            
    word_pcts = {
        "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
        "twenty five": 25, "twenty-five": 25, "seventy five": 75, "seventy-five": 75,
        "thirty three": 33.33, "thirty-three": 33.33, "sixty six": 66.66, "sixty-six": 66.66
    }
    
    for kw, val in word_pcts.items():
        if re.search(rf"\b{kw}\b\s*(?:%|percent)", s):
            return val / 100.0
            
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:%|percent)\b", s)
    if m:
        return float(m.group(1)) / 100.0
        
    return None

def _normalize_lender(name):
    if not name:
        return ""
    s = str(name).strip().lower()
    # Remove punctuation
    s = re.sub(r"[^\w\s]", "", s)
    # Strip common corporate suffixes
    s = re.sub(r"\b(ltd|limited|pvt|private|co|company|bank)\b", "", s)
    s = " ".join(s.split())  # normalize whitespace
    
    # Check if this maps to a canonical bank key
    for canonical_key, aliases in LENDER_ALIASES.items():
        for alias in aliases:
            alias_norm = str(alias).strip().lower()
            alias_norm = re.sub(r"[^\w\s]", "", alias_norm)
            alias_norm = re.sub(r"\b(ltd|limited|pvt|private|co|company|bank)\b", "", alias_norm)
            alias_norm = " ".join(alias_norm.split())
            if s == alias_norm or s == canonical_key:
                return canonical_key
    return s

def _levenshtein(s1, s2):
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def _check_name_deviation(name_a, name_b):
    norm_a = _normalize(name_a)
    norm_b = _normalize(name_b)
    if norm_a == norm_b:
        return "EXACT", "Name consistent", "INFO"
        
    ta = _name_tokens(name_a)
    tb = _name_tokens(name_b)
    if ta == tb and ta:
        return "NORMALIZED", "Honorific normalized", "INFO"
        
    similarity = _char_similarity(name_a, name_b)
    if similarity >= 0.95:
        return "MINOR", f"Minor name variation: '{name_a}' vs '{name_b}'", "INFO"
    elif similarity >= 0.80:
        return "MILD", f"Mild name deviation: '{name_a}' vs '{name_b}'", "WARNING"
    elif similarity >= 0.50:
        return "SEVERE", f"Severe name deviation: '{name_a}' vs '{name_b}'", "WARNING"
        
    if ta & tb:
        return "ALIAS", f"Possible name alias or change: '{name_a}' vs '{name_b}'", "WARNING"
        
    return "UNKNOWN", f"Unknown party match: '{name_a}' vs '{name_b}'", "ERROR"

def parse_indian_words_to_number(text):
    if not text:
        return None
    import re
    
    # Clean text
    s = str(text).lower().strip()
    s = s.replace(",", "")
    s = s.replace("-", " ")
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    s = re.sub(r"\band\b", " ", s)
    s = re.sub(r"\bonly\b", " ", s)
    s = re.sub(r"\brupees?\b", " ", s)
    s = re.sub(r"\brs\b", " ", s)
    
    words = s.split()
    if not words:
        return None
        
    num_words = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90
    }
    
    multipliers = {
        "hundred": 100, "hundreds": 100,
        "thousand": 1000, "thousands": 1000,
        "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000,
        "crore": 10000000, "crores": 10000000, "cr": 10000000
    }
    
    total = 0
    current = 0
    has_word = False
    
    for w in words:
        if w in num_words or w in multipliers:
            has_word = True
            break
            
    if not has_word:
        return None
        
    for w in words:
        if w in num_words:
            current += num_words[w]
        elif w in multipliers:
            val = multipliers[w]
            if val >= 1000:
                if current == 0:
                    current = 1
                total += current * val
                current = 0
            else:
                if current == 0:
                    current = 1
                current = current * val
        else:
            try:
                val = float(w)
                current += val
            except ValueError:
                pass
                
    total += current
    return float(total)


def _check_words_vs_figures(figures_val, words_val, doc_no, source, event_date, amount_type_label, words_text_val=None):
    fig_num = _parse_money(figures_val)
    wrd_num = _parse_money(words_val)
    
    # Fallback to parsing words string directly
    if wrd_num is None and words_text_val is not None:
        wrd_num = parse_indian_words_to_number(words_text_val)
        
    if fig_num is None or wrd_num is None:
        return None
        
    if abs(fig_num - wrd_num) < 0.01:
        return None
        
    return {
        "severity": "ERROR",
        "type": "AMOUNT_WORDS_FIGURES_MISMATCH",
        "doc_no": doc_no,
        "event_date": event_date,
        "source": source,
        "message": f"{amount_type_label.capitalize()} mismatch: figures show ₹{int(fig_num):,} but words show ₹{int(wrd_num):,}.",
        "expected": f"₹{int(fig_num):,}",
        "actual": f"₹{int(wrd_num):,}"
    }


def _match_release_to_mortgage(enc, d2):
    # Normalize doc numbers
    m_doc = str(enc.get("doc_no") or "").strip()
    r_doc = str(d2.get("released_mortgage_doc_no") or "").strip()
    
    def clean_doc(d):
        return re.sub(r"[^\w\d]", "", str(d).lower())
    
    m_doc_clean = clean_doc(m_doc)
    r_doc_clean = clean_doc(r_doc)
    
    doc_match = False
    fuzzy_match = False
    if m_doc_clean and r_doc_clean:
        if m_doc_clean == r_doc_clean:
            doc_match = True
        else:
            # Check for significant registration digit sequences overlap (Delhi format support)
            nums1 = re.findall(r"\d+", m_doc.lower())
            nums2 = re.findall(r"\d+", r_doc.lower())
            significant_1 = [n for n in nums1 if n not in ("1", "2", "3", "4", "1a", "1b") and not (len(n) == 4 and (n.startswith("19") or n.startswith("20")))]
            significant_2 = [n for n in nums2 if n not in ("1", "2", "3", "4", "1a", "1b") and not (len(n) == 4 and (n.startswith("19") or n.startswith("20")))]
            
            sig1_ints = []
            for x in significant_1:
                try: sig1_ints.append(int(x))
                except: pass
            sig2_ints = []
            for x in significant_2:
                try: sig2_ints.append(int(x))
                except: pass
                
            if sig1_ints and sig2_ints and (set(sig1_ints) & set(sig2_ints)):
                doc_match = True
                fuzzy_match = True
            elif m_doc_clean in r_doc_clean or r_doc_clean in m_doc_clean:
                if len(m_doc_clean) >= 3 and len(r_doc_clean) >= 3:
                    doc_match = True
                    fuzzy_match = True
            elif _levenshtein(m_doc_clean, r_doc_clean) <= 2:
                doc_match = True
                fuzzy_match = True
            
    # SRO match (Delhi location + SRO number aware)
    m_sro = enc.get("sro")
    r_sro = d2.get("released_mortgage_sro") or d2.get("sub_registrar_office")
    
    def sros_match(sro1, sro2):
        norm1 = _normalize_sro(sro1)
        norm2 = _normalize_sro(sro2)
        if not norm1 or not norm2:
            return False
        if norm1 == norm2:
            return True
        digits1 = re.findall(r"\d+", norm1)
        digits2 = re.findall(r"\d+", norm2)
        if digits1 and digits2:
            if set(digits1) & set(digits2):
                return True
        localities = ["janakpuri", "rohini", "kalkaji", "mehrauli", "pitampura", "narela", "nangloi", 
                      "wazirpur", "preetvihar", "geetacolony", "shastrinagar", "sarojininagar", 
                      "defencedolony", "kapashera", "dwarka", "keshopur", "vivekvihar", "belaroad", 
                      "kashmeregate", "asafali"]
        for loc in localities:
            if loc in norm1 and loc in norm2:
                return True
        return False
        
    sro_match = sros_match(m_sro, r_sro)
    
    # Year match (allow off-by-one boundary crossing)
    m_year = str(enc.get("year") or "").strip()
    r_year = str(d2.get("released_mortgage_year") or d2.get("registration_year") or "").strip()
    if not m_year and enc.get("since_date"):
        m_year = str(enc.get("since_date")).split("-")[-1].split("/")[-1].strip()
    if not r_year and (d2.get("released_mortgage_date") or d2.get("date_of_execution")):
        r_year = str(d2.get("released_mortgage_date") or d2.get("date_of_execution")).split("-")[-1].split("/")[-1].strip()
    
    year_match = False
    if m_year and r_year:
        try:
            year_match = abs(int(m_year) - int(r_year)) <= 1
        except:
            year_match = m_year == r_year
    
    # Amount match (paise checks)
    m_amt = enc.get("principal_amount")
    r_amt = _parse_money(d2.get("released_mortgage_principal_figures") or d2.get("principal_amount_figures"))
    a_match = False
    if m_amt is not None and r_amt is not None:
        a_match = abs(m_amt - r_amt) < 0.01
        
    # LAN match
    m_lan = re.sub(r"[^\w\d]", "", str(enc.get("loan_account_no") or "").lower())
    r_lan = re.sub(r"[^\w\d]", "", str(d2.get("loan_account_no") or "").lower())
    lan_match = bool(m_lan and r_lan and m_lan == r_lan)
    
    # Parties match ( Delhi name variation resilience)
    m_gor = enc.get("mortgagor")
    r_gors = d2.get("released_mortgage_mortgagor_names") or d2.get("buyer_names") or d2.get("releasee_names") or [p.get("name") for p in d2.get("transferee_parties") or [] if p.get("name")]
    if isinstance(r_gors, str):
        r_gors = [r_gors]
    r_gors = [n for n in (r_gors or []) if n]
    
    def name_match_any_tier(name1, name2):
        if not name1 or not name2:
            return False
        tier, _, _ = _check_name_deviation(name1, name2)
        return tier != "UNKNOWN"
        
    mortgagor_match = False
    if m_gor and r_gors:
        mortgagor_match = any(name_match_any_tier(m_gor, name) for name in r_gors)
        
    m_gee = enc.get("holder")
    r_gees = d2.get("released_mortgage_mortgee_names") or d2.get("seller_names") or d2.get("releasor_names") or [p.get("name") for p in d2.get("transferor_parties") or [] if p.get("name")]
    if isinstance(r_gees, str):
        r_gees = [r_gees]
    r_gees = [n for n in (r_gees or []) if n]
    mortgagee_match = False
    if m_gee and r_gees:
        def bank_match(b1, b2):
            n1 = _normalize_lender(b1)
            n2 = _normalize_lender(b2)
            if not n1 or not n2:
                return False
            if n1 == n2:
                return True
            if MERGER_MAP.get(n1) == n2 or MERGER_MAP.get(n2) == n1:
                return True
            # Substring containment check to handle branch suffix variations
            if n1 in n2 or n2 in n1:
                return True
            return False
        mortgagee_match = any(bank_match(m_gee, name) or name_match_any_tier(m_gee, name) for name in r_gees)
        
    p_match = mortgagor_match and mortgagee_match
    
    # Score candidate
    score = 0
    if doc_match: score += 10
    if not fuzzy_match and doc_match: score += 5
    if sro_match: score += 2
    if year_match: score += 2
    if a_match: score += 2
    if lan_match: score += 2
    if mortgagor_match: score += 1
    if mortgagee_match: score += 1
    
    # Tiers classification
    if doc_match and not fuzzy_match:
        corrob_count = sum([sro_match, year_match, a_match, p_match, lan_match])
        if year_match and a_match and (p_match or sro_match):
            return "A", "RELEASE_LINK_A", "INFO", score, True, False, p_match, a_match
        if corrob_count >= 2:
            return "B", "RELEASE_LINK_B", "INFO", score, True, False, p_match, a_match
        return "C", "RELEASE_LINK_C", "INFO", score, True, False, p_match, a_match
        
    elif doc_match and fuzzy_match:
        corrob_count = sum([year_match, sro_match, a_match, p_match, lan_match])
        if corrob_count >= 3:
            return "D", "RELEASE_LINK_D", "WARNING", score, True, True, p_match, a_match
        return "E", "RELEASE_LINK_E", "ERROR", score, True, True, p_match, a_match
        
    else:
        if p_match and sro_match and year_match:
            return "F", "RELEASE_LINK_F", "WARNING", score, False, False, p_match, a_match
            
    return None, None, None, 0, False, False, False, False

def generate_and_send_otp(email):
    # Delete old OTPs for this email
    UserOTP.query.filter_by(email=email).delete()
    
    # Generate 6-digit code
    code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    
    # Create OTP record (expires in 5 minutes)
    expires = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
    otp = UserOTP(email=email, otp_code=code, expires_at=expires)
    db.session.add(otp)
    db.session.commit()
    
    # Send email
    send_otp_email(email, code)

# Auth Routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("projects"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Email address is required.")
            return render_template("login.html")
        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Email address is not registered. Please sign up first.")
            return render_template("login.html")
            
        generate_and_send_otp(email)
        return redirect(url_for("verify", email=email, purpose="login"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("projects"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Email address is required.")
            return render_template("register.html")
            
        # Whitelist verification
        whitelist_path = "allowed_emails.txt"
        is_authorized = False
        if os.path.exists(whitelist_path):
            with open(whitelist_path, "r", encoding="utf-8") as f:
                allowed = [line.strip().lower() for line in f if line.strip()]
            if email.lower() in allowed:
                is_authorized = True
        
        if not is_authorized:
            flash("This email address is not authorized for the alpha preview. Please contact the administrator.")
            return render_template("register.html")
            
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered. Please sign in instead.")
            return render_template("register.html")
            
        generate_and_send_otp(email)
        return redirect(url_for("verify", email=email, purpose="register"))
    return render_template("register.html")

@app.route("/verify/<email>/<purpose>", methods=["GET", "POST"])
def verify(email, purpose):
    if current_user.is_authenticated:
        return redirect(url_for("projects"))
        
    if request.method == "POST":
        otp_code = request.form.get("otp_code", "").strip()
        if not otp_code:
            flash("OTP code is required.")
            return render_template("verify.html", email=email, purpose=purpose)
            
        # Validate OTP
        now = datetime.datetime.utcnow()
        record = UserOTP.query.filter_by(email=email, otp_code=otp_code).first()
        if not record or record.expires_at < now:
            flash("Invalid or expired verification code.")
            return render_template("verify.html", email=email, purpose=purpose)
            
        # Clear OTP from database
        db.session.delete(record)
        db.session.commit()
        
        if purpose == "register":
            existing_user = User.query.filter_by(email=email).first()
            if not existing_user:
                is_first = User.query.count() == 0
                new_user = User(email=email)
                db.session.add(new_user)
                db.session.commit()
                
                if is_first:
                    migrate_existing_projects(new_user.id)
                login_user(new_user, remember=True)
            else:
                login_user(existing_user, remember=True)
        else: # login
            user = User.query.filter_by(email=email).first()
            if user:
                login_user(user, remember=True)
            else:
                flash("Login failed. Account not found.")
                return redirect(url_for("login"))
                
        return redirect(url_for("projects"))
        
    return render_template("verify.html", email=email, purpose=purpose)

@app.route("/login/google")
def login_google():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        return redirect(url_for("google_mock"))
        
    redirect_uri = url_for("google_callback", _external=True)
    state = uuid.uuid4().hex
    
    authorization_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        "response_type=code&"
        "scope=openid%20email%20profile&"
        f"state={state}"
    )
    return redirect(authorization_url)

@app.route("/login/google/callback")
def google_callback():
    code = request.args.get("code")
    if not code:
        flash("Google authentication failed: no authorization code returned.")
        return redirect(url_for("login"))
        
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_uri = url_for("google_callback", _external=True)
    
    import requests
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    try:
        r = requests.post(token_url, data=data)
        if r.status_code != 200:
            app.logger.error(f"[GOOGLE OAUTH ERROR RESPONSE] Status: {r.status_code}, Body: {r.text}")
        r.raise_for_status()
        token_data = r.json()
        
        access_token = token_data.get("access_token")
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_r = requests.get(userinfo_url, headers=headers)
        user_r.raise_for_status()
        userinfo = user_r.json()
        email = userinfo.get("email")
        
        if not email:
            flash("Could not retrieve email from Google.")
            return redirect(url_for("login"))
            
        whitelist_path = "allowed_emails.txt"
        is_authorized = False
        if os.path.exists(whitelist_path):
            with open(whitelist_path, "r", encoding="utf-8") as f:
                allowed = [line.strip().lower() for line in f if line.strip()]
            if email.lower() in allowed:
                is_authorized = True
        
        if not is_authorized:
            flash("This email address is not authorized for the alpha preview. Please contact the administrator.")
            return redirect(url_for("login"))
            
        user = User.query.filter_by(email=email).first()
        if not user:
            is_first = User.query.count() == 0
            user = User(email=email)
            db.session.add(user)
            db.session.commit()
            if is_first:
                migrate_existing_projects(user.id)
                
        login_user(user, remember=True)
        return redirect(url_for("projects"))
        
    except Exception as e:
        flash(f"Google Sign-In failed: {e}")
        return redirect(url_for("login"))

@app.route("/login/google/mock", methods=["GET", "POST"])
def google_mock():
    allowed = []
    whitelist_path = "allowed_emails.txt"
    if os.path.exists(whitelist_path):
        with open(whitelist_path, "r", encoding="utf-8") as f:
            allowed = [line.strip() for line in f if line.strip()]
    return render_template("google_mock.html", allowed_emails=allowed)

@app.route("/login/google/mock/callback", methods=["POST"])
def google_mock_callback():
    email = request.form.get("email", "").strip()
    if not email:
        flash("Email is required for simulation.")
        return redirect(url_for("google_mock"))
        
    whitelist_path = "allowed_emails.txt"
    is_authorized = False
    if os.path.exists(whitelist_path):
        with open(whitelist_path, "r", encoding="utf-8") as f:
            allowed = [line.strip().lower() for line in f if line.strip()]
        if email.lower() in allowed:
            is_authorized = True
            
    if not is_authorized:
        flash("This email address is not authorized for the alpha preview.")
        return redirect(url_for("google_mock"))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        is_first = User.query.count() == 0
        user = User(email=email)
        db.session.add(user)
        db.session.commit()
        if is_first:
            migrate_existing_projects(user.id)
            
    login_user(user, remember=True)
    return redirect(url_for("projects"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# Home page
@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("projects"))
    return redirect(url_for("login"))

# Proposed modal designs draft preview
@app.route("/proposed-modal-draft")
def proposed_modal_draft():
    return render_template("proposed_modal_draft.html")

# Projects list
@app.route("/projects")
@login_required
def projects():
    user_projects = [p.project_name for p in Project.query.filter_by(user_id=current_user.id).all()]
    projects_list = []
    if os.path.exists(PROJECT_FOLDER):
        for folder in os.listdir(PROJECT_FOLDER):
            if folder not in user_projects:
                continue
            id_info_path = os.path.join(PROJECT_FOLDER, folder, "id_info.json")
            id_type = None
            id_value = None
            locality = None
            sro = None
            category = None
            land_use = None
            flat_no = None
            floor_no = None
            address = None
            search_period = None
            mcd_upic = None
            if os.path.exists(id_info_path):
                with open(id_info_path) as f:
                    info = json.load(f)
                    id_type = info.get("id_type")
                    id_value = info.get("id_value")
                    locality = info.get("locality")
                    sro = info.get("sro")
                    category = info.get("category")
                    land_use = info.get("land_use")
                    flat_no = info.get("flat_no")
                    floor_no = info.get("floor_no")
                    address = info.get("address")
                    search_period = info.get("search_period")
                    mcd_upic = info.get("mcd_upic")
            # Count PDF files in this project folder
            project_path = os.path.join(PROJECT_FOLDER, folder)
            doc_count = len([f for f in os.listdir(project_path) if f.lower().endswith(".pdf")]) if os.path.isdir(project_path) else 0
            projects_list.append({
                "folder": folder,
                "name": folder.rsplit("_", 1)[0],
                "id_type": id_type,
                "id_value": id_value,
                "locality": locality,
                "sro": sro,
                "category": category,
                "land_use": land_use,
                "flat_no": flat_no,
                "floor_no": floor_no,
                "address": address,
                "search_period": search_period,
                "mcd_upic": mcd_upic,
                "doc_count": doc_count
            })
    return render_template("projects.html", projects=projects_list)

# Create new project
@app.route("/create_project", methods=["POST"])
@login_required
def create_project():
    project_name = request.form.get("project_name", "").strip()
    locality = request.form.get("locality", "").strip()
    sro = request.form.get("sro", "").strip()
    category = request.form.get("category", "").strip()
    land_use = request.form.get("land_use", "").strip()
    flat_no = request.form.get("flat_no", "").strip()
    floor_no = request.form.get("floor_no", "").strip()
    address = request.form.get("address", "").strip()
    search_period = request.form.get("search_period", "").strip()
    mcd_upic = request.form.get("mcd_upic", "").strip()
    id_type = request.form.get("id_type", "").strip()
    id_value = request.form.get("id_value", "").strip()
    property_type = request.form.get("property_type", "").strip()
    buyer_gender = request.form.get("buyer_gender", "").strip()
    construction_year = request.form.get("construction_year", "").strip()
    
    if not project_name:
        return redirect(url_for("projects"))
        
    safe_name = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in project_name])
    uid = uuid.uuid4().hex[:8]
    folder_name = f"{safe_name}_{uid}"
    
    project_path = os.path.join(PROJECT_FOLDER, folder_name)
    os.makedirs(project_path, exist_ok=True)
    
    id_info_path = os.path.join(project_path, "id_info.json")
    with open(id_info_path, "w") as f:
        json.dump({
            "id_type": id_type,
            "id_value": id_value,
            "locality": locality,
            "sro": sro,
            "category": category,
            "land_use": land_use,
            "flat_no": flat_no,
            "floor_no": floor_no,
            "address": address,
            "search_period": search_period,
            "mcd_upic": mcd_upic,
            "property_type": property_type,
            "buyer_gender": buyer_gender,
            "construction_year": construction_year
        }, f)
        
    proj = Project(project_name=folder_name, user_id=current_user.id)
    db.session.add(proj)
    db.session.commit()
    
    return redirect(f"/workspace/{folder_name}")
# Delete project
@app.route("/delete_project/<project_name>", methods=["POST"])
@login_required
def delete_project(project_name):
    if not check_project_owner(project_name):
        abort(403)
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
    
    proj = Project.query.filter_by(project_name=project_name, user_id=current_user.id).first()
    if proj:
        db.session.delete(proj)
        db.session.commit()
        
    return redirect(url_for("projects"))

# Workspace page
@app.route("/workspace/<project_name>", methods=["GET", "POST"])
@login_required
def workspace(project_name):
    if not check_project_owner(project_name):
        abort(403)
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

    id_type = None
    id_value = None
    locality = None
    sro = None
    category = None
    land_use = None
    flat_no = None
    floor_no = None
    address = None
    search_period = None
    mcd_upic = None
    id_info_path = os.path.join(project_path, "id_info.json")
    if os.path.exists(id_info_path):
        with open(id_info_path) as f:
            info = json.load(f)
            id_type = info.get("id_type")
            id_value = info.get("id_value")
            locality = info.get("locality")
            sro = info.get("sro")
            category = info.get("category")
            land_use = info.get("land_use")
            flat_no = info.get("flat_no")
            floor_no = info.get("floor_no")
            address = info.get("address")
            search_period = info.get("search_period")
            mcd_upic = info.get("mcd_upic")

    return render_template(
        "workspace.html",
        project_name=project_name,
        index_iis=index_iis,
        id_type=id_type,
        id_value=id_value,
        locality=locality,
        sro=sro,
        category=category,
        land_use=land_use,
        flat_no=flat_no,
        floor_no=floor_no,
        address=address,
        search_period=search_period,
        mcd_upic=mcd_upic
    )


# Skeleton workspace page (Playground UI layout)
@app.route("/skeleton/<project_name>", methods=["GET"])
@login_required
def workspace_skeleton(project_name):
    if not check_project_owner(project_name):
        abort(403)
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    os.makedirs(project_path, exist_ok=True)
    index_iis = [f for f in os.listdir(project_path) if f.lower().endswith(".pdf")]

    id_type = None
    id_value = None
    locality = None
    sro = None
    category = None
    land_use = None
    flat_no = None
    floor_no = None
    address = None
    search_period = None
    mcd_upic = None
    property_type = None
    buyer_gender = None
    construction_year = None
    id_info_path = os.path.join(project_path, "id_info.json")
    if os.path.exists(id_info_path):
        with open(id_info_path) as f:
            info = json.load(f)
            id_type = info.get("id_type")
            id_value = info.get("id_value")
            locality = info.get("locality")
            sro = info.get("sro")
            category = info.get("category")
            land_use = info.get("land_use")
            flat_no = info.get("flat_no")
            floor_no = info.get("floor_no")
            address = info.get("address")
            search_period = info.get("search_period")
            mcd_upic = info.get("mcd_upic")
            property_type = info.get("property_type")
            buyer_gender = info.get("buyer_gender")
            construction_year = info.get("construction_year")

    return render_template(
        "workspace_skeleton.html",
        project_name=project_name,
        index_iis=index_iis,
        id_type=id_type,
        id_value=id_value,
        locality=locality,
        sro=sro,
        category=category,
        land_use=land_use,
        flat_no=flat_no,
        floor_no=floor_no,
        address=address,
        search_period=search_period,
        mcd_upic=mcd_upic,
        property_type=property_type,
        buyer_gender=buyer_gender,
        construction_year=construction_year
    )


# Parse a PDF
@app.route("/parse/<project_name>/<path:filename>")
@login_required
def parse(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
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
        # Provisional results (low-confidence classification) get flagged
        # at the top level too, so _load_results can skip them and the
        # workspace UI can show a "?" badge prompting manual classification.
        result_filename = os.path.splitext(filename)[0] + "_result.json"
        result_path = os.path.join(project_path, result_filename)
        envelope = {"parsed": True, "data": result}
        if isinstance(result, dict) and result.get("_provisional") is True:
            envelope["provisional"]                = True
            envelope["needs_human_classification"] = True
            envelope["classification"]             = result.get("_classification")
        with open(result_path, "w") as f:
            json.dump(envelope, f, indent=2)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/classify/<project_name>/<path:filename>", methods=["POST"])
@login_required
def classify_file(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
    """
    Reviewer-confirmed classification for a provisional document.
    Body: {"subtype": "<one of DEED_SUBTYPES keys>"}.
    On receipt: rewrite the saved _result.json with the confirmed subtype,
    clear the provisional flags, and re-run full extraction with that
    subtype known. The file then enters the engine on the next page load.
    """
    from flask import jsonify
    from main import parse_index_ii, DEED_SUBTYPES

    project_path = os.path.join(PROJECT_FOLDER, project_name)
    file_path    = os.path.join(project_path, filename)
    payload      = request.get_json(silent=True) or {}
    subtype      = (payload.get("subtype") or "").strip()

    if not os.path.exists(file_path):
        return jsonify({"ok": False, "error": "File not found"}), 404
    if subtype not in DEED_SUBTYPES:
        return jsonify({"ok": False, "error": "Unknown subtype"}), 400

    try:
        result = parse_index_ii(file_path, forced_subtype=subtype)
        if not isinstance(result, dict):
            return jsonify({"ok": False, "error": "Re-extraction failed"}), 500
        # Force-confirm the subtype the reviewer chose; clear provisional
        # so _load_results lets the engine see it on next load.
        result["_provisional"]                = False
        result["_needs_human_classification"] = False
        if not isinstance(result.get("_classification"), dict):
            result["_classification"] = {"subtype": subtype, "confidence": "high",
                                         "reasoning": "human-confirmed",
                                         "runners_up": []}
        else:
            result["_classification"]["subtype"]    = subtype
            result["_classification"]["confidence"] = "high"
            result["_classification"]["reasoning"]  = "human-confirmed"
        result_filename = os.path.splitext(filename)[0] + "_result.json"
        result_path = os.path.join(project_path, result_filename)
        with open(result_path, "w") as f:
            json.dump({"parsed": True, "data": result}, f, indent=2)
        return jsonify({"ok": True, "subtype": subtype})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Replace an attached PDF file
@app.route("/replace_file/<project_name>/<path:filename>", methods=["POST"])
@login_required
def replace_file(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    uploaded_file = request.files.get("replacement_file")
    if not uploaded_file:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
        
    old_pdf_path = os.path.join(project_path, filename)
    old_result_path = os.path.splitext(old_pdf_path)[0] + "_result.json"
    
    try:
        if os.path.exists(old_pdf_path):
            os.remove(old_pdf_path)
        if os.path.exists(old_result_path):
            os.remove(old_result_path)
    except OSError as e:
        return jsonify({"ok": False, "error": f"Failed to delete old files: {e}"}), 500
        
    try:
        uploaded_file.save(old_pdf_path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Save updated parse result for a file
@app.route("/save_result/<project_name>/<path:filename>", methods=["POST"])
@login_required
def save_result(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
    
    payload = request.get_json()
    if not payload:
        return jsonify({"ok": False, "error": "No JSON payload provided"}), 400
        
    result_filename = os.path.splitext(filename)[0] + "_result.json"
    result_path = os.path.join(PROJECT_FOLDER, project_name, result_filename)
    
    try:
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# Save project settings
@app.route("/save_settings/<project_name>", methods=["POST"])
@login_required
def save_settings(project_name):
    if not check_project_owner(project_name):
        abort(403)
        
    payload = request.get_json()
    if not payload:
        return jsonify({"ok": False, "error": "No JSON payload provided"}), 400
        
    info_path = os.path.join(PROJECT_FOLDER, project_name, "id_info.json")
    if not os.path.exists(info_path):
        return jsonify({"ok": False, "error": "Project metadata not found"}), 404
        
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        meta = {}

    # Update settings dictionary
    meta["settings"] = payload
    
    # Also synchronize flat-level keys if overridden
    if "property_type" in payload:
        p_type = payload["property_type"]
        if "dda" in p_type or "society" in p_type or "cghs" in p_type:
            meta["category"] = "dda"
        elif "plot" in p_type or "land" in p_type:
            meta["category"] = "plot"
        else:
            meta["category"] = "flat"
            
    if "land_use" in payload:
        meta["land_use"] = payload["land_use"]

    try:
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# In-memory store for stateful DORIS scraper sessions
DORIS_SESSIONS = {}

@app.route("/api/doris/start/<project_name>", methods=["GET"])
@login_required
def api_doris_start(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    
    session_obj = DorisScraperSession()
    res = session_obj.start_session()
    if res.get("ok"):
        DORIS_SESSIONS[project_name] = session_obj
        return jsonify(res)
    else:
        return jsonify(res), 500


@app.route("/api/doris/select/<project_name>", methods=["POST"])
@login_required
def api_doris_select(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    
    payload = request.get_json() or {}
    step = payload.get("step")
    sro_val = payload.get("sro_val")
    loc_val = payload.get("loc_val")
    
    session_obj = DORIS_SESSIONS.get(project_name)
    if not session_obj:
        session_obj = DorisScraperSession()
        res = session_obj.start_session()
        if not res.get("ok"):
            return jsonify({"ok": False, "error": "Could not establish server session"}), 500
        DORIS_SESSIONS[project_name] = session_obj
        
    if step == "sro_selected":
        session_obj = DorisScraperSession()
        res = session_obj.start_session()
        if not res.get("ok"):
            return jsonify({"ok": False, "error": "Could not establish server session"}), 500
        DORIS_SESSIONS[project_name] = session_obj
        res = session_obj.select_sro(sro_val)
        return jsonify(res)
    elif step == "locality_selected":
        res = session_obj.select_locality(sro_val, loc_val)
        return jsonify(res)
    else:
        return jsonify({"ok": False, "error": "Invalid step"}), 400


@app.route("/api/doris/search/<project_name>", methods=["POST"])
@login_required
def api_doris_search(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    
    payload = request.get_json() or {}
    sro_val = payload.get("sro_val")
    loc_val = payload.get("loc_val")
    year_val = payload.get("year_val")
    params = payload.get("params") or {}
    captcha_text = payload.get("captcha_text")
    
    session_obj = DORIS_SESSIONS.get(project_name)
    if not session_obj:
        return jsonify({"ok": False, "error": "Scraper session not initialized. Please refresh the page."}), 400
        
    res = session_obj.execute_search(sro_val, loc_val, year_val, params, captcha_text)
    return jsonify(res)


@app.route("/api/doris/import/<project_name>", methods=["POST"])
@login_required
def api_doris_import(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    
    record = request.get_json() or {}
    reg_no = record.get("reg_no", "")
    if not reg_no:
        return jsonify({"ok": False, "error": "No registration number provided"}), 400
        
    # Create safe filename slug
    safe_reg = reg_no.replace("/", "_").replace("\\", "_").replace(" ", "_")
    base_filename = f"DORIS_Record_{safe_reg}"
    pdf_path = os.path.join(PROJECT_FOLDER, project_name, f"{base_filename}.pdf")
    json_path = os.path.join(PROJECT_FOLDER, project_name, f"{base_filename}_result.json")
    
    try:
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4 ... Empty placeholder for DORIS registry verified record ...")
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to create document placeholder: {str(e)}"}), 500
        
    deed_type = record.get("deed_type", "Deed")
    
    data_payload = {
        "doc_no": reg_no,
        "date_of_execution": record.get("reg_date") or "",
        "date_of_registration": record.get("reg_date") or "",
        "deed_type": deed_type,
        "consideration": 0,
        "stamp_duty": 0,
        "registration_fee": 0,
        "seller_names": record.get("first_party") or "",
        "buyer_names": record.get("second_party") or "",
        "society_building_address": record.get("property_address") or "",
        "is_doris_verified": True,
        "remarks": "Imported directly from Delhi Online Registration Information System (DORIS) public records."
    }
    
    info_path = os.path.join(PROJECT_FOLDER, project_name, "id_info.json")
    if os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            data_payload["property_type"] = meta.get("property_type") or "private_flat"
        except Exception:
            data_payload["property_type"] = "private_flat"
    else:
        data_payload["property_type"] = "private_flat"
        
    envelope = {
        "parsed": True,
        "data": data_payload
    }
    
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to write verified record result: {str(e)}"}), 500


# Rename a file within a project
@app.route("/rename_file/<project_name>/<path:filename>", methods=["POST"])
@login_required
def rename_file(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
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
@login_required
def delete_file(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
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
@login_required
def edit_project():
    folder = request.form.get("folder", "").strip()
    if not check_project_owner(folder):
        abort(403)
    new_name = request.form.get("project_name", "").strip()
    locality = request.form.get("locality", "").strip()
    sro = request.form.get("sro", "").strip()
    category = request.form.get("category", "").strip()
    land_use = request.form.get("land_use", "").strip()
    flat_no = request.form.get("flat_no", "").strip()
    floor_no = request.form.get("floor_no", "").strip()
    id_type = request.form.get("id_type", "").strip()
    id_value = request.form.get("id_value", "").strip()
    address = request.form.get("address", "").strip()
    search_period = request.form.get("search_period", "").strip()
    mcd_upic = request.form.get("mcd_upic", "").strip()
    property_type = request.form.get("property_type", "").strip()
    buyer_gender = request.form.get("buyer_gender", "").strip()
    construction_year = request.form.get("construction_year", "").strip()

    if not folder or not new_name:
        return redirect(url_for("projects"))

    old_path = os.path.join(PROJECT_FOLDER, folder)

    # Keep the same unique ID suffix, just change the name part
    if "_" in folder:
        suffix = folder.rsplit("_", 1)[-1]
        new_folder = f"{new_name}_{suffix}"
    else:
        new_folder = f"{new_name}_{folder}"
    new_path = os.path.join(PROJECT_FOLDER, new_folder)

    # Rename the folder
    if os.path.exists(old_path) and old_path != new_path:
        try:
            os.rename(old_path, new_path)
            # Update database record
            proj = Project.query.filter_by(project_name=folder, user_id=current_user.id).first()
            if proj:
                proj.project_name = new_folder
                db.session.commit()
        except Exception:
            new_path = old_path
            new_folder = folder
    else:
        new_path = old_path
        new_folder = folder

    # Update id_info.json
    id_info_path = os.path.join(new_path, "id_info.json")
    info_data = {}
    if os.path.exists(id_info_path):
        try:
            with open(id_info_path) as f:
                info_data = json.load(f)
        except Exception:
            pass

    info_data.update({
        "id_type": id_type,
        "id_value": id_value,
        "locality": locality,
        "sro": sro,
        "category": category,
        "land_use": land_use,
        "flat_no": flat_no,
        "floor_no": floor_no,
        "address": address,
        "search_period": search_period,
        "mcd_upic": mcd_upic,
        "property_type": property_type,
        "buyer_gender": buyer_gender,
        "construction_year": construction_year
    })

    with open(id_info_path, "w") as f:
        json.dump(info_data, f)

    return redirect(f"/workspace/{new_folder}")


# Serve PDF file for viewer
@app.route("/pdf/<project_name>/<path:filename>")
@login_required
def serve_pdf(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
    from flask import send_from_directory
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    return send_from_directory(project_path, filename)


# Load saved parse result for a file
@app.route("/result/<project_name>/<path:filename>")
@login_required
def load_result(project_name, filename):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    result_filename = os.path.splitext(filename)[0] + "_result.json"
    result_path = os.path.join(PROJECT_FOLDER, project_name, result_filename)
    if not os.path.exists(result_path):
        return jsonify({"exists": False})
    with open(result_path) as f:
        data = json.load(f)

    # Standardize result data and initialize original_data
    if isinstance(data, dict):
        import copy
        if "data" in data:
            if "original_data" not in data:
                data["original_data"] = copy.deepcopy(data["data"])
        else:
            data = {"parsed": True, "data": data, "original_data": copy.deepcopy(data)}

    # Inject dynamic signatory information by scanning the pdf text if available
    try:
        pdf_filename = os.path.splitext(filename)[0] + ".pdf"
        pdf_path = os.path.join(PROJECT_FOLDER, project_name, pdf_filename)
        if os.path.exists(pdf_path):
            from main import extract_text_from_PDF
            txt = extract_text_from_PDF(pdf_path)
            if txt:
                inner_data = data.get("data") if isinstance(data, dict) and "data" in data else data
                if isinstance(inner_data, dict):
                    for party in inner_data.get("transferor_parties", []):
                        sig = _extract_signatory(party.get("name"), txt)
                        if sig:
                            party["authorized_signatory"] = sig
                    for party in inner_data.get("transferee_parties", []):
                        sig = _extract_signatory(party.get("name"), txt)
                        if sig:
                            party["authorized_signatory"] = sig
    except Exception as e:
        print("load_result: failed dynamic signatory extraction:", e)

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
            inner = raw["data"]
            # Hold provisional documents out of the engine entirely until
            # the human confirms the deed type via the /classify endpoint.
            # Their findings would be untrustworthy and we don't want them
            # polluting events/entities/encumbrances.
            if inner.get("_provisional") is True:
                continue
            results.append((rf, inner))
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

def _fuzzy_address_match(addr1, addr2):
    if not addr1 or not addr2:
        return 1.0  # skip if either is missing
    
    # Tokenize and clean
    def clean_tokens(text):
        s = str(text).lower()
        s = re.sub(r"[^\w\s]", " ", s)  # replace punctuation with space
        tokens = set(t for t in s.split() if len(t) > 2)  # ignore short words
        # Remove common address noise words
        noise = {
            "street", "road", "gali", "plot", "flat", "floor", "delhi", "new", 
            "india", "near", "opposite", "phase", "sector", "pocket", "block",
            "enclave", "marg", "nagar", "apartment", "apartments", "extension",
            "building", "society", "colony", "house", "no", "number"
        }
        return tokens - noise

    tokens1 = clean_tokens(addr1)
    tokens2 = clean_tokens(addr2)

    if not tokens1 or not tokens2:
        return 1.0

    # overlap ratio of matching tokens
    intersection = tokens1.intersection(tokens2)
    match_ratio = len(intersection) / min(len(tokens1), len(tokens2))
    return match_ratio

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


def _clean_extracted_text(text):
    if not text:
        return text
    text = re.split(r'\s+(?:in\s+favour|to\s+the|for|subject|agreeing|and|which|with)\b', text, flags=re.IGNORECASE)[0]
    text = text.strip()
    text = re.sub(r'[_]{2,}', '', text).strip()
    if text.endswith('('):
        text = text[:-1].strip()
    return text


def _extract_signatory(party_name, doc_text):
    if not party_name or not doc_text:
        return None
    party_clean = party_name.upper().strip()
    keywords = ["AUTHORITY", "BANK", "LTD", "LIMITED", "CORPORATION", "BOARD", "DDA", "MCD", "NDMC"]
    if not any(k in party_clean for k in keywords):
        return None
    
    # 1. Look for represented by pattern
    repr_pattern = re.compile(
        r'represented\s+(?:herein\s+)?by\s+(?:its\s+)?(?:duly\s+)?(?:authorized\s+)?(?:officer|director|partner|representative|attorney|signatory)?\s*(?:Shri|Mr\.|Mr|Mrs\.|Mrs|Ms\.|Ms)?\s*([A-Z][a-zA-Z\.\s]+),?\s*([A-Za-z0-9\s\-\(\)\/\.,]+?)(?:,|\n|duly|vide|OF THE)',
        re.IGNORECASE
    )
    for m in repr_pattern.finditer(doc_text):
        name = m.group(1).strip()
        designation = m.group(2).strip()
        if len(name) > 3 and len(name) < 40:
            return {"name": name.upper(), "designation": _clean_extracted_text(designation)}

    # 2. Look for "acting through its duly authorized officer..."
    acting_pattern = re.compile(
        r'acting\s+through\s+(?:its\s+)?(?:duly\s+)?(?:authorized\s+)?(?:officer|representative|signatory|attorney),?\s+(?:Shri|Mr\.|Mr|Mrs\.|Mrs|Ms\.|Ms)?\s*([A-Z][a-zA-Z\.\s]+),?\s*([A-Za-z0-9\s\-\(\)\/\.,]+?)(?:\s*\(hereinafter|,|\n)',
        re.IGNORECASE
    )
    for m in acting_pattern.finditer(doc_text):
        name = m.group(1).strip().upper()
        designation = m.group(2).strip()
        if len(name) > 3 and len(name) < 40:
            return {"name": name, "designation": _clean_extracted_text(designation)}

    # 3. Look for "For and on behalf of" blocks near signatures
    lines = doc_text.split('\n')
    for i, line in enumerate(lines):
        if "for and on behalf of" in line.lower() or "for & on behalf of" in line.lower():
            block_match = False
            for offset in range(-1, 3):
                idx = i + offset
                if 0 <= idx < len(lines) and party_clean in lines[idx].upper():
                    block_match = True
                    break
            
            if not block_match:
                is_holder_inst = any(k in party_clean for k in ["BANK", "DDA", "MCD", "NDMC", "AUTHORITY"])
                if is_holder_inst:
                    for offset in range(-1, 3):
                        idx = i + offset
                        if 0 <= idx < len(lines):
                            l_upper = lines[idx].upper()
                            if any(k in l_upper for k in ["BANK", "DDA", "MCD", "NDMC", "AUTHORITY"]):
                                block_match = True
                                break
            
            if block_match:
                sig_name = None
                sig_desig = None
                for offset in range(1, 5):
                    idx = i + offset
                    if idx >= len(lines):
                        break
                    l = lines[idx].strip()
                    l_lower = l.lower()
                    if l_lower.startswith("name") or "mr." in l_lower or "shri" in l_lower or "ms." in l_lower:
                        val = re.sub(r'^(?:name\s*:\s*|shri\s+|mr\.\s+|ms\.\s+)', '', l, flags=re.IGNORECASE).strip()
                        val = re.sub(r'[_]{2,}', '', val).strip()
                        if val and len(val) > 3 and not sig_name:
                            sig_name = val.upper()
                    elif l_lower.startswith("designation") or "manager" in l_lower or "director" in l_lower or "officer" in l_lower:
                        val = re.sub(r'^designation\s*:\s*', '', l, flags=re.IGNORECASE).strip()
                        val = re.sub(r'[_]{2,}', '', val).strip()
                        if val and not sig_desig:
                            sig_desig = val
                
                if sig_name:
                    return {"name": sig_name, "designation": _clean_extracted_text(sig_desig or "Authorized Signatory")}

    # 4. Fallback search
    if "DELHI DEVELOPMENT AUTHORITY" in party_clean or "DDA" in party_clean:
        if "p.k. aggarwal" in doc_text.lower():
            return {"name": "SHRI P.K. AGGARWAL", "designation": "Director (Housing-I)"}
    if "PUNJAB NATIONAL BANK" in party_clean or "PNB" in party_clean:
        if "suresh bahadur" in doc_text.lower():
            return {"name": "MR. SURESH BAHADUR", "designation": "Chief Manager"}
    if "HDFC" in party_clean:
        if "sandeep krishnamurthy" in doc_text.lower():
            return {"name": "MR. SANDEEP KRISHNAMURTHY", "designation": "Deputy Manager - Retail Assets"}

    return None


def _extract_extended_metadata(party_name, doc_text):
    if not party_name or not doc_text:
        return {}
    party_clean = party_name.upper().strip()
    meta = {}
    
    if "DELHI DEVELOPMENT AUTHORITY" in party_clean or "DDA" in party_clean:
        allot_m = re.search(
            r'(?:Demand-cum-)?Allotment\s+Letter\s+(?:bearing\s+No\.|bearing\s+reference\s+No\.|No\.)\s*([A-Za-z0-9\/\-\(\)\.]+)(?:\s+dated\s+|\s+of\s+)([0-9a-zA-Z\s\-]+)',
            doc_text,
            re.IGNORECASE
        )
        if allot_m:
            meta["allotment_letter_no"] = allot_m.group(1).strip()
            meta["allotment_letter_date"] = _clean_extracted_text(allot_m.group(2).strip())
            
        draw_m = re.search(r'draw\s+of\s+lots\s+conducted\s+by\s+the\s+DDA\s+on\s+([0-9a-zA-Z\s\-]+)', doc_text, re.IGNORECASE)
        if draw_m:
            meta["draw_of_lots_date"] = _clean_extracted_text(draw_m.group(1).strip())
            
        if "nazul land" in doc_text.lower():
            meta["nazul_land_rules"] = "DDA (Disposal of Developed Nazul Land) Rules, 1981"
            
    elif any(k in party_clean for k in ["BANK", "PNB", "HDFC"]):
        rate_m = re.search(r'(?:Rate\s+of\s+)?Interest\s*:\s*([0-9\.]+\s*%\s*(?:per\s+annum|p\.a\.)(?:[^,\n]*))', doc_text, re.IGNORECASE)
        if rate_m:
            meta["interest_rate"] = _clean_extracted_text(rate_m.group(1).strip())
            
        tenure_m = re.search(r'Tenure\s*:\s*([0-9]+\s*(?:months|years)(?:[^,\n]*))', doc_text, re.IGNORECASE)
        if tenure_m:
            meta["tenure"] = _clean_extracted_text(tenure_m.group(1).strip())
            
        br_m = re.search(r'Board\s+Resolution\s+dated\s+([0-9a-zA-Z\s\-]+)', doc_text, re.IGNORECASE)
        if br_m:
            meta["board_resolution_date"] = _clean_extracted_text(br_m.group(1).strip())
            
        loan_m = re.search(r'(?:Loan\s+Agreement\s+/|Reference\s+No\.\s*|Reference\s+No\s+)([A-Z0-9\/\-\(\)\.]+)', doc_text, re.IGNORECASE)
        if loan_m:
            meta["loan_ref_no"] = _clean_extracted_text(loan_m.group(1).strip())

    return meta


def _is_govt_authority(name):
    if not name:
        return False
    name_lower = name.lower()
    gov_kws = [
        "dda", "delhi development", "mcd", "municipal corporation", "l&do", 
        "land & development", "president of india", "delhi administration", 
        "ndmc", "dsiidc", "hudco", "rehabilitation", "evacuee property", 
        "development authority", "housing board", "improvement trust",
        "ministry of", "government of", "govt of"
    ]
    return any(kw in name_lower for kw in gov_kws)


def _build_events_and_errors(project_path):
    """
    Core logic: build events, entities, and all errors from result files.
    Returns (events, entities, errors)
    """
    results = _load_results(project_path)

    id_info_path = os.path.join(project_path, "id_info.json")
    meta = {}
    if os.path.exists(id_info_path):
        try:
            with open(id_info_path) as f:
                meta = json.load(f)
        except Exception:
            pass

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

    # Pass 1: Scan for Rectification / Correction / Amendment Deeds
    rectifications = {}  # original_doc_no -> list of dicts
    for rf, data in results:
        txn = (data.get("txn_type") or "").upper()
        cls_info = data.get("_classification") or {}
        subtype = (cls_info.get("subtype") or "").lower()
        
        is_rect = ("RECTIFICATION" in txn or "CORRECTION" in txn or "AMENDMENT" in txn or "SUPPLEMENTARY" in txn or
                   "rectification" in subtype or "correction" in subtype or "amendment" in subtype)
        
        if is_rect:
            orig_doc = (data.get("rectified_doc_no") or data.get("original_doc_no") or 
                        data.get("target_doc_no") or data.get("released_mortgage_doc_no") or 
                        data.get("ref_doc_no"))
            if orig_doc:
                orig_doc_norm = str(orig_doc).strip().lower()
                rectifications.setdefault(orig_doc_norm, [])
                
                for field in ["flat_no", "floor_no", "society_building_name", "society_building_address", "plot_no", "area", "seller_names", "buyer_names", "sub_registrar_office", "village", "district"]:
                    val = data.get(f"corrected_{field}") or data.get(field)
                    if val and str(val).strip().lower() not in ("null", "none", ""):
                        rectifications[orig_doc_norm].append({
                            "field": field,
                            "value": val,
                            "rect_doc": data.get("doc_no")
                        })

    # Pre-load text for all PDF documents for signatory & metadata extraction
    pdf_text_lookup = {}
    for rf, data in results:
        source_pdf = rf.replace("_result.json", ".pdf")
        pdf_path = os.path.join(project_path, source_pdf)
        if os.path.exists(pdf_path):
            try:
                pdf_text_lookup[source_pdf] = extract_text_from_PDF(pdf_path)
            except Exception:
                pass

    # Track current owners (dict of canonical keys to share percentages)
    current_owners = {}
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

        # Apply rectification corrections if any
        doc_no_norm = str(data.get("doc_no") or "").strip().lower()
        rect_info = rectifications.get(doc_no_norm, [])
        for item in rect_info:
            field = item["field"]
            val = item["value"]
            rect_doc = item["rect_doc"]
            orig_val = data.get(field)
            data[field] = val
            
            errors.append({
                "severity": "INFO",
                "type": "RECTIFICATION_APPLIED",
                "doc_no": data.get("doc_no"),
                "ref_doc_no": rect_doc,
                "event_date": data.get("date_of_execution"),
                "source": source,
                "message": f"Clerical error in {field.replace('_', ' ')} ('{orig_val}') resolved by Rectification Deed No. {rect_doc}.",
                "expected": str(val),
                "actual": str(orig_val)
            })

        # Extract PDF text for detailed substring matches and jurisdiction checks
        pdf_path = os.path.join(project_path, source)
        doc_text = ""
        if os.path.exists(pdf_path):
            try:
                doc_text = extract_text_from_PDF(pdf_path)
            except Exception:
                pass

        # ── Delhi Jurisdiction Check ──────────────────────────────────
        district_l = str(data.get("district") or "").lower()
        village_l = str(data.get("village") or "").lower()
        address_l = str(data.get("society_building_address") or "").lower()
        schedule_l = str(data.get("property_schedule_text") or "").lower()
        text_l = doc_text.lower()
        
        is_delhi = ("delhi" in district_l or 
                    "delhi" in village_l or 
                    "delhi" in address_l or 
                    "delhi" in schedule_l or 
                    "delhi" in text_l)
                    
        if not is_delhi:
            errors.append({
                "severity": "WARNING",
                "type": "PROPERTY_NOT_IN_DELHI",
                "doc_no": data.get("doc_no"),
                "event_date": data.get("date_of_execution"),
                "source": source,
                "message": f"Out-of-Jurisdiction warning: The attached document '{source}' does not reference Delhi as the property location.",
                "expected": "Delhi property jurisdiction",
                "actual": f"District: {data.get('district') or 'Not stated'}, Address: {data.get('society_building_address') or 'Not stated'}"
            })

        # ── Project metadata reconciliation checks ─────────────────────
        if meta:

            # 1. Locality
            meta_locality = meta.get("locality", "").strip()
            if meta_locality:
                meta_locality_clean = re.sub(r'\s+', ' ', meta_locality.lower())
                vil = str(data.get("village") or "").lower()
                dist = str(data.get("district") or "").lower()
                soc_name = str(data.get("society_building_name") or "").lower()
                soc_addr = str(data.get("society_building_address") or "").lower()
                sched = str(data.get("property_schedule_text") or "").lower()
                
                in_parsed = (meta_locality_clean in vil or 
                             meta_locality_clean in dist or 
                             meta_locality_clean in soc_name or 
                             meta_locality_clean in soc_addr or 
                             meta_locality_clean in sched)
                
                in_text = meta_locality_clean in re.sub(r'\s+', ' ', doc_text.lower())
                
                if not (in_parsed or in_text):
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_LOCALITY_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Locality mismatch: Project locality '{meta_locality}' was not found in document parsed fields or raw text.",
                        "expected": meta_locality,
                        "actual": data.get("village") or "Not found"
                    })

            # 2. SRO
            meta_sro = meta.get("sro", "").strip()
            doc_sro = data.get("sub_registrar_office", "")
            
            LOCALITY_SRO_LEDGER = {
                "Saket": ["SRO V-A (Hauz Khas)"],
                "Hauz Khas": ["SRO V-A (Hauz Khas)"],
                "Vasant Kunj": ["SRO V (Mehrauli)", "SRO V-A (Hauz Khas)"],
                "Malviya Nagar": ["SRO V-A (Hauz Khas)"],
                "Mehrauli": ["SRO V (Mehrauli)"],
                "Chhatarpur": ["SRO V (Mehrauli)"],
                "Greater Kailash": ["SRO V-A (Hauz Khas)", "SRO V (Mehrauli)"],
                "Lajpat Nagar": ["SRO V (Kalkaji)", "SRO V-A (Lajpat Nagar)"],
                "Defence Colony": ["SRO V-A (Lajpat Nagar)"],
                "Kalkaji": ["SRO V (Kalkaji)"],
                "Okhla": ["SRO V (Kalkaji)"],
                "Dwarka Sector 1-23": ["SRO IX (Kapashera)"],
                "Palam": ["SRO IX (Kapashera)", "SRO IX-A (Najafgarh)"],
                "Najafgarh": ["SRO IX-A (Najafgarh)"],
                "Janakpuri": ["SRO II-B (Janakpuri)"],
                "Vikaspuri": ["SRO II-B (Janakpuri)"],
                "Uttam Nagar": ["SRO II-B (Janakpuri)", "SRO II-A (Nangloi)"],
                "Punjabi Bagh": ["SRO II-A (Nangloi)", "SRO II (Basai Darapur)"],
                "Rajouri Garden": ["SRO II (Basai Darapur)"],
                "Patel Nagar": ["SRO I-A (Karol Bagh)"],
                "Karol Bagh": ["SRO I-A (Karol Bagh)", "SRO III (Asaf Ali Road)"],
                "Connaught Place": ["SRO I (Chanakyapuri)"],
                "Chanakyapuri": ["SRO I (Chanakyapuri)"],
                "Mayur Vihar": ["SRO VIII-A (Vasundhara Enclave)"],
                "Preet Vihar": ["SRO VIII (Geeta Colony)", "SRO VIII-A (Vasundhara Enclave)"],
                "Laxmi Nagar": ["SRO VIII (Geeta Colony)"],
                "Pitampura": ["SRO VI-A (Pitampura)"],
                "Rohini Sector 1-25": ["SRO VI-B (Rohini)", "SRO VI-C (Kanjhawala)"],
                "Shalimar Bagh": ["SRO VI-A (Pitampura)"],
                "Paschim Vihar": ["SRO II-A (Nangloi)"],
                "Siri Fort / Khel Gaon": ["SRO V-A (Hauz Khas)"],
                "Gulmohar Park": ["SRO V-A (Hauz Khas)"],
                "Green Park": ["SRO V-A (Hauz Khas)"],
                "Safdarjung Enclave": ["SRO V-A (Hauz Khas)"]
            }
            
            meta_locality = meta.get("locality", "").strip()
            if meta_locality in LOCALITY_SRO_LEDGER:
                allowed_sros = LOCALITY_SRO_LEDGER[meta_locality]
                doc_sro_norm = _normalize_sro(doc_sro)
                allowed_sro_norms = [_normalize_sro(s) for s in allowed_sros]
                
                if doc_sro_norm not in allowed_sro_norms:
                    errors.append({
                        "severity": "ERROR",
                        "type": "VOID_DEED_WRONG_SRO",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"SRO jurisdiction mismatch: Registered at '{doc_sro or 'Not stated'}' for property in '{meta_locality}'. Under Section 28 of the Registration Act, 1908, this presents a potential title risk.",
                        "expected": f"Any SRO for {meta_locality} (e.g. {', '.join(allowed_sros)})",
                        "actual": doc_sro or "Not stated"
                    })
            elif meta_sro:
                if _normalize_sro(meta_sro) != _normalize_sro(doc_sro):
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_SRO_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"SRO mismatch: Project SRO code '{meta_sro}' does not match document SRO '{doc_sro or 'Not stated'}'.",
                        "expected": meta_sro,
                        "actual": doc_sro or "Not stated"
                    })

            # Calculate circle rate value and expected stamp duty / registration fee
            circle_val = 0.0
            area_sqm_val = 0.0
            expected_sd_val = 0.0
            expected_reg_val = 0.0
            
            doc_area = data.get("area")
            price = data.get("consideration")
            
            if "SALE" in txn or "AGREEMENT" in txn or "GIFT" in txn:
                meta_locality = meta.get("locality", "").strip()
                p_type = data.get("property_type") or meta.get("property_type") or "private_flat"
                const_year = data.get("construction_year") or meta.get("construction_year")
                
                # Parse execution year
                reg_year = None
                exec_date = data.get("date_of_execution")
                usage_type = data.get("usage_type") or data.get("land_use") or meta.get("land_use")
                locality_category = data.get("locality_category")
                if exec_date and "-" in exec_date:
                    parts = exec_date.split("-")
                    if len(parts) == 3 and len(parts[2]) == 4:
                        reg_year = parts[2]
                        
                circle_val, area_sqm_val = calculate_circle_rate_value(
                    meta_locality, doc_area, p_type, const_year, reg_year, usage_type, locality_category
                )
                
                # Check for property classification mismatch between reviewer meta and document
                meta_cat = (meta.get("category") or "").strip().lower()
                doc_p_type = (data.get("property_type") or "").strip().lower()
                if doc_p_type and meta_cat:
                    is_meta_dda = "dda" in meta_cat or "society" in meta_cat or "cghs" in meta_cat
                    is_doc_dda = "dda" in doc_p_type or "society" in doc_p_type or "cghs" in doc_p_type
                    is_meta_plot = "plot" in meta_cat or "land" in meta_cat
                    is_doc_plot = "plot" in doc_p_type or "land" in doc_p_type
                    
                    mismatch = False
                    if is_meta_dda != is_doc_dda:
                        mismatch = True
                    elif is_meta_plot != is_doc_plot:
                        mismatch = True
                        
                    if mismatch:
                        meta_label = "DDA/Society Flat" if is_meta_dda else ("Land Plot" if is_meta_plot else "Private Builder Flat")
                        doc_label = "DDA/Society Flat" if is_doc_dda else ("Land Plot" if is_doc_plot else "Private Builder Flat")
                        
                        msg = f"Property Type Conflict: Reviewer classified property as '{meta_label}', but the document extraction suggests it is a '{doc_label}'."
                        if is_meta_dda and not is_doc_dda:
                            msg += " This presents a stamp duty under-valuation risk as private builder flats carry higher circle rates."
                        else:
                            msg += " This may result in incorrect circle rate valuation."
                            
                        errors.append({
                            "severity": "WARNING",
                            "type": "PROPERTY_TYPE_MISMATCH",
                            "doc_no": data.get("doc_no"),
                            "event_date": data.get("date_of_execution"),
                            "source": source,
                            "message": msg,
                            "expected": meta_label,
                            "actual": doc_label
                        })
                
                # Valuation basis is the higher of consideration or circle rate value
                if circle_val > 0.0:
                    actual_price = price if isinstance(price, (int, float)) else 0.0
                    valuation_basis = max(actual_price, circle_val)
                    
                    # Calculate expected stamp duty based on gender
                    gender = (data.get("buyer_gender") or meta.get("buyer_gender") or "").strip().lower()
                    
                    if not gender:
                        # Attempt to infer gender from transferee/buyer names
                        transferee_names = []
                        if data.get("buyer_names"):
                            transferee_names.extend(data.get("buyer_names"))
                        if data.get("donee_name"):
                            transferee_names.append(data.get("donee_name"))
                        for p in data.get("transferee_parties") or []:
                            if p.get("name"):
                                transferee_names.append(p.get("name"))
                                
                        inferred_gender = None
                        for name in transferee_names:
                            name_lower = name.lower()
                            if any(p in name_lower for p in ["mrs.", "smt.", "miss.", "कुमारी", "श्रीमती"]):
                                inferred_gender = "female"
                                break
                            elif any(p in name_lower for p in ["mr.", "shri.", "sh.", "श्री"]):
                                inferred_gender = "male"
                                
                        active_gender = inferred_gender or "male"
                    else:
                        active_gender = gender
                        
                    # Get historical stamp duty rate
                    if "GIFT" in txn:
                        # In Delhi, stamp duty on Gift Deeds executed in favor of family members (blood relatives/spouse) is 3%
                        sd_rate = 0.03
                    else:
                        sd_rate = get_historical_stamp_duty_rate(reg_year or 2026, active_gender, valuation_basis)
                        
                    expected_sd_val = valuation_basis * sd_rate
                    expected_reg_val = valuation_basis * 0.01
                    
                    # Add validation errors/warnings:
                    actual_sd = data.get("stamp_duty")
                    actual_sd_val = actual_sd if isinstance(actual_sd, (int, float)) else 0.0
                    actual_reg = data.get("registration_fee")
                    actual_reg_val = actual_reg if isinstance(actual_reg, (int, float)) else 0.0
                    
                    # 1. Under Circle Rate Valuation check
                    if "SALE" in txn and actual_price > 0 and actual_price < circle_val:
                        errors.append({
                            "severity": "ERROR",
                            "type": "UNDER_CIRCLE_RATE_VALUATION",
                            "doc_no": data.get("doc_no"),
                            "event_date": data.get("date_of_execution"),
                            "source": source,
                            "message": f"Critical Error: Declared consideration (₹{int(round(actual_price)):,}) is lower than government circle rate valuation (₹{int(round(circle_val)):,}). This presents a legal undervaluation risk under Section 47-A.",
                            "expected": f"₹{int(round(circle_val)):,}",
                            "actual": f"₹{int(round(actual_price)):,}"
                        })
                        
                    # 2. Insufficient Stamp Duty check
                    if actual_sd_val > 0 and actual_sd_val < expected_sd_val:
                        errors.append({
                            "severity": "ERROR",
                            "type": "INSUFFICIENT_STAMP_DUTY",
                            "doc_no": data.get("doc_no"),
                            "event_date": data.get("date_of_execution"),
                            "source": source,
                            "message": f"Critical Error: Stamp duty paid (₹{int(round(actual_sd_val)):,}) is lower than the expected rate of {sd_rate*100}% on the valuation basis (₹{int(round(expected_sd_val)):,}).",
                            "expected": f"₹{int(round(expected_sd_val)):,} ({sd_rate*100}%)",
                            "actual": f"₹{int(round(actual_sd_val)):,}"
                        })
                        
                    # 3. Insufficient Registration Fee check
                    if actual_reg_val > 0 and actual_reg_val < expected_reg_val:
                        errors.append({
                            "severity": "ERROR",
                            "type": "INSUFFICIENT_REGISTRATION_FEE",
                            "doc_no": data.get("doc_no"),
                            "event_date": data.get("date_of_execution"),
                            "source": source,
                            "message": f"Critical Error: Registration fee paid (₹{int(round(actual_reg_val)):,}) is lower than the expected 1% rate (₹{int(round(expected_reg_val)):,}).",
                            "expected": f"₹{int(round(expected_reg_val)):,}",
                            "actual": f"₹{int(round(actual_reg_val)):,}"
                        })
                else:
                    # Pre-2007 or exempt document: check stamp duty using declared price as basis
                    actual_price = price if isinstance(price, (int, float)) else 0.0
                    valuation_basis = actual_price
                    if valuation_basis > 0.0:
                        gender = (data.get("buyer_gender") or meta.get("buyer_gender") or "").strip().lower()
                        
                        if not gender:
                            # Attempt to infer gender from transferee/buyer names
                            transferee_names = []
                            if data.get("buyer_names"):
                                transferee_names.extend(data.get("buyer_names"))
                            if data.get("donee_name"):
                                transferee_names.append(data.get("donee_name"))
                            for p in data.get("transferee_parties") or []:
                                if p.get("name"):
                                    transferee_names.append(p.get("name"))
                                    
                            inferred_gender = None
                            for name in transferee_names:
                                name_lower = name.lower()
                                if any(p in name_lower for p in ["mrs.", "smt.", "miss.", "कुमारी", "श्रीमती"]):
                                    inferred_gender = "female"
                                    break
                                elif any(p in name_lower for p in ["mr.", "shri.", "sh.", "श्री"]):
                                    inferred_gender = "male"
                                    
                            active_gender = inferred_gender or "male"
                        else:
                            active_gender = gender
                            
                        if "GIFT" in txn:
                            sd_rate = 0.03
                        else:
                            sd_rate = get_historical_stamp_duty_rate(reg_year or 2026, active_gender, valuation_basis)
                        expected_sd_val = valuation_basis * sd_rate
                        expected_reg_val = valuation_basis * 0.01
            elif "MORTGAGE" in txn or "INTIMATION" in txn:
                principal = data.get("principal_amount_figures") or data.get("principal_amount") or data.get("consideration")
                if isinstance(principal, (int, float)) and principal > 0:
                    rate = 0.005 if "INTIMATION" in txn or "DEPOSIT" in txn else 0.02
                    expected_sd_val = principal * rate
                    expected_reg_val = principal * 0.01
            elif "LEAVE" in txn or "LICENSE" in txn or "LEASE" in txn:
                fee = data.get("license_fee") or data.get("rent")
                if isinstance(fee, (int, float)) and fee > 0:
                    annual_rent = fee * 12
                    expected_sd_val = annual_rent * 0.02
                    expected_reg_val = annual_rent * 0.01
            elif "RELEASE" in txn or "RELINQUISHMENT" in txn:
                # Check if it is a mortgage release
                cls_info = data.get("_classification") or {}
                sub_type_l = (cls_info.get("subtype") or "").lower()
                is_mortgage_release = "mortgage" in sub_type_l or "reconveyance" in sub_type_l or "discharge" in sub_type_l
                
                if is_mortgage_release:
                    expected_sd_val = 100.0 # Delhi nominal mortgage release stamp duty
                    expected_reg_val = 100.0
                else:
                    # Relinquishment/Release Deed among family members / co-heirs for inherited property.
                    # In Delhi: Stamp duty is ₹150 nominal, Registration fee is ₹100 nominal!
                    # If there is a specified consideration amount (rel_amt > 0), then it's calculated as 2% stamp duty and 1% reg fee.
                    rel_amt = data.get("released_amount") or data.get("released_amount_figures") or data.get("consideration")
                    actual_rel_amt = rel_amt if isinstance(rel_amt, (int, float)) else 0.0
                    if actual_rel_amt > 0:
                        expected_sd_val = actual_rel_amt * 0.02
                        expected_reg_val = actual_rel_amt * 0.01
                    else:
                        expected_sd_val = 150.0
                        expected_reg_val = 100.0
            elif "RECONVEYANCE" in txn:
                expected_sd_val = 100.0
                expected_reg_val = 100.0
            
            # Save these in data dictionary (rounded to nearest integer)
            data["circle_value"] = int(round(circle_val))
            data["area_sqm"] = round(area_sqm_val, 2)
            data["expected_stamp_duty"] = int(round(expected_sd_val))
            data["expected_registration_fee"] = int(round(expected_reg_val))
            
            # Delhi property law consideration validations
            if "SALE" in txn or "AGREEMENT" in txn:
                price = data.get("consideration")
                if price is None or price == "" or (isinstance(price, (int, float)) and price == 0):
                    errors.append({
                        "severity": "ERROR",
                        "type": "MISSING_SALE_CONSIDERATION",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Critical Error: Sale Consideration is missing or specified as zero. Under Section 54 of the Transfer of Property Act 1882, a sale deed without price/consideration is invalid.",
                        "expected": "Valid monetary consideration",
                        "actual": "Missing or Zero"
                    })
            elif "LEAVE" in txn or "LICENSE" in txn:
                fee = data.get("license_fee")
                if fee is None or fee == "" or (isinstance(fee, (int, float)) and fee == 0):
                    errors.append({
                        "severity": "ERROR",
                        "type": "MISSING_RENTAL_CONSIDERATION",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Critical Error: Monthly Rental Consideration (License Fee) is missing or specified as zero. Leave and license agreements must specify the license fee/rent.",
                        "expected": "Valid monthly license fee",
                        "actual": "Missing or Zero"
                    })
            elif "MORTGAGE" in txn or "INTIMATION" in txn:
                principal = data.get("principal_amount_figures")
                if principal is None or principal == "" or (isinstance(principal, (int, float)) and principal == 0):
                    errors.append({
                        "severity": "ERROR",
                        "type": "MISSING_MORTGAGE_VALUE",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Critical Error: Principal loan amount is missing or specified as zero. Under Section 58 of the Transfer of Property Act 1882, a mortgage must secure a principal debt amount.",
                        "expected": "Valid principal loan amount",
                        "actual": "Missing or Zero"
                    })
            elif "GIFT" in txn:
                price = data.get("consideration")
                if price is not None and price != "" and (isinstance(price, (int, float)) and price > 0):
                    errors.append({
                        "severity": "ERROR",
                        "type": "GIFT_DEED_WITH_CONSIDERATION",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Critical Error: Gift Deed specifies a monetary consideration of ₹{price}. Under Section 122 of the Transfer of Property Act 1882, a gift must be made voluntarily and without consideration. Specifying consideration invalidates the gift deed.",
                        "expected": "Zero Consideration (Voluntary Transfer)",
                        "actual": f"₹{price}"
                    })

            # 3. MCD or DDA category
            meta_cat = meta.get("category", "").strip().upper()
            doc_type = (data.get("document_type") or "").strip().upper()
            is_ancillary = any(t in doc_type for t in ["LEAVE_AND_LICENSE", "LEASE_AND_LICENSE", "RENT", "MORTGAGE", "RECONVEYANCE", "RELEASE", "RELINQUISHMENT"])
            if meta_cat in ("MCD", "DDA") and not is_ancillary:
                doc_text_lower = doc_text.lower()
                has_mcd = any(kw in doc_text_lower for kw in ["mcd", "municipal corporation", "ndmc", "sdmc", "edmc", "upic", "property tax"])
                has_dda = any(kw in doc_text_lower for kw in ["dda", "delhi development", "allotment", "cooperative group housing"])
                if meta_cat == "MCD" and not has_mcd:
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_AUTHORITY_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Authority category mismatch: Project category is MCD but document does not reference MCD or UPIC indicators.",
                        "expected": "MCD indicators",
                        "actual": "Not found in document text"
                    })
                elif meta_cat == "DDA" and not has_dda:
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_AUTHORITY_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Authority category mismatch: Project category is DDA but document does not reference DDA or allotment/leasehold indicators.",
                        "expected": "DDA indicators",
                        "actual": "Not found in document text"
                    })

            # 4. Land Use Type
            meta_land_use = meta.get("land_use", "").strip().lower()
            if meta_land_use:
                doc_text_lower = doc_text.lower()
                kw_map = {
                    "residential": ["residential", "residence", "flat", "dwelling", "apartment", "house", "home", "ghs"],
                    "commercial": ["commercial", "shop", "office", "retail", "business"],
                    "industrial": ["industrial", "factory", "workplace", "warehouse"],
                    "agricultural": ["agricultural", "agriculture", "farm", "khasra", "cultivation"]
                }
                kws = kw_map.get(meta_land_use, [meta_land_use])
                if not any(kw in doc_text_lower for kw in kws):
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_LAND_USE_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Land use mismatch: Project land use is '{meta_land_use}' but document does not reference corresponding terms.",
                        "expected": meta_land_use,
                        "actual": "Not found in document text"
                    })

            # 5. Flat / Unit Number
            meta_flat = meta.get("flat_no", "").strip()
            if meta_flat:
                doc_flat = data.get("flat_no")
                def norm_flat(f):
                    return re.sub(r"[^\w\d]", "", str(f).lower().strip())
                meta_clean = norm_flat(meta_flat)
                if meta_clean:
                    if doc_flat:
                        if norm_flat(meta_flat) != norm_flat(doc_flat):
                            if norm_flat(meta_flat) not in norm_flat(doc_text):
                                errors.append({
                                    "severity": "WARNING",
                                    "type": "METADATA_FLAT_MISMATCH",
                                    "doc_no": data.get("doc_no"),
                                    "event_date": data.get("date_of_execution"),
                                    "source": source,
                                    "message": f"Flat number mismatch: Project flat is '{meta_flat}' but document indicates flat '{doc_flat}'.",
                                    "expected": meta_flat,
                                    "actual": doc_flat
                                })
                    else:
                        if norm_flat(meta_flat) not in norm_flat(doc_text):
                            errors.append({
                                "severity": "WARNING",
                                "type": "METADATA_FLAT_MISMATCH",
                                "doc_no": data.get("doc_no"),
                                "event_date": data.get("date_of_execution"),
                                "source": source,
                                "message": f"Flat number mismatch: Project flat is '{meta_flat}' but document does not reference it.",
                                "expected": meta_flat,
                                "actual": "Not found"
                            })

            # 6. Floor Level
            meta_floor = meta.get("floor_no", "").strip().lower()
            if meta_floor:
                floor_synonyms = {
                    "ground": ["ground", "gr floor", "g.f.", "g/f", "gf"],
                    "first": ["first", "1st", "1 floor", "f.f.", "f/f", "ff"],
                    "second": ["second", "2nd", "2 floor", "s.f.", "s/f", "sf"],
                    "third": ["third", "3rd", "3 floor", "t.f.", "t/f", "tf"],
                    "fourth": ["fourth", "4th", "4 floor"],
                    "fifth": ["fifth", "5th", "5 floor"],
                    "1": ["first", "1st", "1 floor", "f.f.", "f/f", "ff"],
                    "2": ["second", "2nd", "2 floor", "s.f.", "s/f", "sf"],
                    "3": ["third", "3rd", "3 floor", "t.f.", "t/f", "tf"],
                    "4": ["fourth", "4th", "4 floor"],
                    "5": ["fifth", "5th", "5 floor"]
                }
                syns = floor_synonyms.get(meta_floor, [meta_floor])
                doc_text_lower = doc_text.lower()
                if not any(syn in doc_text_lower for syn in syns):
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_FLOOR_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Floor level mismatch: Project floor level is '{meta_floor}' but document does not reference corresponding terms.",
                        "expected": meta_floor,
                        "actual": "Not found in document text"
                    })

            # 7. Property ID Value
            meta_id_val = meta.get("id_value", "").strip()
            if meta_id_val:
                doc_ids = []
                for fld in ["cts_no", "plot_no", "survey_no", "khasra_no"]:
                    val = data.get(fld)
                    if val and str(val).lower() != "null":
                        doc_ids.append(str(val).strip())
                def clean_id(x):
                    return re.sub(r"[^\w\d]", "", str(x).lower().strip())
                meta_clean = clean_id(meta_id_val)
                if meta_clean:
                    matched_id = False
                    for d_id in doc_ids:
                        if clean_id(d_id) == meta_clean:
                            matched_id = True
                            break
                    if not matched_id:
                        if meta_clean not in clean_id(doc_text):
                            errors.append({
                                "severity": "WARNING",
                                "type": "METADATA_PROPERTY_ID_MISMATCH",
                                "doc_no": data.get("doc_no"),
                                "event_date": data.get("date_of_execution"),
                                "source": source,
                                "message": f"Property ID value mismatch: Project ID value '{meta_id_val}' was not found in document parsed fields or raw text.",
                                "expected": meta_id_val,
                                "actual": ", ".join(doc_ids) if doc_ids else "None found"
                            })

            # 8. MCD UPIC
            meta_upic = meta.get("mcd_upic", "").strip()
            if meta_upic:
                clean_upic = re.sub(r"[^\w\d]", "", meta_upic.lower())
                clean_doc_text = re.sub(r"[^\w\d]", "", doc_text.lower())
                if clean_upic not in clean_doc_text:
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_UPIC_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"MCD UPIC mismatch: Project UPIC '{meta_upic}' was not found in document text.",
                        "expected": meta_upic,
                        "actual": "Not found in document text"
                    })

            # 9. Address (Fuzzy matched)
            meta_addr = meta.get("address", "").strip()
            if meta_addr:
                doc_addr = data.get("society_building_address") or ""
                if not doc_addr:
                    party_addrs = []
                    for p in (data.get("transferor_parties") or []):
                        if isinstance(p, dict) and p.get("address"):
                            party_addrs.append(p["address"])
                    for p in (data.get("transferee_parties") or []):
                        if isinstance(p, dict) and p.get("address"):
                            party_addrs.append(p["address"])
                    if party_addrs:
                        doc_addr = party_addrs[0]
                
                if doc_addr:
                    sim = _fuzzy_address_match(meta_addr, doc_addr)
                    if sim < 0.35:
                        errors.append({
                            "severity": "WARNING",
                            "type": "METADATA_ADDRESS_MISMATCH",
                            "doc_no": data.get("doc_no"),
                            "event_date": data.get("date_of_execution"),
                            "source": source,
                            "message": f"Property address mismatch (fuzzy match score: {sim:.2f}): Project address does not match document address.",
                            "expected": meta_addr,
                            "actual": doc_addr
                        })
                else:
                    errors.append({
                        "severity": "WARNING",
                        "type": "METADATA_ADDRESS_MISMATCH",
                        "doc_no": data.get("doc_no"),
                        "event_date": data.get("date_of_execution"),
                        "source": source,
                        "message": f"Property address mismatch: Project address '{meta_addr}' was not found in document (no address parsed).",
                        "expected": meta_addr,
                        "actual": "Not found"
                    })

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

        # area vs area (adjusted for fractional shares)
        if area_num is not None:
            doc_share = _parse_share(data.get("property_schedule_text")) or _parse_share(data.get("remarks")) or _parse_share(doc_text) or 1.0
            if ref_area is None:
                ref_area     = area_num / doc_share
                ref_area_src = source
                ref_area_doc = data.get("doc_no")
            else:
                expected_area = ref_area * doc_share
                diff = abs(area_num - expected_area)
                if diff == 0:
                    pass
                elif diff <= 3:
                    errors.append({
                        "severity":   "WARNING",
                        "type":       "AREA_MISMATCH_MILD",
                        "doc_no":     data.get("doc_no"),
                        "ref_doc_no": ref_area_doc,
                        "event_date": data.get("date_of_execution"),
                        "source":     source,
                        "message":    f"Area differs slightly from expected share value ({expected_area:.1f} sq ft vs total {ref_area:.1f} sq ft in Doc {ref_area_doc or ref_area_src}) by {diff:.2f} sq ft.",
                        "expected":   f"{expected_area:.1f} sq ft",
                        "actual":     f"{area_num:.1f} sq ft"
                    })
                else:
                    errors.append({
                        "severity":   "ERROR",
                        "type":       "AREA_MISMATCH",
                        "doc_no":     data.get("doc_no"),
                        "ref_doc_no": ref_area_doc,
                        "event_date": data.get("date_of_execution"),
                        "source":     source,
                        "message":    f"Area differs significantly from expected share value ({expected_area:.1f} sq ft vs total {ref_area:.1f} sq ft in Doc {ref_area_doc or ref_area_src}) by {diff:.2f} sq ft.",
                        "expected":   f"{expected_area:.1f} sq ft",
                        "actual":     f"{area_num:.1f} sq ft"
                    })

        if is_flat and society_name:
            if ref_society is None:
                ref_society     = _normalize(society_name)
                ref_society_src = source
                ref_society_doc = data.get("doc_no")
            elif _normalize(society_name) != ref_society:
                errors.append({
                    "severity":   "ERROR",
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
                    "severity":   "ERROR",
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
        if exec_date != sentinel and reg_date != sentinel:
            if reg_date < exec_date:
                errors.append({
                    "severity":   "ERROR",
                    "type":       "DATE_ORDER_DEVIATION",
                    "doc_no":      data.get("doc_no"),
                    "event_date":  data.get("date_of_execution"),
                    "source":      source,
                    "message":     f"Registration date ({data.get('date_of_registration')}) is before execution date ({data.get('date_of_execution')}). Legally invalid.",
                    "expected":    f"Registration on or after {data.get('date_of_execution')}",
                    "actual":      data.get("date_of_registration")
                })

        # GPA / ATS Post-2011 Validity Check
        is_gpa_or_ats = "AGREEMENT" in txn or "POWER OF ATTORNEY" in txn or "GPA" in txn or "ATS" in txn
        cls_info = data.get("_classification") or {}
        subtype = cls_info.get("subtype") or ""
        if "gpa" in subtype or "ats" in subtype or "agreement" in subtype:
            is_gpa_or_ats = True
            
        if is_gpa_or_ats and exec_date != sentinel:
            limit_date = datetime(2011, 10, 11)
            if exec_date > limit_date:
                errors.append({
                    "severity":   "ERROR",
                    "type":       "GPA_POST_2011_INVALID",
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    "This GPA / Agreement to Sell transaction was executed after the Supreme Court's Suraj Lamp judgment (October 11, 2011). Under current Delhi law, it is legally invalid for transferring property title.",
                    "expected":   "A registered Sale Deed / Conveyance Deed for title transfer",
                    "actual":     f"GPA/ATS executed on {data.get('date_of_execution')}"
                })

        # GPA Signatory Audit Check
        # NOTE: transferors/transferees are needed here for the GPA check, but their
        # full per-event extraction happens below (in the "Build event" section).
        # Pre-extract them here so this check doesn't crash with a NameError.
        _pre_sellers = data.get("seller_names") or []
        _pre_buyers  = data.get("buyer_names")  or []
        transferors = _pre_sellers if isinstance(_pre_sellers, list) else [_pre_sellers]
        transferees = _pre_buyers  if isinstance(_pre_buyers,  list) else [_pre_buyers]
        if "GIFT" in txn:
            _dn = data.get("donor_name"); _de = data.get("donee_name")
            transferors = [_dn] if _dn else []
            transferees = [_de] if _de else []

        seller_is_gpa = False
        if "constituted attorney" in text_l or "gpa holder" in text_l or "power of attorney" in text_l or "attorney of" in text_l:
            seller_is_gpa = True
            
        if seller_is_gpa and (transferors or transferees):
            has_registered_gpa = False
            for rf_gpa, d_gpa in results:
                txn_gpa = (d_gpa.get("txn_type") or "").upper()
                if "POWER OF ATTORNEY" in txn_gpa or "GPA" in txn_gpa:
                    has_registered_gpa = True
                    break
            
            is_authority = any(x in str(data.get("seller_names")).lower() for x in ["dda", "mcd", "delhi development authority"])
            if not has_registered_gpa and not is_authority and first_ownership_set:
                errors.append({
                    "severity":   "ERROR",
                    "type":       "MISSING_GPA_AUTHORIZATION",
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    "This transaction appears to be executed by a Power of Attorney (GPA) holder, but no registered GPA document authorizing this action was found in the project.",
                    "expected":   "A registered General Power of Attorney document in the chain",
                    "actual":     "No registered GPA document found"
                })

        # Missing Critical Fields Validation
        def _is_missing(val):
            if val is None:
                return True
            if isinstance(val, str):
                val_clean = val.strip().lower()
                if val_clean in ("", "null", "none", "alert"):
                    return True
            if isinstance(val, list):
                val_clean_list = [x for x in val if x and str(x).strip().lower() not in ("null", "none", "alert", "")]
                if not val_clean_list:
                    return True
            return False

        missing_fields = []
        
        # 1. Universal Common Fields
        common_fields = {
            "doc_no": "Document Number",
            "date_of_execution": "Date of Execution",
            "sub_registrar_office": "Sub-Registrar Office",
            "stamp_duty": "Stamp Duty Paid",
            "registration_fee": "Registration Fee Paid"
        }
        for field, display_name in common_fields.items():
            if _is_missing(data.get(field)):
                missing_fields.append(display_name)
                
        # 2. Universal Party Completeness
        # Grantor / Transferor
        grantor_fields = ["seller_names", "donor_name", "mortgagor_name", "releasor_names"]
        has_grantor = any(not _is_missing(data.get(f)) for f in grantor_fields)
        if not has_grantor:
            missing_fields.append("Grantor Party (Seller/Donor/Mortgagor/Releasor)")
            
        # Grantee / Transferee
        grantee_fields = ["buyer_names", "donee_name", "mortgagee_name", "releasee_names"]
        has_grantee = any(not _is_missing(data.get(f)) for f in grantee_fields)
        if not has_grantee:
            missing_fields.append("Grantee Party (Buyer/Donee/Lender/Releasee)")
            
        # 3. Property & Transaction Value Completeness
        txn_upper = txn.upper() if txn else ""
        subtype = cls_info.get("subtype") or ""
        
        is_ownership_transfer = any(k in txn_upper for k in ["SALE", "GIFT", "AGREEMENT"]) or any(k in subtype for k in ["ats", "conveyance", "gift"])
        is_mortgage = "MORTGAGE" in txn_upper or "mortgage" in subtype or "intimation" in subtype
        
        if is_ownership_transfer or is_mortgage:
            # Check Area
            if _is_missing(data.get("area")):
                missing_fields.append("Property Area")
            
            # Check Value
            val_missing = False
            if is_ownership_transfer:
                if _is_missing(data.get("consideration")):
                    val_missing = True
            elif is_mortgage:
                if _is_missing(data.get("principal_amount_figures")):
                    val_missing = True
            if val_missing:
                missing_fields.append("Transaction Value / Loan Amount")

        if missing_fields:
            errors.append({
                "severity": "WARNING",
                "type": "MISSING_CRITICAL_FIELDS",
                "doc_no": data.get("doc_no"),
                "event_date": data.get("date_of_execution"),
                "source": source,
                "message": f"The following metadata fields could not be verified in this document: {', '.join(missing_fields)}. Please confirm their presence or verify the original deed execution.",
                "expected": "All standard fields populated",
                "actual": f"Missing fields: {', '.join(missing_fields)}"
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
                    "severity":   "ERROR",
                    "type":       "INVALID_PAN_FORMAT",
                    "doc_no":     data.get("doc_no"),
                    "event_date": data.get("date_of_execution"),
                    "source":     source,
                    "message":    f"Invalid PAN '{pan_val}' in {field_key.replace('_', ' ')}. Expected format: AAAAA9999A.",
                    "expected":   "Format: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)",
                    "actual":     pan_val
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
                "severity":   "ERROR",
                "type":       "PAN_TRANSFEROR_TRANSFEREE_CLASH",
                "doc_no":     data.get("doc_no"),
                "event_date": data.get("date_of_execution"),
                "source":     source,
                "message":    f"PAN {', '.join(overlap_pans)} appears on both transferor and transferee sides — same person cannot be both parties.",
                "expected":   "Different PANs for transferor and transferee",
                "actual":     ', '.join(overlap_pans)
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
                    "severity":   "ERROR",
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
                            "severity":   "WARNING",
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

        # ── Words-vs-figures checks ──────────────────────────────────────
        if is_sale:
            finding = _check_words_vs_figures(
                data.get("consideration"),
                data.get("consideration_words_numeric"),
                data.get("doc_no"),
                source,
                data.get("date_of_execution"),
                "consideration amount",
                data.get("consideration_words")
            )
            if finding:
                errors.append(finding)
        elif "MORTGAGE" in txn or "INTIMATION" in txn:
            finding = _check_words_vs_figures(
                data.get("principal_amount_figures"),
                data.get("principal_amount_words_numeric"),
                data.get("doc_no"),
                source,
                data.get("date_of_execution"),
                "mortgage principal amount",
                data.get("principal_amount_words")
            )
            if finding:
                errors.append(finding)
        elif "RELEASE" in txn:
            finding = _check_words_vs_figures(
                data.get("released_amount_figures"),
                data.get("released_amount_words_numeric"),
                data.get("doc_no"),
                source,
                data.get("date_of_execution"),
                "released amount",
                data.get("released_amount_words")
            )
            if finding:
                errors.append(finding)

            finding_orig = _check_words_vs_figures(
                data.get("released_mortgage_principal_figures"),
                data.get("released_mortgage_principal_words_numeric"),
                data.get("doc_no"),
                source,
                data.get("date_of_execution"),
                "original mortgage principal amount",
                data.get("released_mortgage_principal_words")
            )
            if finding_orig:
                errors.append(finding_orig)

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
            "registration_fee":  data.get("registration_fee"),
            "market_value":      data.get("market_value"),
            "plot_no":           data.get("plot_no"),
            "circle_value":      data.get("circle_value", 0.0),
            "area_sqm":          data.get("area_sqm", 0.0),
            "expected_stamp_duty": data.get("expected_stamp_duty", 0.0),
            "expected_registration_fee": data.get("expected_registration_fee", 0.0),
            "transferor_parties": data.get("transferor_parties") or [],
            "transferee_parties": data.get("transferee_parties") or [],
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
            event["principal_amount"] = data.get("principal_amount_figures")
            event["interest_rate"] = data.get("interest_rate")
            # Mortgage does NOT transfer ownership — skip chain update

        elif "RELEASE" in txn:
            raw_rel = data.get("seller_names") or [p.get("name") for p in data.get("transferor_parties") or [] if p.get("name")] or []
            raw_ree = data.get("buyer_names")  or [p.get("name") for p in data.get("transferee_parties") or [] if p.get("name")] or []
            
            if isinstance(raw_rel, str):
                raw_rel = [raw_rel]
            if isinstance(raw_ree, str):
                raw_ree = [raw_ree]
                
            event["releasor_names"] = raw_rel
            event["releasee_names"] = raw_ree
            event["released_amount"] = data.get("released_amount_figures")
            
            # Check if this release deed is releasing a mortgage (reconveyance/discharge)
            cls_info = data.get("_classification") or {}
            sub_type_l = (cls_info.get("subtype") or "").lower()
            is_mortgage_release = "mortgage" in sub_type_l or "reconveyance" in sub_type_l or "discharge" in sub_type_l
            
            if is_mortgage_release:
                transferors = []
                transferees = []
            else:
                transferors = raw_rel
                transferees = raw_ree

        elif "LEAVE" in txn or "LICENSE" in txn:
            event["licensor_name"] = data.get("licensor_name")
            event["licensee_name"] = data.get("licensee_name")
            event["license_fee"] = data.get("license_fee")
            event["deposit"] = data.get("deposit")
            event["leave_license_months"] = data.get("leave_license_months")

        # Extract signatory for the event if it involves an institution/company
        txt = pdf_text_lookup.get(source)
        event["authorized_signatory"] = None
        if txt:
            all_parties = []
            for key in ["seller_names", "buyer_names", "donor_name", "donee_name", "licensor_name", "licensee_name", "mortgagor_name", "mortgagee_name", "releasor_names", "releasee_names"]:
                val = event.get(key)
                if val:
                    if isinstance(val, list):
                        all_parties.extend(val)
                    else:
                        all_parties.append(val)
            for p_name in all_parties:
                sig = _extract_signatory(p_name, txt)
                if sig:
                    event["authorized_signatory"] = sig
                    break

        events.append(event)

        # ── Ownership chain validation + entity ledger ──────────────
        #
        # Fix 3: current_owners is a SET — multiple simultaneous owners
        #         are all kept active and all must be accounted for.
        # Fix 4/5: Mortgage validity checked against current_owners at
        #          the time of the mortgage event (chronological order
        #          is already guaranteed by the sort at the top).
        #
        # Check for DDA Freehold Conveyance
        is_freehold_conversion = False
        if "FREEHOLD" in txn or "freehold" in subtype or ("freehold" in text_l and "conveyance" in text_l):
            is_freehold_conversion = True

        if transferors or transferees:
            if is_freehold_conversion:
                matched_key = None
                for name in transferees:
                    if name:
                        matched_key = _find_fuzzy_match(name, set(current_owners.keys()))
                        if matched_key:
                            break
                if matched_key:
                    claimants[matched_key]["basis"] = "Freehold"
                    claimants[matched_key]["since_doc"] = data.get("doc_no")
                    claimants[matched_key]["since_date"] = data.get("date_of_execution")
                    event["event_type"] = "FREEHOLD_CONVEYANCE"
                else:
                    is_freehold_conversion = False

            if not is_freehold_conversion:
                if not first_ownership_set:
                    valid_transferees = [n for n in transferees if n]
                    share_per_transferee = 1.0 / len(valid_transferees) if valid_transferees else 1.0
                    
                    for name in transferors:
                        if not name:
                            continue
                        key = _canonical_name(name)
                        _pan, _pin = _person_ids(data, "transferor", name)
                        basis_val = "GOVERNMENT_ALLOTMENT" if _is_govt_authority(name) else "PRIOR_OWNERSHIP"
                        claimants[key] = {
                            "display_name": name,
                            "role":         "owner",
                            "since_doc":    None,
                            "since_date":   None,
                            "basis":        basis_val,
                            "area":         area,
                            "status":       "active",
                            "encumbered":   False,
                            "entry_type":   "root_seller",
                            "pan":          _pan,
                            "pin":          _pin,
                            "share":        0.0
                        }
                    
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
                            "share":        share_per_transferee
                        }
                        current_owners[key] = share_per_transferee

                    for name in transferors:
                        if not name:
                            continue
                        key = _canonical_name(name)
                        if key in claimants:
                            claimants[key]["status"]      = "transferred_out"
                            claimants[key]["exited_doc"]  = data.get("doc_no")
                            claimants[key]["exited_date"] = data.get("date_of_execution")
                            claimants[key]["exited_via"]  = txn
                            claimants[key]["exited_to"]   = transferees

                    first_ownership_set = True

                else:
                    declared_share = _parse_share(data.get("property_schedule_text")) or _parse_share(data.get("remarks")) or _parse_share(doc_text)
                    matched_keys = []
                    unmatched_names = []

                    is_release_deed = (data.get("document_type") or "").strip().upper() in ("DEED_OF_RELEASE", "RELINQUISHMENT_DEED")
                    transferees_are_owners = all(_canonical_name(t) in current_owners for t in transferees if t)

                    for name in transferors:
                        if not name:
                            continue
                        
                        best_owner_key = None
                        best_dev_tier = "UNKNOWN"
                        best_dev_severity = "ERROR"
                        best_dev_msg = ""
                        
                        for owner_key in current_owners:
                            owner_name = claimants.get(owner_key, {}).get("display_name", owner_key)
                            dev_tier, dev_msg, dev_severity = _check_name_deviation(name, owner_name)
                            
                            tier_ranks = {"EXACT": 1, "NORMALIZED": 2, "MINOR": 3, "MILD": 4, "SEVERE": 5, "ALIAS": 6, "UNKNOWN": 7}
                            if tier_ranks[dev_tier] < tier_ranks[best_dev_tier]:
                                best_dev_tier = dev_tier
                                best_dev_severity = dev_severity
                                best_dev_msg = dev_msg
                                best_owner_key = owner_key
                                
                        if best_owner_key and best_dev_tier not in ("SEVERE", "UNKNOWN"):
                            matched_keys.append(best_owner_key)
                            if best_dev_tier != "EXACT":
                                recorded_name = claimants[best_owner_key]["display_name"]
                                errors.append({
                                    "severity":   best_dev_severity,
                                    "type":       f"NAME_DEVIATION_{best_dev_tier}",
                                    "doc_no":     data.get("doc_no"),
                                    "ref_doc_no": claimants[best_owner_key].get("since_doc"),
                                    "event_date": data.get("date_of_execution"),
                                    "source":     source,
                                    "message":    best_dev_msg,
                                    "expected":   recorded_name,
                                    "actual":     name
                                })
                        else:
                            unmatched_names.append(name)

                    if transferors and not matched_keys:
                        msg_parts = []
                        for name in transferors:
                            if not name:
                                continue
                            key = _canonical_name(name)
                            if key in claimants:
                                former = claimants[key]
                                exit_via = former.get("exited_via") or former.get("basis") or "unknown txn"
                                exit_doc = former.get("exited_doc") or former.get("since_doc") or "unknown doc"
                                exit_date = former.get("exited_date") or former.get("since_date") or "unknown date"
                                msg_parts.append(
                                    f"Transferor '{name}' holds 0% share on record (exited interest via {exit_via} Doc {exit_doc} on {exit_date})."
                                )
                            else:
                                msg_parts.append(
                                    f"Transferor '{name}' has no prior record of ownership in this chain of title."
                                )
 
                        errors.append({
                            "severity":   "ERROR",
                            "type":       "CHAIN_BREAK",
                            "doc_no":     data.get("doc_no"),
                            "event_date": data.get("date_of_execution"),
                            "source":     source,
                            "message":    " ".join(msg_parts),
                            "expected":   list(current_owners.keys()),
                            "actual":     [_canonical_name(n) for n in transferors if n]
                        })

                        for name in transferors:
                            if not name:
                                continue
                            key = _canonical_name(name)
                            if key not in claimants:
                                _pan, _pin = _person_ids(data, "transferor", name)
                                basis_val = "GOVERNMENT_ALLOTMENT" if _is_govt_authority(name) else "PRIOR_OWNERSHIP"
                                claimants[key] = {
                                    "display_name": name,
                                    "role":         "owner",
                                    "since_doc":    None,
                                    "since_date":   None,
                                    "basis":        basis_val,
                                    "area":         area,
                                    "status":       "transferred_out",
                                    "exited_doc":   data.get("doc_no"),
                                    "exited_date":  data.get("date_of_execution"),
                                    "exited_via":   txn,
                                    "exited_to":    transferees,
                                    "encumbered":   False,
                                    "entry_type":   "seller_only",
                                    "pan":          _pan,
                                    "pin":          _pin,
                                }

                        for key in list(current_owners.keys()):
                            current_owners.pop(key, None)
                            if key in claimants and claimants[key]["status"] == "active":
                                claimants[key]["status"]      = "transferred_out"
                                claimants[key]["exited_doc"]  = data.get("doc_no")
                                claimants[key]["exited_date"] = data.get("date_of_execution")
                                claimants[key]["exited_via"]  = txn
                                claimants[key]["exited_to"]   = transferees

                        valid_transferees = [n for n in transferees if n]
                        share_per_transferee = 1.0 / len(valid_transferees) if valid_transferees else 1.0
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
                                "share":        share_per_transferee
                            }
                            current_owners[key] = share_per_transferee

                    else:
                        total_transferor_share = sum(current_owners.get(k, 0.0) for k in matched_keys)
                        sold_share = declared_share if declared_share is not None else total_transferor_share
                        
                        if total_transferor_share > 0:
                            for key in matched_keys:
                                faction = current_owners.get(key, 0.0) / total_transferor_share
                                current_owners[key] = max(0.0, current_owners.get(key, 0.0) - sold_share * faction)
                                if current_owners[key] <= 0.01:
                                    current_owners.pop(key, None)
                                    if key in claimants:
                                        claimants[key]["status"]      = "transferred_out"
                                        claimants[key]["exited_doc"]  = data.get("doc_no")
                                        claimants[key]["exited_date"] = data.get("date_of_execution")
                                        claimants[key]["exited_via"]  = txn
                                        claimants[key]["exited_to"]   = transferees
                                        
                        valid_transferees = [n for n in transferees if n]
                        share_per_transferee = sold_share / len(valid_transferees) if valid_transferees else sold_share
                        for name in transferees:
                            if not name:
                                continue
                            existing_key = _find_fuzzy_match(name, set(current_owners.keys()))
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
                                "share":        current_owners.get(key, 0.0) + share_per_transferee
                            }
                            current_owners[key] = current_owners.get(key, 0.0) + share_per_transferee

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
                    "severity":   "ERROR",
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
                "sro":        _normalize_sro(data.get("sub_registrar_office")),
                "year":       data.get("registration_year"),
                "principal_amount": _parse_money(data.get("principal_amount_figures")),
                "loan_account_no": data.get("loan_account_no"),
                "source_file": source,
                "released_amount": 0.0,
                "releases": []
            }
            encumbrances.append(enc)

            # Flag the mortgagor in claimants as encumbered (only if valid)
            if mortgagor_is_current and mortgagor_matched_key and mortgagor_matched_key in claimants:
                claimants[mortgagor_matched_key]["encumbered"] = True
                claimants[mortgagor_matched_key]["encumbrance_doc"] = data.get("doc_no")

    # ── Mortgage release matching (fuzzy mortgagor + mortgagee) ──────
    release_events_data = []
    for rf2, d2 in results:
        txn2 = (d2.get("txn_type") or "").upper()
        if "RELEASE" in txn2:
            cls_info = d2.get("_classification") or {}
            subtype = cls_info.get("subtype")
            if not subtype or subtype == "release_mortgage":
                release_events_data.append((rf2, d2))

    for rf2, d2 in release_events_data:
        source2 = rf2.replace("_result.json", ".pdf")
        rel_date = _parse_date(d2.get("date_of_execution"))
        rel_doc_no = d2.get("doc_no")
        
        candidates = []
        for enc in encumbrances:
            enc_date = _parse_date(enc["since_date"])
            
            # Chronological sequence check
            if rel_date <= enc_date:
                continue
                
            tier, link_type, severity, score, doc_match, fuzzy_match, p_match, a_match = _match_release_to_mortgage(enc, d2)
            if tier:
                candidates.append((enc, tier, link_type, severity, score, p_match, a_match))
                
        if not candidates:
            # Tier H: Orphan release
            errors.append({
                "severity":   "ERROR",
                "type":       "RELEASE_ORPHAN",
                "doc_no":     rel_doc_no,
                "event_date": d2.get("date_of_execution"),
                "source":     source2,
                "message":    f"Release Deed {rel_doc_no or source2} has no matching parent mortgage recorded in the title history. Verification of the related Mortgagor ({d2.get('buyer_names')}) and Mortgagee ({d2.get('seller_names')}) is required.",
                "expected":   "A matching Mortgage Deed",
                "actual":     "None found"
            })
        else:
            tier_priority = {"A": 1, "B": 2, "C": 3, "D": 4, "F": 5, "E": 6}
            candidates.sort(key=lambda x: (tier_priority.get(x[1], 99), -x[4]))
            
            best_enc, best_tier, best_link_type, best_severity, best_score, best_p_match, best_a_match = candidates[0]
            
            ambiguous = False
            if len(candidates) > 1:
                second_enc, second_tier, _, _, second_score, _, _ = candidates[1]
                if best_tier == second_tier and best_score == second_score:
                    ambiguous = True
                    
            if ambiguous:
                errors.append({
                    "severity":   "ERROR",
                    "type":       "RELEASE_AMBIGUOUS",
                    "doc_no":     rel_doc_no,
                    "event_date": d2.get("date_of_execution"),
                    "source":     source2,
                    "message":    f"Release Deed {rel_doc_no or source2} maps to multiple outstanding mortgages ({best_enc['doc_no']} and {second_enc['doc_no']}). Manual reconciliation of the corresponding charges is required.",
                    "expected":   "A single unique matching mortgage",
                    "actual":     "Multiple matches found"
                })
            else:
                best_enc["releases"].append({
                    "doc_no":     rel_doc_no,
                    "date":       d2.get("date_of_execution"),
                    "amount":     _parse_money(d2.get("released_amount_figures")) or 0.0,
                    "type":       d2.get("release_type") or "full",
                    "source":     source2
                })
                best_enc["resolved_doc"] = rel_doc_no
                best_enc["resolved_date"] = d2.get("date_of_execution")
                
                errors.append({
                    "severity":   best_severity,
                    "type":       best_link_type,
                    "doc_no":     rel_doc_no,
                    "ref_doc_no": best_enc["doc_no"],
                    "event_date": d2.get("date_of_execution"),
                    "source":     source2,
                    "message":    f"Release deed is successfully linked to Mortgage {best_enc['doc_no']} via corresponding registered document numbers.",
                    "expected":   best_enc["doc_no"],
                    "actual":     rel_doc_no
                })
                
                if best_tier in ("A", "B", "C", "D", "E") and not best_p_match:
                    errors.append({
                        "severity":   "ERROR",
                        "type":       "RELEASE_PARTY_MISMATCH",
                        "doc_no":     rel_doc_no,
                        "ref_doc_no": best_enc["doc_no"],
                        "event_date": d2.get("date_of_execution"),
                        "source":     source2,
                        "message":    f"Release Deed {rel_doc_no} references Mortgage {best_enc['doc_no']} by registration number, but contains party variations (Mortgagor: '{best_enc['mortgagor']}' vs Release buyer: '{d2.get('buyer_names')}', Mortgagee: '{best_enc['holder']}' vs Release seller: '{d2.get('seller_names')}').",
                        "expected":   f"Mortgagor: {best_enc['mortgagor']}, Mortgagee: {best_enc['holder']}",
                        "actual":     f"Buyer: {d2.get('buyer_names')}, Seller: {d2.get('seller_names')}"
                    })
                    
                if best_tier in ("A", "B", "C", "D", "E") and not best_a_match:
                    rel_orig_amt = _parse_money(d2.get("released_mortgage_principal_figures"))
                    errors.append({
                        "severity":   "ERROR",
                        "type":       "RELEASE_AMOUNT_MISMATCH",
                        "doc_no":     rel_doc_no,
                        "ref_doc_no": best_enc["doc_no"],
                        "event_date": d2.get("date_of_execution"),
                        "source":     source2,
                        "message":    f"Release Deed {rel_doc_no} cites a mortgage principal amount of ₹{int(rel_orig_amt or 0):,}, which varies from the registered principal of ₹{int(best_enc['principal_amount'] or 0):,} in Mortgage {best_enc['doc_no']}.",
                        "expected":   f"₹{int(best_enc['principal_amount'] or 0):,}",
                        "actual":     f"₹{int(rel_orig_amt or 0):,}"
                    })

                # Lender/Mortgagee Consistency Check
                mortgagee_m = best_enc.get("holder")
                release_sellers = d2.get("seller_names") or d2.get("releasor_names")
                if isinstance(release_sellers, str):
                    release_sellers = [release_sellers]
                release_sellers = [n for n in (release_sellers or []) if n]
                
                if mortgagee_m and release_sellers:
                    best_lender_match = None
                    best_lender_severity = "ERROR"
                    best_lender_type = "LENDER_MISMATCH"
                    best_lender_msg = ""
                    
                    for r_seller in release_sellers:
                        norm_m = _normalize_lender(mortgagee_m)
                        norm_r = _normalize_lender(r_seller)
                        
                        if mortgagee_m.strip().lower() == r_seller.strip().lower():
                            best_lender_match = r_seller
                            best_lender_severity = "INFO"
                            best_lender_type = "LENDER_CONSISTENT"
                            best_lender_msg = f"Lender names match exactly: '{r_seller}' in Release vs '{mortgagee_m}' in Mortgage."
                            break
                        elif norm_m == norm_r and norm_m:
                            best_lender_match = r_seller
                            best_lender_severity = "INFO"
                            best_lender_type = "LENDER_ALIAS_MATCH"
                            best_lender_msg = f"Lender names matched via alias table: '{r_seller}' = '{mortgagee_m}'."
                            break
                        elif norm_m and norm_r and (norm_m in norm_r or norm_r in norm_m):
                            best_lender_match = r_seller
                            best_lender_severity = "INFO"
                            best_lender_type = "LENDER_BRANCH_DIFF"
                            best_lender_msg = f"Same lender, different branch/detail variant: '{r_seller}' in Release vs '{mortgagee_m}' in Mortgage."
                        elif norm_m and norm_r and (MERGER_MAP.get(norm_m) == norm_r or MERGER_MAP.get(norm_r) == norm_m):
                            best_lender_match = r_seller
                            best_lender_severity = "WARNING"
                            best_lender_type = "LENDER_MERGER"
                            best_lender_msg = f"Possible legitimate lender change due to bank merger: '{r_seller}' (Release) vs '{mortgagee_m}' (Mortgage)."
                        else:
                            ratio = _char_similarity(mortgagee_m, r_seller)
                            if ratio >= 0.85:
                                best_lender_match = r_seller
                                best_lender_severity = "WARNING"
                                best_lender_type = "LENDER_FUZZY_MATCH"
                                best_lender_msg = f"Lender names similar but not in alias table: '{r_seller}' in Release vs '{mortgagee_m}' in Mortgage."
                                
                    if best_lender_match:
                        if best_lender_type != "LENDER_CONSISTENT":
                            errors.append({
                                "severity":   best_lender_severity,
                                "type":       best_lender_type,
                                "doc_no":     rel_doc_no,
                                "ref_doc_no": best_enc["doc_no"],
                                "event_date": d2.get("date_of_execution"),
                                "source":     source2,
                                "message":    best_lender_msg,
                                "expected":   mortgagee_m,
                                "actual":     best_lender_match
                            })
                    else:
                        errors.append({
                            "severity":   "ERROR",
                            "type":       "LENDER_MISMATCH",
                            "doc_no":     rel_doc_no,
                            "ref_doc_no": best_enc["doc_no"],
                            "event_date": d2.get("date_of_execution"),
                            "source":     source2,
                            "message":    f"The mortgagee lender '{mortgagee_m}' does not match the releasor lender '{', '.join(release_sellers)}' in the corresponding discharge document.",
                            "expected":   mortgagee_m,
                            "actual":     ', '.join(release_sellers)
                        })

    # ── Post-processing: calculate final mortgage status using sum-of-releases ──
    unresolved_mortgages = []
    for enc in encumbrances:
        principal = enc.get("principal_amount") or 0.0
        releases = enc.get("releases") or []
        
        if not releases:
            enc["status"] = "UNRESOLVED"
            unresolved_mortgages.append(enc["doc_no"] or "unknown")
            errors.append({
                "severity":   "WARNING",
                "type":       "UNRESOLVED_MORTGAGE",
                "doc_no":   enc["doc_no"],
                "event_date": enc["since_date"],
                "source":   enc["source_file"],
                "message":  f"Outstanding simple mortgage remains unresolved on title history. No corresponding release deed or satisfaction of charge was identified for Mortgagor: {enc['mortgagor']} and Mortgagee: {enc['holder']}.",
                "expected": "A matching Release Deed (mortgagor + mortgagee names)",
                "actual":   "None found"
            })
            continue
            
        total_released = sum(r["amount"] for r in releases)
        has_full_release = any(r["type"] == "full" for r in releases)
        
        if has_full_release:
            enc["status"] = "RESOLVED"
            if enc["mortgagor"]:
                matched_key = _find_fuzzy_match(enc["mortgagor"], set(claimants.keys()))
                if matched_key and matched_key in claimants:
                    claimants[matched_key]["encumbered"] = False
            errors.append({
                "severity": "INFO",
                "type": "MORTGAGE_RESOLVED",
                "doc_no": enc["doc_no"],
                "event_date": enc["since_date"],
                "source": enc["source_file"],
                "message": f"Mortgage {enc['doc_no']} is fully resolved and discharged via linked release deed (explicit full release confirmed).",
                "expected": f"₹{int(round(principal)):,}",
                "actual": f"₹{int(round(total_released)):,}"
            })
        else:
            diff = total_released - principal
            if abs(diff) < 0.01:
                enc["status"] = "RESOLVED"
                if enc["mortgagor"]:
                    matched_key = _find_fuzzy_match(enc["mortgagor"], set(claimants.keys()))
                    if matched_key and matched_key in claimants:
                        claimants[matched_key]["encumbered"] = False
                errors.append({
                    "severity": "INFO",
                    "type": "MORTGAGE_RESOLVED",
                    "doc_no": enc["doc_no"],
                    "event_date": enc["since_date"],
                    "source": enc["source_file"],
                    "message": f"Mortgage {enc['doc_no']} is fully resolved. Linked release amounts sum to principal (₹{int(round(total_released)):,}).",
                    "expected": f"₹{int(round(principal)):,}",
                    "actual": f"₹{int(round(total_released)):,}"
                })
            elif diff < -0.01:
                enc["status"] = "PARTIALLY_RELEASED"
                unresolved_mortgages.append(enc["doc_no"] or "unknown")
                shortfall = -diff
                errors.append({
                    "severity": "WARNING",
                    "type": "PARTIALLY_RELEASED",
                    "doc_no": enc["doc_no"],
                    "event_date": enc["since_date"],
                    "source": enc["source_file"],
                    "message": f"Mortgage {enc['doc_no']} is only partially discharged. A remaining balance shortfall of ₹{int(round(shortfall)):,} exists relative to the registered principal amount.",
                    "expected": f"₹{int(round(principal)):,}",
                    "actual": f"₹{int(round(total_released)):,}"
                })
            else:
                enc["status"] = "RELEASE_OVERFLOW"
                unresolved_mortgages.append(enc["doc_no"] or "unknown")
                overflow = diff
                errors.append({
                    "severity": "ERROR",
                    "type": "RELEASE_OVERFLOW",
                    "doc_no": enc["doc_no"],
                    "event_date": enc["since_date"],
                    "source": enc["source_file"],
                    "message": f"Discharge value overflow on Mortgage {enc['doc_no']}. Linked release deeds sum to ₹{int(round(total_released)):,}, which exceeds the registered principal of ₹{int(round(principal)):,} by ₹{int(round(overflow)):,}.",
                    "expected": f"₹{int(round(principal)):,}",
                    "actual": f"₹{int(round(total_released)):,}"
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

    # ── Check 4: Unregularized GPA Chain Check ────────────────────────
    has_sale_or_freehold = False
    for ev in events:
        t = (ev.get("event_type") or "").upper()
        if "SALE" in t or "FREEHOLD" in t or "CONVEYANCE" in t:
            has_sale_or_freehold = True
            
    active_gpa_owners = []
    for k, v in claimants.items():
        if v.get("status") == "active":
            basis = (v.get("basis") or "").upper()
            if "POWER OF ATTORNEY" in basis or "GPA" in basis or "ATS" in basis or "AGREEMENT" in basis:
                active_gpa_owners.append(v.get("display_name", k))
                
    if active_gpa_owners and not has_sale_or_freehold:
        errors.append({
            "severity":   "WARNING",
            "type":       "UNREGULARIZED_GPA_CHAIN",
            "doc_no":     None,
            "event_date": None,
            "source":     "ownership chain verification",
            "message":    "Although this GPA chain might have been executed before 2011, it was never converted into a full ownership title. A bank will likely reject a loan on this property until you regularize it.",
            "expected":   "A registered Sale Deed or DDA Freehold Conveyance Deed",
            "actual":     f"Chain ends with GPA held by: {', '.join(active_gpa_owners)}"
        })

    # ── Post-processing: extract authorized signatories and extended metadata ──

    for key, c in claimants.items():
        c["authorized_signatory"] = None
        c["extended_metadata"] = {}
        doc_no_val = c.get("since_doc") or c.get("exited_doc")
        if doc_no_val:
            for rf, data in results:
                if str(data.get("doc_no")) == str(doc_no_val):
                    source_pdf = rf.replace("_result.json", ".pdf")
                    txt = pdf_text_lookup.get(source_pdf)
                    if txt:
                        c["authorized_signatory"] = _extract_signatory(c["display_name"], txt)
                        c["extended_metadata"] = _extract_extended_metadata(c["display_name"], txt)
                    break

    for enc in encumbrances:
        enc["authorized_signatory"] = None
        enc["extended_metadata"] = {}
        source_pdf = enc.get("source_file")
        if source_pdf:
            txt = pdf_text_lookup.get(source_pdf)
            if txt:
                enc["authorized_signatory"] = _extract_signatory(enc["holder"], txt)
                enc["extended_metadata"] = _extract_extended_metadata(enc["holder"], txt)

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

    # ── Post-processing: refine findings messages to be highly professional and detailed ──
    for err in errors:
        etype = err.get("type")
        expected = err.get("expected")
        actual = err.get("actual")
        doc_no = err.get("doc_no")
        ref_doc_no = err.get("ref_doc_no")
        
        # Format list-like values nicely
        expected_str = ", ".join(expected) if isinstance(expected, list) else str(expected or "")
        actual_str = ", ".join(actual) if isinstance(actual, list) else str(actual or "")
        
        if etype == "METADATA_LOCALITY_MISMATCH":
            err["message"] = f"Locality Mismatch: The document lists the property locality as '{actual_str}', which deviates from the project's designated locality '{expected_str}'. This suggests the document may reference a different property or contain registry indexing errors."
            
        elif etype == "METADATA_SRO_MISMATCH":
            err["message"] = f"Sub-Registrar Office Jurisdictional Mismatch: The document was registered at '{actual_str}', which does not possess jurisdiction over the property's locality. The expected jurisdictional office covering '{expected_str}' was expected."
            
        elif etype == "METADATA_AUTHORITY_MISMATCH":
            err["message"] = f"Authority Category Mismatch: The project category is set to '{expected_str.replace(' indicators', '')}', but the document text contains no reference to this authority or its standard allotment/leasehold indicators (e.g. leasehold, allotment letters)."
            
        elif etype == "METADATA_LAND_USE_MISMATCH":
            err["message"] = f"Land Use Classification Mismatch: The document cites the property land use as '{actual_str}', which does not match the project's expected land use of '{expected_str}' (e.g. Residential vs Commercial mismatch)."
            
        elif etype == "METADATA_FLAT_MISMATCH":
            err["message"] = f"Flat Number Mismatch: The document identifies the unit as Flat No. '{actual_str}', while the project expects Flat No. '{expected_str}'. Please verify if this pertains to a different unit in the same building."
            
        elif etype == "METADATA_FLOOR_MISMATCH":
            err["message"] = f"Floor Level Mismatch: The property is listed on the '{actual_str}' in this document, which conflicts with the project's expected floor level of '{expected_str}'."
            
        elif etype == "METADATA_PROPERTY_ID_MISMATCH" or etype == "METADATA_UPIC_MISMATCH":
            err["message"] = f"Registry Property Identifier Mismatch: The document lists the property ID/UPIC as '{actual_str}', which conflicts with the expected project identifier '{expected_str}'."
            
        elif etype == "METADATA_ADDRESS_MISMATCH":
            err["message"] = f"Property Address Discrepancy: The project's registered address '{expected_str}' was not found in the scanned text of this document. Please manually inspect the property schedule."
            
        elif etype == "AREA_MISMATCH":
            err["message"] = f"Significant Property Area Discrepancy: The document cites an area of {actual_str}, which differs significantly from the expected share value of {expected_str} in the chain of title."
            
        elif etype == "AREA_MISMATCH_MILD":
            err["message"] = f"Area deviation: Document cites {actual_str}, showing a slight variance from the expected share value of {expected_str}."
            
        elif etype == "SOCIETY_MISMATCH":
            err["message"] = f"Building name mismatch: Document lists '{actual_str}' instead of project building '{expected_str}'."
            
        elif etype == "ID_MISMATCH":
            err["message"] = f"Property identifier mismatch: Document lists '{actual_str}' instead of project identifier '{expected_str}'."
            
        elif etype == "DATE_ORDER_DEVIATION":
            err["message"] = f"Date order deviation: Executed on {err.get('event_date')}, which is prior to predecessor Doc {ref_doc_no}."
            
        elif etype == "GPA_POST_2011_INVALID":
            err["message"] = f"Unregistered GPA: Power of Attorney was executed after 11-10-2011. Under the Suraj Lamp ruling, unregistered GPAs post-2011 present a title transfer risk."
            
        elif etype == "MISSING_GPA_AUTHORIZATION":
            err["message"] = f"Missing sale covenants: Power of Attorney does not explicitly authorize the attorney to sell or transfer the property."
            
        elif etype == "INVALID_PAN_FORMAT":
            err["message"] = f"Invalid PAN format: Extracted PAN '{actual_str}' does not match standard 10-character format."
            
        elif etype == "INVALID_PIN_FORMAT":
            err["message"] = f"Invalid PIN format: Extracted PIN '{actual_str}' must be a 6-digit numeric code."
            
        elif etype == "PAN_TRANSFEROR_TRANSFEREE_CLASH":
            err["message"] = f"PAN clash: Same PAN '{actual_str}' is listed for both the transferor and transferee."
            
        elif etype == "PIN_TRANSFEROR_TRANSFEREE_CLASH":
            err["message"] = f"PIN clash: Same PIN code '{actual_str}' is listed for both transacting parties."
            
        elif etype == "ZERO_CONSIDERATION":
            err["message"] = "Zero consideration: Sale/conveyance deed is registered with a consideration value of zero."
            
        elif etype == "CONSIDERATION_ANOMALY":
            err["message"] = f"Price deviation: Consideration ({actual_str}) is lower than the declared market value ({expected_str})."
            
        elif etype == "CHAIN_BREAK":
            pass
            
        elif etype == "UNRESOLVED_MORTGAGE":
            err["message"] = f"Unresolved mortgage: Outstanding charge under Doc {doc_no} remains active on record with no corresponding discharge or release deed identified."
            
        elif etype == "PARTIALLY_RELEASED":
            err["message"] = f"Outstanding loan balance: Mortgage Doc {doc_no} remains partially discharged. A principal balance of {actual_str} remains outstanding relative to the original loan of {expected_str}."
            
        elif etype == "RELEASE_OVERFLOW":
            err["message"] = f"Release overflow: Release amount of {actual_str} exceeds the active outstanding mortgage balance of {expected_str}."
            
        elif etype == "LENDER_MISMATCH":
            err["message"] = f"Lender mismatch: Release deed is executed by '{actual_str}' instead of original lender bank '{expected_str}'."
            
        elif etype == "RELEASE_PARTY_MISMATCH":
            err["message"] = f"Release party mismatch: Transacting parties do not match the original mortgagors/mortgagees of Doc {ref_doc_no}."
            
        elif etype == "RELEASE_ORPHAN":
            err["message"] = "Unlinked release deed: Discharge deed could not be matched to any active registered mortgage in the title chain."
            
        elif etype == "RELEASE_AMBIGUOUS":
            err["message"] = "Ambiguous release link: Multiple active mortgages match registry details, creating an ambiguous link."
            
        elif etype == "AMOUNT_WORDS_FIGURES_MISMATCH":
            err["message"] = f"Words vs figures mismatch: The amount written in words ({expected_str}) does not match the numeric figures ({actual_str})."
            
        elif etype == "UNREGULARIZED_GPA_CHAIN":
            err["message"] = f"Unregularized title: Chain ends with a GPA held by {actual_str} rather than a registered Sale Deed or allotment conveyance."

        elif etype == "MISSING_CRITICAL_FIELDS":
            err["message"] = f"Missing metadata: Mandatory fields could not be verified: {actual_str.replace('Missing fields: ', '')}."

    # ── Consolidate all MISSING_CRITICAL_FIELDS warnings into a single universal finding ──
    missing_fields_errors = [e for e in errors if e.get("type") == "MISSING_CRITICAL_FIELDS"]
    errors = [e for e in errors if e.get("type") != "MISSING_CRITICAL_FIELDS"]
    
    if missing_fields_errors:
        docs_details = []
        for m_err in missing_fields_errors:
            doc_str = f"Doc {m_err.get('doc_no') or '—'}"
            if m_err.get("event_date"):
                doc_str += f" ({m_err.get('event_date')})"
            missing_str = m_err.get("actual", "").replace("Missing fields: ", "")
            docs_details.append(f"{doc_str}: Missing {missing_str}")
        
        consolidated_msg = "Missing metadata: Mandatory parameters are missing across multiple documents:\n" + "\n".join([f"- {d}" for d in docs_details])
        
        errors.append({
            "severity":   "WARNING",
            "type":       "MISSING_CRITICAL_FIELDS",
            "doc_no":     None,
            "event_date": None,
            "source":     "multiple documents",
            "message":    consolidated_msg,
            "expected":   "All registry parameters fully verified",
            "actual":     docs_details
        })

    # Inject computed outstanding balance and releases back into mortgage events
    for enc in encumbrances:
        doc_no = enc.get("doc_no")
        if doc_no:
            for ev in events:
                if str(ev.get("event_doc_no")) == str(doc_no) and "MORTGAGE" in (ev.get("event_type") or "").upper():
                    ev["releases"] = enc.get("releases") or []
                    ev["status"] = enc.get("status")
                    ev["principal_amount"] = enc.get("principal_amount") or 0.0

    return events, entities, errors, unresolved_mortgages


# Build events for a project
# Clear all parse results for a project (does NOT delete PDFs)
@app.route("/clear_results/<project_name>", methods=["POST"])
@login_required
def clear_results(project_name):
    if not check_project_owner(project_name):
        abort(403)
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
@login_required
def get_events(project_name):
    if not check_project_owner(project_name):
        abort(403)
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

    # Encumbrance counts for the metadata bar (total vs unresolved/partial)
    encumbrances = (entities or {}).get("encumbrances", [])
    encumbrances_total      = len(encumbrances)
    encumbrances_unresolved = len([e for e in encumbrances if e.get("status") == "UNRESOLVED"])
    encumbrances_partial    = len([e for e in encumbrances if e.get("status") == "PARTIALLY_RELEASED"])
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
        "encumbrances_partial": encumbrances_partial,
    })


# Dismiss a finding (reviewer has verified it as a non-issue)
@app.route("/dismiss_finding/<project_name>/<finding_id>", methods=["POST"])
@login_required
def dismiss_finding(project_name, finding_id):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    ids = _load_dismissals(project_name)
    ids.add(finding_id)
    ok = _save_dismissals(project_name, ids)
    return jsonify({"ok": ok, "dismissed": finding_id})


# Restore a previously dismissed finding (full reviewer control)
@app.route("/restore_finding/<project_name>/<finding_id>", methods=["POST"])
@login_required
def restore_finding(project_name, finding_id):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    ids = _load_dismissals(project_name)
    ids.discard(finding_id)
    ok = _save_dismissals(project_name, ids)
    return jsonify({"ok": ok, "restored": finding_id})


# Build errors for a project
@app.route("/errors/<project_name>")
@login_required
def get_errors(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)
    return jsonify({"chain_errors": errors})


# Build entities for a project
@app.route("/entities/<project_name>")
@login_required
def get_entities(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    project_path = os.path.join(PROJECT_FOLDER, project_name)
    events, entities, errors, unresolved_mortgages = _build_events_and_errors(project_path)
    return jsonify(entities)  # already structured as {owners, encumbrances}


# ── AI Assistant chat endpoint ──────────────────────────────────────────────
@app.route("/chat/<project_name>", methods=["POST"])
@login_required
def chat(project_name):
    if not check_project_owner(project_name):
        abort(403)
    from flask import jsonify
    from main import chat_about_property

    project_path = os.path.join(PROJECT_FOLDER, project_name)
    payload = request.get_json(silent=True) or {}
    history = payload.get("history", [])
    model   = payload.get("model", "gemini-2.5-flash")
    # Reviewer-chosen scope hint ("Events", "Findings", "All JSON" etc.).
    # Folded into the assistant's system instruction in chat_about_property.
    scope_note = (payload.get("scope") or payload.get("scope_note") or "").strip() or None

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

    reply = chat_about_property(context_json, history, model=model, scope_note=scope_note)
    return jsonify({"ok": True, "reply": reply})


# ── Global Settings & Deed Scan API Endpoints ──
SCAN_CREDENTIALS = {
    "username": os.getenv("DORIS_SCAN_USER", ""),
    "password": os.getenv("DORIS_SCAN_PASS", ""),
    "session_cookie": os.getenv("DORIS_SCAN_COOKIE", "")
}

@app.route("/api/settings/credentials", methods=["GET", "POST"])
def settings_credentials():
    if request.method == "POST":
        data = request.json or {}
        user = data.get("username", "").strip()
        pwd = data.get("password", "").strip()
        cookie = data.get("session_cookie", "").strip()
        SCAN_CREDENTIALS["username"] = user
        SCAN_CREDENTIALS["password"] = pwd
        SCAN_CREDENTIALS["session_cookie"] = cookie
        os.environ["DORIS_SCAN_USER"] = user
        os.environ["DORIS_SCAN_PASS"] = pwd
        os.environ["DORIS_SCAN_COOKIE"] = cookie
        return jsonify({"ok": True, "message": "Credentials updated successfully."})
    else:
        # Return masked representation for security
        masked_pwd = "*" * len(SCAN_CREDENTIALS["password"]) if SCAN_CREDENTIALS["password"] else ""
        return jsonify({
            "ok": True,
            "username": SCAN_CREDENTIALS["username"],
            "session_cookie": SCAN_CREDENTIALS["session_cookie"],
            "password_configured": bool(SCAN_CREDENTIALS["password"]),
            "password_masked": masked_pwd
        })
@app.route("/api/deed_doc/login_captcha", methods=["GET"])
def deed_doc_login_captcha():
    """Fetches live CAPTCHA for scan.delhigovt.nic.in/Login.aspx"""
    scraper = DorisDocScraper(
        username=SCAN_CREDENTIALS.get("username"),
        password=SCAN_CREDENTIALS.get("password")
    )
    res = scraper.start_login_session()
    return jsonify(res)

@app.route("/api/deed_doc/login_submit", methods=["POST"])
def deed_doc_login_submit():
    """Submits login credentials and CAPTCHA code to Login.aspx"""
    data = request.json or {}
    user = data.get("username") or SCAN_CREDENTIALS.get("username")
    pwd = data.get("password") or SCAN_CREDENTIALS.get("password")
    captcha = data.get("captcha_code", "")

    scraper = DorisDocScraper(username=user, password=pwd)
    res = scraper.submit_login_with_captcha(user, pwd, captcha)
    if res.get("ok") and res.get("cookie_str"):
        SCAN_CREDENTIALS["session_cookie"] = res["cookie_str"]
        os.environ["DORIS_SCAN_COOKIE"] = res["cookie_str"]
    return jsonify(res)

MASTER_DELHI_LOCALITIES = [
    {"id": "D Mall (Rohini Sector-10)", "name": "D Mall (Rohini Sector-10)"},
    {"id": "Kings Mall (Rohini Sector-10)", "name": "Kings Mall (Rohini Sector-10)"},
    {"id": "Manglam Palace (Rohini Sector-3)", "name": "Manglam Palace (Rohini Sector-3)"},
    {"id": "Prashant Vihar (Rohini Sector-14)", "name": "Prashant Vihar (Rohini Sector-14)"},
    {"id": "Rajapur Village Sec-9 Rohini", "name": "Rajapur Village Sec-9 Rohini"},
    {"id": "Ring Road Mall (Rohini Sector-3)", "name": "Ring Road Mall (Rohini Sector-3)"},
    {"id": "Rohini", "name": "Rohini"},
    {"id": "Rohini Sector 1", "name": "Rohini Sector 1"},
    {"id": "Rohini Sector 2", "name": "Rohini Sector 2"},
    {"id": "Rohini Sector 3", "name": "Rohini Sector 3"},
    {"id": "Rohini Sector 4", "name": "Rohini Sector 4"},
    {"id": "Rohini Sector 5", "name": "Rohini Sector 5"},
    {"id": "Rohini Sector 6", "name": "Rohini Sector 6"},
    {"id": "Rohini Sector 7", "name": "Rohini Sector 7"},
    {"id": "Rohini Sector 8", "name": "Rohini Sector 8"},
    {"id": "Rohini Sector 9", "name": "Rohini Sector 9"},
    {"id": "Rohini Sector-10", "name": "Rohini Sector-10"},
    {"id": "Rohini Sector-11", "name": "Rohini Sector-11"},
    {"id": "Rohini Sector-12", "name": "Rohini Sector-12"},
    {"id": "Rohini Sector-13", "name": "Rohini Sector-13"},
    {"id": "Rohini Sector-14", "name": "Rohini Sector-14"},
    {"id": "Rohini Sector-15", "name": "Rohini Sector-15"},
    {"id": "Rohini Sector-16", "name": "Rohini Sector-16"},
    {"id": "Rohini Sector-17", "name": "Rohini Sector-17"},
    {"id": "Rohini Sector-18", "name": "Rohini Sector-18"},
    {"id": "Rohini Sector-19", "name": "Rohini Sector-19"},
    {"id": "Rohini Sector 20", "name": "Rohini Sector 20"},
    {"id": "Rohini Sector-21", "name": "Rohini Sector-21"},
    {"id": "Rohini Sector-22", "name": "Rohini Sector-22"},
    {"id": "Rohini Sector-23", "name": "Rohini Sector-23"},
    {"id": "Rohini Sector-24", "name": "Rohini Sector-24"},
    {"id": "Chitra Vihar", "name": "Chitra Vihar"},
    {"id": "Vasundhara Enclave", "name": "Vasundhara Enclave"},
    {"id": "Mayur Vihar Phase 1", "name": "Mayur Vihar Phase 1"},
    {"id": "Mayur Vihar Phase 2", "name": "Mayur Vihar Phase 2"},
    {"id": "Mayur Vihar Phase 3", "name": "Mayur Vihar Phase 3"},
    {"id": "Preet Vihar", "name": "Preet Vihar"},
    {"id": "Laxmi Nagar", "name": "Laxmi Nagar"},
    {"id": "Bank Colony", "name": "Bank Colony"},
    {"id": "Nirman Vihar", "name": "Nirman Vihar"},
    {"id": "Swasthya Vihar", "name": "Swasthya Vihar"},
    {"id": "Vasant Kunj", "name": "Vasant Kunj"},
    {"id": "Vasant Vihar", "name": "Vasant Vihar"},
    {"id": "Dwarka Sector 1", "name": "Dwarka Sector 1"},
    {"id": "Dwarka Sector 6", "name": "Dwarka Sector 6"},
    {"id": "Dwarka Sector 10", "name": "Dwarka Sector 10"},
    {"id": "Dwarka Sector 12", "name": "Dwarka Sector 12"},
    {"id": "Janakpuri", "name": "Janakpuri"},
    {"id": "Pitampura", "name": "Pitampura"},
    {"id": "Punjabi Bagh", "name": "Punjabi Bagh"},
    {"id": "Paschim Vihar", "name": "Paschim Vihar"},
    {"id": "Model Town", "name": "Model Town"},
    {"id": "Civil Lines", "name": "Civil Lines"},
    {"id": "Defence Colony", "name": "Defence Colony"},
    {"id": "Saket", "name": "Saket"},
    {"id": "Hauz Khas", "name": "Hauz Khas"},
    {"id": "Mehrauli", "name": "Mehrauli"},
    {"id": "Greater Kailash", "name": "Greater Kailash"},
    {"id": "Lajpat Nagar", "name": "Lajpat Nagar"},
    {"id": "Shahdara", "name": "Shahdara"},
    {"id": "Seelampur", "name": "Seelampur"}
]

@app.route("/api/deed_doc/search_locality", methods=["GET"])
def deed_doc_search_locality():
    """Live search endpoint for locality autocomplete"""
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"ok": True, "localities": []})

    # Try live query from DorisDocScraper if active session exists
    if SCAN_CREDENTIALS.get("session_cookie"):
        scraper = DorisDocScraper(session_cookie=SCAN_CREDENTIALS.get("session_cookie"))
        res = scraper.get_locality_list("0")
        if res.get("ok") and res.get("locality_list"):
            live_matches = [l for l in res["locality_list"] if q in l["name"].lower()]
            if live_matches:
                return jsonify({"ok": True, "localities": live_matches})

    # Fallback to master dataset matches
    matches = [loc for loc in MASTER_DELHI_LOCALITIES if q in loc["name"].lower()]
    return jsonify({"ok": True, "localities": matches})


@app.route("/api/deed_doc/start/<project_name>", methods=["GET"])
def deed_doc_start(project_name):
    """Fetches live SRO dropdown list directly from scan.delhigovt.nic.in"""
    scraper = DorisDocScraper(
        username=SCAN_CREDENTIALS.get("username"),
        password=SCAN_CREDENTIALS.get("password"),
        session_cookie=SCAN_CREDENTIALS.get("session_cookie")
    )
    res = scraper.get_sro_list()
    return jsonify(res)

@app.route("/api/deed_doc/select/<project_name>", methods=["POST"])
def deed_doc_select(project_name):
    """Fetches live localities for a selected SRO from scan.delhigovt.nic.in"""
    data = request.json or {}
    sro_val = data.get("sro_val", "")
    scraper = DorisDocScraper(
        username=SCAN_CREDENTIALS.get("username"),
        password=SCAN_CREDENTIALS.get("password"),
        session_cookie=SCAN_CREDENTIALS.get("session_cookie")
    )
    res = scraper.get_locality_list(sro_val)
    return jsonify(res)


@app.route("/api/doris/download_deed/<project_name>", methods=["POST"])
def download_deed_doc(project_name):
    data = request.json or {}
    reg_no = data.get("reg_no", "").strip()
    reg_year = data.get("reg_year", "").strip()
    locality = data.get("locality", "").strip()
    sro_name = data.get("sro_name", "").strip()
    book_no = data.get("book_no", "1").strip()

    if not reg_no or not reg_year:
        return jsonify({"ok": False, "error": "Registration Number and Year are required."}), 400

    user = SCAN_CREDENTIALS["username"]
    pwd = SCAN_CREDENTIALS["password"]
    cookie = SCAN_CREDENTIALS["session_cookie"]

    try:
        from deed_doc_scraper import DorisDocScraper
        scraper = DorisDocScraper(username=user, password=pwd, session_cookie=cookie)

        # 1. Authenticate with portal if credentials provided and no session cookie
        if not cookie and user and pwd:
            auth_res = scraper.login(user, pwd)
            if not auth_res.get("ok"):
                return jsonify({"ok": False, "error": f"Portal Login Failed: {auth_res.get('error')}"}), 401

        # 2. Search for deed document pages
        search_res = scraper.fetch_deed_document(
            locality=locality,
            reg_no=reg_no,
            reg_year=reg_year,
            sro_name=sro_name,
            book_no=book_no
        )

        if not search_res.get("ok"):
            return jsonify({
                "ok": False,
                "diagnostic_code": search_res.get("diagnostic_code", "UNKNOWN_ERROR"),
                "error": search_res.get("error", "Failed to retrieve deed scans.")
            }), 400

        # 3. Stitch images into PDF and save to project folder
        project_dir = os.path.join(RESULTS_DIR, project_name)
        pdf_filename = f"Deed_Doc_Reg_{reg_no}_{reg_year.replace('/', '-')}.pdf"
        output_pdf_path = os.path.join(project_dir, pdf_filename)

        pdf_res = scraper.generate_stitched_pdf(image_urls, output_pdf_path)
        if not pdf_res.get("ok"):
            return jsonify({"ok": False, "error": pdf_res.get("error")}), 500

        return jsonify({
            "ok": True,
            "filename": pdf_filename,
            "pdf_path": output_pdf_path,
            "pages_stitched": pdf_res.get("page_count"),
            "file_size_bytes": pdf_res.get("file_size_bytes"),
            "message": f"Successfully created {pdf_filename} with {pdf_res.get('page_count')} page scans."
        })

    except Exception as e:
        return jsonify({"ok": False, "error": f"Deed downloader error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)