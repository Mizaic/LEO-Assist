# DC-TRA-001 — International Transfer Risk Assessment

| Field | Value |
|---|---|
| Document ID | DC-TRA-001 |
| Version | 0.1-draft |
| Status | Draft — awaiting DPO review |
| Date | 2026-03-04 |
| Author | Legal / DPO |
| Related DPIA | DPIA-LEO-AI-001 |
| Related DPA | DC-DPA-002 |
| Applicable law | UK GDPR Chapter V; Data (Use and Access) Act 2025; ICO International Transfer guidance |

---

## 1  Purpose

This Transfer Risk Assessment (TRA) documents and justifies every international transfer of personal data made by the LEO AI platform. It is required by UK GDPR Chapter V and ICO guidance on international transfers, and supports NHS PCN NCDA audit questions IS02, OG01, and OG10.

---

## 2  Transfers identified

### 2.1  Summary of all international transfers

| Transfer | From | To | Provider | Data transferred | Volume | Lawful mechanism |
|---|---|---|---|---|---|---|
| **T-001** | UK | Sweden (EEA) | Azure OpenAI | De-identified clinical text (encounter context, entity phrase) | Per coding job; approx. 16,000 chars per call | UK Adequacy Regulations 2021 (EEA adequacy) |
| **T-002** | UK | UK | AWS Bedrock | De-identified clinical text (encounter context, entity phrase) | Per coding job; approx. 16,000 chars per call | No international transfer — eu-west-2 is UK |
| **T-003** | UK | UK | Neo4j Aura | Patient personal data (encrypted Patient Graph) | Per query | No international transfer — UK region confirmed |

> **Note:** Azure Container Apps, Redis, Service Bus, Key Vault, and Blob Storage are all hosted in Azure UK South. **Only Azure OpenAI model inference (T-001) involves a transfer outside the UK**, to Sweden Central (EEA).

---

## 3  Transfer T-001 — UK to Sweden (Azure OpenAI)

### 3.1  Transfer details

| Field | Detail |
|---|---|
| Sending entity | LEO AI (Mizaic Ltd) — Data Processor |
| Receiving entity | Microsoft Corporation (Azure OpenAI Service) — Sub-processor |
| Transfer direction | UK → Sweden Central (EEA) |
| Data subjects | NHS patients at participating GP practices |
| Data categories | De-identified clinical text (encounter context, entity phrase). Not special-category data once de-identified; however, re-identification risk is assessed below. |
| Transfer purpose | LLM-assisted SNOMED CT disambiguation (fallback path when spaCy NER confidence is low) |
| Transfer mechanism | HTTPS API call (TLS 1.3) |
| Frequency | Per coding job; triggered only for low-confidence entities |
| Volume | Max ~16,000 characters of encounter text + ~200 characters of entity text per call |
| Contractual basis | Microsoft Enterprise Data Processing Agreement |

### 3.2  Lawful transfer mechanism

**Adequacy decision:** The UK Secretary of State has determined that the European Economic Area (including Sweden) provides an adequate level of data protection under the Data Protection (Adequacy) (European Union) Regulations 2021. Sweden is an EU Member State and subject to the EU GDPR, which the UK has recognised as providing an adequate level of protection.

**Result:** Transfer T-001 does not require SCCs, UK Binding Corporate Rules, or a UK Addendum. The adequacy decision is the lawful mechanism.

**Adequacy monitoring:** The LEO AI DPO must monitor ICO guidance for any change to the UK's adequacy determination for the EEA. If the determination is amended or revoked, this TRA must be reviewed and alternative transfer mechanisms put in place before transfers continue. This is listed as a DPIA review trigger in DPIA-LEO-AI-001 Section 7.5.

### 3.3  Risk assessment

#### 3.3.1  Nature of data transferred

The text sent to Azure OpenAI has been processed by a three-layer de-identification pipeline (described in DPA Annex B and DC-ARCH-001 Section 4) before transmission:

- Layer 1: Pattern-matching removal of names, NHS numbers, postcodes, addresses, phone numbers, email addresses, dates, and organisation names.
- Layer 2: Pipeline-stage de-identification (pre-NER).
- Layer 3: Export-time safety net.

After de-identification, the text contains:
- Clinical terminology (symptoms, diagnoses, procedures, medications, test results)
- Generic contextual phrases (e.g. "discussed with patient", "referred urgently")
- No patient names, NHS numbers, dates, addresses, or other direct identifiers.

#### 3.3.2  Residual re-identification risk

| Risk | Assessment |
|---|---|
| Direct re-identification (name, NHS number) | Very low — these are explicitly removed by the de-identification pipeline |
| Indirect re-identification (unique clinical narrative) | Low — encounter text is truncated to 16,000 chars; context is generic clinical language |
| Microsoft use of data to re-identify | Contractually prohibited — Microsoft DPA prohibits use of customer data for model training or any purpose other than providing the inference service |
| Swedish government access to data | Low — Sweden is subject to EU GDPR and EU Charter of Fundamental Rights; no equivalent of US FISA Section 702; NATO and EU membership provides rule-of-law assurance |

