# Use Specification — NLP Training and Inference Pipeline UI

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | USE-SPEC-002                   |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |
| Source           | DC-IU-001, NLP-PIPELINE-IP-001 |

---

## 1. User Groups (NLP Pipeline Context)

| User role            | Primary interaction | Training / knowledge | Cognitive load during use |
| -------------------- | ------------------- | -------------------- | ------------------------- |
| **Clinical coders**   | Review LLM proposals; approve, edit, reject; sync gold | SNOMED CT, clinical coding | High — many tasks per session; accuracy-critical |
| **Audit coordinators** | Run pipeline; select patients; monitor progress | Pipeline concepts; patient selection | Medium — batch operations; wait time |
| **System operators** | Build MedSpaCy from gold; run validation; manage config | DevOps; MedSpaCy; export/inference | Low — infrequent; technical |

---

## 2. Use Environment

- **Physical:** Office or remote; NHS primary care audit setting
- **Interruptions:** Possible — phone, colleagues; reviewers may context-switch
- **Multi-tasking:** Coders may have multiple browser tabs; coordinators monitor pipeline while doing other work
- **Equipment:** Standard desktop/laptop; web browser
- **Time constraints:** Audit deadlines; coordinators may rush pipeline runs

---

## 3. Critical Tasks (Use Specification)

Tasks where use error could lead to harm or data loss:

| Task ID | Description | User role | Harm if error |
| ------- | ----------- | --------- | ------------- |
| CT-01 | Validate SNOMED coding proposal and approve/correct | Clinical coder | Wrong coding in audit data |
| CT-02 | Reject incorrect proposal | Clinical coder | Wrong coding propagates |
| CT-03 | Reset patient (remove all DOCUMENTS) | Audit coordinator | Accidental data loss |
| CT-04 | Sync gold to patient graph | Audit coordinator | Unapproved data written to patient graph |
| CT-05 | Export MedSpaCy training | System operator | Wrong/partial gold exported |
| CT-06 | Run inference (dry_run=false) | System operator | Unvalidated entities written |

---

## 4. User Interface Description (NLP Pipeline)

### 4.1 Patient List
- Patient IDs with encounter count
- Filter by ID; Refresh
- Progress bar (when API supports)
- Pipeline panel (Run, Export)

### 4.2 Encounter List (per patient)
- Encounters with status (pending, approved, rejected, escalated)
- Reset patient, Sync gold to patient
- Click → Review (task) or View (encounter)

### 4.3 Review View (HITL)
- Encounter text with highlighted spans
- Entity card (popover): SNOMED, confidence, context flags, Reassign, Adjust span, Remove
- Entity sidebar: list of entities
- CodedLinksSection (patient graph links)
- Corrections log
- Actions: Approve, Correct & Approve, Reject

### 4.4 Encounter Coded View (view/manual coding)
- Encounter text; select text → Code selection
- CodedLinksSection: Recode, Remove
- Run inference (preview)

### 4.5 Pipeline Panel
- Patient IDs, max encounters, workers, dry run
- Run Pipeline → modal with progress/games
- Export MedSpaCy training

---

## 5. Training and Knowledge Assumptions

| Assumption | Rationale |
| ---------- | --------- |
| Coders know SNOMED CT | Required to validate proposals |
| Coders understand negation/context | NEG, UNC, HIST flags |
| Coordinators understand pipeline flow | Reset → Run → Review → Sync → Export |
| Operators understand MedSpaCy export format | entities.jsonl, kb.jsonl |

---

## 6. Traceability

| Section | Traces to |
| ------- | --------- |
| User groups | NLP-PIPELINE-IP-001 §4 |
| Critical tasks | docs/usability/critical-tasks.md |
| UI description | services/ui components |
