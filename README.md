# DelhiTSR
Title Intelligence Engine (Delhi NCT & Haryana [BETA])

<p>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python Version"></a>
  <a href="https://flask.palletsprojects.org/"><img src="https://img.shields.io/badge/Framework-Flask-000000?style=flat-square&logo=flask&logoColor=white" alt="Framework"></a>
  <a href="https://opencv.org/"><img src="https://img.shields.io/badge/Vision-OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white" alt="OpenCV"></a>
  <a href="https://deepmind.google/"><img src="https://img.shields.io/badge/AI-Gemini%202.5%20Vision-4285F4?style=flat-square&logo=google&logoColor=white" alt="AI Engine"></a>
  <a href="#complete-specification-of-all-94-discrepancy--validation-rules"><img src="https://img.shields.io/badge/Rules-94%20Deterministic%20Checks-7B2CBF?style=flat-square" alt="Rule Engine"></a>
</p>

DelhiTSR is a specialized title intelligence engine for property legal due diligence across the National Capital Territory (NCT) of Delhi and Haryana *(Haryana support operates in BETA)*. Designed for institutional mortgage underwriting, title search reporting (TSR), and legal property verification, it ingests multi-deed ownership chains, executes computer vision page deskewing and dual-engine OCR, extracts 80 structured document parameters through a 4-pass LLM pipeline, and evaluates title history against 94 deterministic rules covering statutory stamp duty tariffs, municipal transfer taxes, boundary continuity, and local Sub-Registrar Office (SRO) regulations.

> **Note**: DelhiTSR is under active development. While the engine currently parses documents, reconciles taxes, and audits 94 legal rules, compiled Title Search Report (TSR) generation will be added in future releases.

---

## Table of Contents

