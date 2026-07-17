# Technical Specification: Title Audit & Verification Engine

This document provides a comprehensive technical overview of the automated legal validation rules, statutory audits, and title intelligence features implemented within the platform. It details how the engine evaluates land, property, and transaction records in Delhi to assess title viability, financial exposure, and registration compliance.

---

## 1. Architectural Philosophy & Dual-Tier Verification

The platform employs a **Dual-Tier Verification System** to ensure high-fidelity audits:
1. **Tier-1 (Specialized LLM Cognitive Engine)**: Leverages Gemini to parse raw documents, perform deep semantic extraction of legal terminology (e.g., party intents, boundary descriptions, witness records, and schedules), and classify complex addresses using grounded reference category slabs.
2. **Tier-2 (Deterministic Rules Engine)**: Evaluates the extracted structured JSON payload against statutory laws, local municipal gazetteers, historical circle rate brackets, and mathematical continuity algorithms.

```
                  ┌──────────────────────────────────────┐
                  │ Raw Property Deed (PDF / OCR Stream) │
                  └──────────────────┬───────────────────┘
                                     ▼
                  ┌──────────────────────────────────────┐
                  │ Tier-1: LLM Parsing & Classification │
                  │  (Schema Mapping & Locality Class)  │
                  └──────────────────┬───────────────────┘
                                     ▼
                  ┌──────────────────────────────────────┐
                  │   Tier-2: Deterministic Rules &      │
                  │       Local Gazetteers Database      │
                  └──────────────────┬───────────────────┘
                                     ▼
         ┌───────────────────────────┴───────────────────────────┐
         ▼                           ▼                           ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Valuation Audit │         │ Chain of Title  │         │ Encumbrance Map │
│  (Circle Rates, │         │  (Continuity,   │         │ (Mortgages, Re- │
│  Stamp Duty)    │         │  PAN tracking)  │         │ conveyances)    │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

---

## 2. Circle Rates & Valuation Audit Engine

The valuation engine implements the complex circle rate calculations specified by the **Government of National Capital Territory of Delhi (GNCTD)**. 

### A. Slabs & Classifications
The base circle rates are determined by classifying the locality into categories from **A** (highest, e.g., Vasant Vihar, Hauz Khas Enclave) to **H** (lowest, e.g., rural villages). The base rate is adjusted using three key multipliers:
1. **Usage Multiplier**: Reflects the commercial intensity of the property:
   * **Residential**: `1.0x`
   * **Public/Institutional**: `1.25x`
   * **Industrial**: `2.0x`
   * **Commercial**: `3.0x`
2. **Structure Multiplier**: Varies by structure type and classification:
   * **DDA / Cooperative Society Flats**: Slabs calculated by area (under 50 sqm, 50-100 sqm, and over 100 sqm).
   * **Private Builder Flats**: Flat rate applied across structure categories with a fixed base structure cost.
   * **Plots/Land**: Calculated directly on plot area with structural depreciation rules.
3. **Age Depreciation Multiplier**: Accounted for using the year of construction relative to the transaction execution year:
   * **< 10 Years**: `1.00`
   * **10 - 20 Years**: `0.90`
   * **20 - 30 Years**: `0.80`
   * **30 - 40 Years**: `0.70`
   * **> 40 Years**: `0.60`

### B. Circle Rate Value Formula
For DDA/Society Flats, the expected minimum valuation is:
\[V_{expected} = \text{Stated Area (sqm)} \times R_{flat\_slab\_rate} \times M_{usage} \times M_{age\_factor}\]

For Private Builder Flats & Plots, the calculation integrates the land share value and structural cost:
\[V_{expected} = (\text{Land Area} \times R_{locality\_rate} \times M_{usage}) + (\text{Built Area} \times R_{structure\_rate} \times M_{age\_factor})\]

### C. Legal & Tax Implications Evaluated
* **Stamp Act Section 47-A**: If the declared transaction value is lower than the calculated circle rate value, the engine flags a **Voidance/Under-valuation Risk**. The deed faces impounding by the Sub-Registrar Office (SRO) for stamp duty recovery.
* **Income Tax Act Section 50C & 56(2)(x)**: If the transaction value falls below the circle rate (outside the statutory **10% tolerance band**), the engine flags tax penalty exposure:
  * **Seller**: Deemed capital gains taxed on the higher circle rate value.
  * **Buyer**: The difference is taxed as "Income from Other Sources".

---

## 3. The Mortgage & Encumbrance Layer

The engine tracks the financial health of the property by building a chronological ledger of mortgage deeds, equitable deposits of title deeds, and subsequent discharge or reconveyance deeds.

```
      ┌────────────────────────────────────────────────────────┐
      │                  CHRONOLOGICAL LEDGER                  │
      ├────────────────────────────────────────────────────────┤
      │ 2008: Mortgage Deed (PNB) ──────► Stated Loan: ₹3.5M   │
      │                                                        │
      │ 2012: Reconveyance Deed (PNB) ──► Discharged: ₹3.5M   │
      │                                                        │
      │ Status: RESOLVED (Clean Title, No Active Charge)       │
      └────────────────────────────────────────────────────────┘
