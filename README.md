# DelhiTSR
Title Intelligence Engine (Delhi NCT & Haryana [BETA])

<p align="left">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=flat&logo=python&logoColor=white" alt="Python Version"></a>
  <a href="https://flask.palletsprojects.org/"><img src="https://img.shields.io/badge/Framework-Flask-000000?style=flat&logo=flask&logoColor=white" alt="Framework"></a>
  <a href="https://opencv.org/"><img src="https://img.shields.io/badge/Vision-OpenCV-5C3EE8?style=flat&logo=opencv&logoColor=white" alt="OpenCV"></a>
  <a href="https://deepmind.google/"><img src="https://img.shields.io/badge/AI-Gemini%202.5%20Vision-4285F4?style=flat&logo=google&logoColor=white" alt="AI Engine"></a>
  <a href="#complete-specification-of-all-94-parameters"><img src="https://img.shields.io/badge/Rules-94%20Deterministic%20Audits-7B2CBF?style=flat" alt="Rule Engine"></a>
  <a href="#"><img src="https://img.shields.io/badge/Coverage-Delhi%20NCT%20%7C%20Haryana%20[BETA]-0284C7?style=flat" alt="Coverage"></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active%20Development-10B981?style=flat" alt="Status"></a>
</p>

DelhiTSR is a title verification engine for property ownership chains across the National Capital Territory (NCT) of Delhi and Haryana *(Haryana support operates in BETA)*. Built for property title search reporting (TSR), it ingests property deeds, executes computer vision page deskewing and dual-engine OCR, extracts 80 structured parameters across a 4-pass pipeline, and audits title history against 94 deterministic rules covering stamp duty tariffs, municipal transfer taxes, boundary continuity, and Sub-Registrar Office (SRO) regulations.

> **Note**: DelhiTSR is under active development. While the engine currently audits title deeds, reconciles stamp duty tariffs, and evaluates 94 verification checks, compiled Title Search Report (TSR) generation will be introduced in future releases.

---

## Table of Contents

