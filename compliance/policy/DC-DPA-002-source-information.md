# DC-DPA-002 Source Information Document

## Purpose

This document explains the source information used to create the Data Processing Agreement (DC-DPA-002) between Mizaic / Healthcare CoPilot and NHS Provider Organisations in England. It supports traceability and auditability by recording the legal, regulatory, and technical sources that informed the DPA's drafting.

DC-DPA-002 is structured as a Master DPA with two Use Case Addendums:

- **Addendum A** -- EPR Audit (retrospective clinical pathway audit)
- **Addendum B** -- CDS (LEO clinical decision support for referral triage)

---

## Methodology

The DPA was developed using a full deep web search to identify current UK data protection requirements, NHS-specific guidance, and best practice for processor agreements in the health and social care sector. Research focused on:

- UK GDPR and Data Protection Act 2018 requirements for processor contracts
- ICO guidance on data processing agreements, AI, and pseudonymisation
- NHS Data Security and Protection Toolkit (DSPT) expectations
- Caldicott Principles and health and social care data handling
- Emerging legislation (Data (Use and Access) Act 2025)
- Industry templates and NHS-specific DPA precedents
- UKCA / MHRA guidance on Software as a Medical Device (SaMD) -- for CDS regulatory classification
- DCB0129 and DCB0160 clinical risk management standards -- for CDS clinical safety obligations
- NICE, RCR iRefer, and Royal College clinical guideline licensing and IP -- for CDS third-party content provisions

---

## Primary Legal and Regulatory Sources

### Sources informing the Master DPA (all Use Cases)

