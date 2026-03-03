# DPIA-LEO-AI-001 — Processing of NHS Clinical Data by LEO-AI
| Field | Value |
|---|---|
| Document ID | DPIA-001 |
| Version | 0.2-draft |
| Status | **Draft — awaiting DPO review and sign-off** |
| Date | 2026-03-03 |
| Author | Engineering / Risk Management Team |
| DPO sign-off | _[pending]_ |
| DPO sign-off date | _[pending]_ |
| ICO consultation required | _[DPO to determine at Step 7]_ |
| Related risk file | R-LEO-AI-032 |
| Regulatory basis | UK GDPR Article 35; Data Protection Act 2018; NHS DSPT |
| Review trigger | Any change to data flows, providers, regions, processing purpose, or data categories processed |

---

## Why this DPIA is needed

This DPIA is required under UK GDPR Article 35(3). The processing meets **all three** of the ICO's mandatory criteria:

1. **Large-scale processing of special category data** — the platform processes NHS GP encounter records, which are Article 9(1) health data. Processing spans multiple GP practices.
2. **New technology** — Large Language Models (LLMs) and NLP applied to clinical free text. The ICO identifies AI/ML as triggering a mandatory DPIA.
3. **Automated evaluation with significant effects** — SNOMED CT coding decisions feed national clinical audit datasets that inform quality-of-care assessment for patient populations.

Not completing this DPIA before production deployment would breach Article 35 UK GDPR.

---

## Step 1 — Identify the Need

### 1.1 What the platform does

LEO AI is a retrospective clinical pathway audit platform. It reads GP encounter records (via FHIR R4), codes clinical entities to SNOMED CT using NLP, reconstructs patient pathways, and flags quality issues for human review.

This DPIA covers **all processing of personal data** by the platform, including:

- Ingestion of patient records from GP systems
- Storage of patient and encounter data in Neo4j graph databases
- NLP-based clinical coding (spaCy / scispaCy)
- LLM fallback for low-confidence coding decisions (dual-provider consensus)
- Episode building, guideline checking, safety-netting, and abnormal result detection
- Display of patient data in the web UI
- API access to patient data by authenticated users
- Export of approved coding data for model training
- Analytics and dashboards derived from patient data
- Session management and access control

### 1.2 High-risk screening

| Criterion | Present? | Evidence |
|---|---|---|
| Special category health data (Article 35(3)(b)) | Yes | NHS GP records — Article 9(1) health data |
| Large-scale processing | Yes | Multi-GP-practice national audit programme (NCDA) |
| New technology (Article 35(1)) | Yes | LLMs and NLP applied to clinical free text |
| Automated processing with significant effects | Yes | Coding decisions feed national audit quality measures |
| International data transfer | Yes | UK to Sweden Central (Azure OpenAI); UK to Neo4j Aura (verify region) |
| Profiling / evaluation of individuals | Partial | Per-patient encounter coding; outputs are population-level |
| Vulnerable individuals | Yes | Cancer patients; NHS patients generally |

**DPIA is mandatory. No further screening needed.**

---

## Step 2 — Describe the Processing

### 2.1 Controller / Processor chain

| Entity | Role | Basis |
|---|---|---|
| **GP practice / NHS trust** | **Data Controller** — decides the purpose of processing patient records for audit | Article 9(2)(h); DPA 2018 Sch 1 Part 1 para 2 |
| **LEO AI company** | **Data Processor** — processes patient data on behalf of, and under instruction from, the controller | Data Processing Agreement (DPA) with each GP practice |
| **AWS Bedrock** (Claude — eu-west-2) | **Sub-processor** under LEO AI | AWS Enterprise DPA; named in LEO AI's DPA with GP practices |
| **Azure OpenAI** (GPT-5 mini — Sweden Central) | **Sub-processor** under LEO AI | Microsoft Enterprise DPA; named in LEO AI's DPA with GP practices |
| **Neo4j Aura** (region: verify in Aura console) | **Sub-processor** under LEO AI | Neo4j DPA |
| **Microsoft Azure** (Container Apps, Redis, Service Bus, Key Vault, Blob Storage) | **Sub-processor** under LEO AI | Microsoft Enterprise DPA |
| **Microsoft Entra ID** (Azure AD) | **Sub-processor** (authentication) | Microsoft Enterprise DPA |

> **Joint controllership (Article 26):** AWS, Azure, and Neo4j receive or store clinical data but act only under LEO AI's instructions within their DPAs. They do not decide the purpose or means of processing. They are processors, not joint controllers. Legal counsel should confirm this against current DPA terms.

### 2.2 What data is processed

#### Patient and clinical data (special category)

