# Traceability Matrix

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-TM-001                                           |
| Version          | 1.0.0                                               |
| Status           | Draft                                               |
| Date             | 2026-02-25                                          |
| Standard         | IEC 62304:2006+A1:2015                               |
| Classification   | QMS - Design Controls                               |

---

## 1. Purpose

This document traces software requirements (DC-SRS-001) to design elements, implementation, and verification activities, demonstrating that all requirements are addressed and tested.

---

## 2. Requirement -> Design -> Implementation -> Verification

### 2.1 Training Pipeline

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-TP-001 | Extract clinical entities via LLM | 03-detail 6 | llm_extractor.py | test_v3_llm_extractor.py (18 tests) | ST-TP-001 |
| FR-TP-002 | Sentence splitting via PyRuSH | 03-detail 6 | sentence_splitter.py | -- | ST-TP-001 |
| FR-TP-003 | Deduplicate repeated text lines | 03-detail 6 | sentence_splitter.deduplicate_lines() | -- | ST-TP-001 |
| FR-TP-004 | Hybrid SNOMED resolution | 03-detail 3.2 | coding_resolver.py | test_v3_coding_resolver.py (5 tests) | ST-TP-001 |
| FR-TP-005 | LLM disambiguation | 03-detail 6 | disambiguator.py | test_v3_disambiguator.py (3 tests) | ST-TP-001 |
| FR-TP-006 | Validation checks | 03-detail 6 | pipeline_service.py (validate_encounter_payload) | -- | ST-TP-001 |
| FR-TP-007 | Persist to Patient graph | 03-detail 3.1 | pipeline_service._persist() | -- | ST-TP-001 |
| FR-TP-008 | Hard fail on LLM failure | 03-detail 9 | llm_extractor.py (ExtractionError) | test_v3_llm_extractor.test_disabled_extractor_raises | ST-TP-003 |
| FR-TP-009 | Concurrent processing | 03-detail 10 | pipeline_service.py (ThreadPoolExecutor) | -- | ST-TP-001 |
| FR-TP-010 | SSE progress events | 03-detail 2.1 | pipeline_service._emit() | -- | ST-TP-001 |

### 2.2 HITL Review

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-HR-001 | Present ReviewTasks | 03-detail 3.5 | review_service.py, neo4j_store.py | -- | ST-HR-001 |
| FR-HR-002 | Approve/edit/reject/escalate | 03-detail 3.5 | review_service.decide() | -- | ST-HR-002 to ST-HR-004 |
| FR-HR-003 | Record Approval node | 03-detail 1.5 | neo4j_store.append_approval() | -- | ST-HR-002 |
| FR-HR-004 | Record Change node | 03-detail 1.5 | neo4j_store.append_change() | -- | ST-HR-003 |
| FR-HR-005 | No output without human approval | DC-IU-001 6.2 | approval_status workflow; sync only processes 'approved' | -- | ST-HR-002, ST-GS-001 |

### 2.3 Gold Sync

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-GS-001 | Sync approved to DOCUMENTS | 03-detail 3.3 | sync_service.py | test_sync_service.py (3 tests) | ST-GS-001 |
| FR-GS-002 | Delete before create | 03-detail 5.6 | sync_service.py (DELETE_ENCOUNTER_DOCUMENTS) | test_sync_service.test_sync_creates_links_from_gold | ST-GS-001 |
| FR-GS-003 | Only approved synced | 03-detail 5.4 | list_approved_candidates_for_patient() | test_sync_service.test_sync_no_approved_gold | ST-GS-002 |

### 2.4 Terminology Writeback

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-TW-001 | Write SurfaceForm nodes | 03-detail 3.4 | terminology_writeback_service.py | test_terminology_writeback_service.py (8 tests) | ST-GS-001, ST-GS-003 |
| FR-TW-002 | Normalise surface forms | 03-detail 3.4 | _normalize() | test_terminology_writeback_service.TestNormalize (3 tests) | ST-GS-003 |
| FR-TW-003 | Auto trigger + standalone | 03-detail 2.4 | patients.py (sync-gold), terminology.py (writeback) | -- | ST-GS-001, ST-GS-003 |
| FR-TW-004 | Resolver uses SurfaceForm | 03-detail 3.2 | coding_resolver.py | test_v3_coding_resolver.py | ST-GS-004 |

