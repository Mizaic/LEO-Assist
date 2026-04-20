# Software Requirements Specification


| Field          | Value                              |
| -------------- | ---------------------------------- |
| Document ID    | DC-SRS-001                         |
| Version        | 1.0.0                              |
| Status         | Draft                              |
| Date           | 2026-02-25                         |
| Standard       | IEC 62304:2006+A1:2015, Clause 5.2 |
| Classification | QMS - Design Controls              |


---

## 1. Purpose

This document specifies the software requirements for the NLP Training and Inference Pipeline subsystem of the Primary Care Clinical Pathway Audit Platform.

Requirements are traced forward to design (docs/nlp-pipeline/) and verification (DC-TM-001).

---

## 2. Definitions


| Term               | Definition                                                                         |
| ------------------ | ---------------------------------------------------------------------------------- |
| EncounterCandidate | A de-identified encounter with extracted clinical terms, pending human review      |
| ReviewTask         | A HITL work item linked to an EncounterCandidate                                   |
| DOCUMENTS          | A relationship in the Patient graph linking an Encounter to a coded SNOMED concept |
| SurfaceForm        | A human-approved surface text -> SNOMED concept mapping in the Coding graph        |
| Gold               | EncounterCandidates that have been approved by a human reviewer                    |
| HITL               | Human-in-the-loop review workflow                                                  |


---

## 3. Functional Requirements

### 3.1 Training Pipeline (LLM)


| ID        | Requirement                                                                                                  | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------------------------------------ | -------- | ------------- |
| FR-TP-001 | The system shall extract clinical entities from de-identified GP encounter text using LLM (AWS Bedrock)      | Must     | 02-arch 2.1   |
| FR-TP-002 | The system shall split encounter text into sentences using PyRuSH clinical sentence splitter                 | Must     | 03-detail 6   |
| FR-TP-003 | The system shall deduplicate repeated text lines before extraction                                           | Must     | 03-detail 6   |
| FR-TP-004 | The system shall resolve extracted terms to SNOMED CT concepts using hybrid search (exact, fulltext, vector) | Must     | 03-detail 3.2 |
| FR-TP-005 | The system shall disambiguate multiple SNOMED candidates using LLM when needed                               | Must     | 03-detail 6   |
| FR-TP-006 | The system shall validate each EncounterCandidate against schema, context, and ontology rules                | Must     | 03-detail 6   |
| FR-TP-007 | The system shall persist EncounterCandidate and ReviewTask to the Patient graph                              | Must     | 03-detail 3.1 |
| FR-TP-008 | The system shall hard-fail (ExtractionError) on LLM failure with no fallback to regex                        | Must     | 03-detail 9   |
| FR-TP-009 | The system shall support concurrent processing of encounters via ThreadPoolExecutor (1-8 workers)            | Should   | 03-detail 10  |
| FR-TP-010 | The system shall stream progress events via SSE during pipeline execution                                    | Should   | 03-detail 2.1 |


### 3.2 HITL Review


| ID        | Requirement                                                                                                   | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------------------------------------- | -------- | ------------- |
| FR-HR-001 | The system shall present EncounterCandidates to reviewers as ReviewTasks                                      | Must     | 03-detail 3.5 |
| FR-HR-002 | Reviewers shall be able to approve, edit, reject, or escalate each task                                       | Must     | 03-detail 3.5 |
| FR-HR-003 | The system shall record each review decision as an Approval node with reviewer, action, reason, and timestamp | Must     | 03-detail 1.5 |
| FR-HR-004 | The system shall record all edits as Change nodes for audit trail                                             | Must     | 03-detail 1.5 |
| FR-HR-005 | No AI-generated output shall be accepted as final without human approval                                      | Must     | DC-IU-001 6.2 |


### 3.3 Gold Sync


| ID        | Requirement                                                                                            | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------------------------------ | -------- | ------------- |
| FR-GS-001 | The system shall sync approved EncounterCandidates to Patient graph DOCUMENTS on explicit user request | Must     | 03-detail 3.3 |
| FR-GS-002 | Sync shall delete existing DOCUMENTS for each encounter before creating new ones                       | Must     | 03-detail 5.6 |
| FR-GS-003 | Only candidates with approval_status = 'approved' shall be synced                                      | Must     | 03-detail 5.4 |


### 3.4 Terminology Writeback


| ID        | Requirement                                                                                              | Priority | Trace         |
| --------- | -------------------------------------------------------------------------------------------------------- | -------- | ------------- |
| FR-TW-001 | The system shall write approved surface-form -> SNOMED mappings to the Coding graph as SurfaceForm nodes | Must     | 03-detail 3.4 |
| FR-TW-002 | SurfaceForm text shall be normalised (lowercase, punctuation stripped) for deduplication                 | Must     | 03-detail 3.4 |
| FR-TW-003 | Writeback shall be triggered automatically after sync-gold and available as a standalone endpoint        | Must     | 03-detail 2.4 |
| FR-TW-004 | The resolver shall use SurfaceForm nodes in exact and fulltext search with a score boost                 | Should   | 03-detail 3.2 |


### 3.5 Reset