| Source | Reference / URL | How it informed DC-DPA-002 |
|--------|-----------------|----------------------------|
| **UK GDPR Article 28** | Processor contract requirements | Core structure of the DPA; clauses on instructions, security, sub-processors, assistance with rights, breach notification |
| **UK GDPR Article 32** | Security of processing | Annex A (Security Measures); encryption, access control, network security, database separation |
| **UK GDPR Articles 33--34** | Breach notification | Clause 4.5 -- 24-hour notification to Controller, cooperation with ICO |
| **UK GDPR Article 30(2)** | Records of processing | Clause 4.7 -- Processor keeps records of processing activities |
| **UK GDPR Article 35** | Data Protection Impact Assessment | Clause 4.3 -- Processor assists Controller with DPIA |
| **UK GDPR Articles 15--21** | Data subject rights | Clause 10 -- Assistance with access, rectification, erasure, restriction, portability, objection |
| **UK GDPR Article 5(1)(c)** | Data minimisation | Clause 5.8(b) -- Approved Mappings contain only listed data |
| **UK GDPR Chapter V** | International transfers | Clause 8 -- Restriction on transfers outside UK; adequacy and safeguards |
| **Data Protection Act 2018** | UK implementing legislation | Applicable law; Schedule 1 Part 1 para 2 (health and social care); ss.52--53 (audit without consent) |
| **Data (Use and Access) Act 2025** | In force 19 June 2025 | Included in Data Protection Law definition; ICO guidance update pending |
| **ICO guidance on controller/processor** | [ICO accountability guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/) | Clause 5.7(c) -- Knowledge Graph controller status; "practical realities of processing" |
| **ICO guidance on personal data / identifiability** | [ICO guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/key-documentation-in-the-gdpr/what-is-personal-data/) | Clause 5.7(b) -- Approved Mappings do not identify any person |
| **ICO pseudonymisation guidance** | ICO pseudonymisation guidance (2025) | VT-LEO-AI-014, VT-LEO-AI-016; no user identity in Knowledge Graph (clause 5.3(d), 6.2) |
| **ICO AI and data protection** | [ICO AI guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/artificial-intelligence/guidance-on-ai-and-data-protection/) | DPIA alignment; AI-specific considerations for sub-processors |
| **NHS Data Security and Protection Toolkit** | [dsptoolkit.nhs.uk](https://www.dsptoolkit.nhs.uk/) | Clause 4.6 -- DSPT compliance; Schedule fields; Annex A resilience and incident response |
| **Caldicott Principles** | National Data Guardian framework | DPIA alignment; minimum necessary data; need-to-know access |

### Additional sources for Addendum B (CDS -- LEO)

| Source | Reference / URL | How it informed Addendum B |
|--------|-----------------|----------------------------|
| **UK MDR 2002 (as amended)** | UK Medical Devices Regulations 2002 | B.8 -- UKCA Class I SaMD registration; regulatory classification |
| **MHRA SaMD guidance** | MHRA Software and AI as a Medical Device Change Programme | B.8 -- Classification of LEO as UKCA Class I SaMD |
| **ISO 13485:2016** | Quality Management System for Medical Devices | B.8 -- QMS requirements referenced in regulatory classification |
| **IEC 62304:2006+A1:2015** | Medical Device Software lifecycle processes | B.8 -- Software lifecycle standard |
| **ISO 14971:2019** | Application of risk management to medical devices | B.8 -- Risk management standard |
| **DCB0129** | Clinical Risk Management: Application in Manufacture of Health IT Systems | B.8 -- Manufacturer clinical safety obligations |
| **DCB0160** | Clinical Risk Management: Application in Deployment and Use of Health IT Systems | B.8 -- Controller (deployer) clinical safety obligations; Processor provides supporting documentation |
| **MEDDEV 2.7/1 rev 4** | Clinical evaluation guidance | Clinical evaluation methodology referenced in device description |
| **NICE clinical guidelines** | National Institute for Health and Care Excellence | B.10 -- Third-party clinical content; Controller licensing responsibility |
| **RCR iRefer guidelines** | Royal College of Radiologists | B.10 -- Imaging guideline content; Controller licensing responsibility |
| **Royal College guidance** | Various Royal Colleges (RCP, RCS, RCGP) | B.10 -- Specialty-specific clinical guidelines; Controller licensing responsibility |
| **NHS England pathways** | Faster Diagnosis Standard, national optimal care pathways | B.10 -- FDS pathways and national pathway rules |
| **SNOMED CT UK Edition** | NHS Digital / NHS England | B.10 -- Clinical terminology; Controller licensing responsibility |
| **HL7 FHIR R4 / UK Core** | HL7 International / NHS Digital | B.4 -- Integration standards for EPR, e-RS, PACS, LIMS data sources |
| **NHS e-Referral Service** | NHS Digital / NHS England | B.4, B.6 -- Primary referral data source; write-back target |
| **NHS records management guidance** | NHS England | B.9 -- Minimum 8-year retention for clinical decision support audit trail |

---

## Internal Design Documents

| Document | Path | How it informed DC-DPA-002 |
|----------|------|----------------------------|
| **DPIA-LEO-AI-001** | design-controls/DPIA-LEO-AI-001.md | Controller/processor roles; lawful basis; sub-processor table; open actions (DPA-REVIEW-001, DPA-GP-001) |
| **DC-TM-SEC-002** | design-controls/DC-TM-SEC-002-threat-model.yaml | Security controls; AWS/Azure DPAs; de-identification; sub-processor locations |
| **R-LEO-AI-032** | design-controls/risks/R-LEO-AI-032.yaml | LLM sub-processor obligations; DPA-REVIEW-001; no training use; arbitration call coverage |
| **DC-DPA-001** *(deleted)* | design-controls/DC-DPA-001-learning-loop-clauses.md | Learning Loop clause structure; definitions; pseudonymisation approach. Superseded by DC-DPA-002 Master DPA clause 5; file deleted to avoid confusion. |
| **DC-IU-001** | design-controls/intended-use.md | Service scope; clinical audit purpose (Addendum A) |
| **DC-SC-001** | design-controls/DC-SC-001-safety-classification.md | IEC 62304 Class B classification for EPR Audit (Addendum A) |
| **LEO device description** | Provided by Healthcare CoPilot (not yet in repo) | Full device description including intended purpose, users, patient population, use environment, inputs, outputs, operating principle, limitations, contraindications, third-party content, clinical evaluation, and precautions. Source for Addendum B. |

---

## Technical Implementation References

The DPA's Annex B (De-identification Process) and Annex A (Security Measures) reference specific implementation artefacts:

| Artefact | Path / ID | DPA reference |
|----------|-----------|----------------|
| Pattern matching (Layer 1) | `libs/utils/deidentify.py` | Annex B -- NHS numbers, postcodes, dates, names, etc. |
| Pipeline cleaning (Layer 2) | `libs/deid/deid.py` | Annex B -- Pre-NER de-identification |
| Export safety net (Layer 3) | `services/api/app/services/export_service.py` | Annex B -- Export-time de-identification |
| De-identification validator | `libs/ner/deid_validator.py` | Annex B -- Validation |
| Data governance verification | VT-LEO-AI-014 | Clauses 5.5, 9.1(c), 9.3 -- Automated tests for no PHI in Knowledge Graph |
| Knowledge Graph schema verification | VT-LEO-AI-016 | Clause 5.3(d), 6.2 -- Source tags, no user identity |

---

## Sub-processor Information Sources

| Sub-processor | Source of information | Addendum(s) |
|---------------|------------------------|-------------|
| AWS Bedrock (eu-west-2) | DC-TM-SEC-002; R-LEO-AI-032; AWS Enterprise DPA | A, B |
| Azure OpenAI (UK South) | DC-TM-SEC-002; R-LEO-AI-032; Microsoft Enterprise DPA | A, B |
| Neo4j Aura (EU/UK) | DC-TM-SEC-002; DPIA-LEO-AI-001 | A, B |
| Microsoft Azure (Container Apps, Key Vault, Redis, Blob, Service Bus) | DPIA-LEO-AI-001; infrastructure design | A, B |
| Microsoft Entra ID (authentication) | DPIA-LEO-AI-001; infrastructure design | A, B |

---

## Document History

| Version | Date | Change |
|---------|------|--------|
| 0.1.0 | 2026-03-04 | Initial source information document (EPR Audit only) |
| 0.2.0 | 2026-03-04 | Updated for master DPA structure with Addendum A (EPR Audit) and Addendum B (CDS -- LEO). Added CDS regulatory sources (UKCA, DCB0129/0160, NICE, RCR iRefer, ISO 13485, ISO 14971, MEDDEV 2.7/1, NHS records management). Added Addendum column to sub-processor table. Added LEO device description and DC-SC-001 to internal documents. |

---

*This document should be updated when new sources are consulted or when the DPA is revised to reflect additional research.*
