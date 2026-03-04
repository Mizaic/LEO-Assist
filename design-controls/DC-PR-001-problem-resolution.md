# Software Problem Resolution Process

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-PR-001                                           |
| Version          | 2.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 9                    |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document defines the process for reporting, evaluating, and resolving software problems discovered during development, testing, and operation.

---

## 2. Scope

This process applies to all problems identified in:
- Backend API service (services/api/)
- Frontend application (services/ui/)
- Scripts and tools (scripts/)
- Neo4j schema and queries
- ML models and training pipelines
- Documentation errors

---

## 3. Problem Categories

| Category | Definition | Example |
|----------|-----------|---------|
| **Critical (P0)** | Clinical safety risk; could cause catastrophic or critical harm (Severity 5-4) to patients; system unusable or data integrity at risk | Patient data in Coding graph; missing red-flag rule causing unsafe routing; sync destroys data |
| **Major (P1)** | Could lead to serious harm (Severity 3) or potential severe harm with lower occurrence; significant feature broken; safe workaround exists | Pipeline fails for specific encounter types; extraction defect systematically drops a key entity; rule logic error downgrades urgency |
| **Minor (P2)** | Minor to serious impact (Severity 2-3) with occasional or remote occurrence; user can spot and correct with current controls | Mislabelled advice text; duplicate SNOMED coding skewing analytics; UI copy causing occasional confusion |
| **Low (P3)** | Negligible to minor impact (Severity 1-2); improbable occurrence; no patient-safety consequence | Typos; cosmetic UI defects; non-blocking audit/reporting mismatch |
| **Enhancement** | Not a defect; improvement request | Better error messages; performance optimisation |

---

## 4. Problem Resolution Workflow

### 4.1 Report

1. Problem discovered (user report, testing, monitoring, code review)
2. Create Jira ticket with:
   - Title (concise description)
   - Category (P0 / P1 / P2 / P3 / Enhancement)
   - Steps to reproduce
   - Expected vs actual behaviour
   - Environment details
   - Screenshots or logs if applicable

### 4.2 Triage

1. Assign category and priority
2. Assess safety impact:
   - Could this problem affect patient safety? (For Class B: indirect harm via incorrect audit data is possible)
   - Could this problem affect data governance (FR-DG-001 to FR-DG-003)?
   - Could this problem affect audit data accuracy?
3. Assign to developer
4. Set target resolution timeframe per DC-SMP-001 Non-conformance SLAs:

| Category | Target |
|----------|--------|
| Critical (P0) | 24 hours to remediate (temporary mitigation ASAP) |
| Major (P1) | 7 days |
| Minor (P2) | 30 days |
| Low (P3) | 90 days |
| Enhancement | Backlog (next scheduled release) |

### 4.3 Investigate

1. Reproduce the problem
2. Identify root cause
3. Determine scope of impact
4. Assess if the problem affects released software

### 4.4 Resolve

1. Implement fix on feature/fix branch
2. Write or update tests to prevent regression
3. Update documentation if needed
4. Update risk register (DC-RM-001) if the problem reveals a new hazard
5. Code review via pull request

### 4.5 Verify

1. Run unit tests (all 58+ must pass)
2. Verify the specific problem is resolved
3. Run regression tests if applicable
4. Update Jira ticket with resolution details

### 4.6 Close

1. Mark Jira ticket as resolved
2. Include in release notes
3. Update traceability matrix if new tests added

---

## 5. Escalation

| Condition | Escalation |
|-----------|-----------|
| P0 problem in released software | Notify Quality Manager and Clinical Lead immediately; temporary mitigation ASAP |
| Problem reveals data governance breach | Notify Clinical Lead and Quality Manager |
| Security vulnerability (Critical/High) | Follow Security Vulnerability SLAs (DC-SMP-001 Section 8) |
| Problem cannot be resolved within SLA | Escalate to project lead for reprioritisation |
| Problem reveals safety classification change | Trigger reclassification review (DC-SC-001 Section 6) |

---

## 6. Records

All problem reports and resolutions are maintained in:
- **Jira**: Primary defect and issue tracking system
- **Git history**: Code changes linked to Jira tickets
- **Release notes**: Summary of resolved problems per release

---

## 7. Trend Analysis

Quarterly review of problem reports to identify:
- Recurring problem patterns
- Components with highest defect rates
- SOUP-related issues
- Process improvement opportunities

---

## 8. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |

---

## 9. Resolved Problem Records

Formal records of resolved software problems, maintained here for IEC 62304 Clause 9 traceability in conjunction with the Jira ticket system.

| ID | Category | Title | Root Cause | Fix Reference | Status | Date Resolved |
|----|----------|-------|-----------|--------------|--------|---------------|
| PR-2026-003 | P1 (Major) | Model inference `/reload` 500 error on startup — race condition in `ModelLoader.load_version()` | Concurrent lifespan handler + `_signal_reload()` both attempted Azure Blob download for the same model version, causing file-system collision and `BlobNotFound`. Absence of a serialisation lock meant two threads could enter the download path simultaneously. | DO-LEO-AI-033 (`services/model_inference/app/model_loader.py`, `services/model_inference/app/main.py`) | Closed | 2026-03-03 |

### PR-2026-003 Detail

| Field | Value |
|-------|-------|
| **ID** | PR-2026-003 |
| **Category** | P1 — Major |
| **Reported** | 2026-03-03 |
| **Resolved** | 2026-03-03 |
| **Affected component** | `services/model_inference` — `ModelLoader`, `/reload` endpoint |
| **Symptom** | `POST /reload HTTP/1.1" 500 Internal Server Error`; `BlobNotFound` from Azure Storage SDK |
| **Steps to reproduce** | 1. Start `model_inference` service cold with a canary model version set in Neo4j. 2. Immediately (within ~2 s of startup) trigger a `POST /reload` for the same version. |
| **Root cause** | `ModelLoader.load_version()` had no mutual-exclusion lock. Two concurrent callers (lifespan handler + `/reload` handler) could both pass the `_active_version != version` guard, then both attempt to download and extract `model.tar.gz` from Azure Blob Storage. The second download arrived while the first extraction was still writing to the temp directory, causing the Azure SDK to report the blob as inaccessible and subsequent extraction to fail. |
| **Safety impact** | None direct — model inference service was unavailable for the startup window only; no patient coding requests were served during the failed state. Audit trail unaffected. |
| **Fix** | (1) Added `_load_lock = threading.Lock()` to `ModelLoader.__init__`. `load_version()` now acquires `_load_lock` before any download attempt, serialising concurrent callers. An idempotency re-check inside the lock means the second caller exits early if the first already completed the load. (2) Added an HTTP-layer fast-path to `POST /reload`: if `_loader.active_version == req.version`, the endpoint returns immediately without spawning a background task. |
| **Tests** | VT-LEO-AI-038 (model hot-swap); PR regression test added to `tests/test_model_reload_race.py` (pending — see VT-LEO-AI-038 execution schedule) |
| **Risk register** | No new hazard identified; residual risk is acceptable per existing risk controls. |
| **Design output** | DO-LEO-AI-033 |
| **Closed by** | Engineering |
