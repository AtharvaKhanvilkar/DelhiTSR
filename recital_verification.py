"""
recital_verification.py
Comprehensive Recital & Root Deed Verification Engine for Title Search Reports.

Key Features:
1. Root Deed Exemption: Distinguishes Government Allotments / DDA / L&DO / Sovereign Awards from private link deeds.
2. Eliminates false positives on Root Deeds.
3. Detects missing intermediate private link deeds (RECITAL_LINK_DEED_MISSING).
4. Verifies Legal Heir Recitals & Encumbrance Recital Contradictions.
"""

import re

# Keywords indicating Government / Sovereign Allotment Recitals (Root Deed Exemption)
GOVT_ROOT_KEYWORDS = [
    "LAND ACQUISITION ACT", "DDA", "DELHI DEVELOPMENT AUTHORITY", "L&DO", 
    "LAND AND BUILDING DEPARTMENT", "PRESIDENT OF INDIA", "AWARD NO", 
    "GAZETTE NOTIFICATION", "NAZUL LAND", "GRAM SABHA", "SECRETARY OF STATE",
    "CHIEF COMMISSIONER", "LEASES AND ALLOTMENT"
]

def is_government_root_recital(text):
    """Checks if a recital refers to a sovereign/government land acquisition or allotment."""
    if not text:
        return False
    text_upper = text.upper()
    return any(k in text_upper for k in GOVT_ROOT_KEYWORDS)

def verify_recitals_and_chain(events_data, uploaded_doc_nos):
    """
    Verifies recitals across all deeds in the project session.
    
    Arguments:
      events_data: list of dicts representing parsed document events
      uploaded_doc_nos: set or list of document numbers/filenames present in project
      
    Returns:
      list of finding dicts
    """
    findings = []
    if not events_data:
        return findings

    # Sort events chronologically to establish the session Root Deed
    sorted_events = sorted(events_data, key=lambda x: (x.get('event_date') or '9999-99-99', x.get('event_doc_no') or ''))
    root_event = sorted_events[0] if sorted_events else None
    root_doc_no = root_event.get('event_doc_no') if root_event else None
    root_year = (root_event.get('event_date') or '')[:4] if root_event else ''

    uploaded_set = {str(d).strip().lower() for d in uploaded_doc_nos if d}

    for ev in sorted_events:
        doc_no = ev.get('event_doc_no')
        is_root = (doc_no == root_doc_no)
        recital_text = ev.get('recital_text') or ev.get('notes') or ev.get('summary') or ''

        # 1. Check for missing link deeds in recitals
        # Regex to find cited prior document numbers in recitals (e.g. "Doc No. 1234/1995" or "Deed Regd as 4455")
        cited_docs = re.findall(r'(?:Doc(?:ument)?|Deed|Regd|Registration)\s*(?:No\.?|Number)?\s*:?\s*([0-9]{2,7}(?:/[0-9]{2,4})?)', recital_text, re.IGNORECASE)
        
        for c_doc in cited_docs:
            c_clean = c_doc.strip().lower()
            if c_clean == str(doc_no).strip().lower():
                continue  # Self reference

            # If it's the Root Deed and refers to a Govt/Sovereign Allotment, EXEMPT it!
            if is_root and is_government_root_recital(recital_text):
                continue  # Root Deed Government Allotment Exemption -> No False Positive!

            # For non-root deeds, check if cited prior deed is in uploaded list
            if c_clean not in uploaded_set:
                # Fuzzy check if partial doc number matches
                found_match = any(c_clean in u or u in c_clean for u in uploaded_set)
                if not found_match:
                    findings.append({
                        "type": "RECITAL_LINK_DEED_MISSING",
                        "severity": "ERROR",
                        "message": f"Document {doc_no} recites prior link deed '{c_doc}', but this link deed is NOT uploaded in the project session.",
                        "expected": c_doc,
                        "actual": "Missing from bundle",
                        "doc_no": doc_no,
                        "category": "title_chain"
                    })

        # 2. Check for Legal Heir Recital Deficits (Intestate Succession without Release)
        if "INTESTATE" in recital_text.upper() or "HEIRS" in recital_text.upper():
            if ("WITHOUT RELEASE" in recital_text.upper() or "PARTIAL HEIRS" in recital_text.upper()):
                findings.append({
                    "type": "RECITAL_LEGAL_HEIR_GAP",
                    "severity": "ERROR",
                    "message": f"Document {doc_no} recites intestate succession but lacks registered Release/Relinquishment deeds from all legal heirs.",
                    "doc_no": doc_no,
                    "category": "identity_age_id"
                })

        # 3. Check for Encumbrance Recital Contradiction
        if "FREE FROM ALL ENCUMBRANCES" in recital_text.upper() or "UNENCUMBERED" in recital_text.upper():
            if ev.get("has_active_mortgage"):
                findings.append({
                    "type": "RECITAL_MORTGAGE_CONTRADICTION",
                    "severity": "ERROR",
                    "message": f"Document {doc_no} falsely warrants that the property is unencumbered, despite an active registered bank mortgage on record.",
                    "doc_no": doc_no,
                    "category": "title_chain"
                })

    return findings