| Data category | Source | Where stored | Who can access |
|---|---|---|---|
| Patient demographics (gender, birth date) | GP FHIR API (Patient resource) | Neo4j Patient Graph | Authenticated users with org-scoped access |
| Encounter records (date, free-text clinical narrative) | GP FHIR API (Encounter, DocumentReference) | Neo4j Patient Graph | Authenticated users with org-scoped access |
| SNOMED CT coded links (diagnosis codes, modifiers, context) | Generated by NLP/LLM pipeline | Neo4j Patient Graph | Authenticated users with org-scoped access |
| Clinical episodes (milestones, dates, status) | Generated by analysis pipeline | Neo4j Patient Graph | Authenticated users with org-scoped access |
| Safety-net alerts | Generated by safety-net detector | Neo4j Patient Graph | Authenticated users with org-scoped access |
| Abnormal results | Generated by abnormal detector | Neo4j Patient Graph | Authenticated users with org-scoped access |
| Review decisions (who approved what, when) | Entered by human reviewers via UI | Neo4j Patient Graph | Authenticated users with org-scoped access |
| Training exports (approved gold-standard labels) | Exported by admin users | Downloaded by admin users | Admins only |

#### Data sent to LLM sub-processors

| Field | Max size | Content |
|---|---|---|
| `entity_text` | ~200 chars | The extracted clinical phrase (e.g. "type 2 diabetes mellitus") |
| `encounter_text` | 2,000 chars | Surrounding clinical context from the encounter note, after de-identification |

Both fields pass through `sanitise_for_prompt()` (injection filtering) and de-identification before transmission.

**What LLMs return:** A structured verdict from a closed set of permitted values (e.g. `active_diagnosis`, `informational`, `historical`, `uncertain`). No raw clinical text is returned.

**What is NOT sent to LLMs:** Patient name, NHS number, date of birth, full address. These exist only in Neo4j and are never transmitted to LLM providers.

> **Suggest-aliases endpoint:** A separate LLM call pattern exists for `POST /terminology/concepts/{concept_id}/suggest-aliases`. This sends **only SNOMED CT concept metadata** (fully-specified name, semantic tag, existing surface forms) to AWS Bedrock Claude Haiku. No patient data, encounter text, or personal identifiers are sent. Because no personal or special-category data is transmitted, this call pattern is **outside the scope of this DPIA**. Confirmed in DI-LEO-AI-050 and DO-LEO-AI-033.

#### Operational data (not special category)

| Data category | Where stored | Purpose |
|---|---|---|
| User sessions (email, org membership, access token) | Redis (encrypted at rest) | Authentication and org-scoped access control |
| Pipeline job metadata (patient_id, encounter_id, mode) | Azure Service Bus | Job dispatch for background workers |
| Pipeline progress counters | Redis | Tracking pipeline run progress |
| NER model artifacts | Azure Blob Storage | Model version management |
| System configuration | Neo4j Patient Graph | Platform and org-level settings |
| Audit logs (who did what, when) | Neo4j Patient Graph | Traceability |

### 2.3 How data flows

```
GP FHIR R4 API
  → Core API (ingestion) → Neo4j Patient Graph (storage)

User request (via UI or API)
  → Core API → enqueue job → Azure Service Bus
    → Coding Worker:
        1. Read encounter from Neo4j
        2. Send to Model Inference service (spaCy NER extraction)
        3. Resolve SNOMED CT codes via Terminology API (Neo4j Knowledge Graph + Redis cache)
        4. [If low confidence] De-identify → sanitise → dual-LLM consensus:
             → AWS Bedrock Haiku (eu-west-2, UK) ─┐
             → Azure OpenAI GPT-5 mini (Sweden)   ├→ Consensus → verdict
             → [If disagree] AWS Bedrock Sonnet ──┘
        5. Write coded links to Neo4j Patient Graph
        6. [Optionally] Enqueue analysis job

    → Analysis Worker:
        1. Detect anchors (milestone events)
        2. Build episodes
        3. Run safety-net checks
        4. Detect abnormal results
        5. Calculate KPIs
        6. Run quality checks
        7. Write results to Neo4j Patient Graph

UI / API (display and review)
  → Core API → Neo4j Patient Graph → filtered by user's org scope → UI

Export (training data)
  → Core API → Neo4j Patient Graph → approved labels → download
```

### 2.4 Scope of the processing

| Dimension | Detail |
|---|---|
| Data subjects | NHS patients registered at participating GP practices |
| Nature of data | Special category — Article 9(1) health data |
| Volume | Per-patient, per-programme. NCDA launch: estimated [N] patients; expandable |
| Frequency | Batch (triggered per patient / per encounter); not real-time |
| Retention of encounter text | Stored in Neo4j for the life of the audit programme; deletion policy TBD |
| Retention of coded outputs | Stored in Neo4j for the life of the audit programme; deletion policy TBD |
| Retention of sessions | Redis; TTL set by `SESSION_TTL_HOURS` (12–24 hours in prod) |
| Retention of pipeline checkpoints | Redis; short-lived (hours); used for retry/recovery |
| Automated decision-making | Coding proposals are automated; **all** require human review before acceptance. No Article 22 solely automated decision-making applies. |

### 2.5 Context

