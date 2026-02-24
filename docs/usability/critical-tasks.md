# Critical Task List

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | CRITICAL-TASKS-001             |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |
| Source           | USER-NEEDS-001, URHA-001      |

---

## 1. Critical Tasks

Tasks where use error could cause harm (incorrect audit data, missed safety signal).

| Task ID | Description | User group | Use-related hazard | Risk | Mitigation |
| ------- | ----------- | ---------- | ------------------ | ---- | ---------- |
| CT-01 | Validate SNOMED CT coding proposal and approve or correct | Human reviewers | Incorrect coding approved as final; wrong concept in audit data | Medium | Confidence display; term search for correction; corrections log; mandatory reason on submit |
| CT-02 | Reject incorrect or unsafe coding proposal | Human reviewers | Wrong coding not rejected; propagates to audit | Medium | Reject action; reason required; audit trail |
| CT-03 | Review and act on guideline compliance alerts | Pathway coordinators | Critical alert missed; pathway deviation not investigated | Medium | Alert prioritisation; warning count; escalation path |
| CT-04 | Approve episode classification (confirmed/excluded/inconclusive) | Clinical audit teams | Episode misclassified; audit metrics incorrect | Low | Episode status clearly displayed; review gate |
| CT-05 | Submit decision with reason | All reviewers | Decision submitted without adequate justification | Low | Reason field required; min length validation |

---

## 2. Task Descriptions (Detail)

### CT-01: Validate SNOMED CT coding proposal

**Steps:** 1) Open task from queue; 2) View encounter with highlighted spans; 3) Click span to see proposal; 4) Verify SNOMED concept matches clinical meaning; 5) If wrong, search and select correct term or adjust span; 6) Submit approve (with or without edits) or reject.

**Use error modes:** Approving without reading; approving wrong concept due to similar terms; missing negation/context.

### CT-02: Reject incorrect proposal

**Steps:** 1) Identify incorrect proposal; 2) Select Reject; 3) Enter reason; 4) Submit.

**Use error modes:** Rejecting correct proposal; failing to reject incorrect one; vague reason.

### CT-03: Act on guideline alerts

**Steps:** 1) View tasks with alerts; 2) Prioritise by severity; 3) Investigate pathway deviation; 4) Escalate or resolve.

**Use error modes:** Missing high-priority alert; dismissing without investigation.

### CT-04: Approve episode classification

**Steps:** 1) Review episode timeline and milestones; 2) Verify classification; 3) Approve or request changes.

**Use error modes:** Approving wrong episode type; approving with missing milestones.

### CT-05: Submit decision with reason

**Steps:** 1) Complete review; 2) Enter reason (min 3 chars); 3) Submit.

**Use error modes:** Submitting without meaningful reason; copy-paste generic text.

---

## 3. Traceability

| Task | User need | Hazard |
| ---- | --------- | ------ |
| CT-01 | UN-03, UN-04, UN-05, UN-06 | URH-01 |
| CT-02 | UN-06 | URH-02 |
| CT-03 | UN-09 | URH-03 |
| CT-04 | UN-06, UN-08 | URH-04 |
| CT-05 | UN-06 | URH-05 |
