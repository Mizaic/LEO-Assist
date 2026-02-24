# Use-Related Risk Table — NLP Pipeline UI

| Field            | Value                          |
| ---------------- | ------------------------------ |
| Document ID      | URRT-001                      |
| Version          | 0.1.0-draft                   |
| Status           | Draft                         |
| Date             | 2026-02-24                    |
| Classification   | QMS — Usability Engineering   |

---

## Risk Table

| Critical task | Potential use error | Hazardous situation | Harm | Severity | Probability | Suggested mitigation |
| ------------- | ------------------- | -------------------- | ---- | -------- | ----------- | -------------------- |
| CT-01: Validate and approve coding | Approve without reviewing; approve wrong concept | Incorrect SNOMED in audit data | Population-level metrics wrong; indirect safety signal | Medium | Medium | Confidence display; mandatory reason; corrections log; term search for correction |
| CT-02: Reject incorrect proposal | Fail to reject; reject correct proposal | Wrong coding propagates; correct coding lost | Audit integrity; rework | Medium | Medium | Reject with reason; confirmation for reject |
| CT-03: Reset patient | Accidental click; wrong patient | All DOCUMENTS deleted | Data loss; rework | Medium | Low | Confirmation modal: "Remove all coded links? Cannot be undone." |
| CT-04: Sync gold to patient | Sync before all reviewed; sync wrong patient | Unapproved or wrong data in patient graph | Audit integrity; downstream errors | Medium | Low | Disable until approved > 0; confirm "Apply approved gold?" |
| CT-05: Export MedSpaCy | Export partial set; wrong export name | Training data incomplete/wrong | Model quality; validation fails | Low | Low | Show export summary; confirm patient count |
| CT-06: Run inference (apply) | Apply without validation; dry_run=false by mistake | Unvalidated entities in patient graph | Audit integrity | Medium | Low | No apply button in UI yet (VERIFICATION-REPORT); when added: require confirmation |

---

## Severity Definitions

| Level | Definition |
| ----- | ---------- |
| High | Direct patient harm; critical audit failure |
| Medium | Incorrect audit data; data loss; population-level impact |
| Low | Minor metric error; rework |

---

## Summative Evaluation Readiness

| Critical task | Safety-critical? | Suggested pass/fail criteria |
| ------------- | ----------------- | ---------------------------- |
| CT-01 | Yes | ≥95% of test users correctly approve/reject in scenario; no wrong approval |
| CT-02 | Yes | Same as CT-01 |
| CT-03 | Yes | 100% of users confirm before reset in scenario |
| CT-04 | Yes | No sync without approval; 100% confirm before sync |
| CT-05 | No | Export produces correct format; user can verify count |
| CT-06 | Yes (when implemented) | No apply without explicit confirmation |

---

## Residual Risk (After Mitigations)

| Hazard | Residual risk | Justification |
| ------ | ------------- | ------------- |
| Wrong approval (CT-01, CT-02) | Low | Confidence display, term search, reason, corrections log reduce error; training assumed |
| Accidental reset (CT-03) | Low | Confirmation modal prevents most accidents |
| Premature sync (CT-04) | Low | Button disabled until approved; confirmation |
| Wrong export (CT-05) | Negligible | Low impact; user can re-export |
| Unvalidated inference (CT-06) | N/A | Apply not in UI; when added, confirmation required |
