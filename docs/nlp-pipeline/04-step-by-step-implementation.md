# NLP Training and Inference Pipeline — Implementation History

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-IMPL-001                    |
| Version          | 2.0.0                                   |
| Status           | Current                                  |
| Date             | 2026-02-25                              |

---

## 1. Implementation Phases Overview

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Training pipeline writes to Patient graph (EncounterCandidate + ReviewTask) | Done |
| 2 | Reset patient DOCUMENTS endpoint + service | Done |
| 3 | Sync gold to Patient DOCUMENTS + terminology writeback | Done |
| 4 | UI: Reset, Sync, Export, Inference buttons | Done |
| 5 | MedSpaCy training export + training script | Done |
| 6 | MedSpaCy runtime inference endpoint + service | Done |
| 7 | Graph migration (HITL data from Coding to Patient graph) | Done |
| 8 | Terminology writeback (SurfaceForm nodes in Coding graph) | Done |
| 9 | LLM usage tracking per encounter | Done |
| 10 | Hybrid resolver (exact + fulltext + vector + SurfaceForm) | Done |

---

## 2. Phase 1: Training Pipeline Persistence (Patient Graph)

### Objective

Training pipeline writes EncounterCandidate and ReviewTask to the Patient graph. No DOCUMENTS are written until explicit sync.

### Implementation

- **`pipeline_service.py._persist()`**: Writes to `self.patient_graph` via `upsert_candidate()` and `create_review_task()`.
- Comment: *"Patient graph DOCUMENTS are written only via sync-gold (Phase 3)."*
- `PatientGraphWriter` and `SemanticLinkPayload` are used only by `sync_service` and manual coded-link endpoints.

### Status: [x] Complete

---

## 3. Phase 2: Reset Patient

### Objective

User can remove all DOCUMENTS for a patient, leaving Patient + Encounters + text.

### Implementation

- **`reset_service.py`**: Runs `RESET_PATIENT_DOCUMENTS` and `RESET_PATIENT_DIRECT_SEMANTIC`.
- **`POST /patients/{patient_id}/reset`**: Returns `{ patient_id, links_deleted }`.
- Also: **`POST /patients/{patient_id}/reset-review-queue`** to clear EncounterCandidates + ReviewTasks + Approvals + Changes.

### Status: [x] Complete

---

## 4. Phase 3: Sync Gold + Terminology Writeback

### Objective

User applies approved gold from Patient graph to DOCUMENTS, and approved surface forms are written back to the Coding graph.

### Implementation

- **`sync_service.py`**: Reads approved EncounterCandidates from Patient graph, deletes existing DOCUMENTS, creates new DOCUMENTS from gold terms.
- **`terminology_writeback_service.py`**: Reads approved candidates from Patient graph, extracts surface-form -> concept mappings, writes SurfaceForm nodes to Coding graph.
- **`POST /patients/{patient_id}/sync-gold`**: Runs sync + writeback. Returns `{ patient_id, encounters_synced, links_created, surface_forms_written }`.
- **`POST /terminology/writeback`**: Standalone writeback endpoint.

### Status: [x] Complete

---

## 5. Phase 4: UI Updates

### Implementation

- **Reset button**: `EncounterList.tsx` — calls `resetPatient(patientId)`.
- **Reset review queue**: `EncounterList.tsx` — calls `resetReviewQueue(patientId)`.
- **Sync gold button**: `EncounterList.tsx` — calls `syncGoldToPatient(patientId)`, displays encounters synced + surface forms written.
- **Export MedSpaCy training**: `PipelinePanel.tsx` — calls `exportMedSpaCyTraining()`.
- **Run inference**: `EncounterCodedView.tsx` — calls `inferEncounter(patientId, encounterId, true)`.
- **Review view**: Displays LLM token count and cost per encounter from `llm_usage_json`.
- **Patient list**: Shows review progress bar (reviewed_count / encounter_count).

### Status: [x] Complete

---

## 6. Phase 5: MedSpaCy Training Export + Training Script

### Implementation

- **`POST /exports/medspacy-training`**: Reads approved candidates from Patient graph, exports `entities.jsonl` and `kb.jsonl`.
- **`scripts/train_medspacy.py`**: CLI script that consumes exported JSONL, trains spaCy NER model, builds KnowledgeBase, saves model to `models/medspacy_clinical_ner/`.
- Supports configurable epochs, batch size, eval split, seed, dropout.

