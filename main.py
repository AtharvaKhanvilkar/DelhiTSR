import json
import re
import pdfplumber
import google.generativeai as genai

genai.configure(api_key="AIzaSyBzK1Z_dlGKQoiUq-spmWiwbh0uRUIrZUQ")


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
You are a document parser. Extract the following fields from the document and return ONLY a valid JSON object — no markdown, no code blocks, no explanation, just raw JSON.

- document_type                   (INDEX II, SALE_DEED, AGREEMENT_OF_SALE, GIFT_DEED, MORTGAGE_DEED, INTIMATION_OF_MORTGAGE, RELEASE_DEED, DEED_OF_RELEASE, LEAVE_AND_LICENSE, NULL)
- sub_registrar_office
- registration_no
- registration_year
- doc_no                          (registration_no/registration_year)

- txn_type                        (SALE_DEED, AGREEMENT_OF_SALE, GIFT_DEED, MORTGAGE_DEED, INTIMATION_OF_MORTGAGE, RELEASE_DEED, DEED_OF_RELEASE, LEAVE_AND_LICENSE, NULL)

- survey_no
- plot_no
- cts_no

- society_building_name
- society_building_address        (ALWAYS FULL ADDRESS)

- flat_no
- area                            (include unit: sq.mt or sq.ft)

- village
- district

- deposit                         (ONLY if txn_type = LEAVE_AND_LICENSE)
- license_fee                     (ONLY if txn_type = LEAVE_AND_LICENSE)

- licensor_name                   (ONLY if txn_type = LEAVE_AND_LICENSE)
- licensor_address                (ONLY if txn_type = LEAVE_AND_LICENSE)
- licensee_name                   (ONLY if txn_type = LEAVE_AND_LICENSE)
- licensee_address                (ONLY if txn_type = LEAVE_AND_LICENSE)
- leave_license_months            (ONLY if txn_type = LEAVE_AND_LICENSE)

- donor_name                      (ONLY if txn_type = GIFT_DEED)
- donor_address                   (ONLY if txn_type = GIFT_DEED)
- donee_name                      (ONLY if txn_type = GIFT_DEED)
- donee_address                   (ONLY if txn_type = GIFT_DEED)

- mortgagor_name                  (ONLY if txn_type = MORTGAGE_DEED or INTIMATION_OF_MORTGAGE)
- mortgagor_address               (ONLY if txn_type = MORTGAGE_DEED or INTIMATION_OF_MORTGAGE)
- mortgagee_name                  (ONLY if txn_type = MORTGAGE_DEED or INTIMATION_OF_MORTGAGE)
- mortgagee_address               (ONLY if txn_type = MORTGAGE_DEED or INTIMATION_OF_MORTGAGE)

- date_of_execution               (DD-MM-YYYY)
- date_of_registration            (DD-MM-YYYY)

- stamp_duty                      (IF NULL RETURN "ALERT")
- registration_fee

- seller_names                    (list, ONLY if txn_type = SALE_DEED, AGREEMENT_OF_SALE, RELEASE_DEED, DEED_OF_RELEASE)
- seller_address
- buyer_names                     (list, ONLY if txn_type = SALE_DEED, AGREEMENT_OF_SALE, RELEASE_DEED, DEED_OF_RELEASE)
- buyer_address

- boundary_north
- boundary_south
- boundary_east
- boundary_west

- consideration                   (exclude if LEAVE_AND_LICENSE)
- remarks

STRICTLY DO NOT REPEAT THE SAME FIELDS IN YOUR RESPONSE. EVERY FIELD IN THE GIVEN SCHEMA TO BE ENTERED ONLY ONCE.

- return ONLY valid JSON, no markdown, no code blocks, no explanations
- flat_no MUST contain ONLY the flat number (e.g., "6"), not floor or building details
- Do NOT add labels like "Building Name:", "Road:", "City:"
- Return address exactly as written in the document, without restructuring
- Extract survey_no, plot_no, and cts_no separately. Do NOT merge them
- If unclear, set to null

DOCUMENT:
{document_text}
"""

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)

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