- Patient consent is not required. Processing is clinical audit under the health and social care lawful basis (DPA 2018 ss.52–53). See Step 4.
- The controller (GP practice) is responsible for informing patients about audit processing through their privacy notices. LEO AI, as processor, acts under the controller's instructions via the DPA.
- The system has no patient-facing interface. Outputs are consumed by clinical audit professionals.
- Processing is retrospective only — historical records, not live clinical decisions.
- The platform is **not** clinical decision support. It does not influence live treatment decisions.

### 2.6 Purposes

| Purpose | Detail |
|---|---|
| **Primary** | Retrospective SNOMED CT coding and pathway reconstruction for national clinical audit (initially NCDA) |
| **Secondary** | Continuous improvement of coding accuracy through reviewer feedback and model retraining |
| **Benefit to individuals** | Better audit data helps identify systemic pathway delays, improving care for future patients |
| **Benefit to society** | Higher-quality population-level audit data informs national cancer care policy |

---

## Step 3 — Consultation

### 3.1 DPO consultation (mandatory)

The DPO must be consulted. Their advice must be recorded in Step 7.

**DPO advice:** _[to be completed by DPO]_

**DPO recommendation:** _[proceed / do not proceed / modify / consult ICO]_

### 3.2 Data subjects / patient representatives

Direct patient consultation on the technical implementation is not practicable at this stage. The controller (GP practice) is responsible for patient transparency. Before production deployment, LEO AI will:

- Present a plain-language summary of AI-assisted audit processing to NHS Patient and Public Voice (PPV) partners through the NCDA programme governance structure (PPV-001).
- Engage relevant cancer charity representatives (e.g. Cancer Research UK, Macmillan) as patient advocates.
- Provide controllers with template privacy notice language covering AI-assisted audit processing, for inclusion in the controller's own privacy notices (PN-SUPPORT-001).

**Reason:** Processing is retrospective clinical audit under DPA 2018 ss.52–53. The transparency obligation sits with the controller. LEO AI supports this contractually.

### 3.3 Sub-processors

AWS, Azure, and Neo4j must be consulted to confirm their DPA coverage extends to:
- The data processed (encounter text, coded outputs, patient demographics)
- The triple-call LLM arbitration pattern
- No-retention and no-training-use commitments for LLM providers
- 72-hour breach notification compatible with NHS DSPT

**Status:** Open — see DPA-REVIEW-001.

### 3.4 Other stakeholders

| Stakeholder | Method | Date | Outcome |
|---|---|---|---|
| Legal counsel | _[pending]_ | _[pending]_ | _[pending — controller/processor analysis and adequacy basis]_ |
| Information security | _[pending]_ | _[pending]_ | _[pending]_ |
| Clinical leads (NCDA) | _[pending]_ | _[pending]_ | _[pending]_ |

---

## Step 4 — Necessity and Proportionality

### 4.1 Lawful basis

**Controller's basis for processing personal data (Article 6):**

| Basis | Provision | Why it applies |
|---|---|---|
| Public task | UK GDPR Article 6(1)(e) | GP practices perform clinical audit as part of their official functions. National clinical audit programmes are mandated by NHS England. |

**Controller's basis for processing special category health data (Article 9):**

| Basis | Provision | Why it applies |
|---|---|---|
| Health or social care purposes | UK GDPR Article 9(2)(h) + DPA 2018 Schedule 1, Part 1, paragraph 2 | Processing is for the management of health and social care systems, including clinical audit. This is the primary basis. |
| Public health | UK GDPR Article 9(2)(i) | Processing serves the public interest in ensuring high standards of quality and safety of health care. |

**DPA 2018 specific provisions:**

- **Section 52** permits processing for health and social care purposes, including audit, without individual consent.
- **Section 53** defines health and social care purposes to include the management of health care systems and services, and monitoring and audit of health care provision.

**Caldicott Principles:** Processing is conducted in line with the Caldicott Principles. Patient-identifiable information is used only where necessary, access is on a need-to-know basis (enforced by org-scoped role-based access control), and the minimum necessary data is shared with sub-processors.

**NHS contractual requirements:** Processing is governed by NHS contractual requirements for handling patient-identifiable information, including the Data Security and Protection Toolkit (DSPT) standards.

The controller does **not** rely on consent. Consent is not required for clinical audit processing under the health and social care basis. Relying on consent would compromise audit data completeness and is not appropriate for mandatory national audit programmes.

> **Scope of this DPIA: retrospective clinical audit only.** The processing described in this document is retrospective audit of historical records. It does not influence live clinical decisions or treatment.
>
> The AI components covered here (NLP pipeline, LLM consensus engine) are shared infrastructure within the broader LEO application stack. Other parts of the LEO stack may use these components for Clinical Decision Support (CDS) or other purposes. Any use of these AI components for CDS or other processing purposes beyond retrospective audit is **outside the scope of this DPIA** and requires its own DPIA with a separate lawful basis assessment, risk analysis, and regulatory classification (including SaMD classification under MHRA/UKCA guidance).

