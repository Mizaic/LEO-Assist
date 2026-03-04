# DC-RET-001 — Data Retention Schedule

| Field | Value |
|---|---|
| Document ID | DC-RET-001 |
| Version | 0.1-draft |
| Status | Draft — awaiting DPO and legal review |
| Date | 2026-03-04 |
| Author | DPO / Legal / Engineering |
| NCDA audit item | OG02 |
| Related documents | DPIA-LEO-AI-001, DC-DPA-002 |
| Regulatory basis | UK GDPR Article 5(1)(e); NHS Records Management Code of Practice 2021; DPA 2018 |

---

## 1  Purpose

This document defines the retention periods for all personal data processed by the LEO AI Clinical Pathway Audit Platform. It satisfies:

- UK GDPR Article 5(1)(e) — storage limitation principle
- NCDA audit requirement OG02 — retention aligned with NHS Records Management Code of Practice
- DPIA-LEO-AI-001 open action RET-001

---

## 2  NHS Records Management Code of Practice — applicable schedules

The NHS Records Management Code of Practice (2021) defines retention periods for NHS records. The following schedules apply to LEO AI data:

| Record type | NHS Records Management Code schedule | Retention period |
|---|---|---|
| GP clinical records (primary care) | Schedule 2 — Primary care records | Minimum 10 years after last entry, or 10 years after the patient's 18th birthday if sooner |
| Audit and quality improvement records | Schedule 9 — Administrative and operational records | 6 years after the conclusion of the audit programme |
| Clinical audit programme documentation | Schedule 9 | 6 years |
| System access and audit logs | Schedule 9 — Information technology records | 1–3 years (see Section 3) |

> **Key principle:** LEO AI processes copies of GP clinical records for audit purposes. Retention of data within the LEO AI platform is governed by the audit programme lifecycle, not by the source GP record retention schedule. Once the audit programme concludes and outputs are delivered to the Controller, the source data held in the platform should be deleted unless there is a specific ongoing reason to retain it.

---

## 3  Retention schedule — by data category

### 3.1  Patient personal data (Neo4j Patient Graph)

| Data category | Retention period | Trigger for deletion | Responsible party |
|---|---|---|---|
| **Patient demographics** (gender, birth date) | Duration of active audit programme + 90 days | Audit programme closure; or Controller instruction | LEO AI (on Controller instruction) |
| **Encounter text** (consultation notes, document text) | Duration of active audit programme + 90 days | Audit programme closure; or Controller instruction | LEO AI (on Controller instruction) |
| **SNOMED CT coded links** (NLP outputs) | Duration of active audit programme + 90 days | Audit programme closure; or Controller instruction | LEO AI (on Controller instruction) |
| **Clinical episodes and timelines** | Duration of active audit programme + 90 days | Audit programme closure; or Controller instruction | LEO AI (on Controller instruction) |
| **Safety-net alerts and abnormal result flags** | Duration of active audit programme + 90 days | Audit programme closure; or Controller instruction | LEO AI (on Controller instruction) |
| **Review decisions and approvals** (audit trail) | 6 years from date of review decision | 6-year anniversary | LEO AI |
| **Reviewer staff records** (name, email in audit trail) | 6 years from date of review decision | 6-year anniversary | LEO AI |

> **"Duration of active audit programme"** means the period from the first data ingestion for a Controller's programme to the Controller's written confirmation that the programme is complete and data may be deleted.

> **Rationale:** Clinical audit outputs (review decisions, coded data) are governance records that may be required for regulatory inspection, quality investigations, or legal proceedings for up to 6 years. This aligns with the NHS Records Management Code of Practice Schedule 9.

### 3.2  Operational data (Redis)

| Data category | Retention period | Mechanism |
|---|---|---|
| **OAuth sessions** | 12–24 hours (production) | Redis TTL — automatic expiry |
| **Pipeline job progress counters** | Hours (short-lived) | Redis TTL — automatic expiry |
| **LLM response cache** | _[to be defined — default 24 hours]_ | Redis TTL — automatic expiry |
| **Pipeline checkpoints** (retry/recovery) | Hours — cleared on job completion | Redis TTL — automatic expiry |

### 3.3  LLM provider data

| Data category | Retention period | Basis |
|---|---|---|
| **Data sent to AWS Bedrock** | Not retained — deleted immediately after inference | AWS Enterprise DPA — no-retention commitment |
| **Data sent to Azure OpenAI** | Not retained — deleted immediately after inference | Microsoft Enterprise DPA — no-retention commitment |

### 3.4  Model artefacts (Azure Blob Storage)

