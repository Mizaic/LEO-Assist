# NLP Pipeline Verification Report

| Field   | Value                    |
| ------- | ------------------------ |
| Version | 1.0.0                    |
| Date    | 2026-02-24               |
| Status  | Verification Complete    |

---

## Summary

The implementation has been traced against the documented goals in `docs/nlp-pipeline/` and `design-controls/`. **All six verification items pass** with minor gaps noted below.

---

## 1. Training Pipeline — Coding Graph Only ✓

**Goal:** Training pipeline writes only to the Coding graph; no pre-review writes to Patient graph.

**Verification:**

- **`services/api/app/services/v3/pipeline_service.py`** (lines 369–385):
  - `_persist()` writes only to `self.coding_graph` via `upsert_candidate()` and `create_review_task()`.
  - Explicit comment: *"Patient graph DOCUMENTS are written only via sync-gold (Phase 3)."*
- `PatientGraphWriter` and `SemanticLinkPayload` are **not** used in the pipeline; they are used only by `sync_service` and manual coded-link endpoints.

**Result:** ✓ **PASS** — Training pipeline writes exclusively to the Coding graph.

---

## 2. Reset — DOCUMENTS and Patient→Semantic ✓

**Goal:** Reset removes DOCUMENTS and Patient→semantic relationships; Patient, Encounters, and text remain.

**Verification:**

- **`services/api/app/services/reset_service.py`**:
  - Calls `RESET_PATIENT_DOCUMENTS` (Encounter→DOCUMENTS→semantic).
  - Calls `RESET_PATIENT_DIRECT_SEMANTIC` (Patient→semantic nodes).
- **`services/api/app/models/neo4j_schema.py`**:
  - `RESET_PATIENT_DOCUMENTS` (lines 214–222): Deletes all `(Encounter)-[r:DOCUMENTS]->()` for the patient.
  - `RESET_PATIENT_DIRECT_SEMANTIC` (lines 224–231): Deletes `(Patient)-[r]->(s)` where `s` is SnomedConcept, Clinical_finding, Disease, Situation, Observable_entity, or Procedure.
- **Endpoint:** `POST /patients/{patient_id}/reset` in `patients.py` (lines 59–72).

**Result:** ✓ **PASS** — Reset removes DOCUMENTS and Patient→semantic relationships as specified.

**Note:** Orphaned semantic nodes (no incoming DOCUMENTS) are not deleted. The Phase 5/6 plan marks this as optional; current implementation does not perform it.

---

## 3. Sync Gold — Coding → Patient DOCUMENTS ✓

**Goal:** Sync applies approved EncounterCandidates from the Coding graph to Patient graph DOCUMENTS.

**Verification:**

- **`services/api/app/services/sync_service.py`**:
  - Fetches approved candidates via `list_approved_candidates_for_patient()`.
  - For each candidate: runs `DELETE_ENCOUNTER_DOCUMENTS` to clear existing DOCUMENTS, then uses `PatientGraphWriter.upsert_documents_link()` to write gold terms with `source="gold_sync"`.
- **`services/api/app/services/neo4j_store.py`**:
  - `list_approved_candidates_for_patient()` uses `LIST_APPROVED_CANDIDATES_FOR_PATIENT` (approval_status = 'approved').
- **Endpoint:** `POST /patients/{patient_id}/sync-gold` in `patients.py` (lines 76–100).

**Result:** ✓ **PASS** — Sync correctly applies approved gold to Patient graph DOCUMENTS.

---

## 4. Export — MedSpaCy Training Format ✓

**Goal:** `POST /exports/medspacy-training` produces `entities.jsonl` and `kb.jsonl` from approved gold.

**Verification:**

- **`services/api/app/routers/exports.py`** (lines 37–47): `POST /exports/medspacy-training` with `ExportMedSpaCyRequest` (export_name, optional patient_ids).
- **`services/api/app/services/export_service.py`** (lines 55–114):
  - Reads approved candidates (all or filtered by patient_ids).
  - Writes `{prefix}_entities.jsonl`: spaCy NER format `[text, {"entities": [(start, end, label)]}]` per line.
  - Writes `{prefix}_kb.jsonl`: `{evidence, concept_id, term}` per line for entity linker.
