# User Needs

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | USER-NEEDS-001                 |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |
| Source           | USE-SPEC-001, DC-IU-001       |

---

## 1. User Needs (Traceable)

| ID   | Need statement | Source | Acceptance criterion |
| ---- | ----------------- | ------ | --------------------- |
| UN-01 | Reviewer shall be able to view the review queue and select a task | USE-SPEC-001 §3.1, DC-IU-001 §6.2 | Queue displays pending tasks; user can open a task |
| UN-02 | Reviewer shall be able to view encounter text with AI-proposed spans highlighted | USE-SPEC-001 §3.1 | Encounter text displayed; spans visually distinct |
| UN-03 | Reviewer shall be able to inspect coding proposal (SNOMED concept, confidence, context) per span | USE-SPEC-001 §3.1 | Entity card shows proposal details on span click |
| UN-04 | Reviewer shall be able to search for SNOMED terms to correct or replace a proposal | USE-SPEC-001 §3.1 | Term search returns SNOMED concepts; user can select |
| UN-05 | Reviewer shall be able to apply corrections (span, context, code) before submission | USE-SPEC-001 §3.1 | Corrections editable; corrections log visible |
| UN-06 | Reviewer shall be able to submit a decision (approve/edit/reject) with a reason | USE-SPEC-001 §3.1, DC-IU-001 §6.2 | Submit action available; reason required |
| UN-07 | Reviewer shall be able to escalate a task when unable to complete | USE-SPEC-001 §3.1 | Escalate option available; task reassigned |
| UN-08 | System shall prevent finalisation of audit data without human approval | DC-IU-001 §3, §6.2 | Role-based gate; no auto-finalisation |
| UN-09 | Pathway coordinator shall be able to identify high-priority items (breaches, alerts) | DC-IU-001 §3 | Queue or filters support prioritisation |
| UN-10 | Programme admin shall be able to configure programmes via API | DC-IU-001 §3, §5 | REST API supports configuration operations |

---

## 2. Traceability

| Need | Traces to design input |
| ---- | ---------------------- |
| UN-01 to UN-07 | HITL UI components (ReviewView, EncounterCodedView, TermSearch, etc.) |
| UN-08 | API role-based access, review workflow |
| UN-09 | Review queue, task status, warning_count |
| UN-10 | API endpoints for programme configuration |
