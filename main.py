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


def extract_text_from_PDF(file_path):
    """Read a PDF's embedded text layer and return all its text (with a transparent
    disk cache).

    Text-only by design: the app does NOT OCR. Users bring text-based PDFs. If a PDF
    has no usable text layer this returns an empty/near-empty string, and the caller
    is responsible for telling the user to attach a text-based PDF.
    """
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
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"[extract_text] pdfplumber failed: {e}")

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

    prompt = f"""
You are a structured legal-event extraction engine for Indian property documents — NOT a generic OCR reader. Read the document carefully, understand the type of transaction, and extract the fields below. Return ONLY a valid JSON object — no markdown, no code blocks, no explanation, just raw JSON.

═══════════════════════════════════════════════════════════
DOCUMENT IDENTITY
═══════════════════════════════════════════════════════════
- document_type                   (INDEX II, SALE_DEED, AGREEMENT_OF_SALE, GIFT_DEED, MORTGAGE_DEED, INTIMATION_OF_MORTGAGE, RELEASE_DEED, DEED_OF_RELEASE, LEAVE_AND_LICENSE, NULL)
- txn_type                        (SALE_DEED, AGREEMENT_OF_SALE, GIFT_DEED, MORTGAGE_DEED, INTIMATION_OF_MORTGAGE, RELEASE_DEED, DEED_OF_RELEASE, LEAVE_AND_LICENSE, NULL)
- sub_registrar_office
- registration_no
- registration_year
- doc_no                          (registration_no/registration_year)
- date_of_execution               (DD-MM-YYYY)
- date_of_registration            (DD-MM-YYYY)

═══════════════════════════════════════════════════════════
PROPERTY IDENTITY & DESCRIPTION
═══════════════════════════════════════════════════════════
- survey_no
- plot_no
- cts_no
- khasra_no
- society_building_name
- society_building_address        (ALWAYS FULL ADDRESS, exactly as written)
- flat_no                         (ONLY the flat number, e.g. "6" — not floor or building)
- area                            (include unit: sq.mt or sq.ft)
- property_type                   (must be one of: "dda_flat", "private_flat", "plot" or null. DDA/Cooperative/CGHS flat is "dda_flat", a builder flat or private apartment is "private_flat", open land plot is "plot")
- buyer_gender                    (must be one of: "male", "female", "joint" or null. If all buyers/transferees are female, "female". If all are male, "male". If a mix of male and female, "joint")
- construction_year               (year of completion of the building or construction year mentioned, integer or null)
- village
- district
- boundary_north
- boundary_south
- boundary_east
- boundary_west
- property_schedule_text          (the full schedule/description paragraph of the property, verbatim)

═══════════════════════════════════════════════════════════
FINANCIALS (general)
═══════════════════════════════════════════════════════════
- consideration                   (exclude if LEAVE_AND_LICENSE)
- stamp_duty                      (IF NULL RETURN "ALERT")
- registration_fee
- market_value
{schema_part}
═══════════════════════════════════════════════════════════
E-STAMP CERTIFICATE  (only if an e-Stamp / stamp certificate page is present; else leave null)
═══════════════════════════════════════════════════════════
- estamp_certificate_no           (e.g. "IN-DL44237927139351V"; null if not clearly legible)
- estamp_issued_datetime          (issue date/time exactly as printed)
- estamp_amount                   (numeric value the e-Stamp was purchased for, e.g. 600000)
- estamp_first_party              (first party as printed on the certificate)
- estamp_second_party             (second party as printed on the certificate)
- estamp_duty_paid_by             (who paid the stamp duty, per the certificate)
- estamp_description              (e.g. "Article 23 Sale" or "Article 40 Mortgage")
- stamp_type                      ("E_STAMP", "PHYSICAL_STAMP", "FRANKING", "TREASURY_CHALLAN", or "NULL")
- franking_machine_number         (franking machine registration number, if physical franking)
- treasury_challan_grn            (Govt Treasury receipt/GRN number, if e-Challan)

═══════════════════════════════════════════════════════════
REGISTRATION ENDORSEMENT  (the Sub-Registrar/DORIS registration page & Section-60 certificate)
═══════════════════════════════════════════════════════════
- reg_book_no                     (registration book number, e.g. 1)
- reg_volume_no                   (registration volume number, e.g. 2664)
- reg_pages                       (page range in the register, e.g. "74 to 88")
- doris_document_number           (the long DORIS document number, e.g. "2387212700149")
- presenter_name                  (person who presented the deed for registration)
- pasting_fee                     (pasting fee amount, numeric)

═══════════════════════════════════════════════════════════
VALUATION / SCHEDULE  (circle-rate computation block, if present; else null)
═══════════════════════════════════════════════════════════
- property_number                 (e.g. "170")
- undivided_share_fraction        (e.g. "1/4" — the undivided share in land/stilt, if stated)
- floor_under_sale                (e.g. "First Floor upto ceiling level")
- number_of_storeys               (e.g. "Stilt + Four")
- covered_area                    (plinth/covered area WITH unit)
- plot_area                       (total plot area WITH unit)
- proportionate_stilt_area        (WITH unit)
- structure_type                  (Pucca / Semi-Pucca / Katcha)
- age_factor                      (numeric, if stated)
- structure_type_factor           (numeric, if stated)
- year_of_construction            (e.g. "After 2017")
- building_sanction_ref           (e.g. "MCD File No.10043054 dated 27/10/2017")
- use_factor                      (numeric, if stated)
- min_land_rate                   (numeric per sqm, if stated)
- min_construction_rate           (numeric per sqm, if stated)
- circle_rate_value_stated        (numeric — the deed's OWN stated circle-rate valuation)
- cost_of_land_stated             (numeric component, only if the deed shows the a+b+c breakdown)
- cost_of_construction_stated     (numeric component)
- cost_of_stilt_stated            (numeric component)
- stamp_duty_rate                 (e.g. "3%" or "6%")
- corporation_tax_amount          (numeric, if stated)
- corporation_tax_rate            (e.g. "3%")
- total_non_judicial_stamp        (numeric total stamp-paper value, if stated)
- mcd_upic                        (MCD Unique Property ID Code, e.g. "11009217001")

═══════════════════════════════════════════════════════════
PAYMENT TRAIL  (how the consideration was paid — sale deeds; else empty list)
═══════════════════════════════════════════════════════════
- payment_instruments             (list, ONE object per cheque/RTGS/DD/instrument, each
                                    {{"amount": <numeric>, "mode": "cheque|rtgs|dd|cash|other",
                                      "instrument_no", "bank", "date"}})
- tds_challans                    (list, ONE object per TDS deposit, each
                                    {{"amount": <numeric>, "challan_no", "bsr_code", "serial_no", "date", "bank"}})

═══════════════════════════════════════════════════════════
TITLE-CHAIN RECITALS & STAMP RECITAL TEXT
═══════════════════════════════════════════════════════════
- chain_recitals                  (list, ONE object per prior registered instrument the deed
                                    recites, each {{"instrument_type", "doc_no", "book_no", "volume",
                                    "pages", "sro", "execution_date", "registration_date",
                                    "from_parties", "to_parties"}})
- title_root                      (root/origin of title if stated, e.g. "President of India / DDA Allotment")
- is_root_deed                    (true / false — is this the original root allotment document?)
- leasehold_to_freehold_converted (true / false / null — is a leasehold→freehold conversion recited?)
- recited_stamp_duty_text         (verbatim text recital of stamp duty paid, e.g. "paid vide e-Stamp Cert IN-DL...")

═══════════════════════════════════════════════════════════
WITNESSES  (the attesting witnesses to the deed; empty list if none present)
═══════════════════════════════════════════════════════════
- witnesses                       (list, each {{"name", "relation", "address", "aadhaar"}};
                                    aadhaar null if not clearly legible — NEVER guess digits)

═══════════════════════════════════════════════════════════
ANNEXED SUPPORTING DOCUMENTS  (ID proofs, tax receipt, utility bills, Form-A, undertaking — only if bundled)
═══════════════════════════════════════════════════════════
- annexed_id_proofs               (list of ID cards actually present, each {{"person_name",
                                    "id_type": "aadhaar|pan", "id_value", "dob", "father_or_husband"}})
- property_tax                    (object {{"upic", "receipt_no", "financial_year", "amount",
                                    "paid_date", "ward", "zone", "owner"}} or null)
- utility_bills                   (list, each {{"utility_type": "gas|water|electricity",
                                    "consumer_name", "account_no", "bill_date", "amount_payable",
                                    "arrears"}})
- form_a                          (object {{"transferor", "transferee", "consideration",
                                    "plinth_area", "land_use", "category"}} or null)
- undertaking                     (object {{"buyer_name", "property", "mobile", "serial_no", "sro"}} or null)

═══════════════════════════════════════════════════════════
PARTIES — IDENTITY NUMBERS & ROLES BOUND TO EACH PERSON
═══════════════════════════════════════════════════════════
Return BOTH split lists AND a unified 'parties' list of party objects. Each object pairs ONE person with THEIR OWN identity numbers and role:

- transferor_parties              (list of objects, the GIVING side — sellers/donors/mortgagors/releasors/licensors)
    each object: {{"name", "role", "gender", "age", "dob", "pan", "pin", "aadhaar", "father_or_husband", "address"}}
- transferee_parties              (list of objects, the RECEIVING side — buyers/donees/mortgagees/releasees/licensees)
    each object: {{"name", "role", "gender", "age", "dob", "pan", "pin", "aadhaar", "father_or_husband", "address"}}
- parties                         (unified list of ALL party objects, each {{"name", "role", "gender", "age", "dob", "pan", "pin", "aadhaar", "father_or_husband", "address"}})
    • age: this person's stated age as an integer (e.g. 35), or null if not explicitly recited.
    • dob: this person's date of birth as printed (DD-MM-YYYY or DD.MM.YYYY).
    • aadhaar: the 12-digit Aadhaar bound to THIS person, exactly as printed. If not clearly
      legible, set null. NEVER guess or complete Aadhaar digits.
    • father_or_husband: this person's S/o or W/o name, if stated.

RULES FOR BINDING:
  • Read the document carefully to see which PAN/PIN sits next to which name.
  • If the document lists "Subhan Thakor, PAN BAREN2438L, PIN 411011",
    then that person's object is {{"name":"Subhan Thakor","pan":"BAREN2438L","pin":"411011"}}.
  • If a person has no PAN or PIN stated, set that field to null for THAT person —
    do NOT borrow another person's number.
  • NEVER put one person's PAN on another person. When unsure which number
    belongs to whom, set it to null rather than guessing.

- remarks

═══════════════════════════════════════════════════════════
RULES
═══════════════════════════════════════════════════════════
- Return ONLY valid JSON. No markdown, no code blocks, no explanations.
- Every field in this schema appears ONCE. Do NOT repeat fields.
- For amount-in-words and amount-in-figures: extract BOTH separately and faithfully — do not convert one into the other. Report exactly what the document says for each.
- For words_numeric fields (e.g. consideration_words_numeric, principal_amount_words_numeric, released_amount_words_numeric, released_mortgage_principal_words_numeric): ALWAYS output a clean numeric representation of the corresponding amount-in-words text (e.g. 5000000 for "Fifty Lakhs Only").
- Extract survey_no, plot_no, cts_no, khasra_no SEPARATELY. Do NOT merge them.
- flat_no contains ONLY the flat number (e.g. "6"), not floor/building details.
- Do NOT add labels like "Building Name:", "Road:", "City:" to addresses. Return addresses exactly as written, without restructuring.
- If a field is unclear or absent, set it to null.
- Normalize obvious OCR noise in NAMES (stray punctuation, doubled spaces), but do NOT invent or "correct" content that isn't there.
- CRITICAL — NO FABRICATION on the new blocks (e-Stamp, registration endorsement, valuation,
  payment_instruments, tds_challans, chain_recitals, witnesses, annexed documents): extract a
  field ONLY when that page/line is actually present and clearly legible. If a page type is not
  in this document, return null (for objects) or [] (for lists). NEVER invent a witness, an ID
  number, a payment, a bill, or a recited prior deed that you cannot actually read. A missing
  value is ALWAYS better than a guessed one.
- For every numeric field in payment_instruments, tds_challans, and the *_stated valuation
  components: output a clean number (no commas/₹) ONLY if legible; otherwise null. Do NOT
  compute or reconcile totals yourself — report each line exactly as printed.
- Aadhaar values (party, witness, or annexed ID): 12 digits exactly as printed. If any digit is
  illegible, set the whole value to null. Do NOT pad, complete, or infer digits.

DOCUMENT:
{document_text}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    raw = response.text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    try:
        ACT_data = json.loads(raw)
    except json.JSONDecodeError as e:
        print("JSON Decode Error:", e)
        print("Raw response was:", raw[:500])
        ACT_data = None

    if isinstance(ACT_data, dict):
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

    context_json : a JSON string containing everything known about the property
                   (per-document parsed fields, events, entities, encumbrances,
                   findings). This is the assistant's entire factual world.
    history      : list of {"role": "user"|"assistant", "content": "..."} turns,
                   oldest first. The latest user turn is the current question.
    scope_note   : optional human-readable note describing the slice of data the
                   reviewer has scoped the assistant to (e.g. "Events only" or
                   "Findings only"). Folded into the system instruction so the
                   assistant knows to answer within that slice.

    Returns the assistant's reply text. Uses the free gemini-2.5-flash model
    (same free tier as parsing — no additional cost beyond your existing quota).
    """
    scope_clause = ""
    if scope_note:
        scope_clause = (
            f"\n\nREVIEWER SCOPE: the reviewer has scoped this question to "
            f"\"{scope_note}\". Bias your answer toward that slice of the data, "
            f"but you may still reference other parts when essential.\n"
        )

    system_instruction = (
        "You are DelhiTSR Assistant, a careful title-search analyst helping a "
        "professional reviewer understand ONE specific property. You are given "
        "structured data extracted from that property's documents: per-document "
        "fields, the chronological events, the entity ledger (owners and their "
        "status), encumbrances (mortgages and their resolution), and validation "
        "findings.\n\n"
        "STRICT RULES:\n"
        "1. For ANY question about THIS property — owners, dates, prices, chain, "
        "findings, encumbrances, parties, documents — answer ONLY from the data "
        "provided below. Never invent, assume facts that are not present. "
    
        "2. You MUST answer general definitional questions (e.g. 'what is an "
        "encumbrance?', 'what does a release deed do?') from general legal knowledge "
        "— but when you do, make clear it is a general explanation, not a fact about "
        "this property.\n"
        "3. Never give legal advice or opinions on validity beyond what the findings "
        "state. But you are allowed to have an opinion and present it as long as you clearly state it's not final.\n"
        "4. Be clear and natural not ROBOTIC and dry. Use the actual names, doc numbers, and dates from "
        "the data. When referring to a finding, explain what it means in plain terms.\n"
        "5. If asked to summarise, base the summary on the data."
        + scope_clause +
        "\n\n=== PROPERTY DATA (your entire factual world for this property) ===\n"
        + context_json +
        "\n=== END OF PROPERTY DATA ==="
    )

    # Build the conversation for Gemini: system instruction folded into the first
    # user turn context, then the back-and-forth history.
    contents = []
    contents.append({
        "role": "user",
        "parts": [{"text": system_instruction +
                   "\n\nAcknowledge silently and wait for my questions."}]
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Understood. I'll answer only from this property's "
                   "parsed data, and clearly mark any general explanations. "
                   "What would you like to know?"}]
    })

    for turn in history:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})

    try:
        response = client.models.generate_content(
            model=model or "gemini-2.5-flash",
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
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = (response.text or "").strip()
        text = re.sub(r'[*_#`]', '', text)
        return text
    except Exception as e:
        print(f"[summarize_discrepancy_with_ai] Gemini call error: {e}")
        return None