- **Design doc** (`06-phase5-6-implementation-plan.md`): Specifies `entities.jsonl` and `entity_kb.jsonl`. Implementation uses `{prefix}_entities.jsonl` and `{prefix}_kb.jsonl` for uniqueness; content format matches.

**Result:** ✓ **PASS** — Export produces the expected entities and KB JSONL files.

---

## 5. Inference Endpoint — Structure and Stub ✓

**Goal:** `POST /patients/{id}/encounters/{encounter_id}/infer` exists and returns the expected structure (stub OK).

**Verification:**

- **`services/api/app/routers/patients.py`** (lines 136–155): Endpoint exists at `POST /patients/{patient_id}/encounters/{encounter_id}/infer`.
- **Request:** `InferRequest` with `dry_run: bool = True`.
- **`services/api/app/services/inference_service.py`**:
  - Returns `{ encounter_id, entities, written, message }`.
  - Stub returns `entities: []` and `message: "MedSpaCy model not yet built. Export gold and train first."`
- **Design doc:** Specifies `{ encounter_id, entities: [{ text, span_start, span_end, concept_id, term, confidence }], written }`. Implementation matches; stub omits entity fields when empty.

**Result:** ✓ **PASS** — Endpoint exists and returns the expected structure; stub behavior is correct.

---

## 6. UI — Buttons Present and Wired ✓

**Goal:** Reset, Sync gold, Export MedSpaCy training, and Run inference buttons are present and wired correctly.

**Verification:**

| Button                    | Location              | API Call                          | Status |
| ------------------------- | --------------------- | --------------------------------- | ------ |
| Reset patient             | `EncounterList.tsx`   | `resetPatient(patientId)` → POST /patients/{id}/reset | ✓ |
| Sync gold to patient      | `EncounterList.tsx`   | `syncGoldToPatient(patientId)` → POST /patients/{id}/sync-gold | ✓ |
| Export MedSpaCy training  | `PipelinePanel.tsx`   | `exportMedSpaCyTraining()` → POST /exports/medspacy-training | ✓ |
| Run inference             | `EncounterCodedView.tsx` | `inferEncounter(patientId, encounterId, true)` → POST /patients/.../infer | ✓ |

- **`services/ui/src/lib/api.ts`**: All four functions implemented and call the correct endpoints.
- **Run inference:** Uses `dry_run=true` only. Design allows "dry_run=true first (preview) or dry_run=false (apply)"; current UI provides preview only, no apply button.

**Result:** ✓ **PASS** — All four buttons are present and wired. Run inference currently supports preview only (no apply/dry_run=false in UI).

---

## Gaps and Recommendations

### Minor

1. **Export filename:** Design mentions `entity_kb.jsonl`; implementation uses `{prefix}_kb.jsonl`. Content format is correct; naming is a cosmetic difference.
2. **Run inference apply:** UI has no "Apply" (dry_run=false) option. Design says "dry_run=true first (preview) or dry_run=false (apply)". Consider adding an "Apply to patient" button that calls with `dry_run=false` when the model exists.
3. **Orphaned semantic nodes:** Reset does not delete orphaned semantic nodes. Phase 5/6 plan marks this as optional; acceptable as-is.

### None

- No critical gaps identified. The two-pipeline architecture, dual Neo4j separation, user journey (Reset → Run → Review → Sync gold), Phase 5 export, and Phase 6 inference stub are implemented as designed.

---

## Trace Summary

| Feature           | Code Path                                                                 | Design Doc                    |
| ----------------- | ------------------------------------------------------------------------- | ----------------------------- |
| Training pipeline | `pipeline_service._persist` → `neo4j_store.upsert_candidate` (Coding only) | 01-intended-purpose §6.1      |
| Reset             | `reset_service` → `RESET_PATIENT_DOCUMENTS`, `RESET_PATIENT_DIRECT_SEMANTIC` | 06-phase5-6 §1.1, 01 §6.4     |
| Sync gold         | `sync_service.sync_gold_to_patient` → `PatientGraphWriter`                | 01 §6.3                       |
| Export            | `export_service.export_medspacy_training` → entities.jsonl, kb.jsonl     | 06 §2                          |
| Inference         | `inference_service.infer_encounter` (stub) → patients router              | 06 §3                          |
| UI buttons        | EncounterList, PipelinePanel, EncounterCodedView → api.ts                 | 06 §2.4, §3.4                 |