```

### A. Mortgage Matching Logic
1. **Lender Matching**: Verifies that the bank or financial institution executing the discharge matches the original mortgagee.
2. **Partial Release Tracking**: Evaluates whether a release/reconveyance covers the entire outstanding principal or only a fractional release of co-borrowers/units.
3. **Discharge Surcharges**: Confirms nominal statutory stamp duties for reconveyances in Delhi (expected stamp duty of ₹500 and registration fee of ₹100).
4. **Outstanding Charge Alert**: If a mortgage is found in the chain without a corresponding, fully matched discharge deed, it flags an **Active Mortgage Charge** as a critical financial liability.

---

## 4. Chain of Title & Ownership Continuity

The system compiles a chronological ownership matrix tracking how the property moves from owner to owner:

* **Transferor-Transferee Alignment**: The buyer in Document \(N\) must match the seller in Document \(N+1\). A mismatch flags a **Chain of Title Discontinuity (Chain Break)**.
* **PAN Card Validation**: Tracks party PAN numbers to detect transcription errors and identify potential self-dealing or circular transactions (where buyer PAN matches seller PAN).
* **Rectification Deeds**: Detects and applies corrections from subsequent Rectification Deeds to retroactively update SRO details, boundaries, or name errors in the original root deed.

---

## 5. GPA & Suraj Lamp Compliance Check

Power of Attorney (GPA) transfers have unique legal restrictions in Delhi:
* **The Suraj Lamp Judgment (October 11, 2011)**: The Supreme Court ruled that General Power of Attorney (GPA), Agreement to Sell (ATS), and Wills do not transfer title of immovable property.
* **Audit Implementation**: The engine flags any GPA or ATS document executed **after October 11, 2011** that purports to transfer ownership as **Legally Invalid / Voidance Hazard** under the Suraj Lamp compliance check.
* **GPA Signatory Check**: Checks if the seller is acting as a constituted attorney, validating if the associated GPA is registered and authorized.

---

## 6. Complete Inventory of Validation Checks

The engine evaluates over 40 distinct checks, categorized here with their technical error codes, severity levels, and specific triggers:

### Category A: Valuation & Financial Audits
| Technical Error Code | Severity Level | Audit Check Description & Trigger Condition |
| :--- | :--- | :--- |
| `UNDER_CIRCLE_RATE_VALUATION` | Voidance Hazard | Declared consideration is below the calculated Delhi circle rate minimum. |
| `INSUFFICIENT_STAMP_DUTY` | Voidance Hazard | Stamped amount is below the legally required rate (adjusts for male 6%, female 4%, joint 5%, and pre-2007 structures). |
| `INSUFFICIENT_REGISTRATION_FEE`| Voidance Hazard | Stated registration fee is below the mandatory 1% of property value (max capped where applicable). |
| `MISSING_SALE_CONSIDERATION` | Documentation Conflict| A Sale Deed fails to declare a financial consideration, violating Section 54 of the Transfer of Property Act. |
| `MISSING_RENTAL_CONSIDERATION` | Documentation Conflict| A Lease or Leave & License deed is missing the monthly rent or security deposit fields. |
| `MISSING_MORTGAGE_VALUE` | Documentation Conflict| A Mortgage deed fails to declare the principal loan amount. |
| `GIFT_DEED_WITH_CONSIDERATION` | Voidance Hazard | A Gift Deed contains consideration, violating Section 122 of the Transfer of Property Act (rendering the deed invalid). |
| `ZERO_CONSIDERATION` | Informational Log | The transaction was recorded at zero value. |
| `CONSIDERATION_ANOMALY` | Ownership Dispute Risk| A sudden, drastic reduction in property valuation compared to a previous sale in the chain. |

### Category B: Jurisdiction & SRO Audits
| Technical Error Code | Severity Level | Audit Check Description & Trigger Condition |
| :--- | :--- | :--- |
| `VOID_DEED_WRONG_SRO` | Voidance Hazard | The property was registered at an SRO that lacks jurisdiction over the locality, violating Section 28 of the Registration Act. |
| `METADATA_SRO_MISMATCH` | Documentation Conflict| The document SRO does not match the project's target SRO. |
| `PROPERTY_NOT_IN_DELHI` | Voidance Hazard | Property boundaries lie outside the National Capital Territory (NCT) of Delhi. |
| `METADATA_LOCALITY_MISMATCH` | Documentation Conflict| Stated document locality differs from the project folder metadata. |

### Category C: Title Continuity & Identity Audits
| Technical Error Code | Severity Level | Audit Check Description & Trigger Condition |
| :--- | :--- | :--- |
| `CHAIN_BREAK` | Ownership Dispute Risk| Seller in deed \(N+1\) does not match the buyer in deed \(N\). |
| `PAN_TRANSFEROR_TRANSFEREE_CLASH`| Voidance Hazard | Buyer PAN and Seller PAN are identical, indicating fraudulent self-dealing. |
| `INVALID_PAN_FORMAT` | Informational Log | PAN card number does not match the 10-character alphanumeric Indian Tax format. |
| `GPA_POST_2011_INVALID` | Voidance Hazard | GPA/ATS transfer executed after October 11, 2011 (Suraj Lamp violation). |
| `UNREGULARIZED_GPA_CHAIN` | Ownership Dispute Risk| The chain transfers title via GPA without ever registering a final Conveyance or Sale Deed. |
| `MISSING_GPA_AUTHORIZATION` | Voidance Hazard | A signatory executes the deed on behalf of an owner but has no registered GPA document in the chain. |
| `DATE_ORDER_DEVIATION` | Voidance Hazard | Registration date of the deed is prior to the execution date. |

### Category D: Property Dimension & Metadata Audits
| Technical Error Code | Severity Level | Audit Check Description & Trigger Condition |
| :--- | :--- | :--- |
| `PROPERTY_TYPE_MISMATCH` | Voidance Hazard | Mismatch in property category (e.g., DDA Flat registered as Private Builder Flat to evade higher circle rates). |
| `AREA_MISMATCH` | Documentation Conflict| Property area differs by more than 5% compared to the root document. |
| `AREA_MISMATCH_MILD` | Informational Log | Minor property area deviation (less than 5%). |
| `METADATA_FLAT_MISMATCH` | Documentation Conflict| Flat number in deed differs from metadata. |
| `METADATA_FLOOR_MISMATCH` | Documentation Conflict| Floor number in deed differs from metadata. |
| `METADATA_PROPERTY_ID_MISMATCH` | Documentation Conflict| Plot or Khasra number in deed does not match project metadata. |
| `METADATA_UPIC_MISMATCH` | Documentation Conflict| Unique Property Identification Code (UPIC) in deed does not match project metadata. |
| `METADATA_ADDRESS_MISMATCH` | Documentation Conflict| Stated address does not match project metadata. |
| `SOCIETY_MISMATCH` | Documentation Conflict| Name of Cooperative Group Housing Society (CGHS) differs from project metadata. |

### Category E: Encumbrance & Mortgage Audits
| Technical Error Code | Severity Level | Audit Check Description & Trigger Condition |
| :--- | :--- | :--- |
| `UNRESOLVED_MORTGAGE` | Financial Liability | An active mortgage exists in the chain without a matching discharge or reconveyance. |
| `LENDER_MISMATCH` | Documentation Conflict| Lender executing the reconveyance differs from the original mortgagee. |
| `RELEASE_ORPHAN` | Documentation Conflict| A Release Deed has no preceding root deed or mortgage transaction to release. |
| `PARTIALLY_RELEASED` | Informational Log | Only a partial release of the mortgage debt has occurred. |
| `RELEASE_OVERFLOW` | Documentation Conflict| Stated released amount exceeds the original mortgage loan amount. |

---

## 7. Reviewer Customization & Settings Engine

Reviewers can fine-tune audit thresholds using the **Project Settings Modal**:
* **Area Tolerance Buffer**: Allows adjusting the trigger threshold for area mismatch warnings (e.g., changing from the 5% default to 2%).
* **Distress Value Buffer**: Configures a buffer for circle rate checks (e.g., a 10% buffer to align with Income Tax Section 50C compliance).
* **Ignore Minor Shortfalls**: Silences minor stamp duty or registration fee warnings (e.g., ignoring deficits under ₹100).
* **Auditing Toggles**: Turn specific rules on/off, such as SRO matching, Suraj Lamp checks, or gender-based stamp duty evaluations.