| Data category | Retention period | Notes |
|---|---|---|
| **NER model artefacts** | Retained while the model version is in use + 2 years | No patient data; versioned for traceability |
| **Superseded model versions** | Archived for 2 years after decommission | Regulatory traceability |

### 3.5  Knowledge Graph (Approved Mappings)

| Data category | Retention period | Basis |
|---|---|---|
| **Approved Mappings** (de-identified phrase → SNOMED code) | Indefinite — managed as a shared clinical terminology resource | No patient personal data. See DPA clause 11.3. |

---

## 4  Deletion process

### 4.1  End-of-programme deletion

On conclusion of an audit programme, or on termination of a Controller's service contract:

1. **Controller instruction:** The Controller sends a written deletion instruction to LEO AI.
2. **Deletion within 30 days:** LEO AI deletes all Patient Graph data for the Controller's organisation within 30 calendar days.
3. **Backup deletion:** All backup copies are deleted within 90 calendar days.
4. **Deletion confirmation:** LEO AI provides a written certificate of destruction to the Controller (as required by DPA clause 11.1(d)).

### 4.2  Individual patient erasure (Article 17 requests)

On receipt of a valid erasure instruction from the Controller:

1. **Controller instruction received:** Controller sends written instruction to LEO AI.
2. **Deletion within 24 hours:** LEO AI deletes the relevant patient's data from the Patient Graph within 24 hours.
3. **Confirmation:** LEO AI confirms deletion in writing to the Controller.
4. **Approved Mappings:** Not affected — they contain no patient personal data.

### 4.3  Automated retention enforcement

**Status:** Automated retention enforcement (scheduled deletion jobs) is an **open engineering action** (RET-001-ENG). Until automated deletion is implemented, retention enforcement is a manual process triggered by Controller instruction or programme closure.

---

## 5  Retention period by DPA Addendum

| Addendum | Data | Retention |
|---|---|---|
| A — EPR Audit | Patient personal data in Patient Graph | Duration of audit programme + 90 days |
| A — EPR Audit | Review decisions / audit trail | 6 years |
| B — CDS (LEO) | Patient personal data in Patient Graph | Minimum 8 years (NHS records management for clinical decision support audit trails) |
| B — CDS (LEO) | Audit trail (clinician decisions, write-backs) | Minimum 8 years |

> **CDS note:** Clinical decision support audit trails are governance records with potential medico-legal significance. The NHS Records Management Code of Practice requires these to be retained for at least 8 years. This is reflected in DPA Addendum B clause B.9.

---

## 6  Backup arrangements

| Backup type | Frequency | Retention | Integrity testing |
|---|---|---|---|
| Neo4j Aura backups | Daily (platform-managed) | _[confirm with Neo4j — default 7 days]_ | _[confirm with Neo4j]_ |
| Azure Redis backups | Not applicable — ephemeral data (short TTL) | N/A | N/A |
| Azure Blob Storage (model artefacts) | Azure geo-redundant storage | Per artefact retention above | Integrity checks via Azure Storage |

> **Open action:** Confirm Neo4j Aura backup frequency, retention, integrity testing, and restoration procedures with Neo4j account team (linked to SP-006 in DC-SP-001).

---

## 7  Open actions

| ID | Action | Owner | Target date |
|---|---|---|---|
| RET-001-POLICY | DPO and legal to review and formally approve this retention schedule | DPO / Legal | 2026-06-01 |
| RET-001-ENG | Engineering to implement automated deletion jobs for expired patient data in Neo4j | Engineering | 2026-06-01 |
| RET-001-NEO4J | Confirm Neo4j Aura backup frequency, retention, and restore procedures | Engineering | 2026-05-01 |
| RET-001-CERT | Prepare certificate of destruction template for use on programme closure | Legal | 2026-05-01 |
| RET-001-PROC | Document end-of-programme deletion process as an operational runbook | Engineering / DPO | 2026-06-01 |

---

## 8  Sign-off

| Role | Name | Signature | Date |
|---|---|---|---|
| DPO | _[name]_ | _[signature]_ | _[date]_ |
| Legal | _[name]_ | _[signature]_ | _[date]_ |

---

## 9  References

| Reference | Document |
|---|---|
| DPIA-LEO-AI-001 | Data Protection Impact Assessment (Section 2.4, 4.4, open action RET-001) |
| DC-DPA-002 | Data Processing Agreement (Clause 11; Addendum A clause A.8; Addendum B clause B.9) |
| NHS Records Management Code of Practice 2021 | https://www.nhsx.nhs.uk/information-governance/guidance/records-management-code/ |
| UK GDPR Article 5(1)(e) | Storage limitation principle |
| DC-SP-001 | Sub-processor Evidence Register (Neo4j backup details) |