**Processor's lawful basis:**

| Basis | Provision | Why it applies |
|---|---|---|
| Contract | UK GDPR Article 6(1)(b) | LEO AI (Mizaic) processes personal data because it is necessary for the performance of the Data Processing Agreement between the controller (GP practice) and LEO AI. Without processing the data, LEO AI cannot deliver the contracted audit service. |

LEO AI is a data processor. It acts solely under the controller's instructions and the terms of the DPA. All obligations relating to patient transparency, privacy notices, and individual rights sit with the controller. LEO AI's contractual obligation is to support the controller in meeting those obligations (e.g. by providing deletion APIs, access APIs, and data export capabilities).

### 4.2 Necessity — could the purpose be achieved with less data or fewer systems?

| Alternative | Assessment |
|---|---|
| Manual clinical coding (no AI) | Would require clinical coders to read and code every encounter manually. Not scalable to national audit volumes. |
| NLP only — no LLM fallback | Would produce more uncertain/uncoded entities, reducing audit completeness. Not viable for national audit quality standards. |
| On-premises LLM | Possible but requires major GPU infrastructure. Self-hosted model performance is lower than frontier models for clinical disambiguation. Not proportionate at current scale. |
| Send entity text only (no encounter context) to LLMs | Viable for many cases. This is a data minimisation opportunity — see open action DM-001. |
| Single LLM provider instead of dual | Removes the safety benefit of dual-model consensus (R-LEO-AI-026, R-LEO-AI-030). Not acceptable given clinical coding risk. |
| No storage of encounter text in Neo4j | Would prevent human review of original text, making audit validation impossible. Not viable. |
| No patient demographics | Demographics are needed for audit stratification (e.g. by age, gender). Minimum fields only (gender, birth date). |

**Conclusion:** The processing activities are necessary for the stated audit purpose. The dual-provider LLM pattern is proportionate to the safety requirements.

### 4.3 Data minimisation

**Controls in place:**

| Control | What it does |
|---|---|
| Encounter text truncation (2,000 chars) | Limits the volume of text sent to LLMs |
| Entity text limit (~200 chars) | Restricts the clinical phrase sent to LLMs |
| De-identification before LLM calls | Removes NHS numbers, postcodes, dates of birth, phone numbers |
| `sanitise_for_prompt()` | Strips injection patterns from text before LLM calls |
| Org-scoped access | Users see only patients belonging to their organisation |
| Minimum demographics | Only gender and birth date stored; no full address or contact details |
| LLM response restriction | LLMs return only a verdict string from a closed set; no free text returned |

**Open action:**

- **DM-001:** Evaluate whether disorder verification can work with `entity_text` alone (no encounter context) for most entities.

### 4.4 Retention

| Data | Current retention | Action needed |
|---|---|---|
| Encounter text in Neo4j | Life of audit programme | Define and document retention period (RET-001) |
| Coded outputs in Neo4j | Life of audit programme | Define and document retention period (RET-001) |
| Review decisions | Life of audit programme | Define and document retention period (RET-001) |
| Sessions in Redis | 12–24 hours (TTL) | Adequate |
| Pipeline checkpoints in Redis | Hours (short-lived) | Adequate |
| LLM call data | Not retained by LEO AI; not retained by providers per DPA | Confirm with providers (DPA-REVIEW-001) |
| Training exports | Downloaded by admin; not stored on platform | Adequate — admin responsible for downstream retention |
| NER model artifacts | Azure Blob Storage; versioned | Contains no patient data |

### 4.5 Individual rights

| Right | How it is supported |
|---|---|
| Access (Article 15) | Controller (GP practice) holds source records. LEO AI coded outputs are accessible to the controller via API. |
| Rectification (Article 16) | Reviewers can correct any coding proposal; corrections are persisted and traceable. |
| Erasure (Article 17) | Patient data can be deleted from Neo4j via the patient graph delete API. Process must be documented (RET-001). |
| Objection (Article 21) | Handled by the controller. LEO AI must provide a way for controllers to exclude specific patients. |
| Restriction (Article 18) | Controller can instruct LEO AI to stop processing a patient's data. Mechanism to be documented. |
| Automated decisions (Article 22) | **Not engaged** — all coding proposals need human reviewer approval before they become audit data. No solely automated decision with legal or similarly significant effect. |

---

## Step 5 — Identify and Assess Risks to Individuals

Risks are scored: severity (1–5) × likelihood (1–5). Scores of 9 or above are high risk.

### 5.1 Data storage and access risks