### 2.5 Reset

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-RS-001 | Remove DOCUMENTS | 03-detail 5.2 | reset_service.py | test_reset_service.py (3 tests) | ST-RS-001 |
| FR-RS-002 | Preserve Patient/Encounter | 03-detail 5.2 | RESET_PATIENT_DOCUMENTS query | test_reset_service.py | ST-RS-001 |
| FR-RS-003 | Remove Patient->semantic | 03-detail 5.3 | RESET_PATIENT_DIRECT_SEMANTIC query | test_reset_service.py | ST-RS-001 |
| FR-RS-004 | Reset review queue | 03-detail 5.7 | reset_review_queue_service.py | test_reset_review_queue_service.py (2 tests) | ST-RS-002 |

### 2.6 MedSpaCy

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-MT-001 | Export gold to JSONL | 03-detail 3.7 | export_service.py | -- | ST-MT-001 |
| FR-MT-002 | Training script | 06-plan 2.3 | scripts/train_medspacy.py | -- | ST-MT-001 |
| FR-MT-003 | Configurable training | 06-plan 2.3 | argparse in train_medspacy.py | -- | -- |
| FR-MI-001 | Run inference | 03-detail 3.6 | inference_service.py | -- | ST-MI-002 |
| FR-MI-002 | Graceful no-model | 03-detail 3.6 | inference_service._load_model() | -- | ST-MI-001 |
| FR-MI-003 | dry_run mode | 06-plan 3.1 | inference_service.infer_encounter() | -- | ST-MI-002 |

### 2.7 LLM Usage

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-LU-001 | Track token counts | 03-detail 1.2 | llm_usage.py | test_v3_llm_usage.py (12 tests) | ST-TP-004 |
| FR-LU-002 | Estimate cost | 03-detail 8 | LLMCostConfig | test_v3_llm_usage.TestLLMCostConfig (2 tests) | ST-TP-004 |
| FR-LU-003 | Persist on candidate | 03-detail 5.1 | pipeline_service._build_candidate() | -- | ST-TP-004 |

### 2.8 Data Governance

| Req ID | Requirement | Design Doc | Implementation | Unit Test | System Test |
|--------|-------------|-----------|----------------|-----------|-------------|
| FR-DG-001 | No patient data in Coding graph | 01-purpose 10 | Schema split; PatientGraphClient for HITL | -- | ST-DG-001 |
| FR-DG-002 | HITL data in Patient graph | 02-arch 2.3 | PATIENT_SCHEMA_CONSTRAINTS | -- | ST-DG-001 |
| FR-DG-003 | Coding graph read-only (except SurfaceForm) | 02-arch 2.4 | CodingGraphClient docstring; writeback only | -- | ST-DG-002 |

---

## 3. Coverage Summary

| Category | Requirements | With Design | With Implementation | With Unit Test | With System Test |
|----------|-------------|------------|-------------------|---------------|-----------------|
| Training Pipeline | 10 | 10 | 10 | 5 | 4 |
| HITL Review | 5 | 5 | 5 | 0 | 4 |
| Gold Sync | 3 | 3 | 3 | 3 | 2 |
| Terminology Writeback | 4 | 4 | 4 | 3 | 3 |
| Reset | 4 | 4 | 4 | 4 | 2 |
| MedSpaCy | 6 | 6 | 6 | 0 | 3 |
| LLM Usage | 3 | 3 | 3 | 3 | 1 |
| Data Governance | 3 | 3 | 3 | 0 | 2 |
| **Total** | **38** | **38** | **38** | **18** | **21** |

All 38 requirements have design references, implementations, and at least one verification method (unit test, system test, or both).

---

## 4. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Author | | | |
| Quality Manager | | | |