#### 3.3.3  Swedish / EEA legal environment

| Factor | Assessment |
|---|---|
| Data protection law | EU GDPR — equivalent standard to UK GDPR |
| Government surveillance powers | EU law constraints on surveillance; no FISA-equivalent; Article 8 ECHR applies |
| Rule of law | High — EU Member State, Council of Europe member, ECHR signatory |
| Adequacy determination | UK has recognised EEA as adequate |
| CLOUD Act risk | Microsoft is a US company; however, data stored in EU datacentres has additional protections under EU law (Schrems II / C-311/18 principles; EU Data Act) |

#### 3.3.4  Contractual protections in place

| Protection | Status |
|---|---|
| Microsoft DPA prohibits training use of customer data | Yes — confirmed in Microsoft Enterprise DPA |
| Microsoft DPA prohibits retention of customer data beyond the inference call | Yes — confirmed in Microsoft Enterprise DPA |
| Microsoft DPA includes 72-hour breach notification | To be confirmed — see DPA-REVIEW-001 (open action) |
| Microsoft Sub-processor listed in LEO AI DPA (DC-DPA-002 Annex C) | Yes |
| 30-day notice of sub-processor changes | Yes — DPA clause 7.3 |

### 3.4  TRA conclusion for T-001

| Criterion | Assessment |
|---|---|
| Transfer mechanism adequate? | **Yes** — EEA adequacy decision applies |
| Residual risk to data subjects acceptable? | **Yes** — de-identified data; contractual protections in place |
| Proportionate to purpose? | **Yes** — LLM disambiguation improves coding accuracy for national clinical audit |
| Adequacy monitoring in place? | **Yes** — listed as DPIA review trigger |
| Open actions required? | DPA-REVIEW-001: confirm 72-hour breach notification with Microsoft |

**DPO determination:** _[DPO to sign off: transfer T-001 is lawful and the residual risk is acceptable / not acceptable — reason: ___]_

---

## 4  Non-transfers confirmed

### 4.1  AWS Bedrock (T-002)

AWS Bedrock inference uses the `eu-west-2` region (London, UK). This is a UK-to-UK data flow. No international transfer occurs. Confirmed by AWS Bedrock ARN format: `arn:aws:bedrock:eu-west-2::foundation-model/...`.

### 4.2  Neo4j Aura (T-003)

Patient Graph and Knowledge Graph are hosted in Neo4j Aura's UK/EU region. No international transfer (outside UK/EEA) occurs. **Confirm:** UK-specific Aura region selection should be verified in the Neo4j Aura console (see open action ARCH-002 in DC-ARCH-001).

---

## 5  Transfer inventory maintenance

This TRA must be reviewed if:

- A new LLM provider is added outside the UK or EEA.
- An existing provider's data region changes.
- The UK's adequacy determination for the EEA is amended or revoked.
- A new sub-processor is engaged in a non-UK/EEA jurisdiction.
- A personal data breach occurs involving transferred data.

Review frequency: at least annually, and at each DPIA review trigger event.

---

## 6  Open actions

| ID | Action | Owner | Target date |
|---|---|---|---|
| TRA-001 | Confirm Microsoft DPA includes 72-hour breach notification compatible with NHS DSPT (linked to DPA-REVIEW-001) | Legal / DPO | 2026-05-01 |
| TRA-002 | Confirm Neo4j Aura UK region selection in Aura console (linked to ARCH-002) | Engineering | 2026-05-01 |
| TRA-003 | Monitor ICO guidance for any change to EEA adequacy determination | DPO | Ongoing |
| TRA-004 | Assess whether entity_text-only fast path (DM-001) would eliminate or reduce T-001 transfer volume | Engineering / DPO | 2026-06-01 |

---

## 7  Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| DPO | _[name]_ | _[signature]_ | _[date]_ |
| Caldicott Guardian | _[name]_ | _[signature]_ | _[date]_ |

---

## 8  References

| Reference | Document |
|---|---|
| DPIA-LEO-AI-001 | Data Protection Impact Assessment (Section 1.2, 6.1) |
| DC-DPA-002 | Data Processing Agreement (Clause 8, Annex C) |
| DC-ARCH-001 | System Architecture Document (Section 2, 4) |
| UK Adequacy Regulations 2021 | The Data Protection (Adequacy) (European Union) Regulations 2021 |
| ICO International Transfers guidance | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/international-transfers/ |
| Microsoft Enterprise DPA | https://www.microsoft.com/en-us/trust-center/privacy/data-management |
| Data (Use and Access) Act 2025 | DUAA Part 2 (international transfers framework) |
