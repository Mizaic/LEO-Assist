# DC-DTAC-001 — DTAC Compliance Statement

| Field | Value |
|---|---|
| Document ID | DC-DTAC-001 |
| Version | 0.1-draft |
| Status | Draft — evidence items to be completed |
| Date | 2026-03-04 |
| Author | Engineering / DPO / Clinical Safety Officer |
| NCDA audit items | SI02, SI03, SI04, SI05, SI06 |
| Related documents | DC-SC-001, DC-UE-001, DC-PT-001, DC-ARCH-001 |

---

## 1  Purpose

This document sets out LEO AI's compliance status against the NHS Digital Technology Assessment Criteria (DTAC). DTAC is the NHS's framework for assessing health IT products before procurement. This statement supports NHS PCN NCDA supplier due-diligence assessments (SI02–SI06).

DTAC covers five domains:

1. Clinical Safety (DCB0129 / DCB0160)
2. Data Protection (DSPT / UK GDPR)
3. Technical Assurance (architecture, SLA, security, pen test)
4. Interoperability (NHS standards)
5. Usability and Accessibility (WCAG 2.1 AA)

---

## 2  DTAC compliance summary

| DTAC domain | Status | Evidence |
|---|---|---|
| Clinical Safety | Partial | DC-SC-001; DCB0129 pending formal submission |
| Data Protection | Partial | DPIA-LEO-AI-001; DC-DPA-002; DSPT submission pending |
| Technical Assurance | Partial | DC-ARCH-001; DC-KM-001; DC-PT-001 (pending) |
| Interoperability | Partial | FHIR R4; SNOMED CT UK Edition |
| Usability and Accessibility | Partial | DC-UE-001; WCAG assessment pending |

---

## 3  Domain 1 — Clinical Safety

### 3.1  DCB0129 — Clinical Risk Management (Manufacturer)

DCB0129 requires the manufacturer of a health IT system to implement a clinical risk management process covering hazard identification, risk estimation, evaluation, and mitigation.

| Element | Status | Evidence |
|---|---|---|
| Clinical safety case | In progress | DC-SC-001 (safety classification) |
| Hazard log | In progress | Hazard log maintained within risk management system |
| Safety classification | Class B (IEC 62304) | DC-SC-001 |
| DCB0129 declaration | **Pending formal preparation** | To be completed by Clinical Safety Officer |
| Clinical Safety Officer appointed | _[to be confirmed]_ | _[name, GMC/NMC number]_ |

> **EPR Audit (Addendum A):** The EPR Audit platform is classified as IEC 62304 Class B software. It is retrospective and does not provide real-time clinical decision support. It does not directly influence individual patient treatment decisions. MHRA/UKCA SaMD classification assessment is pending.

> **CDS — LEO (Addendum B):** LEO is registered as UKCA Class I Software as a Medical Device. DCB0129 compliance is required and in progress.

### 3.2  DCB0160 — Clinical Risk Management (Deployment)

DCB0160 is the deployer's (Controller's) responsibility. Mizaic provides the following to support Controllers:

- DCB0160 supporting documentation pack
- System Risk Assessment (SRA) for the LEO AI platform
- Hazard log for use by the deploying organisation's Clinical Safety Officer

**Status:** _[Pending — to be prepared by Clinical Safety Officer]_

### 3.3  Non-clinical classification statement (SI03)

For the EPR Audit use case (Addendum A):

> LEO AI EPR Audit is a retrospective clinical pathway audit platform. It does not provide clinical decision support, does not influence individual patient treatment decisions in real time, and does not drive clinical actions. All outputs are proposals that require qualified human review and approval before they constitute audit data. The platform is classified as IEC 62304 Class B software. It is not currently classified as a Medical Device under UK MDR 2002.
>
> **Signed:** _[Clinical Safety Officer name, date]_

---

## 4  Domain 2 — Data Protection

| Element | Status | Evidence |
|---|---|---|
| NHS DSPT assessment | _[pending submission]_ | DSPT account: _[org ODS code]_ |
| DPIA completed | Draft — awaiting DPO sign-off | DPIA-LEO-AI-001 |
| Data Processing Agreement | Draft — for legal review | DC-DPA-002 |
| Sub-processor register | Complete (evidence pending) | DC-SP-001 |
| Transfer Risk Assessment | Complete | DC-TRA-001 |
| ICO registration | _[confirm registration number]_ | _[ICO registration number]_ |

> **DSPT target:** LEO AI (Mizaic Ltd) is working toward NHS DSPT "Standards Met" status. Target date: _[to be confirmed]_.

---

## 5  Domain 3 — Technical Assurance

### 5.1  System architecture

A system architecture document is provided at DC-ARCH-001. A formal architecture diagram in Visio/draw.io format is being prepared for DTAC submission (open action ARCH-001).

### 5.2  Service availability SLA

| Metric | Value |
|---|---|
| Target uptime | 99.9% (measured monthly, excluding planned maintenance) |
| Recovery Time Objective | < 4 hours |
| Recovery Point Objective | < 1 hour |

