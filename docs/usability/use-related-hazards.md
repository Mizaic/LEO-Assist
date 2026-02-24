# Use-Related Hazard Analysis

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | URHA-001                       |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |
| Source           | CRITICAL-TASKS-001, DC-IU-001 |

---

## 1. Use-Related Hazards

| Hazard ID | Description | Cause | Effect | Severity | Probability | Risk control | Residual risk |
| --------- | ----------- | ----- | ------ | -------- | ----------- | ------------ | ------------- |
| URH-01 | Incorrect SNOMED coding approved as final audit data | Reviewer approves wrong concept; confusion between similar terms; fatigue | Audit data inaccurate; downstream quality metrics wrong; potential population-level misinterpretation | Medium | Medium | Confidence display; term search; corrections log; mandatory reason; training | Low |
| URH-02 | Incorrect coding not rejected | Reviewer misses error; unclear UI; time pressure | Wrong coding propagates; audit integrity compromised | Medium | Medium | Reject action; reason required; warning indicators; escalation | Low |
| URH-03 | Critical guideline alert missed | Alert buried in queue; poor prioritisation; reviewer skips | Pathway deviation not investigated; potential patient-safety signal missed (indirect) | Medium | Low | Warning count; prioritisation; escalation path | Low |
| URH-04 | Episode misclassified (confirmed/excluded/inconclusive) | Unclear status display; reviewer misunderstanding | Audit metrics incorrect; episode count wrong | Low | Low | Clear status; review gate; training | Negligible |
| URH-05 | Decision submitted without adequate justification | Optional or short reason; copy-paste | Audit trail weak; difficult to trace decisions | Low | Medium | Min length (3 chars) on reason; audit log | Low |

---

## 2. Severity Definitions

| Level | Definition |
| ----- | ---------- |
| High | Direct patient harm; critical audit failure |
| Medium | Incorrect audit data; population-level impact; indirect safety signal |
| Low | Minor metric error; weak audit trail |

---

## 3. Risk Control Measures (Summary)

1. **Confidence display** — show AI confidence per proposal to support reviewer judgment
2. **Term search** — enable correction via SNOMED lookup
3. **Corrections log** — visible audit trail before submit
4. **Mandatory reason** — require reason on approve/reject (min 3 chars)
5. **Warning indicators** — highlight tasks with alerts or low-confidence items
6. **Escalation** — allow reassignment when reviewer cannot complete
7. **Role-based gate** — no finalisation without appropriate human approval

---

## 4. Traceability

| Hazard | Critical task | Design input |
| ------ | ------------- | ------------ |
| URH-01 | CT-01 | EntityCard (confidence), TermSearch, CorrectionsLog |
| URH-02 | CT-02 | ReviewView (reject action, reason field) |
| URH-03 | CT-03 | Review queue, warning_count, task status |
| URH-04 | CT-04 | Episode review UI (future) |
| URH-05 | CT-05 | submitDecision (reason min_length=3) |