- [Processing Pipeline](#processing-pipeline)
  - [1. Document Pre-Processing \& OCR](#1-document-pre-processing--ocr)
  - [2. 80-Field Schema Extraction](#2-80-field-schema-extraction)
  - [3. Tax \& Local Authority Reconciliation](#3-tax--local-authority-reconciliation)
- [Recognized Banks \& Housing Finance Companies](#recognized-banks--housing-finance-companies)
- [5-Tier Legal Severity Scale](#5-tier-legal-severity-scale)
- [Legal Privilege \& Compliance Policy](#legal-privilege--compliance-policy)
- [Security \& Data Protection Controls](#security--data-protection-controls)
- [Complete Specification of All 94 Parameters](#complete-specification-of-all-94-parameters)
  - [1. Tier 1: Material Defects (Critical Severity)](#1-tier-1-material-defects-critical-severity)
  - [2. Tier 2: Substantive Defects (Major Severity)](#2-tier-2-substantive-defects-major-severity)
  - [3. Tier 3: Statutory Requisitions](#3-tier-3-statutory-requisitions-financial--legal-requisitions)
  - [4. Tier 4: Procedural Anomalies](#4-tier-4-procedural-anomalies-minor--formatting-anomalies)
  - [5. Tier 5: Record Notations](#5-tier-5-record-notations-system-observations--logs)
- [Parameter Enforcement Note](#parameter-enforcement-note)
- [Installation \& Local Setup](#installation--local-setup)
- [Repository Structure](#repository-structure)

---

## Processing Pipeline

Property title chains in India consist of multi-page scanned documents spanning 30+ years of ownership history. DelhiTSR decouples image pre-processing, schema extraction, tax reconciliation, and rule evaluation into clear processing stages:

```mermaid
flowchart LR
    A["Raw Deed PDF / Scan Ingestion"] --> B["Stage 1: Vision OCR & Deskew"]
    B --> C["Stage 2: 4-Pass Schema Extraction"]
    C --> D["Stage 3: Tax & Local Body Reconciler"]
    D --> E["Stage 4: 94 Rule Discrepancy Engine"]
    E --> F["Structured Workspace Dashboard"]
```

---

### 1. Document Pre-Processing & OCR

Before document text is parsed, pages undergo automated computer vision processing:

1. **Orientation Angle Detection**: `pypdfium2` renders PDF pages to numpy arrays. OpenCV detects baseline text orientation using minimum area bounding rectangles (`cv2.minAreaRect`).
2. **Affine Rotation**: Rotates pages back to 0° alignment for detected skew angles between 0.5° and 45.0°.
3. **Otsu Binarization**: Cleans background yellowing, shadow artifacts, and faint watermarks using Otsu thresholding (`cv2.THRESH_OTSU`).
4. **Adaptive Text Extraction**:
   * **Direct Vector Stream**: Embedded digital fonts are extracted directly via `pdfplumber`.
   * **RapidOCR Fallback**: If page text density is below 40 characters per page (indicating scanned images), pages automatically route to `rapidocr-onnxruntime` with OpenCV contrast enhancement.
   * **Multimodal Vision Fallback**: Handwritten recitals, faint endorsement stamps, or damaged paper marginalia route to Gemini 2.5 Vision.

---

### 2. 80-Field Schema Extraction

To prevent context drift across long legal deeds, extraction is partitioned into 4 specialized schema passes, extracting 80 target parameters per document:

* **Pass 1: Document Identity & Stamp Paper Ledger**
  * Registration number, volume/page numbers, SRO office, e-stamp certificate number, issue date, article number, execution date, registration date.
* **Pass 2: Party Identity, Gender & KYC Ledger**
  * Transferor and transferee names, PAN identifiers, masked Aadhaar numbers, gender classification (sole female, joint, male), PIN codes, party residential addresses.
* **Pass 3: Financial Consideration & Payment Instrument Ledger**
  * Stated consideration, rental fee/premium, secured loan principal, e-stamp value, MCD tax amount, local authority tax, cheque/DD/RTGS numbers, TDS Form 26QB verification.
* **Pass 4: Property Schedule & Boundary Chain**
  * Property address, plot/flat number, survey/khasra/hadbast number, floor level, share percentage, area measurement and units (Sq. Yards, Bigha, Biswas, Sq. Meters), north/south/east/west boundaries.

---

### 3. Tax & Local Authority Reconciliation

#### Delhi Stamp Duty & Municipal Tax Schedule

Evaluates compliance under the Indian Stamp Act, 1899 (Schedule I-A Delhi Amendment) and Section 147 of the Delhi Municipal Corporation Act, 1957:

| Period / Document Category | Sole Female Purchaser | Joint (Female + Male) | Male Purchaser | Statutory Reference |
| :--- | :--- | :--- | :--- | :--- |
| **Pre-2003 Resale Conveyances** | 8.00% | 8.00% | 8.00% | Article 23 (5% SD + 3% MCD Tax) |
| **Pre-2003 DDA / Government Conveyances** | **6.00%** | **6.00%** | **6.00%** | Pre-2003 DDA Rule |
| **2003 – 2007 Conveyance Deeds** | 5.00% | 7.00% | 8.00% | Delhi Notification 2003 Tariff |
| **2008 – Present Conveyance Deeds** | **4.00%** *(3% SD + 1% MCD)* | **5.00%** *(3.5% SD + 1.5% MCD)* | **6.00%** *(3% SD + 3% MCD)* | Current NCT Delhi Duty Schedule |
| **Blood Relative Gift Deed** | 3.00% | 3.00% | 3.00% | Family Concession Schedule (+ 1% Reg Fee) |
| **Simple Mortgage without Possession** | 2.00% | 2.00% | 2.00% | Article 40 (2% on Principal Amount) |
| **Equitable Mortgage (Title Deposit)** | 0.50% | 0.50% | 0.50% | Article 40(b) Capped Schedule |

#### Haryana Jurisdiction & Duty Rates [BETA]

> **[BETA STAGE MODULE]**: *All Haryana stamp duty, registration fee slab, and urban vs. rural Gram Panchayat jurisdiction rules operate under BETA status.*

Evaluates compliance under the Haryana Stamp Act and Haryana Municipal Corporation Act:

| Transferee Composition | Urban Municipal Area *(MCG / MCF / Sector / HUDA)* | Rural Gram Panchayat Area *(Hadbast / Revenue Estate)* |
| :--- | :--- | :--- |
| **Sole Female Purchaser(s)** | **5.00%** *(3% Stamp Duty + 2% Municipal Duty)* | **3.00%** *(3% Stamp Duty + 0% Municipal Duty)* |
| **Joint Purchasers (Male + Female)** | **6.00%** *(4% Stamp Duty + 2% Municipal Duty)* | **4.00%** *(4% Stamp Duty + 0% Municipal Duty)* |
| **Male Purchaser(s)** | **7.00%** *(5% Stamp Duty + 2% Municipal Duty)* | **5.00%** *(5% Stamp Duty + 0% Municipal Duty)* |

---

## Recognized Banks & Housing Finance Companies

The engine incorporates a normalized lender entity ledger that resolves spelling variations, branch suffixes, and historical bank mergers when auditing mortgage charges and release deeds:

| Institution Category | Recognized Entities & Banking Institutions |
| :--- | :--- |
| **Public Sector Banks** | State Bank of India (SBI), Punjab National Bank (PNB), Bank of Baroda (BOB), Union Bank of India, Canara Bank, Indian Bank, Bank of India (BOI), Central Bank of India, Indian Overseas Bank, UCO Bank, Punjab & Sind Bank. |
| **Private Sector Banks** | HDFC Bank, ICICI Bank, Axis Bank, Kotak Mahindra Bank, IndusInd Bank, YES Bank, IDBI Bank, Federal Bank, Jammu & Kashmir Bank, RBL Bank. |
| **Housing Finance Companies (HFCs) & NBFCs** | LIC Housing Finance Ltd (LICHFL), PNB Housing Finance, Tata Capital Housing Finance, Bajaj Housing Finance, Aditya Birla Housing Finance, Indiabulls Housing Finance, Home First Finance Company, Aavas Financiers, DMI Housing Finance. |
| **Historical Merger Transitions** | • *Corporation Bank / Andhra Bank* $\rightarrow$ **Union Bank of India**<br>• *Syndicate Bank* $\rightarrow$ **Canara Bank**<br>• *Allahabad Bank* $\rightarrow$ **Indian Bank**<br>• *Oriental Bank of Commerce / United Bank of India* $\rightarrow$ **Punjab National Bank**<br>• *Vijaya Bank / Dena Bank* $\rightarrow$ **Bank of Baroda** |

---

## 5-Tier Legal Severity Scale

> **Platform Findings Integration**: All defects, requisitions, procedural anomalies, and record notations identified by the engine are surfaced directly as interactive **findings** within the platform's workspace dashboard, complete with document location markers and contextual risk details.


Findings are classified into a 5-tier legal scale based on legal weight:

- **Material Defect**: Critical flaws (missing private link deeds, unreleased legal heir ownership shares).
- **Substantive Defect**: Major flaws (e-stamp party mismatches, invalid certificate formats).
- **Statutory Requisition**: Financial deficits (stamp duty shortfalls).
- **Procedural Anomaly**: Operational gaps (missing witness details, unverified SRO seals).
- **Record Notation**: System logs and informational observations.

---

## Legal Privilege & Compliance Policy

1. **Factual Output Only**: The engine reports objective observations (such as stamp duty calculations, boundary discrepancies, or missing authorization documents). It does not declare titles void, defective, or invalid.
2. **Advocate Support**: Output is structured to support legal review while preserving advocate-client privilege.

---

## Security & Data Protection Controls

The platform implements security controls to protect sensitive real estate transactions, identity data, and document processing routines:

### 1. Prompt Injection & AI Safety Controls
* **Payload Encapsulation**: Document text supplied to LLM extraction routines (`main.py`) is bounded inside `<untrusted_document_payload>` XML tags.
* **Defensive System Mandates**: Prompts enforce system-level instructions requiring the engine to process tag contents strictly as static data.
* **Stateless API Executions**: Extraction passes execute statelessly without context memory or database access.
* **Strict Schema Sanitization**: Responses are validated against explicit JSON schemas.

### 2. Authentication & Data Privacy
* **AES-256 PII Encryption**: Aadhaar identifiers are encrypted at rest using Fernet symmetric encryption (`cryptography.fernet`). Decryption occurs strictly in-memory during real-time audit evaluation.
* **Access Control**: Project workspace endpoints enforce ownership validation (`check_project_owner`), restricting access to the authenticated user ID.

### 3. Web Security Headers
* **HTTP Security Headers**: Every HTTP response sets `Content-Security-Policy`, `Strict-Transport-Security`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, and `Cache-Control`.

---

## Complete Specification of All 94 Parameters

The engine evaluates 94 parameters across 12 domains, checking reconciled metadata for an event against governing laws, title continuity requirements, and state stamp schedules to assign each finding a 5-tier severity rating. All identified defects surface directly as findings within the platform's workspace dashboard:

### 1. Tier 1: Material Defects (Critical Severity)

Material defects represent critical title or legal failures that compromise ownership validity or transferability:

| Code | Severity | Finding Name | Statutory Provision / Authority | Verification Function & Technical Scope |
| :--- | :--- | :--- | :--- | :--- |
| `CHAIN_BREAK_TRANSFEROR` | **Material Defect** | Ownership Chain Break | `Sec 5, Transfer of Property Act 1882` | Audits title continuity to ensure the seller in each deed matches the buyer in the preceding registered deed. |
| `UNRELEASED_MORTGAGE_CHARGE` | **Material Defect** | Outstanding Bank Charge | `Sec 58, Transfer of Property Act 1882` | Identifies outstanding mortgages in title history lacking a registered Release Deed or Reconveyance Deed. |
| `VOID_DEED_SRO_JURISDICTION` | **Material Defect** | SRO Jurisdiction Mismatch | `Sec 28, Registration Act 1908` | Evaluates whether the deed was registered at the Sub-Registrar Office (SRO) holding territorial jurisdiction over the property locality, flagging registrations outside territorial limits as void. |
| `GPA_TITLE_TRANSFER_INVALID` | **Material Defect** | Post-2011 GPA Title Transfer | `Suraj Lamp Ruling (Supreme Court, 2011)` | Flags title transfers executed via General Power of Attorney after October 11, 2011 without a registered Sale Deed. |
| `MISSING_GPA_AUTHORIZATION` | **Material Defect** | Missing Attorney Authorization | `Sec 32 & 33, Registration Act 1908` | Verifies that attorney transfers cite a valid registered Power of Attorney in the title chain. |
| `MISSING_SALE_CONSIDERATION` | **Material Defect** | Missing Sale Price | `Sec 54, Transfer of Property Act 1882` | Verifies that monetary sale consideration is declared in conveyances. |
| `MISSING_RENTAL_CONSIDERATION` | **Material Defect** | Missing Lease License Fee | `Sec 105, Transfer of Property Act 1882` | Verifies that rent, premium, or license fees are recited in Lease Deeds. |
| `MISSING_MORTGAGE_VALUE` | **Material Defect** | Missing Secured Loan Principal | `Sec 58, Transfer of Property Act 1882` | Verifies that the principal loan amount is declared in Mortgage Deeds. |
| `GIFT_DEED_WITH_CONSIDERATION` | **Material Defect** | Gift with Consideration | `Sec 122, Transfer of Property Act 1882` | Flags Gift Deeds that recite monetary consideration. |
| `CONSIDERATION_ZERO_OR_INVALID` | **Material Defect** | Invalid Consideration Value | `Sec 25, Indian Contract Act 1872` | Flags conveyances declaring zero or invalid consideration values. |
| `MISSING_TRANSFEROR_NAME` | **Material Defect** | Missing Seller Identity | `Sec 5, Transfer of Property Act 1882` | Flags missing or unextracted seller names in conveyances. |
| `MISSING_TRANSFEREE_NAME` | **Material Defect** | Missing Buyer Identity | `Sec 5, Transfer of Property Act 1882` | Flags missing or unextracted buyer names in conveyances. |
| `NAME_SPELLING_CRITICAL` | **Material Defect** | Major Name Mismatch | `N/A (Engine Levenshtein Audit)` | Flags major spelling discrepancies between party names across title chain deeds. |
| `MISSING_RECONVEYANCE_DEED` | **Material Defect** | Missing Release Deed | `Sec 60, Transfer of Property Act 1882` | Flags satisfied bank loans lacking a formal registered Release Deed. |
| `LIS_PENDENS_CHARGE_CHECK` | **Material Defect** | Pending Court Litigation Charge | `Sec 52, Transfer of Property Act 1882` | Flags pending court litigation recitals or stay orders against the property. |
| `ATTACHMENT_ORDER_CHECK` | **Material Defect** | Judicial / Revenue Attachment | `Order 38 Rule 5, CPC 1908 / Revenue Recovery Act` | Flags court attachment orders, tax liens, or revenue recovery decrees against the property. |
| `SARFAESI_NOTICE_CHECK` | **Material Defect** | SARFAESI Enforcement Charge | `Sec 13(2) & 13(4), SARFAESI Act 2002` | Scans title recitals for active SARFAESI demand notices, possession notices, or bank auction proceedings. |
| `PLOT_NUMBER_MISMATCH` | **Material Defect** | Plot Identifier Mismatch | `Sec 21, Registration Act 1908` | Reconciles plot, flat, and property unit numbers across link deeds to detect transcription errors. |
| `CHRONOLOGICAL_DATE_ANOMALY` | **Material Defect** | Reverse Date Sequencing | `N/A (Engine Chronology Audit)` | Flags derivative deeds dated earlier than their parent root deed. |
| `FUTURE_REGISTRATION_DATE` | **Material Defect** | Future Registration Stamp | `N/A (Engine Temporal Audit)` | Flags registration dates that occur in the future. |

### 2. Tier 2: Substantive Defects (Major Severity)

Substantive defects represent major legal, registration, or document discrepancies requiring corrective action:

| Code | Severity | Finding Name | Statutory Provision / Authority | Verification Function & Technical Scope |
| :--- | :--- | :--- | :--- | :--- |
| `UNREGULARIZED_GPA_CHAIN` | **Substantive Defect** | Unregularized GPA Chain | `Sec 54, Transfer of Property Act 1882` | Detects title chains ending with an unregularized Power of Attorney or Agreement to Sell without a registered Sale Deed. |
| `MUTATION_RECORD_MISSING` | **Substantive Defect** | Missing Revenue Mutation Record | `Delhi Land Revenue Act 1954 / DMC Act 1957` | Flags property transfers lacking government revenue mutation records (Khasra/Khatauni or MCD tax mutation). |
| `MULTIPLE_ACTIVE_OWNERS` | **Substantive Defect** | Ambiguous Undivided Ownership | `Sec 44, Transfer of Property Act 1882` | Detects conflicting full ownership claims over the same property unit. |
| `INVALID_PAN_FORMAT` | **Substantive Defect** | Structural PAN Defect | `Income Tax Rules 1962 (Rule 114)` | Validates Permanent Account Number (PAN) strings against standard Income Tax format. |
| `NAME_SPELLING_MODERATE` | **Substantive Defect** | Moderate Name Variation | `N/A (Engine Levenshtein Audit)` | Flags moderate spelling variations (such as phonetic differences) across chain deeds. |
| `MORTGAGE_AMOUNT_EXCEEDED` | **Substantive Defect** | Charge Amount Discrepancy | `Sec 60, Transfer of Property Act 1882` | Flags release deeds where released amount is less than the original loan principal. |
| `NOC_BANK_RELEASE_MISSING` | **Substantive Defect** | Missing Bank No Objection Certificate | `Sec 48, Transfer of Property Act 1882` | Flags transactions on mortgaged property conducted without bank No Objection Certificates. |
| `MORTGAGE_DATE_PRIORITY` | **Substantive Defect** | Mortgage Priority Audit | `Sec 48, Transfer of Property Act 1882` | Verifies chronological priority among multiple mortgages on the same property. |
| `RELEASE_DEED_PARTY_MISMATCH` | **Substantive Defect** | Mortgagee Identity Mismatch | `Sec 130, Transfer of Property Act 1882` | Flags release deeds executed by entities other than the original mortgagee bank without debt assignment proof. |
| `ASSIGNMENT_OF_DEBT_CHECK` | **Substantive Defect** | Debt Assignment Verification | `Sec 130, Transfer of Property Act 1882` | Verifies registered Deed of Assignment of Debt when a successor lender releases a mortgage created by another bank. |
| `PROPERTY_AREA_DISCREPANCY` | **Substantive Defect** | Area Calculation Deviation | `Sec 21, Registration Act 1908` | Detects area variances between root deeds and subsequent transfers. |
| `HADBAST_NUMBER_AUDIT` | **Substantive Defect** | Hadbast / Khasra Verification | `Haryana Land Revenue Act 1887` | Cross-checks Hadbast revenue estate numbers and Khasra parcel identifiers against Haryana Land Records. |
| `IMPOUNDING_RISK_ASSESSMENT` | **Substantive Defect** | Deed Impounding Risk | `Sec 33, Indian Stamp Act 1899` | Flags inadequately stamped deeds subject to impounding under Section 33. |

### 3. Tier 3: Statutory Requisitions (Financial & Legal Requisitions)

Statutory requisitions represent duty shortfalls, tax deficits, and fee reconciliation requirements:

| Code | Severity | Finding Name | Statutory Provision / Authority | Verification Function & Technical Scope |
| :--- | :--- | :--- | :--- | :--- |
| `STAMP_DUTY_DEFICIT_MALE` | **Statutory Requisition** | Male Stamp Duty Deficit | `Indian Stamp Act 1899 / Delhi Govt Notification 2008` | Reconciles stamp duty paid by male purchasers against prescribed Delhi rates (6% total: 4% stamp duty + 2% MCD tax). |
| `STAMP_DUTY_DEFICIT_FEMALE` | **Statutory Requisition** | Female Stamp Duty Deficit | `Indian Stamp Act 1899 / Delhi Govt Notification 2008` | Reconciles stamp duty paid by female purchasers against concession rates (4% total: 3% stamp duty + 1% MCD tax). |
| `STAMP_DUTY_DEFICIT_JOINT` | **Statutory Requisition** | Joint Stamp Duty Deficit | `Indian Stamp Act 1899 / Delhi Govt Notification 2008` | Reconciles stamp duty paid by joint purchasers against joint concession rates (5% total). |
| `MCD_TRANSFER_TAX_DEFICIT` | **Statutory Requisition** | MCD Transfer Tax Deficit | `Sec 147, Delhi Municipal Corporation Act 1957` | Reconciles municipal transfer tax paid on Delhi conveyances under Section 147 of MCD Act. |
| `CIRCLE_RATE_EVALUATION` | **Statutory Requisition** | Minimum Circle Rate Audit | `Delhi Stamp (Prevention of Undervaluation) Rules 2007` | Calculates minimum valuation based on Delhi Category A-H circle rates and flags undervaluation. |
| `UNDERVALUATION_PENALTY_CHECK` | **Statutory Requisition** | Undervaluation Requisition | `Sec 47A, Indian Stamp Act 1899` | Identifies stamp duty shortfalls subject to impounding and penalty under Section 47A. |
| `REGISTRATION_FEE_CHECK` | **Statutory Requisition** | Registration Fee Audit | `Table of Registration Fees (Sec 78, Reg Act 1908)` | Reconciles 1% registration fees paid at SRO. |
| `MISSING_PARTY_PAN` | **Statutory Requisition** | Missing Income Tax PAN | `Sec 139A, Income Tax Act 1961` | Flags high-value property transactions registered without PAN or Form 60/61. |
| `ALIAS_NAME_RECITAL_CHECK` | **Statutory Requisition** | Alias / Also Known As Recital | `Sec 91 & 92, Indian Evidence Act 1872` | Verifies whether name variations are backed by explicit alias recitals or gazette notifications. |
| `ENCLOSED_DEPOSIT_TITLE_DEEDS` | **Statutory Requisition** | Equitable Mortgage Audit | `Sec 17(1)(c), Registration Act 1908` | Audits Memorandum of Deposit of Title Deeds (MODTD) for compulsory registration. |
| `PARTIAL_RELEASE_CHARGE` | **Statutory Requisition** | Partial Reconveyance Audit | `Sec 60, Transfer of Property Act 1882` | Identifies partial mortgage release where an encumbrance remains active on remaining property portions. |
| `RECHARGE_STAMP_DUTY_CHECK` | **Statutory Requisition** | Mortgage Stamp Duty Audit | `Article 40, Indian Stamp Act 1899` | Verifies stamp duty paid on Mortgage Deeds. |
| `MODTD_REGISTRATION_CHECK` | **Statutory Requisition** | MODTD Registration Audit | `Sec 17(1), Registration Act 1908 / State Stamp Acts` | Verifies compulsory registration of Memorandum of Deposit of Title Deeds under state stamp laws. |
| `NBFC_HFC_REGISTRATION_CHECK` | **Statutory Requisition** | RBI / NHB License Audit | `Reserve Bank of India Act 1934 (Sec 45-IA)` | Audits lender entities against RBI/NHB registry to verify mortgage creation authority. |
| `ARTICLE_23_CONVEYANCE_DUTY` | **Statutory Requisition** | Article 23 Conveyance Tariff | `Article 23, Schedule I-A, Indian Stamp Act 1899` | Verifies conveyance stamp duty rates on sale deeds under Article 23. |
| `ARTICLE_55_RELEASE_DUTY` | **Statutory Requisition** | Article 55 Release Tariff | `Article 55, Schedule I-A, Indian Stamp Act 1899` | Audits stamp duty paid on Release / Relinquishment Deeds under Article 55. |
| `ARTICLE_33_GIFT_DUTY` | **Statutory Requisition** | Article 33 Gift Tariff | `Article 33, Schedule I-A, Indian Stamp Act 1899` | Audits stamp duty paid on Gift Deeds under Article 33. |
| `ARTICLE_48_GPA_DUTY` | **Statutory Requisition** | Article 48 Power of Attorney Tariff | `Article 48, Schedule I-A, Indian Stamp Act 1899` | Audits stamp duty paid on Power of Attorney instruments under Article 48. |
| `ARTICLE_35_LEASE_DUTY` | **Statutory Requisition** | Article 35 Lease Tariff | `Article 35, Schedule I-A, Indian Stamp Act 1899` | Audits stamp duty paid on Lease Agreements under Article 35 based on lease duration and rent. |
| `ARTICLE_40_MORTGAGE_DUTY` | **Statutory Requisition** | Article 40 Mortgage Tariff | `Article 40, Schedule I-A, Indian Stamp Act 1899` | Audits stamp duty paid on Mortgage Deeds under Article 40. |
| `HARYANA_FEMALE_CONCESSION` | **Statutory Requisition** | Haryana Female Concession Audit | `Indian Stamp (Haryana Amendment) Act` | Audits Haryana stamp duty rates (5% Urban / 3% Rural for females vs 7% Urban / 5% Rural for males). |
| `HARYANA_GRAM_PANCHAYAT_DUTY` | **Statutory Requisition** | 2% Gram Panchayat Duty Audit | `Haryana Panchayati Raj Act 1994 (Sec 200)` | Audits the 2% local body transfer duty levied in rural Haryana Gram Panchayat areas. |

### 4. Tier 4: Procedural Anomalies (Minor & Formatting Anomalies)

Procedural anomalies represent minor formatting, date precedence, or boundary description gaps:

| Code | Severity | Finding Name | Statutory Provision / Authority | Verification Function & Technical Scope |
| :--- | :--- | :--- | :--- | :--- |
| `PROPERTY_NOT_IN_DELHI` | **Procedural Anomaly** | Out-of-Jurisdiction Location | `Delhi Land Revenue Act 1954` | Flags properties located outside Delhi NCT or Haryana (BETA) boundaries. |
| `DEED_EXECUTION_DATE_MISSING` | **Procedural Anomaly** | Missing Execution Date | `Sec 23, Registration Act 1908` | Checks for missing execution dates in deed preambles or signatures. |
| `DEED_REGISTRATION_DATE_MISSING` | **Procedural Anomaly** | Missing SRO Registration Date | `Sec 60, Registration Act 1908` | Flags conveyances lacking Sub-Registrar registration dates. |
| `CORPORATE_CIN_CHECK` | **Procedural Anomaly** | Corporate Identity Audit | `Sec 12, Companies Act 2013` | Validates Corporate Identification Numbers (CIN/LLPIN) for corporate buyers or sellers. |
| `PARTY_ADDRESS_MISSING` | **Procedural Anomaly** | Missing Party Address | `Sec 32A, Registration Act 1908` | Identifies deed parties lacking formal residential or corporate addresses. |
| `MORTGAGE_PROPERTY_MATCH` | **Procedural Anomaly** | Mortgage Property Match | `Sec 21, Registration Act 1908` | Cross-checks property unit details in Mortgage Deeds against underlying title deeds. |
| `UNRECOGNIZED_LENDER_ENTITY` | **Procedural Anomaly** | Unknown Lender Entity | `RBI / NHB Regulatory Guidelines` | Flags mortgage instruments executed with private entities outside recognized Commercial Bank, HFC, and NBFC registries. |
| `BOUNDARY_NORTH_MISMATCH` | **Procedural Anomaly** | North Boundary Mismatch | `Sec 21, Registration Act 1908` | Cross-references North boundary descriptions across successive deeds. |
| `BOUNDARY_SOUTH_MISMATCH` | **Procedural Anomaly** | South Boundary Mismatch | `Sec 21, Registration Act 1908` | Cross-references South boundary descriptions across successive deeds. |
| `BOUNDARY_EAST_MISMATCH` | **Procedural Anomaly** | East Boundary Mismatch | `Sec 21, Registration Act 1908` | Cross-references East boundary descriptions across successive deeds. |
| `BOUNDARY_WEST_MISMATCH` | **Procedural Anomaly** | West Boundary Mismatch | `Sec 21, Registration Act 1908` | Cross-references West boundary descriptions across successive deeds. |
| `STAMP_PAPER_DATE_PRECEDENCE` | **Procedural Anomaly** | Stamp Paper Date Precedence | `Sec 29, Indian Stamp Act 1899` | Verifies that non-judicial stamp paper purchase dates precede or match deed execution date. |

### 5. Tier 5: Record Notations (System Observations & Logs)

Record notations represent system logs, name normalizations, and informational observations:

| Code | Severity | Finding Name | Statutory Provision / Authority | Verification Function & Technical Scope |
| :--- | :--- | :--- | :--- | :--- |
| `SEC28_REG_ACT_AUDIT` | **Record Notation** | Mandatory SRO Validation | `Sec 28, Registration Act 1908` | Audits Sub-Registrar registration stamps against SRO jurisdiction boundaries. |
| `SRO_TERRITORY_MATRIX` | **Record Notation** | SRO Territory Ledger Mapping | `N/A (Engine Jurisdiction Ledger)` | Cross-references SRO designations against the 350+ Delhi locality mapping matrix. |
| `SRO_CODE_NORMALIZER` | **Record Notation** | SRO Code Canonicalization | `N/A (Engine Canonical Logic)` | Normalizes variant SRO text strings into standard SRO identifiers. |
| `SRO_LOCALITY_TOKEN_MATCH` | **Record Notation** | Locality Boundary Token Check | `N/A (Engine Token Matching)` | Matches property address tokens against SRO jurisdiction boundaries. |
| `EXPLICIT_SRO_RECITAL` | **Record Notation** | Explicit Header SRO Recital | `Sec 28, Registration Act 1908` | Validates SRO recitals in deed preambles against registry stamps. |
| `CONSIDERATION_FORMAT_AUDIT` | **Record Notation** | Consideration Parsing Validation | `N/A (Engine Financial Parser)` | Compares numerical figures against written word recitals to detect monetary discrepancies. |
| `CONSIDERATION_CURRENCY_CHECK` | **Record Notation** | Currency Unit Standardization | `Reserve Bank of India Act 1934` | Verifies that monetary consideration is recorded in standard INR currency. |
| `TITLE_CHAIN_SPAN_AUDIT` | **Record Notation** | Title History Duration Check | `Sec 90, Indian Evidence Act 1872` | Computes total title span and flags chains shorter than the 30-year requirement. |
| `PARTIAL_SHARE_TRANSFER` | **Record Notation** | Undivided Share Audit | `Sec 44, Transfer of Property Act 1882` | Tracks undivided land share percentages across deeds to ensure complete title transfer. |
| `DOCUMENT_SEQUENCE_ORDER` | **Record Notation** | Chronological Ledger Order | `N/A (Engine Chronology Audit)` | Sorts multi-deed packages into chronological order by registration timestamp. |
| `REPRESENTATIVE_CAPACITY` | **Record Notation** | Execution Authority Audit | `Sec 180, Companies Act 2013` | Verifies board resolutions, power of attorney recitals, or trust authorizations for corporate signatories. |
| `SALUTATION_NORMALIZER` | **Record Notation** | Name Honorific Normalization | `N/A (Engine Name Normalizer)` | Strips honorifics (Shri, Smt, Dr, M/s) prior to party name matching. |
| `SURNAME_INITIAL_EXPANSION` | **Record Notation** | Initial vs. Full Name Check | `N/A (Engine Name Normalizer)` | Matches abbreviated initials against full expanded names. |
| `PARTY_ROLE_CANONICALIZER` | **Record Notation** | Party Role Normalization | `N/A (Engine Entity Canonicalizer)` | Maps party role terms (Vendor/Vendee, Lessor/Lessee, Donor/Donee) into standard system roles. |
| `LENDER_MERGER_TRANSITION` | **Record Notation** | Bank Merger Mapping | `Banking Regulation Act 1949 (Sec 44A)` | Maps historical bank mergers when verifying release deeds executed by successor banks. |
| `ENCUMBRANCE_FREE_DECLARATION` | **Record Notation** | Encumbrance Warranty Recital | `Sec 55(1)(g), Transfer of Property Act 1882` | Audits seller warranty recitals declaring the property free from encumbrances. |
| `CHARGE_REGISTER_CANONICALIZER` | **Record Notation** | Encumbrance Ledger Normalization | `N/A (Engine Charge Normalizer)` | Compiles active, partial, and discharged charges into a unified encumbrance ledger. |
| `HISTORICAL_BANK_MERGER_MAP` | **Record Notation** | Merger Succession Mapping | `Banking Regulation Act 1949 (Sec 44A)` | Resolves bank mergers (e.g. Syndicate Bank to Canara Bank, Vijaya Bank to Bank of Baroda). |
| `MORTGAGEE_NAME_STANDARDIZATION` | **Record Notation** | Lender Name Normalization | `N/A (Engine Levenshtein Normalizer)` | Standardizes corporate bank name variations into canonical entity codes. |
| `COLONY_NAME_NORMALIZER` | **Record Notation** | Locality Name Normalization | `N/A (Engine Locality Dictionary)` | Standardizes locality names using official locality dictionaries. |
| `UNIT_MEASUREMENT_CONVERSION` | **Record Notation** | Area Unit Standardization | `N/A (Engine Measurement Converter)` | Converts variant area metrics (sq. yards, bigha, biswa) into square meters. |
| `PROPERTY_TYPE_CANONICALIZER` | **Record Notation** | Property Classification | `Delhi Master Plan 2021 (MPD-2021)` | Classifies property usage (Residential, Commercial, Industrial, Agricultural) based on deed schedule. |
| `ADDRESS_LINE_RECONCILIATION` | **Record Notation** | Full Address Parsing | `N/A (Engine Address Parser)` | Reconciles address strings against postal and municipal records. |
| `PRE_2003_CONVEYANCE_TAX_CHECK` | **Record Notation** | Pre-2003 Flat Rate Duty Check | `Indian Stamp Act 1899 (Delhi Schedule)` | Evaluates historical stamp duty compliance for conveyances registered prior to 2003 under flat 8% tariff. |
| `DDA_CONVEYANCE_EXEMPTION` | **Record Notation** | DDA Tax Concession | `DDA Allotment Rules / Delhi Stamp Notification` | Applies stamp duty exemptions for initial DDA / Government allotments prior to 2003 (6% rate). |
| `E_STAMP_CERTIFICATE_VERIFY` | **Record Notation** | E-Stamp Authentication | `Sec 3, Indian Stamp Act 1899 / SHCIL System` | Validates e-stamp certificate numbers, issue dates, and amounts against registration endorsements. |
| `AGGREGATE_DUTY_COMPUTATION` | **Record Notation** | Multi-Receipt Duty Aggregation | `N/A (Engine Tax Aggregator)` | Aggregates split e-stamp receipts, state stamp duty, and local transfer tax payments. |
| `FEMALE_CONCESSION_ELIGIBILITY` | **Record Notation** | Female Rate Concession Audit | `Delhi Govt Stamp Duty Concession Notification 2008` | Verifies female ownership recitals to validate stamp duty concession eligibility. |
| `STAMP_REFUND_CLAIM_CHECK` | **Record Notation** | Unused Stamp Paper Audit | `Sec 49, Indian Stamp Act 1899` | Identifies unexecuted stamp papers submitted for refund within 6 months. |
| `PAST_STAMP_LAW_AMENDMENT_MAP` | **Record Notation** | Historical Stamp Rate Ledger | `N/A (Engine Historical Tax Matrix)` | Maps historical Delhi stamp duty rate amendments (1995, 2003, 2008, 2012) against execution dates. |
| `TAX_EXEMPTION_RECITAL_VERIFY` | **Record Notation** | Tax Exemption Recital | `Sec 9, Indian Stamp Act 1899` | Verifies tax exemption recitals against official notification orders. |
| `HARYANA_URBAN_RURAL_CLASSIFIER` | **Record Notation** | Municipal vs Gram Panchayat Classifier | `Haryana Municipal Corporation Act 1994 / Panchayati Raj Act 1994` | Classifies Haryana property locations into Urban Municipal Corporation (MCG/MCF) vs Rural Gram Panchayat areas. |
| `PAGE_SKEW_ANGLE_DETECT` | **Record Notation** | Deskew Angle Detection | `N/A (Computer Vision / OpenCV)` | Computes page rotation skew angle (-45° to +45°) using OpenCV bounding box analysis. |
| `AFFINE_ROTATION_DESKEW` | **Record Notation** | Computer Vision Page Deskew | `N/A (Computer Vision / OpenCV)` | Applies 2D affine rotation matrix to straighten skewed scanned deed pages prior to OCR. |
| `OTSU_BINARIZATION_CLEAN` | **Record Notation** | Artifact & Shadow Removal | `N/A (Computer Vision / OpenCV)` | Executes adaptive Otsu thresholding to remove background yellowing, stamp bleed, and shadow artifacts. |
| `DUAL_ENGINE_OCR_ROUTER` | **Record Notation** | Digital Vector vs. OCR Routing | `N/A (Engine Pipeline Router)` | Routes pages between direct PDF vector text extraction and computer vision OCR based on text layer quality. |
| `WATERMARK_SHADOW_SUPPRESSION` | **Record Notation** | Watermark Noise Filter | `N/A (Computer Vision / Image Filter)` | Filters out background watermarks and SRO security stamps that obscure deed text. |
| `RESOLUTION_DPI_NORMALIZER` | **Record Notation** | Image Resolution Normalization | `N/A (Computer Vision / Image Rescaling)` | Rescales low-resolution document scans to 300 DPI baseline for OCR accuracy. |
| `MULTI_PAGE_SEQUENCE_CHECK` | **Record Notation** | Page Sequence Continuity | `N/A (Engine PDF Struct Parser)` | Detects missing pages or out-of-order page sequences in uploaded PDF packages. |
| `ENDORSEMENT_STAMP_CROP` | **Record Notation** | SRO Endorsement Bounding Box | `N/A (Computer Vision / Bounding Box)` | Locates and crops registration endorsement stamps on deed margins for targeted OCR. |
| `IMAGE_BLUR_QUALITY_AUDIT` | **Record Notation** | Image Clarity Audit | `N/A (Computer Vision / Laplacian Variance)` | Measures Laplacian variance to flag illegible or blurry document scans. |
| `NO_VERDICT_PROSE_ENFORCER` | **Record Notation** | Legal Opinion Verdict Filter | `N/A (Engine Compliance Directive)` | Enforces neutral platform stance by filtering out conclusive legal verdicts (e.g. declaring deeds 'void' or 'invalid'). |
| `PRIVILEGE_DISCLAIMER_ATTACH` | **Record Notation** | Legal Privilege Disclaimer | `N/A (Engine Compliance Directive)` | Attaches mandatory disclaimers declaring outputs as technical audit assistance, not formal legal opinions. |
| `CONFIDENTIALITY_METADATA_GUARD` | **Record Notation** | Data Privacy & KYC Shield | `Digital Personal Data Protection Act 2023` | Redacts sensitive personal identifiable information (PII) and KYC data from system logs under DPDP Act 2023. |

---

## Parameter Enforcement Note

DelhiTSR does NOT use isolated (and naive) if-else checks. Rules enforced are interdependent; meaning evaluating a single parameter requires verifying multiple related variables across the document set. The aforementioned are a few examples.

### Basic Rules vs. Interdependent Enforcement

| Parameter | Naive If-Else Check | DelhiTSR Interdependent Enforcement |
| :--- | :--- | :--- |
| **Prior Link Deeds** | Flags any cited document number not found in the upload list. | Checks document origin first. Exempts government allotments (DDA, L&DO, Gazette notifications) from missing root deed defects while enforcing link deed continuity for private transfers. |
| **e-Stamp Authorization** | Checks if an e-stamp certificate exists on page 1. | Scans all pages, validates state certificate number formatting, and cross-checks the e-stamp buyer against deed transferors and power of attorney records. |
| **Encumbrance Recitals** | Reads text phrases like "free from encumbrances". | Cross-references body text declarations against active mortgage entries, court attachment notices, and bank charge records in the session bundle. |
| **Legal Heir Succession** | Checks if the word "heir" or "intestate" is present. | When a deceased owner's property is sold by one family member, the engine checks whether all other legal heirs have signed registered Relinquishment Deeds giving up their ownership shares. |

---

### Core Enforcement Mechanisms

1. **Document Provenance and Root Context**  
   Before checking title continuity, the engine evaluates whether the starting deed is a government allotment (DDA, L&DO, President of India grant). If so, it exempts the initial transfer from missing root deed defects. For private transfers, it enforces complete link deed chain continuity.

2. **Cross-Page Entity and Role Matching**  
   The engine extracts party identities, aliases, and capacities across all pages. It verifies that e-stamp purchasers match the executing transferors, ensuring third-party stamp purchases without authorization are flagged immediately.

3. **Recital and Encumbrance Reconciliation**  
   Declarations made in deed text are checked against independent document findings. If a deed states the property is unencumbered but mortgage recitals or bank charges exist in related session documents, a contradiction flag is raised.

4. **Legal Heir Relinquishment Verification**  
   When a property owner dies without a Will, all legal heirs inherit equal ownership shares. If only one heir sells the property, the engine verifies whether registered Relinquishment or Release Deeds exist from all other legal heirs to confirm the seller has 100% transferable title.

5. **Weighted Severity Classification**  
   Findings are mapped to a 5-tier legal scale based on legal weight rather than binary flags:
   - **Material Defect**: Critical flaws (missing private link deeds, unreleased legal heir ownership shares).
   - **Substantive Defect**: Major flaws (e-stamp party mismatches, invalid certificate formats).
   - **Duty Requisition**: Financial deficits (stamp duty shortfalls).
   - **Procedural Anomaly**: Operational gaps (missing witness details, unverified SRO seals).
   - **Record Notation**: System logs and informational observations.

---

## Installation & Local Setup

### Prerequisites

* Python 3.10+
* OpenCV & Poppler dependencies
* Tesseract OCR / ONNX Runtime (for RapidOCR)

### Step 1: Clone Repository & Create Virtual Environment

```bash
git clone https://github.com/your-org/tsr-engine.git
cd tsr-engine

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Create a `.env` file in the root directory:

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
GEMINI_API_KEY=your-google-gemini-api-key
DATABASE_URL=sqlite:///instance/tsr_engine.db
```

### Step 4: Run Development Server

```bash
python app.py
```

---

## Repository Structure

```
tsr-engine/
├── app.py                     # Flask application entrypoint & API routes
├── main.py                    # OpenCV deskewing, RapidOCR engine & 4-Pass LLM extraction
├── circle_rates.py            # Circle rates, stamp duty matrices & Haryana jurisdiction classifier
├── doris_scraper.py           # Delhi DORIS sub-registrar scraper session manager
├── deed_doc_scraper.py        # Sub-Registrar document indexing scraper
├── recital_verification.py    # Recital verification & boundary cross-matcher
├── stamp_verification.py      # E-Stamp certificate validation engine
├── static/                    # CSS, JavaScript UI components & assets
├── templates/
│   └── workspace.html         # Main dashboard & metric card views
├── instance/                  # SQLite database instance
├── uploads/                   # Temporary upload directory
└── requirements.txt           # Python dependencies manifest
```
