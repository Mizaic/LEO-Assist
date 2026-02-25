# Software Integration Test Plan

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-ITP-001                                          |
| Version          | 1.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015, Clause 5.6                  |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document defines the integration test plan for the NLP Training and Inference Pipeline, as required by IEC 62304 Clause 5.6 for Class B software.

Integration testing verifies that software units interact correctly with each other and with external interfaces when combined into larger aggregates.

---

## 2. Scope

This plan covers integration between:
- Internal software components (pipeline stages, services, routers)
- Software and database interfaces (Patient graph, Coding graph)
- Software and external services (AWS Bedrock LLM)
- Backend API and frontend application
- Training pipeline and inference pipeline (via shared gold data)

---

## 3. Integration Strategy

The project uses a **bottom-up** integration strategy:

1. **Unit level** - Individual components verified in isolation (58+ unit tests, mocked dependencies)
2. **Component integration** - Components combined and tested against real or emulated external interfaces
3. **Subsystem integration** - Backend API, database, and LLM service tested together
4. **System integration** - Full stack including frontend verified end-to-end

Integration proceeds incrementally: each pipeline stage is integrated and tested before adding the next.

---

## 4. Test Environment

| Item | Configuration |
|------|--------------|
| Python | 3.12 |
| Neo4j | 5.x Community Edition (two instances: Patient + Coding) |
| AWS Bedrock | Live for integration tests; mocked for CI |
| Test runner | pytest |
| Test data | Controlled set of known encounters with expected outputs |

---

## 5. Integration Test Cases

### 5.1 Pipeline Stage Integration

These tests verify that output from one pipeline stage is correctly consumed by the next.

| ID | Integration Point | Components | Steps | Expected Result | Req Trace |
|----|-------------------|------------|-------|-----------------|-----------|
| IT-PI-001 | Text preparation to LLM extraction | `SentenceSplitter` -> `LLMExtractor` | Provide raw encounter text; verify splitter output is accepted by extractor | ExtractedTerms returned with correct sentence indices; no data loss between stages | FR-TP-001, FR-TP-002, FR-TP-003 |
| IT-PI-002 | LLM extraction to coding resolution | `LLMExtractor` -> `CodingResolver` | Provide extracted terms; verify resolver receives all terms and returns candidates | Each extracted term has SNOMED candidates; lookup_term and expected_tags passed correctly | FR-TP-004, FR-TP-005 |
| IT-PI-003 | Coding resolution to disambiguation | `CodingResolver` -> `CodingDisambiguator` | Provide resolver output; verify disambiguator selects best candidate for each term | Each term has exactly one selected candidate with score and rationale | FR-TP-005 |
| IT-PI-004 | Disambiguation to persistence | `CodingDisambiguator` -> `PatientGraphWriter` | Provide disambiguated results; verify EncounterCandidate written to Patient graph | EncounterCandidate node exists with correct structure; ReviewTask created | FR-TP-006, FR-TP-009 |
| IT-PI-005 | LLM usage accumulation | `LLMExtractor` + `CodingDisambiguator` -> `pipeline_service._process_encounter` | Run pipeline on 1 encounter | llm_usage_json on EncounterCandidate contains summed tokens from both extraction and disambiguation calls | FR-LU-001, FR-LU-002, FR-LU-003 |

### 5.2 Database Integration

These tests verify correct interaction between the application and Neo4j databases.

| ID | Integration Point | Components | Steps | Expected Result | Req Trace |
|----|-------------------|------------|-------|-----------------|-----------|
| IT-DB-001 | Patient graph schema initialisation | `PatientGraphClient` + `PATIENT_SCHEMA_CONSTRAINTS` | Call initialize_schema() on Patient graph | All constraints and indexes created; no errors | FR-DG-001 |
| IT-DB-002 | Coding graph schema initialisation | `CodingGraphClient` + `CODING_SCHEMA_CONSTRAINTS` | Call initialize_schema() on Coding graph | All constraints, fulltext index, and SurfaceForm index created | FR-DG-002 |
| IT-DB-003 | EncounterCandidate write + read | `PatientGraphWriter` -> `ReviewService` | Write candidate via writer; read back via review service | Data round-trips correctly; all fields preserved including llm_usage_json | FR-TP-009, FR-HR-001 |
| IT-DB-004 | Approval write + sync read | `ReviewService` -> `SyncService` | Approve candidate; then sync patient | Sync reads only approved candidates; creates correct DOCUMENT structure | FR-HR-003, FR-GS-001 |
| IT-DB-005 | SurfaceForm writeback to Coding graph | `TerminologyWritebackService` -> Coding graph | Write approved terms; query Coding graph | SurfaceForm nodes exist with correct surface_form, concept_id, source; linked to Term nodes | FR-TW-001, FR-TW-002, FR-TW-003 |
| IT-DB-006 | SurfaceForm consumed by resolver | `CodingResolver` + SurfaceForm nodes | Add SurfaceForm; resolve same surface text | SurfaceForm result appears in candidates with 1.2x boost | FR-TW-004 |
| IT-DB-007 | Reset removes HITL data | `ResetReviewQueueService` -> Patient graph | Create candidates, tasks, approvals; reset; query | All HITL nodes removed; Patient and Encounter preserved | FR-RS-004 |

### 5.3 Cross-Graph Data Governance

These tests verify the architectural separation between Patient and Coding graphs.

