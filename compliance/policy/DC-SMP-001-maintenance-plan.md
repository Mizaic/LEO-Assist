# Software Maintenance Plan


| Field          | Value                            |
| -------------- | -------------------------------- |
| Document ID    | DC-SMP-001                       |
| Version        | 2.0.0                            |
| Status         | Draft                            |
| Date           | 2026-02-25                       |
| Standard       | IEC 62304:2006+A1:2015, Clause 6 |
| Classification | QMS - Design Controls            |


---

## 1. Purpose

This document defines the software maintenance plan for the NLP Training and Inference Pipeline in accordance with IEC 62304 Clause 6.

---

## 2. Scope

Maintenance covers:

- Corrective maintenance (bug fixes)
- Adaptive maintenance (environment changes, dependency updates)
- Perfective maintenance (performance, usability improvements)
- Preventive maintenance (security patches, SOUP updates)

---

## 3. Feedback Sources


| Source                     | Channel                              | Response                                               |
| -------------------------- | ------------------------------------ | ------------------------------------------------------ |
| User-reported defects      | Jira                                 | Triage within 5 business days                          |
| SOUP security advisories   | CVE databases, GitHub Dependabot     | Per Security Vulnerability SLAs (Section 8)            |
| Terminology updates        | TRUD / UMLS release notifications    | Schedule update within 30 days                         |
| Clinical accuracy feedback | HITL review corrections              | Captured via terminology writeback; reviewed quarterly |
| Performance issues         | Operational monitoring, user reports | Assess and prioritise                                  |


---

## 4. Maintenance Activities

### 4.1 Regular Activities


| Activity                     | Frequency                   | Owner       |
| ---------------------------- | --------------------------- | ----------- |
| SOUP vulnerability scan      | Quarterly                   | Development |
| Dependency update review     | Quarterly                   | Development |
| SNOMED UK terminology update | Per TRUD release (biannual) | Operations  |
| UMLS update                  | Per NLM release (biannual)  | Operations  |
| Neo4j version review         | Annual                      | Development |
| Risk register review         | Annual or on change         | Quality     |
| Backup verification          | Monthly                     | Operations  |


### 4.2 Triggered Activities


| Trigger                                                    | Activity                                                           |
| ---------------------------------------------------------- | ------------------------------------------------------------------ |
| Critical CVE in SOUP component                             | Immediate assessment; remediate per Security Vulnerability SLAs (Section 8) |
| User-reported defect (Jira ticket)                         | Log in problem resolution (DC-PR-001); fix based on severity       |
| New SNOMED release                                         | Load terminology; regression test against gold; update DC-SOUP-001 |
| Model retraining needed                                    | Export gold; run train_medspacy.py; validate F1; deploy            |
| Safety classification review trigger (DC-SC-001 Section 6) | Re-assess classification; update documentation                     |


---

## 5. Change Impact Assessment

Before any maintenance change:

1. Identify affected components (code, configuration, SOUP, documentation)
2. Assess impact on safety classification (DC-SC-001)
3. Assess risk impact (DC-RM-001)
4. Determine required testing (regression, system, or unit)
5. Update documentation as needed
6. Follow change control process (DC-CM-001 Section 4)

---

## 6. MedSpaCy Model Maintenance

The MedSpaCy model is a key component that improves over time:


| Activity          | Trigger                                                      | Process                                                       |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------------------- |
| Retrain NER model | New gold data available (>50 additional approved encounters) | Export gold; train; validate F1 >= 0.90; deploy               |
| Validate model    | Terminology update or model retrain                          | Dry-run comparison against gold set                           |
| Retire model      | F1 drops below 0.85 after terminology change                 | Revert to LLM-only pipeline; retrain with updated terminology |


---

## 7. Terminology Writeback Maintenance

The learning loop (SurfaceForm writeback) requires monitoring:


| Check                    | Frequency                | Action                                                  |
| ------------------------ | ------------------------ | ------------------------------------------------------- |
| SurfaceForm count growth | Quarterly                | Review growth rate; spot-check quality                  |
| SurfaceForm accuracy     | Quarterly                | Sample 50 SurfaceForm nodes; verify mapping correctness |
| Resolver performance     | After terminology update | Run benchmark queries; compare resolution rates         |