### Status: [x] Complete

---

## 7. Phase 6: MedSpaCy Runtime Inference

### Implementation

- **`inference_service.py`**: Lazy-loads trained spaCy model from `models/medspacy_clinical_ner/`. Returns entities with span, label, concept_id. Graceful fallback when no model exists.
- **`POST /patients/{id}/encounters/{eid}/infer`**: Fetches encounter text, runs inference, returns entities.
- UI "Run inference" button in `EncounterCodedView.tsx` (dry_run=true only).

### Status: [x] Complete

---

## 8. Phase 7: Graph Migration

### Objective

Move all HITL data (EncounterCandidate, ReviewTask, Approval, Change) from Coding graph to Patient graph for data governance.

### Implementation

- **Schema split**: `PATIENT_SCHEMA_CONSTRAINTS` (HITL nodes) and `CODING_SCHEMA_CONSTRAINTS` (SurfaceForm only).
- **PatientGraphClient**: Initializes HITL schema. Used by pipeline, review, audit, export, sync.
- **CodingGraphClient**: Initializes SurfaceForm schema. Read-only for terminology lookups, plus writeback writes.
- **All HITL routers** (review, audit, exports, patients) switched from `CodingGraphClient` to `PatientGraphClient`.
- **Coding graph**: Contains no patient_id, no encounter_id, no EncounterCandidate — only terminology.

### Status: [x] Complete

---

## 9. Phase 8: Terminology Writeback

### Objective

Approved surface-form -> SNOMED mappings written from Patient graph to Coding graph as SurfaceForm nodes.

### Implementation

- **`terminology_writeback_service.py`**: Normalises surface forms, deduplicates, batched writes.
- **`coding_resolver.py`**: Queries SurfaceForm nodes alongside Term nodes (exact + fulltext), with 1.2x score boost for human-approved mappings.
- **`CODING_SCHEMA_CONSTRAINTS`**: Adds `surface_form_fulltext` index and `surface_form_normalized` uniqueness constraint.

### Status: [x] Complete

---

## 10. Phase 9: LLM Usage Tracking

### Implementation

- **`llm_usage.py`**: `LLMUsage` dataclass with `+` operator and `to_dict(cost_config)` method.
- **`LLMCostConfig`**: Reads cost rates from environment variables.
- **`pipeline_service.py`**: Sums extraction + disambiguation usage per encounter, stores in `llm_usage_json` on EncounterCandidate.
- **Frontend**: Displays token count and cost in pipeline stream status and review view header.

### Status: [x] Complete

---

## 11. Phase 10: Hybrid Resolver

### Implementation

- **`coding_resolver.py`**: Three-tier search (exact, fulltext, vector) with SurfaceForm included in exact and fulltext tiers.
- Score normalisation (0-1 range per tier), weighted fusion, semantic tag re-ranking.
- **Embeddings**: Bio_ClinicalBERT via sentence-transformers, CUDA GPU with CPU fallback.
- **Graceful degradation**: Missing vector or fulltext indexes logged once and skipped.

### Status: [x] Complete

---

## 12. Rollback Plan

| Phase | Rollback |
| ----- | -------- |
| 1 | Revert _persist() to write to Coding graph |
| 2 | Remove reset endpoint; no data impact |
| 3 | Remove sync + writeback endpoints; no data impact |
| 4 | Remove UI buttons |
| 7 | Revert schema split; move HITL data back to Coding graph |
| 8 | Remove SurfaceForm queries from resolver; drop SurfaceForm nodes |

---

## 13. Acceptance Criteria

- [x] Run pipeline: EncounterCandidate + ReviewTask written to Patient graph
- [x] No patient data in Coding graph
- [x] Reset: all DOCUMENTS removed for patient; text retained
- [x] Reset review queue: all HITL nodes removed for patient
- [x] Sync: approved gold appears as DOCUMENTS in Patient graph
- [x] Writeback: SurfaceForm nodes created in Coding graph from approved terms
- [x] Resolver: uses SurfaceForm nodes with score boost
- [x] LLM usage tracked per encounter
- [x] Export produces entities.jsonl and kb.jsonl
- [x] MedSpaCy training script produces model
- [x] Inference endpoint works (with or without trained model)
- [x] UI: all buttons work end-to-end
- [x] 58 unit tests passing