- [System Architecture \& Pipeline Workflow](#system-architecture--pipeline-workflow)
- [Module 1: Document Pre-processing \& Dual-Engine OCR](#module-1-document-pre-processing--dual-engine-ocr)
- [Module 2: 4-Pass 80-Parameter Extraction Pipeline](#module-2-4-pass-80-parameter-extraction-pipeline)
- [Module 3: Universal Tax \& Local Authority Reconciliation Engine](#module-3-universal-tax--local-authority-reconciliation-engine)
  - [Delhi Statutory Duty \& MCD Tax Matrix](#delhi-statutory-duty--mcd-tax-matrix)
  - [Haryana Urban vs. Rural Jurisdiction Engine [BETA]](#haryana-urban-vs-rural-jurisdiction-engine-beta)
  - [Constituent Tax Aggregation Algorithm](#constituent-tax-aggregation-algorithm)
- [5-Tier Legal Severity Classification Framework](#5-tier-legal-severity-classification-framework)
- [Complete Specification of All 94 Discrepancy \& Validation Rules](#complete-specification-of-all-94-discrepancy--validation-rules)
  - [1. Legal \& Statutory Compliance Audits](#1-legal--statutory-compliance-audits)
  - [2. Consideration \& Financial Valuation Audits](#2-consideration--financial-valuation-audits)
  - [3. Title Chain \& Ownership Integrity Audits](#3-title-chain--ownership-integrity-audits)
  - [4. Party Identity, PAN \& KYC Audits](#4-party-identity-pan--kyc-audits)
  - [5. Party Name Spelling Deviation Audits](#5-party-name-spelling-deviation-audits)
  - [6. Mortgage, Encumbrance \& Charge Release Audits](#6-mortgage-encumbrance--charge-release-audits)
  - [7. Lender Bank Match \& Merger Transition Audits](#7-lender-bank-match--merger-transition-audits)
  - [8. Project Metadata Reconciliation Audits](#8-project-metadata-reconciliation-audits)
  - [9. Statutory Stamp Duty \& Municipal Tax Audit Matrix](#9-statutory-stamp-duty--municipal-tax-audit-matrix)
  - [10. Haryana Jurisdiction \& Revenue Estate Audits [BETA]](#10-haryana-jurisdiction--revenue-estate-audits-beta)
  - [11. Pre-Processing \& Computer Vision Rules](#11-pre-processing--computer-vision-rules)
  - [12. Meta-Rules \& Legal Privilege Enforcement](#12-meta-rules--legal-privilege-enforcement)
- [No-Verdict Policy \& Legal Privilege Protection](#no-verdict-policy--legal-privilege-protection)
- [Setup \& Local Development Installation](#setup--local-development-installation)
- [Repository File Blueprint](#repository-file-blueprint)

---

## System Architecture & Pipeline Workflow

Property title chains in India consist of heterogeneous, multi-page scanned documents spanning 30+ years of ownership history. Standard document parsing engines fail on these inputs due to split tax receipts (e.g., separate stamp duty and local authority tax payments), missing localized statutory context (e.g., pre-2003 DDA conveyance stamp exemptions), and LLM context drift on long files.

DelhiTSR decouples image pre-processing, schema extraction, tax reconciliation, and rule evaluation into isolated processing stages:

```
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│  Raw Deed PDF / Scan   │ ───► │  Module 1: Vision OCR  │ ───► │ Module 2: 4-Pass LLM   │
│  Ingestion & Upload    │      │ Deskew & Text Recovery │      │ 20-Field Extraction    │
└────────────────────────┘      └────────────────────────┘      └────────────────────────┘
                                                                            │
                                                                            ▼
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│  Structured Workspace  │ ◄─── │  Module 4: 94 Rule     │ ◄─── │ Module 3: Tax & Local  │
│  Interactive Dashboard │      │  Discrepancy Engine   │      │  Body Reconciler       │
└────────────────────────┘      └────────────────────────┘      └────────────────────────┘
```

---

## Module 1: Document Pre-processing & Dual-Engine OCR

Before document text is parsed, pages undergo automated computer vision processing:

1. **Orientation Angle Detection**: `pypdfium2` renders PDF pages to numpy arrays. OpenCV detects baseline text orientation using minimum area bounding rectangles (`cv2.minAreaRect`).
2. **Affine Rotation**: Rotates pages back to 0° alignment for detected skew angles between 0.5° and 45.0°.
3. **Otsu Binarization**: Cleans background yellowing, shadow artifacts, and faint watermarks using Otsu thresholding (`cv2.THRESH_OTSU`).
4. **Adaptive Text Extraction Pipeline**:
   * **Direct Vector Stream**: Embedded digital fonts are extracted directly via `pdfplumber`.
   * **RapidOCR Fallback**: If page text density is below 40 characters per page (indicating scanned images), pages automatically route to `rapidocr-onnxruntime` with OpenCV contrast enhancement.
   * **Multimodal Vision Fallback**: Handwritten recitals, faint endorsement stamps, or damaged paper marginalia route to Gemini 2.5 Vision.

---

## Module 2: 4-Pass 80-Parameter Extraction Pipeline

To prevent context drift and attention splitting across 50+ page legal deeds, extraction is partitioned into 4 specialized schema passes, extracting 80 target parameters per document:

* **Pass 1: Document Identity & Stamp Paper Ledger**
  * Registration number, volume/page numbers, SRO office, e-stamp certificate number, issue date, article number, execution date, registration date.
* **Pass 2: Party Identity, Gender & KYC Ledger**
  * Transferor and transferee names, PAN identifiers, masked Aadhaar numbers, gender classification (sole female, joint, male), PIN codes, party residential addresses.
* **Pass 3: Financial Consideration & Payment Instrument Ledger**
  * Stated consideration, rental fee/premium, secured loan principal, e-stamp value, MCD tax amount, local authority tax, cheque/DD/RTGS numbers, TDS Form 26QB verification.
* **Pass 4: Property Schedule & Boundary Chain**
  * Property address, plot/flat number, survey/khasra/hadbast number, floor level, share percentage, area measurement and units (Sq. Yards, Bigha, Biswas, Sq. Meters), north/south/east/west boundaries.

---

## Module 3: Universal Tax & Local Authority Reconciliation Engine

### Delhi Statutory Duty & MCD Tax Matrix

Evaluates compliance under the Indian Stamp Act, 1899 (Schedule I-A Delhi Amendment) and Section 147 of the Delhi Municipal Corporation Act, 1957:

| Period / Document Category | Sole Female Purchaser | Joint (Female + Male) | Male Purchaser | Statutory Reference |
| :--- | :--- | :--- | :--- | :--- |
| **Pre-2003 Resale Conveyances** | 8.00% | 8.00% | 8.00% | Article 23 (5% SD + 3% MCD Tax) |
| **Pre-2003 DDA / Government Conveyances** | **6.00%** | **6.00%** | **6.00%** | Pre-2003 DDA Statutory Rule |
| **2003 – 2007 Conveyance Deeds** | 5.00% | 7.00% | 8.00% | Delhi Notification 2003 Tariff |
| **2008 – Present Conveyance Deeds** | **4.00%** *(3% SD + 1% MCD)* | **5.00%** *(3.5% SD + 1.5% MCD)* | **6.00%** *(3% SD + 3% MCD)* | Current NCT Delhi Duty Schedule |
| **Blood Relative Gift Deed** | 3.00% | 3.00% | 3.00% | Family Concession Schedule (+ 1% Reg Fee) |
| **Simple Mortgage without Possession** | 2.00% | 2.00% | 2.00% | Article 40 (2% on Principal Amount) |
| **Equitable Mortgage (Title Deposit)** | 0.50% | 0.50% | 0.50% | Article 40(b) Capped Schedule |

### Haryana Urban vs. Rural Jurisdiction Engine [BETA]

> **[BETA STAGE MODULE]**: *All Haryana statutory stamp duty, registration fee slab, and urban vs. rural Gram Panchayat jurisdiction rules operate under BETA status.*

Evaluates compliance under the Haryana Stamp Act and Haryana Municipal Corporation Act:

| Transferee Composition | Urban Municipal Area *(MCG / MCF / Sector / HUDA)* | Rural Gram Panchayat Area *(Hadbast / Revenue Estate)* |
| :--- | :--- | :--- |
| **Sole Female Purchaser(s)** | **5.00%** *(3% Stamp Duty + 2% Municipal Duty)* | **3.00%** *(3% Stamp Duty + 0% Municipal Duty)* |
| **Joint Purchasers (Male + Female)** | **6.00%** *(4% Stamp Duty + 2% Municipal Duty)* | **4.00%** *(4% Stamp Duty + 0% Municipal Duty)* |
| **Male Purchaser(s)** | **7.00%** *(5% Stamp Duty + 2% Municipal Duty)* | **5.00%** *(5% Stamp Duty + 0% Municipal Duty)* |

* **Haryana Registration Fee Slabs [BETA]**: Haryana applies a slab-based registration fee structure capped at ₹50,000 for considerations over ₹1 Crore.

### Constituent Tax Aggregation Algorithm

To prevent false deficit findings when stamp duty and local body transfer taxes are paid on separate receipts, `_compute_total_stamp_duty_paid` executes dynamic aggregation:

`Total Duty Paid = Max(E-Stamp Certificate Amount, Total Non-Judicial Stamp Paper, Sum of Constituent Line Items)`

Where `Sum of Constituent Line Items = State Stamp Duty (Article 23) + MCD Transfer Tax (Sec 147) + Local Body Tax`.

---

## 5-Tier Legal Severity Classification Framework

- **Material Defect**
- **Substantive Defect**
- **Statutory Requisition**
- **Procedural Anomaly**
- **Record Notation**

---

## Complete Specification of All 94 Discrepancy & Validation Rules

### 1. Legal & Statutory Compliance Audits (10 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `VOID_DEED_WRONG_SRO` | **Material Defect** | SRO Jurisdiction Mismatch | Section 28 Registration Act 1908 territorial jurisdiction audit. |
| `GPA_POST_2011_INVALID` | **Material Defect** | Post-2011 GPA Title Transfer | *Suraj Lamp & Industries v. State of Haryana* (2011) Supreme Court ruling. |
| `MISSING_GPA_AUTHORIZATION` | **Material Defect** | Missing Attorney Authorization | Triggers when attorney executes deed without registered GPA in chain. |
| `UNREGULARIZED_GPA_CHAIN` | **Substantive Defect** | Unregularized GPA Chain | Chain concludes with GPA rather than registered Sale Deed. |
| `PROPERTY_NOT_IN_DELHI` | **Procedural Anomaly** | Out-of-Jurisdiction Location | Property parsed outside NCT Delhi revenue districts. |
| `SEC28_REG_ACT_AUDIT` | **Record Notation** | Mandatory SRO Validation | Territorial compliance against 11 NCT Delhi Revenue Districts. |
| `SRO_TERRITORY_MATRIX` | **Record Notation** | SRO Territory Ledger Mapping | Validates SRO office assignments against 350+ Delhi Locality Ledger. |
| `SRO_CODE_NORMALIZER` | **Record Notation** | SRO Code Canonicalization | Normalizes SRO strings (e.g. SRO V-A Hauz Khas -> `5a`). |
| `SRO_LOCALITY_TOKEN_MATCH` | **Record Notation** | Locality Boundary Token Check | Cross-references address locality against SRO boundary ledger. |
| `EXPLICIT_SRO_RECITAL` | **Record Notation** | Explicit Header SRO Recital | Validates SRO jurisdiction explicitly stated in header endorsement text. |

### 2. Consideration & Financial Valuation Audits (7 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `MISSING_SALE_CONSIDERATION` | **Material Defect** | Missing Sale Price | Section 54 Transfer of Property Act 1882 compliance. |
| `MISSING_RENTAL_CONSIDERATION` | **Material Defect** | Missing Lease License Fee | Section 105 Transfer of Property Act 1882 lease premium check. |
| `MISSING_MORTGAGE_VALUE` | **Material Defect** | Missing Secured Loan Principal | Section 58 Transfer of Property Act 1882 loan principal check. |
| `GIFT_DEED_WITH_CONSIDERATION` | **Material Defect** | Gift with Consideration | Section 122 Transfer of Property Act 1882 voluntary gift check. |
| `ZERO_CONSIDERATION` | **Material Defect** | Zero Value Conveyance | Flags ₹0 consideration sale deeds violating Stamp Act. |
| `CONSIDERATION_ANOMALY` | **Substantive Defect** | Transaction Price Drop | Price drops below 70% of historical sale price in same chain. |
| `AMOUNT_WORDS_FIGURES_MISMATCH` | **Material Defect** | Words vs. Figures Mismatch | Discrepancy between value written in words vs numeric figures. |

### 3. Title Chain & Ownership Integrity Audits (10 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `CHAIN_BREAK` | **Material Defect** | Title Chain Break | Seller has no prior record of ownership or holds 0% share on record. |
| `AREA_MISMATCH` | **Material Defect** | Significant Area Mismatch | Area differs by >5% from expected inherited fractional share. |
| `AREA_MISMATCH_MILD` | **Procedural Anomaly** | Minor Area Deviation | Area difference under 3 sq. ft. due to unit rounding. |
| `SOCIETY_MISMATCH` | **Material Defect** | Building Name Mismatch | Building or society name conflicts with root document. |
| `ID_MISMATCH` | **Material Defect** | Property ID Conflict | Plot, Survey, Khasra, or Flat number changes unexpectedly. |
| `DATE_ORDER_DEVIATION` | **Material Defect** | Date Sequence Anomaly | Registration date prior to execution date or predecessor deed date. |
| `CHAIN_HANDSHAKE_VERIFIED` | **Record Notation** | Title Handshake Verification | Transferee in deed N exactly matches transferor in deed N+1. |
| `RECTIFICATION_APPLIED` | **Record Notation** | Clerical Rectification | Error resolved by subsequent registered Rectification Deed. |
| `ROOT_DEED_TRACED` | **Record Notation** | Root of Title Origin | Traces original DDA/L&DO allotment or President of India grant. |
| `LEASEHOLD_CONVERTED` | **Record Notation** | Freehold Conversion Traced | Tracks conversion from leasehold tenure to absolute freehold. |

### 4. Party Identity, PAN & KYC Audits (7 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `INVALID_PAN_FORMAT` | **Material Defect** | Invalid PAN Format | Tax identifier fails 10-char regex (`[A-Z]{5}[0-9]{4}[A-Z]`). |
| `INVALID_PIN_FORMAT` | **Procedural Anomaly** | Invalid PIN Format | Postal code fails 6-digit numeric pattern. |
| `PAN_TRANSFEROR_TRANSFEREE_CLASH` | **Material Defect** | Intra-document PAN Clash | Seller and buyer share the exact same PAN in same deed. |
| `PIN_TRANSFEROR_TRANSFEREE_CLASH` | **Procedural Anomaly** | Intra-document PIN Clash | Parties share same PIN code in same document. |
| `SHARED_PAN` | **Material Defect** | Inter-document PAN Reuse | Same PAN shared by different named parties across deeds. |
| `SHARED_PIN` | **Procedural Anomaly** | Inter-document ID Reuse | Same personal identifier shared by different parties. |
| `MASKED_AADHAAR_VALID` | **Record Notation** | Masked Aadhaar Verified | Accepts UIDAI Masked Aadhaar (`XXXX-XXXX-1234`) as valid. |

### 5. Party Name Spelling Deviation Audits (6 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `NAME_DEVIATION_NORMALIZED` | **Record Notation** | Normalized Match | Spaces, dots, or title prefixes stripped ("Mr. Raj" -> "Raj"). |
| `NAME_DEVIATION_MINOR` | **Record Notation** | Minor Deviation | Levenshtein edit distance = 1 ("Sanjay" vs "Sanjeev"). |
| `NAME_DEVIATION_MILD` | **Procedural Anomaly** | Mild Deviation | Levenshtein edit distance = 2 ("Chauhan" vs "Chowhan"). |
| `NAME_DEVIATION_SEVERE` | **Material Defect** | Severe Deviation | Edit distance >= 3, indicating major spelling conflict. |
| `NAME_DEVIATION_ALIAS` | **Record Notation** | Legal Alias Match | Spelling mismatch resolved via registered alias tables. |
| `NAME_DEVIATION_UNKNOWN` | **Material Defect** | Unresolved Name Clash | Party name does not match any prior owner in chain. |

### 6. Mortgage, Encumbrance & Charge Release Audits (16 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `INVALID_MORTGAGOR` | **Material Defect** | Invalid Mortgagor | Party mortgaging property previously conveyed interest away. |
| `UNKNOWN_MORTGAGOR` | **Material Defect** | Unknown Mortgagor | Mortgagor has no prior ownership record in chain. |
| `RELEASE_ORPHAN` | **Material Defect** | Unlinked Release Deed | Release deed has no corresponding active mortgage in chain. |
| `RELEASE_AMBIGUOUS` | **Material Defect** | Ambiguous Release Link | Release deed matches multiple active mortgages. |
| `RELEASE_LINK_A` | **Record Notation** | Link Tier A (Exact Match) | Exact reg number match + SRO, year, and party consistency. |
| `RELEASE_LINK_B` | **Record Notation** | Link Tier B (Verified Match) | Reg number match + at least two corroborative parameters. |
| `RELEASE_LINK_C` | **Record Notation** | Link Tier C (Matched Link) | Reg number match with minimal corroboration. |
| `RELEASE_LINK_D` | **Procedural Anomaly** | Link Tier D (Fuzzy Link) | Fuzzy reg number match (Levenshtein <= 2) + 3 parameters. |
| `RELEASE_LINK_E` | **Material Defect** | Link Tier E (Disputed Link) | Fuzzy reg number match without corroboration. |
| `RELEASE_LINK_F` | **Procedural Anomaly** | Link Tier F (Indirect Link) | Party name, SRO, and execution year match without reg number. |
| `RELEASE_PARTY_MISMATCH` | **Material Defect** | Release Party Conflict | Release deed references mortgage but lists different parties. |
| `RELEASE_AMOUNT_MISMATCH` | **Material Defect** | Release Amount Conflict | Release deed references mortgage but cites different loan amount. |
| `UNRESOLVED_MORTGAGE` | **Substantive Defect** | Active Unresolved Charge | Active registered mortgage on title with no satisfaction on record. |
| `MORTGAGE_RESOLVED` | **Record Notation** | Satisfied Charge | Mortgage fully released and discharged. |
| `PARTIALLY_RELEASED` | **Substantive Defect** | Partial Discharge Shortfall | Linked release amounts are less than registered mortgage principal. |
| `RELEASE_OVERFLOW` | **Material Defect** | Discharge Value Overflow | Linked release amounts exceed registered mortgage principal. |

### 7. Lender Bank Match & Merger Audits (6 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `LENDER_MISMATCH` | **Material Defect** | Lender Bank Mismatch | Discharging bank does not match original mortgagee bank. |
| `LENDER_CONSISTENT` | **Record Notation** | Consistent Lender | Lender names match exactly across mortgage and release. |
| `LENDER_ALIAS_MATCH` | **Record Notation** | Lender Alias Match | Match resolved via standard bank alias tables ("SBI" = "State Bank of India"). |
| `LENDER_BRANCH_DIFF` | **Record Notation** | Branch Variant Match | Same lender bank, different branch description. |
| `LENDER_MERGER` | **Substantive Defect** | Bank Merger Transition | Discharging bank matches via historical merger records (e.g. Corporation Bank -> Union Bank). |
| `LENDER_FUZZY_MATCH` | **Procedural Anomaly** | Fuzzy Lender Match | Lender names highly similar (character match >= 0.85). |

### 8. Project Metadata Reconciliation Audits (10 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `METADATA_LOCALITY_MISMATCH` | **Procedural Anomaly** | Locality Mismatch | Locality in deed differs from project metadata setting. |
| `METADATA_SRO_MISMATCH` | **Procedural Anomaly** | SRO Office Mismatch | SRO office in deed differs from project metadata setting. |
| `METADATA_AUTHORITY_MISMATCH` | **Procedural Anomaly** | Authority Mismatch | Fails to reference MCD/DDA indicators matching project setting. |
| `METADATA_LAND_USE_MISMATCH` | **Procedural Anomaly** | Land Use Mismatch | Land use classification differs from project setting. |
| `METADATA_FLAT_MISMATCH` | **Procedural Anomaly** | Unit Number Mismatch | Unit or flat number parsed differs from project setting. |
| `METADATA_FLOOR_MISMATCH` | **Procedural Anomaly** | Floor Level Mismatch | Floor level parsed differs from project setting. |
| `METADATA_PROPERTY_ID_MISMATCH` | **Procedural Anomaly** | Property ID Mismatch | Khasra/Plot/Survey number differs from project setting. |
| `METADATA_UPIC_MISMATCH` | **Procedural Anomaly** | MCD UPIC Mismatch | Property UPIC in deed differs from project setting. |
| `METADATA_ADDRESS_MISMATCH` | **Procedural Anomaly** | Address Mismatch | Address fuzzy similarity score below 0.35 threshold. |
| `MISSING_CRITICAL_FIELDS` | **Procedural Anomaly** | Missing Mandatory Metadata | Consolidates warnings for deeds missing crucial values. |

### 9. Statutory Stamp Duty & Municipal Tax Audit Matrix (23 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `PRE2003_STD_8PCT` | **Statutory Requisition** | Pre-2003 Resale Standard Rate | Enforces 8.00% Combined Rate (5% SD + 3% MCD Tax). |
| `PRE2003_DDA_6PCT` | **Statutory Requisition** | Pre-2003 DDA Concessional Rate | Enforces 6.00% Rate (inclusive of MCD tax) for pre-2003 DDA allotments. |
| `RATE_2003_MALE_8PCT` | **Statutory Requisition** | 2003-2007 Male Buyer Tariff | Enforces 8.00% Combined Rate for male buyers. |
| `RATE_2003_JOINT_7PCT` | **Statutory Requisition** | 2003-2007 Joint Buyer Tariff | Enforces 7.00% Combined Rate for joint buyers. |
| `RATE_2003_FEMALE_5PCT` | **Statutory Requisition** | 2003-2007 Female Buyer Tariff | Enforces 5.00% Combined Rate for female buyers. |
| `RATE_PRESENT_MALE_6PCT` | **Statutory Requisition** | 2008-Present Male Buyer Tariff | Enforces 6.00% Combined Rate (3% SD + 3% MCD Tax). |
| `RATE_PRESENT_JOINT_5PCT` | **Statutory Requisition** | 2008-Present Joint Buyer Tariff | Enforces 5.00% Combined Rate (3.5% SD + 1.5% MCD Tax). |
| `RATE_PRESENT_FEMALE_4PCT` | **Statutory Requisition** | 2008-Present Female Buyer Tariff | Enforces 4.00% Combined Rate (3% SD + 1% MCD Tax). |
| `GIFT_FAMILY_3PCT` | **Statutory Requisition** | Gift Deed Family Concession | Applies 3.00% Stamp Duty + 1.00% Reg Fee for family gifts. |
| `GIFT_NON_FAMILY_STD` | **Statutory Requisition** | Gift Deed Non-Family Tariff | Applies standard general conveyance rates (4%-6%). |
| `MORTGAGE_SIMPLE_2PCT` | **Statutory Requisition** | Simple Mortgage Tariff | Applies 2.00% Stamp Duty on loan principal under Article 40. |
| `MORTGAGE_EQUITABLE_0.5PCT` | **Statutory Requisition** | Equitable Mortgage Tariff | Applies 0.50% Stamp Duty on deposit of title deeds. |
| `RELINQUISH_NOMINAL_SD` | **Statutory Requisition** | Relinquishment Nominal Duty | Applies nominal ₹150 stamp duty for family share releases. |
| `RELINQUISH_NOMINAL_REG` | **Statutory Requisition** | Relinquishment Nominal Fee | Applies nominal ₹100 registration fee for family share releases. |
| `RELINQUISH_CONSIDERATION` | **Statutory Requisition** | Relinquishment Consideration Duty | Applies 2.00% SD + 1.00% Reg Fee on monetary consideration. |
| `RECONVEYANCE_SD_100` | **Statutory Requisition** | Reconveyance Nominal Duty | Applies nominal ₹100 stamp duty under Article 55. |
| `RECONVEYANCE_REG_100` | **Statutory Requisition** | Reconveyance Nominal Fee | Applies nominal ₹100 registration fee. |
| `LEASE_2PCT_RENT` | **Statutory Requisition** | Lease / License Fee Tariff | Applies 2.00% Stamp Duty on annual rent / license fee. |
| `REG_FEE_1PCT` | **Statutory Requisition** | Standard Registration Fee | Applies 1.00% of consideration / market value. |
| `SD_ROUNDING_TOLERANCE` | **Record Notation** | Rounding Math Tolerance | Allows ₹1 mathematical rounding tolerance. |
| `COMBINED_SD_RECONCILE` | **Record Notation** | Combined Tax Reconciler | Reconciles separate 3% SD + 3% MCD Tax into 6% total. |
| `INSUFFICIENT_STAMP_DUTY` | **Statutory Requisition** | Stamp Duty Shortfall | Flags paid stamp duty falling below statutory requirement. |
| `INSUFFICIENT_REGISTRATION_FEE` | **Statutory Requisition** | Registration Fee Shortfall | Flags paid registration fee falling below statutory requirement. |

### 10. Haryana Jurisdiction & Revenue Estate Audits (4 Rules) [BETA STAGE]

> **Note**: *All Haryana rules and jurisdiction audit routines operate in BETA.*

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `HARYANA_URBAN_MUNICIPAL` | **Statutory Requisition** | Haryana Urban Municipal Tariff [BETA] | Enforces 5% (Female) / 6% (Joint) / 7% (Male) tariff in MCG/MCF/HUDA areas. |
| `HARYANA_RURAL_GRAM_PANCHAYAT` | **Statutory Requisition** | Haryana Rural Gram Panchayat Tariff [BETA] | Enforces 3% (Female) / 4% (Joint) / 5% (Male) tariff in Gram Panchayat areas. |
| `HARYANA_REGISTRATION_SLAB` | **Statutory Requisition** | Haryana Registration Fee Slab [BETA] | Enforces slab-based registration fee capped at max ₹50,000. |
| `HARYANA_JURISDICTION_CLASSIFIED` | **Record Notation** | Haryana Jurisdiction Audit [BETA] | Logs classification into Urban Municipal vs Rural Gram Panchayat. |

### 11. Pre-Processing & Computer Vision Rules (9 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `OPENCV_SKEW_DETECT` | **Record Notation** | OpenCV Baseline Skew Detect | Detects page line orientation using `cv2.minAreaRect`. |
| `DESKEW_TRANSFORM_BOUNDS` | **Record Notation** | Deskew Rotation Bounds | Applies affine rotation for skew angles between 0.5° and 45°. |
| `OTSU_BINARIZATION` | **Record Notation** | Otsu Contrast Binarization | Cleans background yellowing and watermarks via Otsu thresholding. |
| `PDF_VECTOR_EXTRACT` | **Record Notation** | PDF Vector Stream Extract | Direct extraction of embedded PDF vector fonts via `pdfplumber`. |
| `RAPIDOCR_FALLBACK_TRIGGER` | **Record Notation** | RapidOCR Fallback Trigger | Triggers RapidOCR + OpenCV when text density < 40 chars/page. |
| `PARALLEL_4PASS_SCHEMA` | **Record Notation** | 4-Pass 20-Field Schema | Splits 80 document fields across 4 parallel API passes. |
| `ESTAMP_PARTY_ALIGN` | **Record Notation** | E-Stamp Party Alignment | Verifies e-stamp party names against Vendor/Vendee roles. |
| `PAYMENT_LEDGER_SUM` | **Record Notation** | Payment Instrument Summation | Verifies sum of Payment Instruments + TDS = Consideration. |
| `TDS_26QB_AUDIT` | **Record Notation** | TDS Form 26QB Verification | Extracts BSR codes, challan serials, and 1% TDS payment details. |

### 12. Meta-Rules & Legal Privilege Enforcement (3 Rules)

| Code | Severity | Finding Name | Legal & Logical Basis |
| :--- | :--- | :--- | :--- |
| `NO_VERDICT_PRIVILEGE_GUARD` | **Record Notation** | No Legal Verdict Policy | Enforces prohibition against rendering legal verdicts. |
| `DISCREPANCY_DEDUPLICATION` | **Record Notation** | Rule Deduplication Engine | Filters duplicate error findings generated across passes. |
| `PROVISIONAL_AUDIT_STATE` | **Record Notation** | Provisional Audit State | Flags workspaces undergoing active processing. |

---

## Legal Privilege Policy

1. **Factual Output Only**: The engine reports objective observations (such as stamp duty calculations, boundary discrepancies, or missing authorization documents). It does not declare titles void, defective, or invalid.
2. **Advocate Support**: Output is structured to support legal review while preserving advocate-client privilege.

---

## Setup & Local Development Installation

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

## Repository File Blueprint

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
