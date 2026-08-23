import json
import re
import os
import pdfplumber
from google import genai
from dotenv import load_dotenv

load_dotenv()  # reads .env from the project root into the environment

# API key is read ONLY from the environment — never hardcoded.
# Set it before running, e.g.:
#   Windows (PowerShell):  $env:GEMINI_API_KEY="your-key-here"
#   Linux/Mac:             export GEMINI_API_KEY="your-key-here"
_API_KEY = os.environ.get("GEMINI_API_KEY")
if not _API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Set it as an environment variable "
        "before running. Do NOT hardcode the key in this file."
    )
client = genai.Client(api_key=_API_KEY)

import cv2
import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR

_rapid_ocr_engine = None

def get_ocr_engine():
    global _rapid_ocr_engine
    if _rapid_ocr_engine is None:
        _rapid_ocr_engine = RapidOCR()
    return _rapid_ocr_engine

def deskew_and_preprocess_image(image_np):
    """
    Module 1: Image Pre-Processing & Deskewer Pipeline
    Detects text baseline orientation using OpenCV minAreaRect,
    deskews image if tilt angle > 0.5 deg, and applies contrast binarization.
    """
    try:
        gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY) if len(image_np.shape) == 3 else image_np.copy()
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) > 50:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if abs(angle) > 0.5 and abs(angle) < 45:
                (h, w) = image_np.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                image_np = cv2.warpAffine(image_np, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return image_np
    except Exception as e:
        print(f"[deskew_and_preprocess_image] Warning: {e}")
        return image_np

def extract_text_from_PDF(file_path):
    """Read a PDF's embedded text layer (with hybrid OCR fallback + deskewing) and return all text."""
    cache_path = file_path + ".txt"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = f.read()
            if cached.strip():
                return cached
        except Exception:
            pass

    text = ""
    try:
        pdf_doc = pdfium.PdfDocument(file_path)
        ocr = get_ocr_engine()
        with pdfplumber.open(file_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                # Module 1 & 2: If native text layer is missing or sparse (<40 chars), deskew and run RapidOCR
                if len(page_text.strip()) < 40 and page_idx < len(pdf_doc):
                    try:
                        pil_img = pdf_doc[page_idx].render(scale=2.0).to_pil()
                        img_np = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                        img_deskewed = deskew_and_preprocess_image(img_np)
                        ocr_res, _ = ocr(img_deskewed)
                        if ocr_res:
                            lines = [item[1] for item in ocr_res if item and len(item) > 1]
                            page_text = "\n".join(lines)
                    except Exception as ocr_err:
                        print(f"[hybrid_ocr] Page {page_idx+1} OCR fallback failed: {ocr_err}")
                if page_text:
                    text += f"--- PAGE {page_idx+1} ---\n" + page_text + "\n\n"
    except Exception as e:
        print(f"[extract_text] Failed: {e}")

    if not text.strip():
        # Fallback to pdfplumber text iteration if pypdfium2 failed
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    pt = page.extract_text()
                    if pt:
                        text += pt + "\n"
        except Exception:
            pass

    if text.strip():
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    return text


def pdf_has_text_layer(file_path, min_chars=40):
    """True if the PDF has a usable embedded text layer. Used to reject image-only
    PDFs up front with a clear message instead of parsing garbage."""
    try:
        return len((extract_text_from_PDF(file_path) or "").strip()) >= min_chars
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT SORTER — AI-first per-page classifier for uncleaned bundles
# A downloaded deed PDF is a bundle of many documents. This labels every page,
# then groups them into (a) the deed INSTRUMENT (goes to the title parser) and
# (b) SUPPORTING documents (filed separately). Text-only; no OCR.
# ─────────────────────────────────────────────────────────────────────────────
SORTER_DOC_TYPES = [
    # instrument body types
    "SALE_DEED", "CONVEYANCE_DEED", "GIFT_DEED", "MORTGAGE_DEED", "RELEASE_DEED",
    "LEAVE_LICENSE", "AGREEMENT_TO_SELL", "GPA",
    # instrument-attached pages
    "E_STAMP", "REGISTRATION_ENDORSEMENT",
    # supporting documents
    "PAN_CARD", "AADHAAR_CARD", "PASSPORT", "VOTER_ID", "DRIVING_LICENSE",
    "ELECTRICITY_BILL", "GAS_BILL", "WATER_BILL", "PROPERTY_TAX_RECEIPT",
    "FORM_A", "UNDERTAKING", "NOC", "SANCTION_PLAN", "MUTATION",
    # catch-alls
    "BLANK", "OTHER",
]

# Types that make up the refined deed instrument (everything else is supporting).
SORTER_INSTRUMENT_TYPES = {
    "SALE_DEED", "CONVEYANCE_DEED", "GIFT_DEED", "MORTGAGE_DEED", "RELEASE_DEED",
    "LEAVE_LICENSE", "AGREEMENT_TO_SELL", "GPA", "E_STAMP", "REGISTRATION_ENDORSEMENT",
}

SORTER_TYPE_LABELS = {
    "SALE_DEED": "Sale Deed", "CONVEYANCE_DEED": "Conveyance Deed", "GIFT_DEED": "Gift Deed",
    "MORTGAGE_DEED": "Mortgage Deed", "RELEASE_DEED": "Release Deed",
    "LEAVE_LICENSE": "Leave & License", "AGREEMENT_TO_SELL": "Agreement to Sell", "GPA": "Power of Attorney",
    "E_STAMP": "e-Stamp Certificate", "REGISTRATION_ENDORSEMENT": "Registration Endorsement",
    "PAN_CARD": "PAN Card", "AADHAAR_CARD": "Aadhaar Card", "PASSPORT": "Passport",
    "VOTER_ID": "Voter ID", "DRIVING_LICENSE": "Driving License",
    "ELECTRICITY_BILL": "Electricity Bill", "GAS_BILL": "Gas Bill", "WATER_BILL": "Water Bill",
    "PROPERTY_TAX_RECEIPT": "Property Tax Receipt", "FORM_A": "Form-A",
    "UNDERTAKING": "Undertaking", "NOC": "NOC", "SANCTION_PLAN": "Sanction Plan",
    "MUTATION": "Mutation", "BLANK": "Blank Page", "OTHER": "Other Document",
}


def _extract_pages_text(file_path):
    """Return a list of per-page text (empty string for pages with no text layer)."""
    pages = []
    with pdfplumber.open(file_path) as pdf:
        for pg in pdf.pages:
            pages.append(pg.extract_text() or "")
    return pages


def classify_bundle_pages(file_path, snippet_chars=900):
    """AI-FIRST page classifier for an uncleaned bundle PDF.

    Sends every page's text to the model in one strict pass and returns a manifest:
    {
      "total_pages": int,
      "pages": [{page, type, is_deed_instrument, is_blank, confidence, reason}],
      "instrument": {"type": <body type or None>, "pages": [ints]},
      "supporting": [{"type", "label", "pages":[ints]}],
      "blanks": [ints],
    }
    Defensive: pages with no text are forced BLANK; unknown/garbled labels become
    OTHER; missing pages are backfilled — the caller always gets one row per page.
    """
    pages_text = _extract_pages_text(file_path)
    n = len(pages_text)

    blocks = []
    for i, t in enumerate(pages_text):
        snip = re.sub(r"\s+", " ", (t or "").strip())[:snippet_chars]
        blocks.append(f"===== PAGE {i+1} =====\n{snip or '(no extractable text)'}")
    joined = "\n\n".join(blocks)

    prompt = f"""You are a STRICT document-sorting engine for Indian property registration bundles.
A bundle is ONE PDF that concatenates MANY documents: the main registrable instrument
(Sale Deed / Conveyance / Gift / Mortgage / Release / Lease / Agreement to Sell / GPA), its
e-Stamp certificate, the Sub-Registrar / DORIS registration endorsement, plus supporting
documents (PAN cards, Aadhaar cards, electricity / gas / water bills, property-tax receipts,
Form-A, undertakings), and blank pages.

Classify EVERY page below into EXACTLY ONE type from this list:
{", ".join(SORTER_DOC_TYPES)}

Rules:
- Decide ONLY from the page text shown. Do NOT invent or assume.
- A page with essentially no meaningful text is BLANK.
- e-Stamp certificate page(s) -> E_STAMP. The registration receipt / "Certificate (Section 60)" /
  DORIS presenter/endorsement page -> REGISTRATION_ENDORSEMENT.
- For a multi-page instrument, label EVERY page of the deed body with the instrument type
  (including continuation pages like "PAGE No. X OF SALE DEED").
- If a page is genuinely unrecognizable, use OTHER. Never guess a specific type you cannot justify.
- confidence is your certainty 0.0-1.0. reason is <= 12 words.

Return ONLY a JSON array — one object per page, in page order, no prose, no code fences:
[{{"page": 1, "type": "E_STAMP", "confidence": 0.95, "reason": "India Non-Judicial e-Stamp certificate"}}]

PAGES:
{joined}
"""

    arr = []
    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = resp.text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
        arr = json.loads(raw)
    except Exception as e:
        print("[classify_bundle] classification failed:", e)
        arr = []

    by_page = {}
    for o in arr:
        if isinstance(o, dict) and o.get("page") is not None:
            try:
                by_page[int(o["page"])] = o
            except (ValueError, TypeError):
                pass

    pages = []
    for i in range(1, n + 1):
        o = by_page.get(i, {})
        typ = str(o.get("type") or "OTHER").upper().strip()
        if typ not in SORTER_DOC_TYPES:
            typ = "OTHER"
        if not pages_text[i - 1].strip():   # no text at all -> definitively blank
            typ = "BLANK"
        try:
            conf = float(o.get("confidence"))
        except (ValueError, TypeError):
            conf = 0.0
        pages.append({
            "page": i,
            "type": typ,
            "label": SORTER_TYPE_LABELS.get(typ, typ.title()),
            "is_blank": typ == "BLANK",
            "is_deed_instrument": typ in SORTER_INSTRUMENT_TYPES,
            "confidence": round(max(0.0, min(1.0, conf)), 2),
            "reason": str(o.get("reason") or "")[:120],
        })

    from collections import Counter
    body_counts = Counter(
        p["type"] for p in pages
        if p["is_deed_instrument"] and p["type"] not in ("E_STAMP", "REGISTRATION_ENDORSEMENT")
    )
    instrument_type = body_counts.most_common(1)[0][0] if body_counts else None
    # Smart Instrument & Supporting Sorter Logic:
    # 1. Dedicated supporting documents (PAN, Aadhaar, Electricity Bill, Tax Receipt, Sanction Plan, etc.) remain SORTED OUT as supporting files.
    # 2. Scanned deed pages (photo recitals, thumbprints, witness signature pages, map schedules) are retained as DEED_INSTRUMENT.
    # 3. Only true empty scanner sheets are marked BLANK.
    for idx, p in enumerate(pages):
        # Do not override explicitly identified supporting documents
        if p["type"] in ("PAN_CARD", "AADHAAR_CARD", "PASSPORT", "VOTER_ID", "DRIVING_LICENSE",
                         "ELECTRICITY_BILL", "GAS_BILL", "WATER_BILL", "PROPERTY_TAX_RECEIPT",
                         "FORM_A", "UNDERTAKING", "NOC", "SANCTION_PLAN", "MUTATION"):
            p["is_deed_instrument"] = False
            continue

        # If a page has low text but falls inside the deed flow (between e-Stamp and Endorsement),
        # it is a scanned deed photo/signature page — retain as deed instrument!
        if p["type"] in ("OTHER", "BLANK") and not pages_text[idx].strip():
            # If surrounded by deed instrument pages, it is part of the deed body
            prev_is_deed = (idx > 0 and pages[idx-1]["is_deed_instrument"])
            next_is_deed = (idx < n - 1 and pages[idx+1]["is_deed_instrument"])
            if prev_is_deed or next_is_deed:
                p["is_deed_instrument"] = True
                p["type"] = instrument_type or "SALE_DEED"
                p["label"] = SORTER_TYPE_LABELS.get(p["type"], "Deed Instrument")
                p["is_blank"] = False

    instrument_pages = [p["page"] for p in pages if p["is_deed_instrument"]]

    # Group supporting docs into consecutive runs of the same type
    supporting, run = [], None
    for p in pages:
        if p["is_deed_instrument"] or p["is_blank"]:
            if run:
                supporting.append(run); run = None
            continue
        if run and run["type"] == p["type"]:
            run["pages"].append(p["page"])
        else:
            if run:
                supporting.append(run)
            run = {"type": p["type"], "label": p["label"], "pages": [p["page"]]}
    if run:
        supporting.append(run)

    return {
        "total_pages": n,
        "pages": pages,
        "instrument": {
            "type": instrument_type,
            "label": SORTER_TYPE_LABELS.get(instrument_type, "Deed Instrument") if instrument_type else "Deed Instrument",
            "pages": instrument_pages,
        },
        "supporting": supporting,
        "blanks": [p["page"] for p in pages if p["is_blank"]],
    }


# ─────────────────────────────────────────────────────────────────────────────
# DEED CLASSIFICATION TAXONOMY
# Single source of truth for what deed sub-types DelhiTSR recognizes.
# Synonyms cover the regional/legacy variants we've seen in Indian deeds.
# ─────────────────────────────────────────────────────────────────────────────
DEED_SUBTYPES = {
    "index_ii":              ["index ii", "index 2", "index-ii", "index-2", "extract from index ii", "form-i & xiv index ii"],
    "sale_absolute":         ["sale deed", "deed of sale", "conveyance deed", "deed of conveyance", "deed of absolute sale", "absolute sale deed"],
    "sale_conditional":      ["conditional sale deed", "sale with condition", "agreement of sale", "agreement for sale"],
    "mortgage_simple":       ["mortgage deed", "deed of mortgage", "simple mortgage deed", "deed of simple mortgage", "registered mortgage"],
    "mortgage_equitable":    ["memorandum of deposit of title deeds", "mdtd", "equitable mortgage", "deposit of title deeds", "intimation of mortgage"],
    "mortgage_english":      ["english mortgage", "english mortgage deed"],
    "mortgage_conditional":  ["mortgage by conditional sale"],
    "release_mortgage":      ["release of mortgage", "deed of reconveyance", "satisfaction of mortgage", "mortgage discharge deed", "deed of discharge", "release deed mortgage"],
    "release_family":        ["family release deed", "relinquishment deed", "deed of relinquishment", "release deed family"],
    "release_partition":     ["partition release", "partition deed"],
    "release_settlement":    ["settlement release"],
    "gift_inter_vivos":      ["gift deed", "deed of gift", "settlement deed", "hiba", "deed of hiba"],
    "leave_license":         ["leave and license", "leave & license", "licence agreement", "license agreement"],
    "exchange":              ["exchange deed", "deed of exchange"],
    "other":                 [],
}


def classify_deed(document_text):
    """
    Stage 1: cheap classifier call using gemini-3.1-flash-lite.
    Returns: {"subtype": "<key from DEED_SUBTYPES>", "confidence": "high|medium|low",
              "reasoning": "<short>", "runners_up": [<keys>]}

    Confidence is the model's own self-report. If 'low', the caller should
    treat the document as provisional — needing human classification — and
    skip full extraction until confirmed.
    """
    # Truncate to first ~6000 chars — deed type is always declared up top.
    sample = (document_text or "")[:6000]

    # Build the synonym graph for the prompt so the LLM maps regional variants
    # ("Settlement Deed" → gift_inter_vivos in TN; "MDTD" → mortgage_equitable) deterministically.
    synonym_lines = []
    for subtype, syns in DEED_SUBTYPES.items():
        if syns:
            synonym_lines.append(f"  {subtype}: {', '.join(syns)}")
        else:
            synonym_lines.append(f"  {subtype}: (fallback — only if nothing else fits)")

    prompt = f"""You classify Indian property deeds. Return ONLY a JSON object — no markdown, no prose.

TASK
Identify which deed sub-type best matches the document. Use the synonym graph below:
{chr(10).join(synonym_lines)}

CRITICAL NOTES
- "Release Deed" alone is ambiguous. Distinguish:
    release_mortgage   → discharges a registered mortgage (references original mortgage doc number / bank releasor)
    release_family     → heir/co-owner relinquishing claim to another (ownership transfer between family members)
    release_partition  → release as part of a partition between co-owners
    release_settlement → release as part of settling a dispute
- "Settlement Deed" in Tamil Nadu usage typically means a gift → gift_inter_vivos.
- "Memorandum of Deposit of Title Deeds" / "MDTD" → mortgage_equitable (usually unregistered).
- "Index II" is the government extract summary, NOT the underlying deed itself.

SEMANTIC RELATIONSHIP & COVENANT GUIDELINES (WHEN EXPLICIT TITLE IS ABSENT OR GENERAL):
- Do NOT rely solely on the document's title. If a document has a generic title (e.g. "DEED", "AGREEMENT", "MEMORANDUM"), analyze the underlying legal relationship and transactions:
  - MORTGAGE: If it is between a Borrower (debtor) and a Bank/Lender (creditor), and describes depositing original title deeds (e.g. sale deed, allotment letter) or creating a charge on the property to secure a loan/credit facility, classify it as a mortgage (e.g., mortgage_equitable or mortgage_simple).
  - RELEASE/RECONVEYANCE: If it is executed by a bank/lender releasing/reconveying the property, returning title deeds, or declaring a loan/mortgage has been fully satisfied/discharged, classify it as release_mortgage.
  - RELINQUISHMENT: If family members (co-owners or heirs) release, relinquish, or renounce their rights/shares to another out of love and affection without consideration, classify it as release_family.
  - SALE/CONVEYANCE: If it absolutely transfers property ownership for a sale price/consideration, classify it as sale_absolute.
  - LEAVE & LICENSE: If it grants a temporary right to occupy for a short term with license fees and security deposit, classify it as leave_license.

CONFIDENCE
- "high"   = the deed title, recitals, or core covenants clearly indicate one subtype, no ambiguity
- "medium" = the deed title is generic/missing but covenants/relationships are clear, OR subtype is inferred from context
- "low"    = title is missing/ambiguous, covenants are unclear, multiple subtypes are plausible

OUTPUT JSON
{{
  "subtype": "<one of the keys above>",
  "confidence": "high|medium|low",
  "reasoning": "<one short sentence — what tipped the decision>",
  "runners_up": ["<other plausible keys, if any>"]
}}

DOCUMENT (first 6000 chars):
{sample}
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )
        raw = (response.text or "").strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        result = json.loads(raw)
    except Exception as e:
        # On any failure we fall back to provisional/low so the file goes to manual review.
        print("classify_deed: classifier failed:", e)
        return {
            "subtype": "other",
            "confidence": "low",
            "reasoning": f"classifier error: {type(e).__name__}",
            "runners_up": [],
        }

    # Defensive normalization — coerce unexpected values to safe defaults.
    sub = result.get("subtype") or "other"
    if sub not in DEED_SUBTYPES:
        sub = "other"
    conf = result.get("confidence") or "low"
    if conf not in ("high", "medium", "low"):
        conf = "low"

    # Semantic keyword rescue fallback if classifier returns 'other'
    doc_text_lower = (document_text or "").lower()
    if sub == "other":
        if any(w in doc_text_lower for w in ["deposit of title deeds", "mdtd", "equitable mortgage", "mortgagor", "loan account", "principal amount"]) and any(w in doc_text_lower for w in ["bank", "lender", "cooperative"]):
            sub = "mortgage_equitable"
            conf = "medium"
            result["reasoning"] = "Rescued via loan/charge keywords to mortgage_equitable."
        elif any(w in doc_text_lower for w in ["reconveyance", "discharge of mortgage", "releasing the mortgage", "satisfaction of charge"]):
            sub = "release_mortgage"
            conf = "medium"
            result["reasoning"] = "Rescued via reconveyance/discharge keywords to release_mortgage."
        elif any(w in doc_text_lower for w in ["relinquishment deed", "deed of relinquishment", "relinquish", "releasor"]):
            sub = "release_family"
            conf = "medium"
            result["reasoning"] = "Rescued via relinquishment/release keywords to release_family."

    return {
        "subtype":    sub,
        "confidence": conf,
        "reasoning":  (result.get("reasoning") or "")[:300],
        "runners_up": result.get("runners_up") or [],
    }


def get_category_from_subtype(subtype):
    if not subtype:
        return "generic"
    sub = subtype.lower()
    if "release" in sub or "reconveyance" in sub or "relinquishment" in sub or "discharge" in sub:
        if "family" in sub or "relinquishment" in sub:
            return "generic"
        return "release"
    elif "sale" in sub or "agreement" in sub:
        return "sale"
    elif "mortgage" in sub or "mdtd" in sub or "equitable" in sub or "intimation" in sub:
        return "mortgage"
    elif "gift" in sub or "hiba" in sub:
        return "gift"
    elif "leave" in sub or "license" in sub:
        return "leave_license"
    return "generic"


def classify_locality_category(address, locality):
    prompt = f"""You are an expert on Delhi property registration law and circle rate categories.
The Government of Delhi divides all residential colonies and villages into 8 categories (A to H).

Reference Guidelines:
- Category A (Premium): Vasant Vihar, Golf Links, Jor Bagh, Maharani Bagh, Panchsheel Park, Friends Colony, Shanti Niketan, Sunder Nagar, West End, Anand Niketan, Chanakyapuri.
- Category B (Very High): Hauz Khas, Hauz Khas Enclave, Defence Colony, Greater Kailash I/II/III/IV, Safdarjung Enclave, Gulmohar Park, Green Park, South Extension, Anand Lok, Nizamuddin East.
- Category C (High): Lajpat Nagar, Karol Bagh, Patel Nagar, Alaknanda, Kalkaji, Chittaranjan Park (CR Park), Malviya Nagar, East of Kailash, Vasant Kunj, Munirka.
- Category D (Moderate): Dwarka, Rohini, Daryaganj, Pitampura, Laxmi Nagar, Shalimar Bagh, Paschim Vihar, Janakpuri, Hari Nagar, Kirti Nagar, Mayur Vihar.
- Category E (Low-Moderate): Chandni Chowk, Dilshad Garden, Hauz Qazi, Geeta Colony, Pahar Ganj.
- Category F (Low): Anand Vihar, Nand Nagri, Majnu ka Tila, Yamuna Vihar, Nehru Place.
- Category G (Very Low): Ambedkar Nagar, Jahangirpuri, Sultanpuri, Dakshinpuri, Sangam Vihar.
- Category H (Rural): Sultanpur Majra, rural agricultural lands.

Given the property address: "{address}" and locality: "{locality}"
Classify it into the correct category. Return ONLY the category letter ("A", "B", "C", "D", "E", "F", "G", "H") or "null".
Do not write any explanation or markdown. Return exactly one character.
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        cat = response.text.strip().upper()
        if len(cat) == 1 and cat in "ABCDEFGH":
            return cat
    except Exception as e:
        print("Error during specialized locality classification:", e)
    return None


def parse_index_ii(file_path, forced_subtype=None):
    document_text = extract_text_from_PDF(file_path)

    # ── STAGE 1: classify the document ──────────────────────────────────
    if forced_subtype:
        classification = {
            "subtype": forced_subtype,
            "confidence": "high",
            "reasoning": "human-confirmed",
            "runners_up": []
        }
    else:
        classification = classify_deed(document_text)

    if classification["confidence"] == "low" and not forced_subtype:
        return {
            "_provisional":                 True,
            "_needs_human_classification":  True,
            "_classification":              classification,
            "document_type":                None,
            "txn_type":                     None,
        }

    subtype = classification["subtype"]
    category = get_category_from_subtype(subtype)

    # Build prompts dynamically based on category
    schemas = {
        "sale": """
═══════════════════════════════════════════════════════════
SALE DEED / AGREEMENT OF SALE SPECIFIC FIELDS
═══════════════════════════════════════════════════════════
- consideration                   (the sale price / consideration amount in numbers, e.g. 5000000)
- consideration_words             (the sale price in words, e.g. "Fifty Lakhs Only")
- consideration_words_numeric     (the exact numeric value represented by the consideration-in-words text, e.g. 5000000)
""",
        "mortgage": """
═══════════════════════════════════════════════════════════
MORTGAGE DEED SPECIFIC FIELDS
═══════════════════════════════════════════════════════════
- principal_amount_figures        (the mortgage loan principal in numbers, e.g. 2500000)
- principal_amount_words          (the mortgage loan principal in words, e.g. "Twenty Five Lakhs Only")
- principal_amount_words_numeric  (the exact numeric value represented by the principal-amount-in-words text, e.g. 2500000)
- loan_account_no                 (the loan account number / LAN, if cited in the deed, e.g. "LH-123456")
- interest_rate                   (the interest rate, e.g. "9.5% per annum")
- tenure                          (the repayment tenure, e.g. "120 months")
""",
        "release": """
═══════════════════════════════════════════════════════════
RELEASE DEED SPECIFIC FIELDS (discharging a mortgage)
═══════════════════════════════════════════════════════════
- released_mortgage_doc_no        (the registration number of the ORIGINAL mortgage being released, if cited, e.g. "4521/2020")
- released_mortgage_date          (the execution or registration date of the original mortgage being released, if cited, DD-MM-YYYY)
- released_mortgage_sro           (the name of the Sub-Registrar Office where the original mortgage was registered, if cited, e.g. "Haveli No. 3")
- released_mortgage_year          (the registration year of the original mortgage being released, if cited, e.g. 2020)
- released_mortgage_principal_figures (the principal amount of the original mortgage in numbers, e.g. 5000000)
- released_mortgage_principal_words   (the principal amount of the original mortgage in words, e.g. "Fifty Lakhs Only")
- released_mortgage_principal_words_numeric (the exact numeric value represented by the original mortgage principal words text, e.g. 5000000)
- released_mortgage_mortgagor_names   (list of names of original borrowers/mortgagors, if cited)
- released_mortgage_mortgee_names     (list of names of original lenders/mortgagees/banks, if cited)
- release_type                    (MUST be one of: "full", "partial_amount", "partial_parcel", "partial_party", "conditional")
- released_amount_figures         (for partial releases, the amount being released in numbers, e.g. 1000000)
- released_amount_words           (for partial releases, the amount being released in words, e.g. "Ten Lakhs Only")
- released_amount_words_numeric   (the exact numeric value represented by the released-amount-in-words text, e.g. 1000000)
- loan_account_no                 (the loan account number / LAN, if cited in the deed, e.g. "LH-123456")
""",
        "leave_license": """
═══════════════════════════════════════════════════════════
LEAVE & LICENSE SPECIFIC FIELDS
═══════════════════════════════════════════════════════════
- deposit                         (security deposit in numbers, e.g. 100000)
- license_fee                     (monthly license fee, e.g. 15000)
- leave_license_months            (duration in months, e.g. 11)
""",
        "generic": ""
    }

    schema_part = schemas.get(category, "")

def _call_gemini_json(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[_call_gemini_json] Error: {e}")
        return {}


def _extract_pass_1_identity_and_stamps(document_text):
    prompt = f"""
You are a specialized legal document identity & registration stamp extraction engine.
Read the document text and extract EXACTLY these 20 fields as raw valid JSON:
1. document_type (SALE_DEED, CONVEYANCE_DEED, GIFT_DEED, MORTGAGE_DEED, RELEASE_DEED, LEAVE_AND_LICENSE, AGREEMENT_OF_SALE, null)
2. txn_type (SAME AS document_type)
3. sub_registrar_office (e.g. "SRO V-A (Hauz Khas), New Delhi")
4. registration_no
5. registration_year
6. doc_no (registration_no/registration_year e.g. "123/1995")
7. date_of_execution (DD-MM-YYYY)
8. date_of_registration (DD-MM-YYYY)
9. estamp_certificate_no (e.g. "IN-DL44237927139351V" or null)
10. estamp_issued_datetime (e.g. "15-Jan-1995 11:30 AM" or null)
11. estamp_amount (numeric value of e-Stamp purchased)
12. estamp_first_party (name printed as first party on stamp)
13. estamp_second_party (name printed as second party on stamp)
14. estamp_duty_paid_by (who paid stamp duty)
15. estamp_description (e.g. "Article 23 Conveyance")
16. stamp_type ("E_STAMP", "PHYSICAL_STAMP", "FRANKING", "TREASURY_CHALLAN", null)
17. franking_machine_number
18. treasury_challan_grn
19. reg_book_no
20. reg_volume_no

Return ONLY valid JSON.

DOCUMENT TEXT:
{document_text}
"""
    return _call_gemini_json(prompt)


def _extract_pass_2_parties_and_kyc(document_text):
    prompt = f"""
You are a specialized legal party & KYC recital extraction engine for Indian property deeds.
Extract party identity & KYC details as raw valid JSON:
- transferor_parties: list of objects on the GIVING side (sellers/donors/mortgagors/releasors).
  Each object: {{"name", "role", "gender", "age", "dob", "pan", "pin", "aadhaar", "father_or_husband", "address"}}
- transferee_parties: list of objects on the RECEIVING side (buyers/donees/mortgagees/releasees).
  Each object: {{"name", "role", "gender", "age", "dob", "pan", "pin", "aadhaar", "father_or_husband", "address"}}
- parties: unified list of ALL party objects with their fields.
- seller_names: list of seller/transferor name strings.
- buyer_names: list of buyer/transferee name strings.
- seller_address: seller address string.
- buyer_address: buyer address string.
- transferor_pan: list of seller PAN strings.
- transferor_pin: list of seller PIN strings.
- transferee_pan: list of buyer PAN strings.
- transferee_pin: list of buyer PIN strings.

RULE FOR AADHAAR: For Aadhaar, extract exact digits or masked format (e.g. "XXXX-XXXX-9661"). If illegible or unstated, return null. NEVER guess.

Return ONLY valid JSON.

DOCUMENT TEXT:
{document_text}
"""
    return _call_gemini_json(prompt)


def _extract_pass_3_financials_and_payments(document_text, category):
    prompt = f"""
You are a specialized financial consideration, payment trail & tax audit extraction engine.
Extract financial breakdown & payment details as raw valid JSON:
- consideration (sale consideration price in numbers, e.g. 5000000)
- consideration_words (consideration price in words)
- consideration_words_numeric (exact numeric value represented by words)
- stamp_duty (TOTAL stamp duty paid for the transaction. CRITICAL: In Delhi/Indian deeds, stamp duty is often split into Statutory Stamp Duty e.g. 3% (Rs.3,00,000) and Municipal Corporation / MCD Tax e.g. 3% (Rs.3,00,000), or reported on Sub-Registrar Endorsement page as 600,000. Output the COMBINED TOTAL e.g. 600000 or the Total Non-Judicial Stamp Paper value. Do NOT output just the partial 3% component.)
- registration_fee (actual registration fee paid, numeric e.g. 100000)
- market_value (numeric or null)
- payment_instruments: list of payment objects [ {{"amount": numeric, "mode": "cheque|rtgs|dd|cash", "instrument_no": str, "bank": str, "date": str}} ]
- tds_challans: list of Form 26QB TDS deposit objects [ {{"amount": numeric, "challan_no": str, "bsr_code": str, "serial_no": str, "date": str, "bank": str}} ]
- corporation_tax_amount (MCD transfer tax e.g. 300000, numeric or null)
- corporation_tax_rate (e.g. "3%")
- stamp_duty_rate (e.g. "6%")
- total_non_judicial_stamp (total stamp paper value e.g. 600000)
- principal_amount_figures (if mortgage)
- principal_amount_words (if mortgage)
- loan_account_no (if mortgage/release)

Return ONLY valid JSON.

DOCUMENT TEXT:
{document_text}
"""
    return _call_gemini_json(prompt)


def _extract_pass_4_property_and_chain(document_text):
    prompt = f"""
You are a specialized property schedule & title chain extraction engine.
Extract property boundaries, schedule & title chain recitals as raw valid JSON:
- survey_no / plot_no / cts_no / khasra_no
- society_building_name
- society_building_address (full address)
- flat_no (ONLY flat number e.g. "8")
- area (stated area with unit e.g. "1200 sq.ft.")
- property_type ("dda_flat", "private_flat", "plot", null)
- buyer_gender ("male", "female", "joint", null)
- construction_year (integer or null)
- village / district
- mcd_upic (MCD Unique Property ID Code)
- boundary_north / boundary_south / boundary_east / boundary_west
- property_schedule_text (verbatim schedule description paragraph)
- chain_recitals: list of prior registered instruments [ {{"instrument_type": str, "doc_no": str, "execution_date": str, "from_parties": str, "to_parties": str}} ]
- title_root (origin of title e.g. "President of India / DDA Allotment")
- is_root_deed (true / false)

Return ONLY valid JSON.

DOCUMENT TEXT:
{document_text}
"""
    return _call_gemini_json(prompt)


def parse_index_ii(file_path, forced_subtype=None):
    document_text = extract_text_from_PDF(file_path)

    # ── STAGE 1: classify the document ──────────────────────────────────
    if forced_subtype:
        classification = {
            "subtype": forced_subtype,
            "confidence": "high",
            "reasoning": "human-confirmed",
            "runners_up": []
        }
    else:
        classification = classify_deed(document_text)

    if classification["confidence"] == "low" and not forced_subtype:
        return {
            "_provisional":                 True,
            "_needs_human_classification":  True,
            "_classification":              classification,
            "document_type":                None,
            "txn_type":                     None,
        }

    subtype = classification["subtype"]
    category = get_category_from_subtype(subtype)

    # ── STAGE 2: 4-Endpoint Modular Extraction Passes ───────────────────
    pass1 = _extract_pass_1_identity_and_stamps(document_text)
    pass2 = _extract_pass_2_parties_and_kyc(document_text)
    pass3 = _extract_pass_3_financials_and_payments(document_text, category)
    pass4 = _extract_pass_4_property_and_chain(document_text)

    # Merge all 4 endpoint JSON outputs into unified ACT_data dictionary
    ACT_data = {}
    ACT_data.update(pass1)
    ACT_data.update(pass2)
    ACT_data.update(pass3)
    ACT_data.update(pass4)

    # Programmatic Reconciliation for Combined Stamp Duty (SD + MCD Tax / Endorsement Stamp Duty)
    try:
        sd_val = float(re.sub(r"[^\d.]", "", str(ACT_data.get("stamp_duty") or 0))) if ACT_data.get("stamp_duty") != "ALERT" else 0.0
    except Exception:
        sd_val = 0.0
    try:
        mcd_val = float(re.sub(r"[^\d.]", "", str(ACT_data.get("corporation_tax_amount") or ACT_data.get("mcd_transfer_tax") or 0)))
    except Exception:
        mcd_val = 0.0
    try:
        total_stamp_paper = float(re.sub(r"[^\d.]", "", str(ACT_data.get("total_non_judicial_stamp") or 0)))
    except Exception:
        total_stamp_paper = 0.0
    try:
        estamp_amt = float(re.sub(r"[^\d.]", "", str(ACT_data.get("estamp_amount") or 0)))
    except Exception:
        estamp_amt = 0.0

    # Determine exact total stamp duty paid without double-counting
    if total_stamp_paper > 0:
        best_sd = total_stamp_paper
    elif estamp_amt > 0:
        best_sd = estamp_amt
    elif mcd_val > 0:
        best_sd = sd_val + mcd_val if sd_val <= mcd_val * 1.2 else sd_val
    else:
        best_sd = sd_val

    if best_sd > 0:
        ACT_data["stamp_duty"] = int(round(best_sd))
        ACT_data["total_stamp_duty"] = int(round(best_sd))

    ACT_data["_provisional"]                = False
    ACT_data["_needs_human_classification"] = False
    ACT_data["_classification"]             = classification

    # Call specialized locality classifier
    addr = ACT_data.get("society_building_address") or ""
    loc = ACT_data.get("society_building_name") or ""
    if addr or loc:
        category_char = classify_locality_category(addr, loc)
        if category_char:
            ACT_data["locality_category"] = category_char

        # Normalize document_type and txn_type based on the classification
        if category == "sale":
            ACT_data["txn_type"] = "SALE_DEED" if "absolute" in subtype else "AGREEMENT_OF_SALE"
            ACT_data["document_type"] = ACT_data["txn_type"]
        elif category == "mortgage":
            ACT_data["txn_type"] = "MORTGAGE_DEED" if "simple" in subtype or "registered" in subtype else "INTIMATION_OF_MORTGAGE"
            ACT_data["document_type"] = ACT_data["txn_type"]
        elif category == "release":
            ACT_data["txn_type"] = "RELEASE_DEED"
            ACT_data["document_type"] = "RELEASE_DEED"
        elif category == "gift":
            ACT_data["txn_type"] = "GIFT_DEED"
            ACT_data["document_type"] = "GIFT_DEED"
        elif category == "leave_license":
            ACT_data["txn_type"] = "LEAVE_AND_LICENSE"
            ACT_data["document_type"] = "LEAVE_AND_LICENSE"
        else:
            if "index" in subtype:
                ACT_data["document_type"] = "INDEX_II"
            else:
                ACT_data["document_type"] = ACT_data.get("document_type") or "NULL"
            if not ACT_data.get("txn_type"):
                ACT_data["txn_type"] = "NULL"

        # Populate legacy flat fields in Python to guarantee backward compatibility
        transferor_parties = ACT_data.get("transferor_parties") or []
        transferee_parties = ACT_data.get("transferee_parties") or []

        # Fallback to general 'parties' list if transferor/transferee split lists are empty
        all_parties = ACT_data.get("parties") or []
        if isinstance(all_parties, list) and not transferor_parties and not transferee_parties:
            for p in all_parties:
                if isinstance(p, dict):
                    role = str(p.get("role") or "").upper()
                    if any(r in role for r in ["VENDOR", "SELLER", "DONOR", "LESSOR", "LICENSOR", "MORTGAGOR", "TRANSFEROR", "FIRST", "1ST"]):
                        transferor_parties.append(p)
                    elif any(r in role for r in ["VENDEE", "BUYER", "DONEE", "LESSEE", "LICENSEE", "MORTGAGEE", "TRANSFEREE", "SECOND", "2ND"]):
                        transferee_parties.append(p)

        transferor_parties = [p for p in transferor_parties if isinstance(p, dict)]
        transferee_parties = [p for p in transferee_parties if isinstance(p, dict)]

        transferor_names = [p.get("name") for p in transferor_parties if p.get("name")]
        transferee_names = [p.get("name") for p in transferee_parties if p.get("name")]

        txn = (ACT_data.get("txn_type") or "").upper()
        if "SALE" in txn or "AGREEMENT" in txn or "RELEASE" in txn:
            ACT_data["seller_names"] = transferor_names
            ACT_data["buyer_names"] = transferee_names
            if transferor_parties:
                ACT_data["seller_address"] = transferor_parties[0].get("address")
            if transferee_parties:
                ACT_data["buyer_address"] = transferee_parties[0].get("address")
        elif "GIFT" in txn:
            if transferor_names:
                ACT_data["donor_name"] = transferor_names[0]
            if transferor_parties:
                ACT_data["donor_address"] = transferor_parties[0].get("address")
            if transferee_names:
                ACT_data["donee_name"] = transferee_names[0]
            if transferee_parties:
                ACT_data["donee_address"] = transferee_parties[0].get("address")
        elif "MORTGAGE" in txn or "INTIMATION" in txn:
            if transferor_names:
                ACT_data["mortgagor_name"] = transferor_names[0]
            if transferor_parties:
                ACT_data["mortgagor_address"] = transferor_parties[0].get("address")
            if transferee_names:
                ACT_data["mortgagee_name"] = transferee_names[0]
            if transferee_parties:
                ACT_data["mortgagee_branch_address"] = transferee_parties[0].get("address")
        elif "LEAVE" in txn or "LICENSE" in txn:
            if transferor_names:
                ACT_data["licensor_name"] = transferor_names[0]
            if transferor_parties:
                ACT_data["licensor_address"] = transferor_parties[0].get("address")
            if transferee_names:
                ACT_data["licensee_name"] = transferee_names[0]
            if transferee_parties:
                ACT_data["licensee_address"] = transferee_parties[0].get("address")

        # Flat lists of PAN/PIN
        ACT_data["transferor_pan"] = [p.get("pan") for p in transferor_parties if p.get("pan")]
        ACT_data["transferor_pin"] = [p.get("pin") for p in transferor_parties if p.get("pin")]
        ACT_data["transferee_pan"] = [p.get("pan") for p in transferee_parties if p.get("pan")]
        ACT_data["transferee_pin"] = [p.get("pin") for p in transferee_parties if p.get("pin")]

        # ── New structured blocks: guarantee presence + derive SAFE totals ──
        # Everything here is defensive so the downstream audit never sees a
        # malformed shape and never receives a total derived from illegible data.
        def _to_number(v):
            """Best-effort numeric parse. Returns float or None. Never raises."""
            if v is None:
                return None
            if isinstance(v, bool):
                return None
            if isinstance(v, (int, float)):
                return float(v)
            s = re.sub(r"[^\d.]", "", str(v))
            if not s or s == ".":
                return None
            try:
                return float(s)
            except ValueError:
                return None

        def _digits_only(v):
            if v is None:
                return None
            d = re.sub(r"\D", "", str(v))
            return d or None

        # Ensure list/object fields exist so downstream audit code is null-safe.
        for _lst in ("payment_instruments", "tds_challans", "chain_recitals",
                     "witnesses", "annexed_id_proofs", "utility_bills"):
            if not isinstance(ACT_data.get(_lst), list):
                ACT_data[_lst] = []
        for _obj in ("property_tax", "form_a", "undertaking"):
            if not isinstance(ACT_data.get(_obj), dict):
                ACT_data[_obj] = None

        # Normalize Aadhaar to 12-digit strings on every person object; anything
        # that isn't a clean 12-digit value becomes None (never a partial guess).
        # Masking/encryption happens later at the storage layer (app.py).
        for _p in transferor_parties + transferee_parties + ACT_data["witnesses"]:
            if isinstance(_p, dict) and _p.get("aadhaar") is not None:
                d = _digits_only(_p.get("aadhaar"))
                _p["aadhaar"] = d if (d and len(d) == 12) else None
        for _idp in ACT_data["annexed_id_proofs"]:
            if isinstance(_idp, dict) and str(_idp.get("id_type", "")).lower() == "aadhaar":
                d = _digits_only(_idp.get("id_value"))
                _idp["id_value"] = d if (d and len(d) == 12) else None

        # Derive payment sums for the PAYMENT_SUM_MISMATCH audit — but ONLY when
        # every listed amount is legibly numeric. If a single line is unreadable we
        # publish None, so the audit stays silent rather than raising a false mismatch.
        pay_amts = [_to_number(p.get("amount")) for p in ACT_data["payment_instruments"] if isinstance(p, dict)]
        tds_amts = [_to_number(t.get("amount")) for t in ACT_data["tds_challans"] if isinstance(t, dict)]
        pay_complete = bool(pay_amts) and all(a is not None for a in pay_amts)
        tds_complete = all(a is not None for a in tds_amts)  # empty list -> True
        ACT_data["payments_only_sum"] = sum(pay_amts) if pay_complete else None
        ACT_data["tds_total"] = sum(a for a in tds_amts if a is not None) if tds_amts else 0.0
        if pay_complete and tds_complete:
            ACT_data["total_payments_sum"] = ACT_data["payments_only_sum"] + ACT_data["tds_total"]
            ACT_data["_payments_complete"] = True
        else:
            ACT_data["total_payments_sum"] = None
            ACT_data["_payments_complete"] = False

    return ACT_data


def chat_about_property(context_json, history, model="gemini-2.5-flash", scope_note=None):
    """
    Answer a reviewer's question about a specific property, grounded ONLY in
    the parsed data for that project.
    """
    model_map = {
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.5-pro": "gemini-2.5-pro",
        "gemini-1.5-pro": "gemini-1.5-pro",
        "Gemini 2.5 Flash": "gemini-2.5-flash",
        "Gemini 2.5 Pro": "gemini-2.5-pro",
        "Gemini 1.5 Pro": "gemini-1.5-pro"
    }
    actual_model = model_map.get(model, "gemini-2.5-flash")

    scope_instructions = {
        "findings & chain of title": "FOCUS: Focus specifically on surfaced legal discrepancies, title risks, audit observations, document execution order, vendor/vendee transfers, parent deed continuity, and title timeline.",
        "encumbrances & mortgages": "FOCUS: Focus specifically on bank mortgages, equitable charges, loan account numbers, release deeds, and encumbrance clearance statuses.",
        "financials & stamp duty": "FOCUS: Focus specifically on sale consideration figures, statutory stamp duty paid, MCD transfer tax, e-stamp numbers, and payment modes.",
        "raw extracted json": "FOCUS: Format your response emphasizing exact extracted field keys, values, raw JSON structures, and document field data."
    }

    scope_clause = ""
    if scope_note:
        key = str(scope_note).lower().strip()
        custom_focus = scope_instructions.get(key, f"Bias your answer toward '{scope_note}'.")
        scope_clause = f"\n\n[REVIEWER SCOPE FILTER: {str(scope_note).upper()}]\n{custom_focus}\n"

    system_instruction = (
        "You are DelhiTSR Assistant, a sharp title analyst chatting with a colleague about ONE specific property.\n\n"
        "STRICT CONCISE CHAT RULES:\n"
        "1. BE CONCISE & PUNCHY: Keep answers brief, direct, and easy to skim. Never write multi-paragraph essays or long story-like descriptions of every document.\n"
        "2. MAXIMUM 2-4 SHORT BULLETS OR 2-3 SHORT SENTENCES: When asked what is wrong or for an overview, list ONLY the top 2-3 main issues in short 1-line bullet points. Do not elaborate on every background deed unless explicitly asked.\n"
        "3. NO ROBOTIC FILLER: Skip conversational intros like 'Hey, so there are a few significant issues here' or concluding filler. Jump straight to the key points.\n"
        "4. CLEAN FORMATTING: Use simple bullet points (-) for findings. Keep each bullet to 1 clear sentence.\n"
        "5. FACTUAL TRUTH: Reference real document numbers, dates, parties, and amounts from the property data below when relevant.\n"
        "6. NO-VERDICT RULE: State facts neutrally. Never declare legal invalidity or use words like 'void', 'defective', or 'illegal'.\n"
        + scope_clause +
        "\n\n=== PROPERTY DATA ===\n"
        + context_json +
        "\n=== END OF PROPERTY DATA ==="
    )

    contents = []
    contents.append({
        "role": "user",
        "parts": [{"text": system_instruction +
                   "\n\nAcknowledge silently."}]
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Got it. I'm ready to chat about this property."}]
    })

    for turn in history:
        r = turn.get("role", "")
        role = "user" if r in ("user", "human") else "model"
        text_content = turn.get("content") or turn.get("parts", [{}])[0].get("text", "")
        if text_content:
          contents.append({"role": role, "parts": [{"text": text_content}]})

    try:
        response = client.models.generate_content(
            model=actual_model,
            contents=contents,
        )
        return (response.text or "").strip()
    except Exception as e:
        return f"[Assistant error: {e}]"


def summarize_discrepancy_with_ai(finding_dict):
    """
    Uses Gemini AI (gemini-2.5-flash) to generate a simple, non-verdict 2-sentence
    factual explanation of a document finding for the advocate modal.
    """
    disc_type = finding_dict.get("type", "DISCREPANCY")
    doc_no = finding_dict.get("doc_no", "N/A")
    event_date = finding_dict.get("event_date", "N/A")
    expected = finding_dict.get("expected", "")
    actual = finding_dict.get("actual", "")
    desc = finding_dict.get("description", "")

    exp_str = ", ".join(expected) if isinstance(expected, list) else str(expected)
    act_str = ", ".join(actual) if isinstance(actual, list) else str(actual)

    prompt = f"""You are a helpful assistant for a property legal audit tool used by bank advocates.
Provide a clear, simple 2-sentence explanation of the finding below.

Finding Details:
- Discrepancy Type: {disc_type}
- Document Number: {doc_no} ({event_date})
- Expected Record State: {exp_str}
- Actual Recorded State: {act_str}
- Finding Description: {desc}

CRITICAL MANDATORY RULES:
1. NEVER ANNOUNCE A VERDICT. Do NOT use words like "void", "invalid", "illegal", "defective", "null", or declare any final legal ruling. The final verdict belongs strictly to the reviewing advocate.
2. KEEP IT SIMPLE AND NON-TECHNICAL. Explain what the difference is between the expected record and the actual document in plain, everyday language without complicated legal jargon or statutory section dumping.
3. Output ONLY the 2-sentence explanation in clean plain text. No markdown formatting, no bullet points, no headers.
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )
        text = (response.text or "").strip()
        text = re.sub(r'[*_#`]', '', text)
        return text
    except Exception as e:
        print(f"[summarize_discrepancy_with_ai] Gemini call error: {e}")
        return None