| Risk ID | Risk | Sev | Like | Score | Level | Primary mitigation |
|---|---|---|---|---|---|---|
| R-032-DP-010 | Unauthorised access to patient data in Neo4j via compromised credentials | 4 | 2 | 8 | Medium | Azure AD (Entra) OAuth; session-based auth; org-scoped access; MFA support; session TTL 12–24h |
| R-032-DP-011 | Patient data exposed through API without proper access controls | 4 | 1 | 4 | Low | Org-scoped queries; role-based access (builder, reviewer, releaser, operator); X-Requested-With guard for mutations |
| R-032-DP-012 | Session hijacking gives access to patient data | 3 | 2 | 6 | Low | HttpOnly cookie; SameSite=Lax; Secure flag; Redis-backed sessions (no client-side tokens); session TTL |
| R-032-DP-013 | Patient data in Redis (checkpoints) exposed via Redis compromise | 3 | 1 | 3 | Low | Azure Managed Redis; TLS in transit; encryption at rest; short TTL on checkpoints |
| R-032-DP-014 | Bulk patient data exposure via export endpoint | 4 | 1 | 4 | Low | Admin-only access; audit logging; no automated bulk export |
| R-032-DP-015 | Cross-tenant data leakage in multi-tenant deployment | 5 | 1 | 5 | Low | Org-scoped queries enforced at API layer; separate Neo4j databases per data type |

### 5.2 Processing and pipeline risks

| Risk ID | Risk | Sev | Like | Score | Level | Primary mitigation |
|---|---|---|---|---|---|---|
| R-032-DP-001 | Residual PHI in encounter text sent to AWS/Azure LLMs (de-identification gap) | 4 | 2 | 8 | Medium | De-identification pass; data minimisation; DPAs prohibit training use |
| R-032-DP-005 | Re-identification of de-identified encounter text by frontier LLM | 3 | 1 | 3 | Low | Data minimisation; truncation; de-identification |
| R-032-DP-016 | Encounter text stored in Neo4j longer than necessary | 3 | 2 | 6 | Low | Retention policy to be defined (RET-001) |
| R-032-DP-017 | Pipeline checkpoint in Redis contains patient clinical data | 3 | 1 | 3 | Low | Short TTL; Azure Managed Redis with TLS and encryption at rest |
| R-LEO-AI-030 | Prompt injection causes incorrect coding decision (clinical harm) | 4 | 1 | 4 | Low | INJECTION_GUARD; sanitise_for_prompt; cap_llm_response; dual-model consensus |
| R-LEO-AI-029 | LLM infers false diagnosis from lab value | 4 | 1 | 4 | Low | Prompt instruction; lab-value guard; resolver penalty |
| R-LEO-AI-026 | Autonomous coding without human review | 3 | 1 | 3 | Low | Dual-model consensus; tier classifier; HITL default for all proposals |

### 5.3 Transfer and sub-processor risks

| Risk ID | Risk | Sev | Like | Score | Level | Primary mitigation |
|---|---|---|---|---|---|---|
| R-032-DP-002 | Azure OpenAI (Sweden) international transfer not documented in RoPA | 3 | 2 | 6 | Low | UK adequacy regulations for EEA; document in RoPA (ROPA-001) |
| R-032-DP-003 | AWS/Azure DPA does not cover triple-call arbitration pattern | 4 | 1 | 4 | Low | DPA review (DPA-REVIEW-001) |
| R-032-DP-018 | Neo4j Aura data region not confirmed; potential undocumented international transfer | 3 | 2 | 6 | Low | Verify region in Aura console; document in RoPA |
| R-032-DP-004 | No per-call audit log for LLM API calls — forensic gap if breach occurs | 3 | 1 | 3 | Low | Open action LOG-LLM-CALLS-001 |

### 5.4 Individual rights and fairness risks

| Risk ID | Risk | Sev | Like | Score | Level | Primary mitigation |
|---|---|---|---|---|---|---|
| R-032-DP-006 | Erasure and objection rights not operationalised by controller | 3 | 2 | 6 | Low | Controller responsibility; LEO AI provides deletion API; process to be documented |
| R-032-DP-007 | NLP/LLM performs differently across ethnic groups, leading to biased audit data | 3 | 2 | 6 | Low | Ongoing bias monitoring; reviewer corrections; ICO AI fairness guidance |
| R-032-DP-019 | Patients unaware their data is processed by AI systems | 3 | 2 | 6 | Low | Controller responsibility. The GP practice (as controller) is responsible for privacy notices covering audit processing. LEO AI (as processor) acts under the controller's instructions via the DPA and supports the controller with template privacy notice language (PN-SUPPORT-001). |

### 5.5 Risk summary

**No risk exceeds the high-risk threshold.**

The highest scored risks are R-032-DP-001 and R-032-DP-010 (both score 8, Medium), both mitigated by the controls listed.

R-032-DP-019 (patient awareness) scores 6 (Low). The obligation to inform patients sits with the controller (GP practice), not with LEO AI as processor. LEO AI processes data under the controller's instructions via the DPA. The controller already has privacy notice obligations covering clinical audit under the health and social care lawful basis (DPA 2018 ss.52–53). LEO AI will support controllers by providing template privacy notice language covering AI-assisted processing (open action PN-SUPPORT-001).

> **DPO determination required:** The DPO must confirm at Step 7 whether voluntary ICO consultation is advisable given the scale of NHS patient data processing and the novel technology involved.

