# DC-NDOO-001 — National Data Opt-Out Handling Policy

| Field | Value |
|---|---|
| Document ID | DC-NDOO-001 |
| Version | 0.1-draft |
| Status | Draft — awaiting DPO review |
| Date | 2026-03-04 |
| Author | DPO / Legal |
| NCDA audit item | DP05 |
| Related documents | DPIA-LEO-AI-001, DC-DPA-002 |
| NHS policy basis | National Data Opt-Out (NDOO) programme — NHS England |

---

## 1  Purpose

This document describes how the LEO AI Clinical Pathway Audit Platform handles the NHS National Data Opt-Out (NDOO). It supports NHS PCN NCDA audit requirement DP05.

---

## 2  What the National Data Opt-Out is

The National Data Opt-Out (NDOO) allows patients to opt out of their confidential patient information being used for purposes beyond their individual care — specifically for planning and research purposes that rely on data flowing from NHS organisations via NHS Digital / NHS England.

The NDOO applies to:
- Secondary uses of data where patient consent is not the lawful basis
- Uses supported by Section 251 NHS Act 2006 approvals
- Flows of identifiable patient data from NHS organisations to third parties for research and planning

The NDOO does **not** apply to:
- Individual direct care
- Clinical audit carried out within or on behalf of the care-providing organisation
- Processing that is lawfully based on explicit patient consent

---

## 3  Applicability assessment for LEO AI

### 3.1  EPR Audit (Addendum A — NCDA)

**NDOO does not apply** to the EPR Audit use case. The reasons are:

| Criterion | Assessment |
|---|---|
| **Lawful basis** | Processing is under DPA 2018 ss.52–53 — health and social care purposes including clinical audit. This is direct care audit, not a secondary use of data for research or planning. |
| **Consent required?** | No — DPA 2018 s.52 permits clinical audit without individual consent. |
| **Type of use** | Retrospective clinical pathway audit carried out by or on behalf of the GP practice as part of its NHS functions. This is a direct care activity. |
| **Data flow pathway** | GP practice → LEO AI (processor) → audit outputs back to the GP practice. There is no flow of patient data to NHS England or NHS Digital for planning purposes. |
| **Section 251 support** | Not required — processing is a direct care activity under DPA 2018 ss.52–53. |

**Conclusion:** The NCDA EPR Audit use case does not fall within the scope of the NDOO. No NDOO check is required for this use case.

> **Reference:** NHS England NDOO policy: "The national data opt-out does not apply to the use of your data for your individual care." GP practices processing patient data for audit of their own clinical care fall within the direct care exemption.

### 3.2  CDS — LEO (Addendum B)

**NDOO does not apply** to the CDS use case. Processing is for the purpose of supporting clinicians in individual patient care decisions (referral triage). This is direct care, not a secondary use of data.

### 3.3  Future use cases — model training on population data

If LEO AI were to use patient data for purposes beyond direct care (for example, sharing data with NHS England for national research, or using patient data to train AI models for use by unrelated third parties), the NDOO **would** apply. Any such use case would require:

1. A fresh DPIA
2. A fresh lawful basis assessment
3. An NDOO compliance check (and application of opt-outs to the dataset before processing)
4. Notification to the ICO if the lawful basis changes

This scenario does not apply to the current EPR Audit or CDS use cases.

---

## 4  Training data and the Learning Loop

The Learning Loop (DPA clause 5 and DPIA Section 2.2) creates Approved Mappings — de-identified clinical phrase-to-SNOMED-code pairs stored in the Knowledge Graph. Because:

- Approved Mappings contain no patient personal data (confirmed by automated test VT-LEO-AI-014)
- They cannot be linked to any patient, user, or organisation

The NDOO does not apply to the creation or use of Approved Mappings.

---

## 5  Controller responsibilities

The GP practice (as Data Controller) is responsible for:

1. Implementing the NDOO for any data flows from their practice that fall within the NDOO's scope.
2. Informing patients about how their data is used through the practice's privacy notice.
3. Applying the NDOO where required before sharing patient data with LEO AI, if any such use case falls within NDOO scope.

LEO AI (as Data Processor) is responsible for:

1. Confirming its use cases are within the direct care exemption and do not require NDOO compliance (as documented in this policy).
2. Notifying the Controller if any new processing activity might fall within NDOO scope.
3. Providing Controllers with information to support their own NDOO assessment.

---

## 6  Monitoring and review

This policy must be reviewed if:

- A new use case is added that involves patient data being shared for planning, research, or purposes beyond direct care.
- NHS England or the ICO updates guidance on NDOO and direct care audit.
- The Data (Use and Access) Act 2025 triggers changes to NDOO scope or application.

Review frequency: at least annually, and at each DPIA review trigger event.

---

## 7  Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| DPO | _[name]_ | _[signature]_ | _[date]_ |
| Caldicott Guardian | _[name]_ | _[signature]_ | _[date]_ |

---

## 8  References

| Reference | Document / URL |
|---|---|
| DPIA-LEO-AI-001 | Data Protection Impact Assessment (Step 4.1 — lawful basis) |
| DC-DPA-002 | Data Processing Agreement (Clauses 3, 5) |
| NHS England NDOO guidance | https://www.england.nhs.uk/contact-us/privacy-notice/how-we-use-your-information/our-services/national-data-opt-out/ |
| ICO direct marketing and research guidance | https://ico.org.uk/ |
| DPA 2018 ss.52–53 | Health and social care purposes |
| Data (Use and Access) Act 2025 | Relevant provisions on data access and opt-outs |