### 5.3  Penetration testing (SI04 / TA04)

| Element | Status |
|---|---|
| Annual penetration test by CREST-accredited third party | See DC-PT-001 |
| Most recent test date | _[to be completed]_ |
| Remediation plan | _[to be completed — see DC-PT-001]_ |

### 5.4  Cyber Essentials Plus (SI04)

| Element | Status |
|---|---|
| Cyber Essentials Plus certification | _[pending]_ |
| Certification body | _[to be confirmed]_ |
| Certificate expiry | _[to be confirmed]_ |
| Roadmap to certification (if not yet certified) | _[to be completed — target date: 2026-09-01]_ |

> **Note:** Cyber Essentials Plus is a DTAC requirement. Until certification is obtained, LEO AI will provide the PCN with evidence of equivalent technical controls (see DC-ARCH-001, DC-TM-SEC-002, DC-PT-001) and a completion roadmap.

---

## 6  Domain 4 — Interoperability

| Standard | Status | Evidence |
|---|---|---|
| HL7 FHIR R4 | Implemented | GP FHIR R4 API ingestion (Patient, Encounter, DocumentReference) |
| SNOMED CT UK Edition | Implemented | Terminology service; UMLS + UK SNOMED CT edition |
| NHS Digital number format (NHS number) | Implemented | NHS number de-identification in pipeline |
| UK Core FHIR profiles | In progress | _[confirm alignment with UK Core profiles]_ |
| NHS Login / NHS SSO | Supported | Azure Entra ID (NHS Single Sign-On via Entra) |
| NHS e-RS | Implemented (CDS — Addendum B) | LEO CDS integration |

---

## 7  Domain 5 — Usability and Accessibility

### 7.1  WCAG 2.1 AA (SI05)

| Element | Status |
|---|---|
| WCAG 2.1 AA accessibility audit | _[pending]_ |
| Accessibility statement published | _[pending]_ |
| Automated accessibility scanning (e.g. axe, Lighthouse) | _[to be confirmed]_ |
| Manual accessibility review | _[pending]_ |
| Roadmap to WCAG 2.1 AA compliance | _[to be prepared — target date: 2026-09-01]_ |

### 7.2  Usability and user testing (SI06)

| Element | Status |
|---|---|
| User research with clinical audit teams | DC-UE-001 (usability engineering plan) |
| Formative usability studies | _[to be documented — reference DC-UE-001]_ |
| Summative usability testing | _[pending]_ |
| User feedback loops | Built into review workflow (reviewer corrections feed back to model) |
| NHS PPV engagement | PPV-001 (open action in DPIA-LEO-AI-001) |

> Evidence of usability studies and user testing outcomes is maintained in DC-UE-001 and can be provided to the PCN on request.

---

## 8  Open actions

| ID | Action | Owner | Target date |
|---|---|---|---|
| DTAC-001 | Complete DSPT submission to NHS "Standards Met" | DPO | 2026-07-01 |
| DTAC-002 | Obtain Cyber Essentials Plus certification | Engineering / DPO | 2026-09-01 |
| DTAC-003 | Complete WCAG 2.1 AA audit and publish accessibility statement | Engineering | 2026-09-01 |
| DTAC-004 | Prepare DCB0129 declaration (CSO sign-off) | Clinical Safety Officer | 2026-06-01 |
| DTAC-005 | Prepare DCB0160 supporting documentation for deployers | Clinical Safety Officer | 2026-06-01 |
| DTAC-006 | Prepare formal architecture diagram for DTAC submission | Engineering | 2026-05-01 |
| DTAC-007 | Confirm ICO registration number | DPO | 2026-04-01 |
| DTAC-008 | Complete and document summative usability testing | Product / Engineering | 2026-09-01 |

---

## 9  Contact

For DTAC-related queries, contact:

| Role | Name | Email |
|---|---|---|
| Data Protection Officer | _[name]_ | _[email]_ |
| Clinical Safety Officer | _[name]_ | _[email]_ |
| Technical Lead | _[name]_ | _[email]_ |

---

## 10  References

| Reference | Document |
|---|---|
| DC-SC-001 | Safety Classification |
| DC-UE-001 | Usability Engineering Plan |
| DC-PT-001 | Penetration Testing Summary |
| DC-ARCH-001 | System Architecture Document |
| DC-SP-001 | Sub-processor Evidence Register |
| DPIA-LEO-AI-001 | Data Protection Impact Assessment |
| DC-DPA-002 | Data Processing Agreement |
| NHS DTAC | https://www.digitalregulations.innovation.nhs.uk/digital-technology-assessment-criteria-dtac/ |
| NHS DSPT | https://www.dsptoolkit.nhs.uk/ |
| DCB0129 | https://digital.nhs.uk/data-and-information/information-standards/information-standards-and-data-collections-including-extractions/publications-and-notifications/standards-and-collections/dcb0129-clinical-risk-management-its-application-in-the-manufacture-of-health-it-systems |
| WCAG 2.1 | https://www.w3.org/TR/WCAG21/ |