---

## Step 6 — Mitigating Measures

### 6.1 Technical measures — in place

| Measure | Risks addressed | Reference |
|---|---|---|
| Azure AD (Entra) OAuth with JWKS verification | R-032-DP-010, R-032-DP-011 | DC-TM-SEC-002 |
| Server-side sessions in Redis (HttpOnly, Secure, SameSite=Lax cookie) | R-032-DP-010, R-032-DP-012 | DC-TM-SEC-002 |
| Org-scoped data access (Practitioner → Organisation hierarchy) | R-032-DP-011, R-032-DP-015 | DC-TM-SEC-002 |
| Role-based access control (builder, reviewer, releaser, operator, platform admin) | R-032-DP-011, R-032-DP-014 | DC-TM-SEC-002 |
| X-Requested-With header required for mutations | R-032-DP-012 | DC-TM-SEC-002 |
| Rate limiting (slowapi) | R-032-DP-010 | DC-TM-SEC-002 |
| MFA support (configurable via SystemConfig) | R-032-DP-010 | DC-TM-SEC-002 |
| Inter-service authentication (SERVICE_AUTH_SECRET) | R-032-DP-011 | DC-TM-SEC-002 |
| ACA mTLS peer-traffic encryption | R-032-DP-011, R-032-DP-013 | DC-TM-SEC-002 |
| Azure Key Vault for all secrets | R-032-DP-010 | DC-TM-SEC-002 |
| Azure Managed Redis with TLS and encryption at rest | R-032-DP-012, R-032-DP-013, R-032-DP-017 | DC-TM-SEC-002 |
| De-identification before LLM calls (libs/deid) | R-032-DP-001, R-032-DP-005 | GAP-008 |
| Encounter text truncation (2,000 chars) | R-032-DP-001 | DI-LEO-AI-045 |
| `sanitise_for_prompt()` injection filter | R-LEO-AI-030 | DO-LEO-AI-030; VT-LEO-AI-038 |
| `cap_llm_response()` response limiter | R-LEO-AI-030 | DO-LEO-AI-030; VT-LEO-AI-038 |
| INJECTION_GUARD system prompt prefix | R-LEO-AI-030 | DO-LEO-AI-030 |
| Dual-model consensus (AWS + Azure) | R-LEO-AI-026, R-LEO-AI-030 | DI-LEO-AI-036; DO-LEO-AI-023 |
| HITL mandatory review for all proposals | R-LEO-AI-026, R-032-DP-006 | DC-IU-001 section 6.2 |
| UK data residency — AWS eu-west-2 | R-032-DP-002 | Confirmed via Bedrock ARN |
| EEA data residency — Azure Sweden | R-032-DP-002 | Confirmed via endpoint |
| Admin-only rule mutation | R-LEO-AI-031 | DI-LEO-AI-046; DO-LEO-AI-031 |
| CSP, HSTS, X-Frame-Options headers | R-032-DP-012 | DC-TM-SEC-002 |
| Session TTL (12–24 hours in prod) | R-032-DP-012 | DC-TM-SEC-002 |
| Non-root, distroless container images | R-032-DP-010 | DC-TM-SEC-002 |

### 6.2 Technical measures — open actions

| Action ID | Measure | Risks addressed | Target date |
|---|---|---|---|
| LOG-LLM-CALLS-001 | Per-call audit log for LLM API calls (provider, model, entity length, timestamp, patient-id hash — no content) | R-032-DP-004 | 2026-05-15 |
| DM-001 | Evaluate sending entity_text only (not encounter_text) for disorder verification | R-032-DP-001 | 2026-06-01 |
| DEID-002 | NER-based name detection as second de-identification pass (spaCy PERSON model) | R-032-DP-001 (GAP-008) | 2026-07-01 |
| LOG-ACCESS-001 | Audit trail for patient record access via the UI and API | R-032-DP-010, R-032-DP-011 | 2026-06-01 |
| NEO4J-REGION-001 | Confirm Neo4j Aura data region and document in RoPA | R-032-DP-018 | 2026-04-15 |

### 6.3 Contractual measures — open actions

| Action ID | Measure | Risks addressed | Target date |
|---|---|---|---|
| DPA-REVIEW-001 | Review AWS and Azure DPAs — confirm: (a) triple-call arbitration covered, (b) no training use, (c) 72-hour breach notification, (d) sub-processor disclosure | R-032-DP-003 | 2026-05-01 |
| DPA-GP-001 | Update GP practice DPAs to name AWS, Azure, Neo4j, and Microsoft Azure PaaS as sub-processors | R-032-DP-003 | 2026-05-01 |
| DPA-NEO4J-001 | Review Neo4j Aura DPA for data residency, breach notification, and deletion commitments | R-032-DP-018 | 2026-05-01 |

### 6.4 Governance measures — open actions