---

## 8. Security Vulnerability Service Level Objectives

SLAs are measured from the point the fix becomes available.

| Priority | SLA | Definition | Examples |
|----------|-----|-----------|----------|
| **Critical** | 24 hours | Vulnerabilities that cause privilege escalation from unprivileged to admin, allow remote code execution, financial theft, or unauthorised access to/extraction of sensitive data | Remote Code Execution, Vertical Authentication bypass, SSRF, XXE, SQL Injection, User authentication bypass |
| **High** | 7 days | Vulnerabilities that affect the security of the platform including the processes it supports | Lateral authentication bypass, Stored XSS, some CSRF depending on impact |
| **Medium** | 30 days | Vulnerabilities that affect multiple users and require little or no user interaction to trigger | Reflective XSS, Direct object reference, URL Redirect, some CSRF depending on impact |
| **Low** | 90 days | Issues that affect singular users and require interaction or significant prerequisites (MitM) to trigger | Common flaws, Debug information, Mixed Content |

---

## 9. Non-conformance Service Level Objectives

SLAs are measured from the point the fix becomes available.

| Priority | SLA | Definition | Examples |
|----------|-----|-----------|----------|
| **P0 - Critical clinical safety** | 24 hours to remediate (temporary mitigation ASAP) | Any defect/change that could cause catastrophic or critical harm (Severity 5-4) to one or more patients OR any issue with confirmed harm. Includes high-likelihood mis-triage/signposting to unsafe setting, missed red-flag routing, or contraindicated advice. | Missing red-flag rule causing suspected cancer not to route to 2WW; misclassification that sends chest-pain to routine backlog; allergy/contraindication not surfaced leading to unsafe advice; corrupted guideline mapping for time-critical pathways (e.g., stroke, sepsis). |
| **P1 - High** | 7 days | Could lead to serious harm (Severity 3) or potential severe harm (Severity 4) but with lower occurrence/detected early; affects multiple patients or a common pathway; safe workaround exists with controls. | Rule logic error that downgrades urgency for a subset of presentations (e.g., GI bleed without haemodynamic flags); extraction defect that systematically drops a key symptom entity impacting a popular pathway; incorrect threshold in risk score that nudges many cases to less urgent triage but not time-critical. |
| **P2 - Medium** | 30 days | Minor to serious impact (Severity 2-3) with occasional or remote occurrence, typically needs specific preconditions; user can spot and correct with current controls; does not change urgent/critical routing. | Mislabelled advice text that doesn't alter disposition; duplicate/non-critical SNOMED coding that slightly skews analytics; UI copy leading to occasional data entry confusion but no mis-triage. |
| **P3 - Low** | 90 days | Negligible to minor impact (Severity 1-2), improbable occurrence, requires significant prerequisites or manual interaction; no patient-safety consequence. | Typos; cosmetic UI defects; non-blocking audit/reporting mismatch; rare mixed content in non-clinical help text. |

---

## 10. Release and Deployment Schedule

HCCP operates a **continuous deployment** model. Production releases are scheduled on the **5th of every month**, with changes promoted as soon as they meet quality, safety, and governance checks for inclusion in that month's deployment.

| Release Type | Schedule | Governance |
|-------------|----------|-----------|
| Scheduled production release | 5th of every month | All changes must pass quality, safety, and governance checks |
| Emergency hotfix (P0 / Critical security) | Within SLA window (24 hours) | Expedited review; post-release retrospective |
| Terminology update | Per TRUD/UMLS release schedule | Regression tested against gold set before deployment |
| MedSpaCy model update | As needed (>50 new gold encounters) | F1 >= 0.90 validation before deployment |

---

## 11. Records

Maintenance activities shall be recorded in:

- Jira (user-reported defects, feature requests)
- Git commit history (code changes)
- Design control document versions (documentation changes)
- DC-PR-001 (problem resolution records)

---

## 12. Approval


| Role            | Name | Date | Signature |
| --------------- | ---- | ---- | --------- |
| Author          |      |      |           |
| Quality Manager |      |      |           |