| ID | Integration Point | Components | Steps | Expected Result | Req Trace |
|----|-------------------|------------|-------|-----------------|-----------|
| IT-DG-001 | Pipeline writes only to Patient graph | Full pipeline + both graphs | Run pipeline on 1 patient; query Coding graph | No EncounterCandidate, ReviewTask, Approval, or Change nodes in Coding graph | FR-DG-001, FR-DG-002 |
| IT-DG-002 | Writeback writes only SurfaceForm to Coding graph | `TerminologyWritebackService` + Coding graph | Run writeback; query Coding graph for all node labels | Only Term, Concept, ReadCode, SurfaceForm, and terminology infrastructure nodes present | FR-DG-003 |
| IT-DG-003 | No patient_id in Coding graph | Full pipeline + writeback | Run pipeline and writeback; search Coding graph for any patient_id property | Zero results | FR-DG-001 |

### 5.4 External Service Integration

These tests verify interaction with external services.

| ID | Integration Point | Components | Steps | Expected Result | Req Trace |
|----|-------------------|------------|-------|-----------------|-----------|
| IT-EX-001 | AWS Bedrock LLM extraction | `LLMExtractor` -> AWS Bedrock | Send real encounter text to Bedrock | Valid JSON response matching ExtractedTerm schema; LLMUsage populated | FR-TP-002, FR-LU-001 |
| IT-EX-002 | AWS Bedrock LLM disambiguation | `CodingDisambiguator` -> AWS Bedrock | Send candidates for disambiguation | Valid JSON response; one candidate selected per term; LLMUsage populated | FR-TP-005, FR-LU-001 |
| IT-EX-003 | LLM hard fail on error | `LLMExtractor` with invalid credentials | Attempt extraction | ExtractionError raised; no fallback to regex; clear error message | FR-TP-008 |
| IT-EX-004 | Neo4j hybrid search (exact + fulltext + vector) | `CodingResolver` -> Coding graph | Resolve a term using all three search methods | Results returned from all available methods; scores normalised and fused | FR-TP-004 |

### 5.5 Frontend-Backend Integration

These tests verify the API contract between frontend and backend.

| ID | Integration Point | Components | Steps | Expected Result | Req Trace |
|----|-------------------|------------|-------|-----------------|-----------|
| IT-FE-001 | Patient list with progress | Frontend `fetchPatients` -> `GET /patients` | Load patient list page | Patients displayed with encounter_count, reviewed_count, progress | FR-HR-001 |
| IT-FE-002 | Review task load | Frontend `ReviewView` -> `GET /review/tasks/{id}` | Open review task | EncounterCandidate displayed with sentences, terms, SNOMED candidates; llm_usage_json parsed and shown | FR-HR-002 |
| IT-FE-003 | Sync gold with writeback | Frontend `EncounterList` -> `POST /patients/{id}/sync-gold` | Click sync button | Response includes encounters_synced, links_created, surface_forms_written; success message displayed | FR-GS-001, FR-TW-001 |
| IT-FE-004 | Pipeline SSE stream | Frontend -> `GET /pipeline/run` (SSE) | Start pipeline; observe SSE events | Events received: encounter_start, extraction_complete, coding_complete, encounter_complete | FR-TP-010 |

### 5.6 Training-Inference Integration

These tests verify the data flow from gold export through model training to inference.

| ID | Integration Point | Components | Steps | Expected Result | Req Trace |
|----|-------------------|------------|-------|-----------------|-----------|
| IT-TI-001 | Export to training script | `ExportService` -> `train_medspacy.py` | Export training data; verify format consumable by training script | entities.jsonl and kb.jsonl parse correctly; all required fields present | FR-MT-001, FR-MT-003 |
| IT-TI-002 | Trained model to inference service | `train_medspacy.py` -> `InferenceService` | Train model; load in inference service; run inference | Model loads without error; entities returned with spans and linked concept IDs | FR-MI-001, FR-MI-002 |

---

## 6. Integration Test Execution Order

Tests should be executed in the following order to ensure dependencies are satisfied:

1. **Database integration** (IT-DB-001, IT-DB-002) - schemas initialised
2. **Pipeline stage integration** (IT-PI-001 through IT-PI-005) - verify pipeline data flow
3. **External service integration** (IT-EX-001 through IT-EX-004) - verify LLM and search
4. **Cross-graph governance** (IT-DG-001 through IT-DG-003) - verify data separation
5. **Frontend-backend integration** (IT-FE-001 through IT-FE-004) - verify API contract
6. **Training-inference integration** (IT-TI-001, IT-TI-002) - verify ML pipeline
7. **Remaining database integration** (IT-DB-003 through IT-DB-007) - verify read-back and round-trip

---

## 7. Existing Integration Coverage

Several existing unit tests already provide partial integration coverage through realistic mocking:

| Test File | Integration Aspect Covered |
|-----------|--------------------------|
| test_v3_coding_resolver.py | Hybrid search query construction (5 tests) |
| test_v3_llm_extractor.py | LLM prompt/response parsing (18 tests) |
| test_v3_llm_usage.py | Usage accumulation and cost calculation (12 tests) |
| test_terminology_writeback_service.py | Writeback query construction and normalisation (8 tests) |
| test_sync_service.py | Sync query construction (3 tests) |
| test_reset_review_queue_service.py | Reset query construction (2 tests) |
| test_v3_disambiguator.py | Disambiguation prompt/response parsing (3 tests) |
| test_v3_patient_graph_writer.py | Persistence query construction (4 tests) |
| test_reset_service.py | Reset query construction (3 tests) |

These tests use mocked database sessions but verify correct query parameters and data transformations.

---

## 8. Pass/Fail Criteria

- All integration test cases pass
- No data governance violations (IT-DG-001 through IT-DG-003)
- External service interactions return expected data formats
- Data round-trips through the system without loss or corruption
- Integration tests must pass before system testing (DC-STP-001) begins

---

## 9. Defect Handling

Integration defects shall be:
1. Logged per DC-PR-001 (Problem Resolution Process)
2. Triaged for severity and impact on integration
3. Root-caused to the originating component(s)
4. Fixed and re-verified before integration testing continues

---

## 10. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
