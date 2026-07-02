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
    """Read PDF and return all text."""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# ─────────────────────────────────────────────────────────────────────────────
# DEED CLASSIFICATION TAXONOMY
# Single source of truth for what deed sub-types AutoTSR recognizes.
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
PARTIES — IDENTITY NUMBERS BOUND TO EACH PERSON
═══════════════════════════════════════════════════════════
PAN and PIN are UNIQUE to each individual. You MUST bind each PAN/PIN
to the specific person it belongs to — NEVER return them as detached
lists, because that loses which number belongs to whom.

Return TWO lists of party objects. Each object pairs ONE person with
THEIR OWN identity numbers, exactly as the document associates them:

- transferor_parties              (list of objects, the GIVING side — sellers/donors/mortgagors/releasors/licensors)
    each object: {{"name", "pan", "pin", "address"}}
- transferee_parties              (list of objects, the RECEIVING side — buyers/donees/mortgagees/releasees/licensees)
    each object: {{"name", "pan", "pin", "address"}}

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
        "You are AutoTSR Assistant, a careful title-search analyst helping a "
        "professional reviewer understand ONE specific property. You are given "
        "structured data extracted from that property's documents: per-document "
        "fields, the chronological events, the entity ledger (owners and their "
        "status), encumbrances (mortgages and their resolution), and validation "
        "findings.\n\n"
        "STRICT RULES:\n"
        "1. For ANY question about THIS property — owners, dates, prices, chain, "
        "findings, encumbrances, parties, documents — answer ONLY from the data "
        "provided below. Never invent, assume, or infer facts that are not present. "
        "If the data does not contain the answer, say plainly: 'That information "
        "isn't in the parsed documents.' Do not guess.\n"
        "2. You MAY answer general definitional questions (e.g. 'what is an "
        "encumbrance?', 'what does a release deed do?') from general legal knowledge "
        "— but when you do, make clear it is a general explanation, not a fact about "
        "this property.\n"
        "3. Never give legal advice or opinions on validity beyond what the findings "
        "state. You surface and explain what the data shows; the reviewer judges.\n"
        "4. Be concise and precise. Use the actual names, doc numbers, and dates from "
        "the data. When referring to a finding, explain what it means in plain terms.\n"
        "5. If asked to summarise, base the summary strictly on the data."
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