| Action ID | Measure | Risks addressed | Target date |
|---|---|---|---|
| ROPA-001 | Add UK → Sweden (Azure OpenAI) and Neo4j Aura transfers to Records of Processing Activities with adequacy basis | R-032-DP-002, R-032-DP-018 | 2026-04-15 |
| PN-SUPPORT-001 | Provide controllers with template privacy notice language covering AI-assisted audit processing, for inclusion in their own privacy notices | R-032-DP-019 | 2026-05-15 |
| RET-001 | Define retention periods for Neo4j patient data (encounter text, coded outputs, review decisions); implement deletion | R-032-DP-006, R-032-DP-016 | 2026-06-01 |
| BIAS-001 | Coding accuracy analysis stratified by patient ethnicity and gender | R-032-DP-007 | 2026-09-01 |
| PPV-001 | Engage NHS PPV partners and cancer charities on AI processing | R-032-DP-019 | 2026-05-01 |
| RIGHTS-001 | Document and test the process for handling erasure and objection requests end-to-end (controller instructs LEO AI, LEO AI deletes from Neo4j, confirms to controller) | R-032-DP-006 | 2026-06-01 |

---

## Step 7 — Sign-off and Outcomes

### 7.1 Residual risk assessment

After all confirmed mitigations are in place, the residual risk level is:

**LOW** — no residual high risk identified. The highest scored risks (R-032-DP-001, R-032-DP-010, both score 8) are mitigated to Medium by the controls in Step 6.

### 7.2 ICO consultation

| Criterion | Assessment |
|---|---|
| Residual high risk that cannot be mitigated? | No — all risks mitigated to Medium or Low |
| Mandatory ICO consultation required? | No — Article 36 threshold not met once mitigations complete |
| Voluntary ICO consultation recommended? | _[DPO to determine — consider scale of NHS data and novel AI]_ |

**DPO determination on ICO consultation:** _[pending DPO sign-off]_

### 7.3 Decision to proceed

| Condition | Status |
|---|---|
| Azure AD (Entra) OAuth authentication in place | Done |
| Org-scoped access control in place | Done |
| Role-based access control in place | Done |
| AWS eu-west-2 (UK) data residency confirmed | Done |
| Azure Sweden EEA data residency confirmed | Done |
| UK adequacy regulations for EEA apply | Done |
| De-identification before LLM calls in place | Done (residual gaps documented) |
| Dual-provider DPAs prohibit training use | Done (arbitration coverage needs confirming) |
| HITL review for all coding proposals | Done |
| Prompt injection controls deployed and tested | Done |
| Neo4j Aura data region confirmed | Pending (NEO4J-REGION-001) |
| DPO consulted | Pending |
| DPA-REVIEW-001 complete | Pending (2026-05-01) |
| DPA-NEO4J-001 complete | Pending (2026-05-01) |
| ROPA-001 complete | Pending (2026-04-15) |
| PN-SUPPORT-001 template privacy notice language provided to controllers | Pending (2026-05-15) |
| PPV-001 patient engagement completed | Pending (2026-05-01) |
| LOG-LLM-CALLS-001 implemented | Pending (2026-05-15) |
| RET-001 retention policy defined | Pending (2026-06-01) |
| RIGHTS-001 erasure process documented | Pending (2026-06-01) |

**Recommendation:** Processing may proceed in **pilot scope only** (limited GP practice cohort) while open actions are completed. Production rollout is conditional on DPO sign-off and completion of: DPA-REVIEW-001, DPA-NEO4J-001, ROPA-001, PN-SUPPORT-001, RET-001, and RIGHTS-001.

### 7.4 DPO sign-off

> I have reviewed this DPIA and confirm it correctly describes the processing, the risks, and the mitigations. My advice is that the processing **[may proceed / should not proceed / should be modified as follows]** subject to completion of the open actions in Step 6.
>
> **DPO name:** _[name]_
> **DPO signature:** _[signature / electronic confirmation]_
> **Date:** _[date]_
> **Advice followed / not followed:** _[followed]_
> **If not followed, reason:** _[n/a]_

### 7.5 Review triggers

This DPIA must be reviewed if any of the following happen:

- A new LLM provider is added or an existing provider's data region changes
- A new data store is added or an existing store's data region changes
- The volume of data processed increases significantly (e.g. new GP practice groups)
- The processing purpose changes (e.g. real-time clinical decision support is added)
- New categories of personal data are collected or processed
- The de-identification approach changes
- The authentication or access control model changes
- The UK's adequacy decision for the EEA is amended or revoked
- A personal data breach occurs
- ICO guidance changes applicable requirements
- New sub-processors are introduced

> **Note (2026-03-03):** The `suggest-aliases` call pattern (see Section 2.2) was assessed and confirmed out of scope — no patient data is transmitted.

---

## Appendix A — Open Actions Register

