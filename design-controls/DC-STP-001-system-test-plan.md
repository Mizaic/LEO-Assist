# Software System Test Plan

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-STP-001                                          |
| Version          | 1.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 5.7                  |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document defines the system-level test plan for the NLP Training and Inference Pipeline. System tests verify that the integrated system meets the requirements specified in DC-SRS-001.

---

## 2. Test Environment

| Item | Configuration |
|------|--------------|
| Python | 3.12 |
| Neo4j | 5.x Community Edition (Patient graph + Coding graph) |
| AWS Bedrock | Live (or mocked for CI) |
| Browser | Chrome/Edge latest |
| OS | Windows 10+ or Linux |

---

## 3. Pre-conditions

- Both Neo4j instances running and accessible
- Terminology data loaded in Coding graph (SNOMED UK Clinical Edition)
- At least one patient with encounters loaded in Patient graph
- API service running (`uvicorn app.main:app`)
- Frontend running (`npm run dev` in services/ui)
- Environment variables configured (secrets/.env)

---

## 4. System Test Cases

### 4.1 Training Pipeline

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-TP-001 | Run pipeline on single patient | POST /pipeline/run with 1 patient, max_encounters=5 | EncounterCandidates created in Patient graph; ReviewTasks created; SSE events streamed | FR-TP-001 to FR-TP-010 |
| ST-TP-002 | Run pipeline dry run | POST /pipeline/run with dry_run=true | Stats returned; no EncounterCandidates persisted | FR-TP-007 |
| ST-TP-003 | Pipeline LLM failure | Run with invalid AWS credentials | ExtractionError raised; no regex fallback; encounter_error SSE event | FR-TP-008 |
| ST-TP-004 | LLM usage tracked | Run pipeline on 1 encounter | llm_usage_json populated on EncounterCandidate with token counts and cost | FR-LU-001 to FR-LU-003 |

### 4.2 HITL Review

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-HR-001 | List review tasks | GET /review/tasks | Tasks listed with status, priority, patient_id | FR-HR-001 |
| ST-HR-002 | Review and approve | GET /review/tasks/{id} then POST decision (approve) | Approval node created; status = approved | FR-HR-002, FR-HR-003 |
| ST-HR-003 | Review and edit | POST decision (edit) with edited_candidate | Change node created; candidate updated | FR-HR-002, FR-HR-004 |
| ST-HR-004 | Review and reject | POST decision (reject) | Status = rejected; Approval node created | FR-HR-002 |

### 4.3 Gold Sync + Writeback

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-GS-001 | Sync approved gold | Approve at least 1 candidate; POST /patients/{id}/sync-gold | DOCUMENTS created in Patient graph; surface_forms_written > 0 | FR-GS-001 to FR-GS-003, FR-TW-001 to FR-TW-003 |
| ST-GS-002 | Sync with no approvals | POST /patients/{id}/sync-gold (no approved candidates) | 400 error with message | FR-GS-003 |
| ST-GS-003 | Standalone writeback | POST /terminology/writeback | SurfaceForm nodes in Coding graph | FR-TW-001, FR-TW-003 |
| ST-GS-004 | Resolver uses SurfaceForm | After writeback, re-run pipeline on text containing a written-back surface form | SurfaceForm result appears with boosted score | FR-TW-004 |

### 4.4 Reset

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-RS-001 | Reset patient DOCUMENTS | POST /patients/{id}/reset | DOCUMENTS removed; Patient and Encounter preserved | FR-RS-001, FR-RS-002 |
| ST-RS-002 | Reset review queue | POST /patients/{id}/reset-review-queue | EncounterCandidates, ReviewTasks, Approvals, Changes removed | FR-RS-004 |

### 4.5 Data Governance

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-DG-001 | No patient data in Coding graph | Run pipeline; query Coding graph for EncounterCandidate or patient_id | No results; Coding graph contains only Term, Concept, ReadCode, SurfaceForm | FR-DG-001, FR-DG-002 |
| ST-DG-002 | Coding graph read-only | Verify no app code writes HITL data to Coding graph | Only SurfaceForm writeback writes to Coding graph | FR-DG-003 |

### 4.6 MedSpaCy Export and Inference

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-MT-001 | Export training data | POST /exports/medspacy-training | entities.jsonl and kb.jsonl created with correct format | FR-MT-001 |
| ST-MI-001 | Inference without model | POST /patients/{id}/encounters/{eid}/infer | entities: [], message: "MedSpaCy model not yet built..." | FR-MI-002 |
| ST-MI-002 | Inference with model | Train model; POST infer with dry_run=true | Entities returned with spans and labels | FR-MI-001, FR-MI-003 |

### 4.7 End-to-End Happy Path

| ID | Test | Steps | Expected Result | Req Trace |
|----|------|-------|-----------------|-----------|
| ST-E2E-001 | Full user journey | 1. Reset patient 2. Run pipeline 3. Review and approve 4. Sync gold 5. View coded encounters 6. Export training data | Each step succeeds; DOCUMENTS match gold; export contains approved data | All FR |

---

## 5. Unit Test Summary

Unit tests are maintained in `services/api/tests/` and provide the following coverage:

| Test File | Tests | Components Covered |
|-----------|-------|--------------------|
| test_sync_service.py | 3 | SyncService |
| test_v3_disambiguator.py | 3 | CodingDisambiguator |
| test_v3_patient_graph_writer.py | 4 | PatientGraphWriter |
| test_reset_review_queue_service.py | 2 | ResetReviewQueueService |
| test_reset_service.py | 3 | ResetService |
| test_v3_coding_resolver.py | 5 | CodingResolver (hybrid) |
| test_v3_llm_usage.py | 12 | LLMUsage, LLMCostConfig |
| test_terminology_writeback_service.py | 8 | TerminologyWritebackService |
| test_v3_llm_extractor.py | 18 | LLMExtractor |

**Total: 58 unit tests**

Run command: `python -m pytest services/api/tests/ -v`

---

## 6. Integration Testing

Integration testing is documented separately in **DC-ITP-001** (Integration Test Plan), as required by IEC 62304 Clause 5.6 for Class B software. DC-ITP-001 covers:

- Cross-component integration between pipeline stages
- Patient graph / Coding graph data flow separation
- API-to-database round-trip verification
- External interface integration (AWS Bedrock, Neo4j)

Integration tests must pass before system testing begins.

---

## 7. Pass/Fail Criteria

- All unit tests pass (58/58)
- All integration tests pass (DC-ITP-001)
- All system test cases pass
- No critical defects open
- Data governance tests pass (ST-DG-001, ST-DG-002)

---

## 8. Test Reporting

Test results shall be recorded with:
- Date of execution
- Test environment details
- Pass/fail for each test case
- Defect IDs for any failures
- Tester name

---

## 9. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
