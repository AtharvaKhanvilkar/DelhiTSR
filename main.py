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


def parse_index_ii(file_path):
    document_text = extract_text_from_PDF(file_path)

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

═══════════════════════════════════════════════════════════
PARTIES — TRANSFER DEEDS (Sale / Agreement / Release)
═══════════════════════════════════════════════════════════
- seller_names                    (list, ONLY if SALE_DEED, AGREEMENT_OF_SALE, RELEASE_DEED, DEED_OF_RELEASE)
- seller_address
- buyer_names                     (list, ONLY if SALE_DEED, AGREEMENT_OF_SALE, RELEASE_DEED, DEED_OF_RELEASE)
- buyer_address

═══════════════════════════════════════════════════════════
PARTIES — GIFT DEED
═══════════════════════════════════════════════════════════
- donor_name                      (ONLY if GIFT_DEED)
- donor_address                   (ONLY if GIFT_DEED)
- donee_name                      (ONLY if GIFT_DEED)
- donee_address                   (ONLY if GIFT_DEED)

═══════════════════════════════════════════════════════════
PARTIES — LEAVE & LICENSE
═══════════════════════════════════════════════════════════
- licensor_name                   (ONLY if LEAVE_AND_LICENSE)
- licensor_address                (ONLY if LEAVE_AND_LICENSE)
- licensee_name                   (ONLY if LEAVE_AND_LICENSE)
- licensee_address                (ONLY if LEAVE_AND_LICENSE)
- deposit                         (ONLY if LEAVE_AND_LICENSE)
- license_fee                     (ONLY if LEAVE_AND_LICENSE)
- leave_license_months            (ONLY if LEAVE_AND_LICENSE)

═══════════════════════════════════════════════════════════
MORTGAGE DEED — detailed extraction
(ONLY if txn_type = MORTGAGE_DEED or INTIMATION_OF_MORTGAGE)
═══════════════════════════════════════════════════════════
MORTGAGORS (borrowers) — there may be MORE THAN ONE. Return as a LIST of objects.
- mortgagors                      (list of objects, each: {{"name", "father_or_spouse_name", "age", "address", "pan", "aadhaar"}})
  • Extract EVERY mortgagor named in the "Between" clause, not just the first.
  • If a field for a mortgagor is missing, set it to null inside that object.

MORTGAGEE (lender) — usually a bank/institution.
- mortgagee_name                  (institution name)
- mortgagee_branch_address        (branch address)
- mortgagee_authorized_signatory  (name of the person signing on the lender's behalf, if stated)

RECITALS / CONTEXT
- ownership_declaration           (how the mortgagor states they own the property, verbatim or summarized)
- loan_purpose                    (stated purpose of the loan, if any)
- prior_encumbrance_references    (any mention of earlier mortgages/charges/deeds, as a list of strings)

FINANCIAL TERMS
- principal_amount_figures        (the loan principal in numbers)
- principal_amount_words          (the loan principal in words, exactly as written)
- interest_rate                   (e.g. "9.5% per annum")
- repayment_terms                 (EMI / tenure / schedule text)
- security_collateral_references  (any collateral besides the property itself)

FLAT-LEVEL CONVENIENCE FIELDS (keep these too, for backward compatibility):
- mortgagor_name                  (the FIRST mortgagor's name only — for older code paths)
- mortgagor_address               (the FIRST mortgagor's address only)

═══════════════════════════════════════════════════════════
RELEASE DEED — linkage back to the original mortgage
(ONLY if txn_type = RELEASE_DEED or DEED_OF_RELEASE)
═══════════════════════════════════════════════════════════
- released_mortgage_doc_no        (the registration number of the ORIGINAL mortgage being released, if the release deed cites it — e.g. "4521/2020")
- released_mortgage_date          (the date of the original mortgage being released, if cited, DD-MM-YYYY)
- released_mortgagors             (list of the borrower names being released by THIS deed — may be a subset of the original borrowers)
- release_is_partial              (true if this release explicitly discharges only PART of the property/loan or only SOME borrowers; false if it releases everything; null if unclear)
- released_area                   (if a partial release, the specific area/plot/unit being released; else null)
- release_consideration           (any amount paid for the release, if stated)

═══════════════════════════════════════════════════════════
IDENTITY NUMBERS — BOUND TO EACH PERSON (CRITICAL)
═══════════════════════════════════════════════════════════
PAN and PIN are UNIQUE to each individual. You MUST bind each PAN/PIN
to the specific person it belongs to — NEVER return them as detached
lists, because that loses which number belongs to whom.

Return TWO lists of party objects. Each object pairs ONE person with
THEIR OWN identity numbers, exactly as the document associates them:

- transferor_parties              (list of objects, the GIVING side — sellers/donors/mortgagors/releasors)
    each object: {{"name", "pan", "pin", "address"}}
- transferee_parties              (list of objects, the RECEIVING side — buyers/donees/mortgagees/releasees)
    each object: {{"name", "pan", "pin", "address"}}

RULES FOR BINDING:
  • Read the document carefully to see which PAN/PIN sits next to which name.
  • If the document lists "Subhan Thakor, PAN BAREN2438L, PIN 411011",
    then that person's object is {{"name":"Subhan Thakor","pan":"BAREN2438L","pin":"411011"}}.
  • If a person has no PAN or PIN stated, set that field to null for THAT person —
    do NOT borrow another person's number.
  • NEVER put one person's PAN on another person. When unsure which number
    belongs to whom, set it to null rather than guessing.

BACKWARD-COMPATIBILITY (keep these flat lists too, but the party objects above
are the AUTHORITATIVE source — these flats are only for older code):
- transferor_pan                  (list of transferor PANs)
- transferor_pin                  (list of transferor PINs)
- transferee_pan                  (list of transferee PANs)
- transferee_pin                  (list of transferee PINs)

- remarks

═══════════════════════════════════════════════════════════
RULES
═══════════════════════════════════════════════════════════
- Return ONLY valid JSON. No markdown, no code blocks, no explanations.
- Every field in this schema appears ONCE. Do NOT repeat fields.
- For "mortgagors": ALWAYS return a list, even if there is only one mortgagor (a list with one object).
- For amount-in-words and amount-in-figures: extract BOTH separately and faithfully — do not convert one into the other. Report exactly what the document says for each.
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

    return ACT_data


def chat_about_property(context_json, history, model="gemini-2.5-flash"):
    """
    Answer a reviewer's question about a specific property, grounded ONLY in
    the parsed data for that project.

    context_json : a JSON string containing everything known about the property
                   (per-document parsed fields, events, entities, encumbrances,
                   findings). This is the assistant's entire factual world.
    history      : list of {"role": "user"|"assistant", "content": "..."} turns,
                   oldest first. The latest user turn is the current question.

    Returns the assistant's reply text. Uses the free gemini-2.5-flash model
    (same free tier as parsing — no additional cost beyond your existing quota).
    """
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
        "5. If asked to summarise, base the summary strictly on the data.\n\n"
        "=== PROPERTY DATA (your entire factual world for this property) ===\n"
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