| ID | Description | Owner | Target date | Status |
|---|---|---|---|---|
| DPA-REVIEW-001 | Review AWS and Azure DPAs for triple-call arbitration, no training use, 72-hour breach notification, sub-processor obligations | Legal / DPO | 2026-05-01 | Open |
| DPA-GP-001 | Update GP practice DPAs to name all sub-processors (AWS, Azure, Neo4j, Microsoft Azure PaaS) | Legal | 2026-05-01 | Open |
| DPA-NEO4J-001 | Review Neo4j Aura DPA for data residency, breach notification, deletion | Legal / DPO | 2026-05-01 | Open |
| NEO4J-REGION-001 | Confirm Neo4j Aura data region; document in RoPA | Engineering / DPO | 2026-04-15 | Open |
| ROPA-001 | Add all international transfers to RoPA with adequacy basis | DPO | 2026-04-15 | Open |
| PN-SUPPORT-001 | Provide controllers with template privacy notice language covering AI-assisted audit processing | Product / Legal | 2026-05-15 | Open |
| PPV-001 | Engage NHS PPV partners and cancer charities on AI processing | Product | 2026-05-01 | Open |
| LOG-LLM-CALLS-001 | Per-call audit log for LLM API calls | Engineering | 2026-05-15 | Open |
| LOG-ACCESS-001 | Audit trail for patient record access via UI and API | Engineering | 2026-06-01 | Open |
| DM-001 | Evaluate entity_text-only fast path for disorder verification | Engineering | 2026-06-01 | Open |
| DEID-002 | NER-based name detection as second de-identification pass | Engineering | 2026-07-01 | Open |
| RET-001 | Define retention periods for all patient data in Neo4j; implement deletion | Engineering / Legal | 2026-06-01 | Open |
| RIGHTS-001 | Document and test erasure/objection request process end-to-end | Engineering / Legal | 2026-06-01 | Open |
| BIAS-001 | Coding accuracy analysis stratified by ethnicity and gender | Clinical / Engineering | 2026-09-01 | Open |

---

## Appendix B — References

| Reference | Document |
|---|---|
| ICO DPIA guidance | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/ |
| ICO AI and data protection guidance | https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/artificial-intelligence/guidance-on-ai-and-data-protection/ |
| UK GDPR Article 35 | UK GDPR as retained in UK law by the European Union (Withdrawal) Act 2018 |
| DPA 2018 Schedule 1 Part 1 para 2 | Health or social care purposes lawful basis for special category data |
| DPA 2018 ss.52–53 | Health and social care purposes including audit, without individual consent |
| Caldicott Principles | National Data Guardian framework for handling patient-identifiable information |
| UK Adequacy Regulations 2021 | The Data Protection (Adequacy) (European Union) Regulations 2021 |
| Data (Use and Access) Act 2025 | In force 19 June 2025 — ICO guidance update pending |
| NHS DSPT | https://www.dsptoolkit.nhs.uk/ |
| NHS Digital Regulations guidance | https://www.digitalregulations.innovation.nhs.uk/ |
| R-LEO-AI-032 | design-controls/risks/R-LEO-AI-032.yaml |
| DC-TM-SEC-002 | design-controls/DC-TM-SEC-002-threat-model.yaml |
| DC-IU-001 | design-controls/intended-use.md |

---

## Appendix C — Data Map Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│ GP FHIR R4 API                                                         │
│ (Patient, Encounter, DocumentReference)                                │
└──────────────┬──────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Core API (FastAPI)                                                       │
│ Auth: Azure AD (Entra) OAuth → Redis sessions                           │
│ Access: Org-scoped, role-based                                          │
│                                                                          │
│ Stores patient + encounter data → Neo4j Patient Graph                   │
│ Dispatches jobs → Azure Service Bus                                     │
│ Serves UI requests, API calls, exports                                  │
└──────┬───────────┬────────────────────────────────────┬─────────────────┘
       │           │                                    │
       ▼           ▼                                    ▼
┌────────────┐ ┌───────────────┐                 ┌──────────────┐
│ Coding     │ │ Analysis      │                 │ UI (Next.js) │
│ Worker     │ │ Worker        │                 │              │
│            │ │               │                 │ Displays:    │
│ 1. NER     │ │ 1. Anchors    │                 │ - Patients   │
│ 2. SNOMED  │ │ 2. Episodes   │                 │ - Encounters │
│ 3. LLM     │ │ 3. Safety-net │                 │ - Coded data │
│    fallback│ │ 4. Abnormals  │                 │ - Episodes   │
│ 4. Write   │ │ 5. KPIs       │                 │ - Alerts     │
│    to Neo4j│ │ 6. Quality    │                 │ - Reviews    │
└──────┬─────┘ └──────┬────────┘                 └──────────────┘
       │              │
       ▼              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Neo4j Patient Graph                                                      │
│ Patient, Encounter, CodedLinks, Episodes, Alerts, Reviews, Approvals    │
└──────────────────────────────────────────────────────────────────────────┘

LLM calls (fallback only, de-identified):
  → AWS Bedrock (eu-west-2, UK)
  → Azure OpenAI (Sweden Central, EEA)
  → AWS Bedrock Sonnet (arbitrator, if providers disagree)
```