| ID        | Requirement                                                                                                         | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------------------------------------------- | -------- | ------------- |
| FR-RS-001 | The system shall remove all DOCUMENTS for a patient's encounters on explicit user request                           | Must     | 03-detail 5.2 |
| FR-RS-002 | Reset shall preserve Patient, Encounter, and text data                                                              | Must     | 03-detail 5.2 |
| FR-RS-003 | The system shall remove Patient -> semantic node direct relationships during reset                                  | Must     | 03-detail 5.3 |
| FR-RS-004 | The system shall support resetting the review queue (removing EncounterCandidates, ReviewTasks, Approvals, Changes) | Must     | 03-detail 5.7 |


### 3.6 MedSpaCy Training


| ID        | Requirement                                                                                                  | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------------------------------------ | -------- | ------------- |
| FR-MT-001 | The system shall export approved gold to spaCy NER training format (entities.jsonl) and KB format (kb.jsonl) | Must     | 03-detail 3.7 |
| FR-MT-002 | A training script shall consume exported JSONL and produce a trained spaCy NER model + KnowledgeBase         | Must     | 06-plan 2.3   |
| FR-MT-003 | The training script shall support configurable epochs, batch size, eval split, and dropout                   | Should   | 06-plan 2.3   |


### 3.7 MedSpaCy Inference


| ID        | Requirement                                                                                 | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------------------- | -------- | ------------- |
| FR-MI-001 | The system shall run spaCy NER inference on encounter text and return entity predictions    | Must     | 03-detail 3.6 |
| FR-MI-002 | The system shall gracefully handle the absence of a trained model (return guidance message) | Must     | 03-detail 3.6 |
| FR-MI-003 | Inference shall support dry_run mode (no writes to Patient graph)                           | Must     | 06-plan 3.1   |


### 3.8 LLM Usage Tracking


| ID        | Requirement                                                                     | Priority | Trace         |
| --------- | ------------------------------------------------------------------------------- | -------- | ------------- |
| FR-LU-001 | The system shall track input, output, and cached token counts for each LLM call | Must     | 03-detail 1.2 |
| FR-LU-002 | The system shall estimate cost per encounter using configurable cost rates      | Must     | 03-detail 8   |
| FR-LU-003 | LLM usage shall be persisted on each EncounterCandidate as llm_usage_json       | Must     | 03-detail 5.1 |


---

## 4. Data Governance Requirements


| ID        | Requirement                                                                                                 | Priority | Trace         |
| --------- | ----------------------------------------------------------------------------------------------------------- | -------- | ------------- |
| FR-DG-001 | The Coding graph shall contain no patient IDs, encounter IDs, or patient-identifiable data                  | Must     | 01-purpose 10 |
| FR-DG-002 | All HITL workflow data (EncounterCandidate, ReviewTask, Approval, Change) shall reside in the Patient graph | Must     | 02-arch 2.3   |
| FR-DG-003 | The Coding graph shall be used read-only by application code, except for SurfaceForm writeback              | Must     | 02-arch 2.4   |


---

## 5. Non-Functional Requirements


| ID      | Requirement                                                                                            | Priority | Trace        |
| ------- | ------------------------------------------------------------------------------------------------------ | -------- | ------------ |
| NFR-001 | The system shall process at least 10 encounters per patient within 5 minutes (training pipeline)       | Should   | --           |
| NFR-002 | The API shall respond to list/get requests within 2 seconds                                            | Should   | --           |
| NFR-003 | The system shall support concurrent pipeline runs for different patients                               | Should   | 03-detail 10 |
| NFR-004 | The system shall log operational events (encounter fetched, LLM called, coding resolved) at INFO level | Must     | --           |
| NFR-005 | The system shall handle Neo4j connection failures gracefully with error messages                       | Must     | 03-detail 9  |
| NFR-006 | The resolver shall gracefully degrade when vector or fulltext indexes are missing                      | Must     | 03-detail 9  |
| NFR-007 | Embedding computation shall use GPU when available, falling back to CPU                                | Should   | --           |


---

## 6. Interface Requirements

### 6.1 External Interfaces


| Interface        | Type     | Description                                                    |
| ---------------- | -------- | -------------------------------------------------------------- |
| Patient Neo4j    | Database | Patient data, encounters, HITL workflow, DOCUMENTS             |
| Coding Neo4j     | Database | SNOMED terminology, SurfaceForm nodes                          |
| AWS Bedrock      | API      | LLM inference (Claude Haiku) for extraction and disambiguation |
| Bio_ClinicalBERT | ML Model | Sentence-transformer for vector embeddings                     |


### 6.2 User Interface


| Interface       | Framework             | Users                                                 |
| --------------- | --------------------- | ----------------------------------------------------- |
| Web application | Next.js / React / MUI | Reviewers, audit coordinators                         |
| API             | FastAPI (REST + SSE)  | Frontend, scripts, operators                          |
| CLI scripts     | Python                | Operators (training, embedding backfill, diagnostics) |


---

## 7. Approval


| Role            | Name | Date | Signature |
| --------------- | ---- | ---- | --------- |
| Author          |      |      |           |
| Clinical Lead   |      |      |           |
| Quality Manager |      |      |           |


