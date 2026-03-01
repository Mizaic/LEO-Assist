# Phase 5, 6, 7 & 8 Implementation Plan

| Field   | Value                    |
| ------- | ------------------------ |
| Version | 2.0.0                    |
| Date    | 2026-02-25               |

---

## 1. Pre-requisites (Completed)

### 1.1 Reset: Patient direct SNOMED relationships

**Status:** Implemented.

`RESET_PATIENT_DIRECT_SEMANTIC` query deletes `(Patient)-[r]->(s)` for SnomedConcept, Clinical_finding, Disease, Situation, Observable_entity, Procedure nodes.

### 1.2 Data Governance: No patient data in Coding graph

**Status:** Resolved.

The graph migration (Phase 7) moved all HITL data (EncounterCandidate, ReviewTask, Approval, Change) to the Patient graph. The Coding graph now contains only terminology (Term, Concept, ReadCode, Icd10Code, SurfaceForm) — no patient_id, no encounter_id.

This eliminates the re-identification risk entirely, making pseudonymisation unnecessary.

---

## 2. Phase 5: MedSpaCy Training Export — Implemented

### 2.1 REST Endpoint

```
POST /exports/medspacy-training
Body: { "patient_ids"?: string[], "export_name": string }
```

- If `patient_ids` omitted: export all approved candidates
- If `patient_ids` provided: export only those patients' approved gold
- Returns: `{ export_id, export_path, entity_count, kb_count, encounter_count }`

### 2.2 Export Output

- `{prefix}_entities.jsonl` — spaCy NER format: `[text, {"entities": [(start, end, label)]}]` per line
- `{prefix}_kb.jsonl` — `{evidence, concept_id, term}` per line for entity linker

### 2.3 Training Script

**File:** `scripts/train_medspacy.py`

**Usage:**
```bash
python scripts/train_medspacy.py \
  --entities exports/{name}_entities.jsonl \
  --kb exports/{name}_kb.jsonl \
  --output models/medspacy_clinical_ner \
  --epochs 30 --batch-size 16
```

**Features:**
- Configurable epochs, batch size, eval split, seed, dropout
- Builds InMemoryLookupKB from kb.jsonl
- Trains spaCy NER from entities.jsonl
- Evaluates on held-out eval set
- Saves model + KB + training_metrics.json

### 2.4 UI Button

- Location: `PipelinePanel.tsx`
- Label: "Export MedSpaCy training"
- Calls `POST /exports/medspacy-training`
- Shows success with entity_count, kb_count, encounter_count

### Status: [x] Implemented

---

## 3. Phase 6: MedSpaCy Runtime Inference — Implemented

### 3.1 REST Endpoint

```
POST /patients/{patient_id}/encounters/{encounter_id}/infer
Body: { "dry_run"?: boolean }
```

- **dry_run=true (default):** Run inference, return entities only; do not write to Patient graph
- **dry_run=false:** Run inference, write DOCUMENTS to Patient graph (source="medspacy_runtime")

**Response:**
```json
{
  "encounter_id": "...",
  "entities": [
    { "text": "...", "span_start": 0, "span_end": 5, "concept_id": "...", "term": "...", "confidence": 0.95, "semantic_tag": "..." }
  ],
  "entity_count": 3,
  "written": false,
  "dry_run": true,
  "model_path": "models/medspacy_clinical_ner"
}
```

### 3.2 Service

**File:** `services/api/app/services/inference_service.py`

- Lazy-loads trained spaCy model from `models/medspacy_clinical_ner/`
- Caches after first load
- Returns `InferredEntity` objects with text, span, concept_id, confidence, semantic_tag
- When no model exists: returns `{ entities: [], message: "MedSpaCy model not yet built. Export gold data and run: python scripts/train_medspacy.py" }`

### 3.3 UI Button

- Location: `EncounterCodedView.tsx`
- Label: "Run inference"
- Calls infer endpoint with `dry_run=true` (preview)
- Shows results

### Status: [x] Implemented

---

## 4. Phase 7: Graph Migration — Implemented

### 4.1 Purpose

Move all HITL workflow data from the Coding graph to the Patient graph to enforce data governance.

### 4.2 Changes

| Component | Before | After |
| --------- | ------ | ----- |
| Schema | Single `SCHEMA_CONSTRAINTS` | Split: `PATIENT_SCHEMA_CONSTRAINTS` + `CODING_SCHEMA_CONSTRAINTS` |
| pipeline_service._persist() | Wrote to `self.coding_graph` | Writes to `self.patient_graph` |
| review_service | Used `CodingGraphClient` | Uses `PatientGraphClient` |
| audit router | Used `CodingGraphClient` | Uses `PatientGraphClient` |
| export_service | Used `CodingGraphClient` | Uses `PatientGraphClient` |
| sync_service | Two sessions (coding + patient) | Single patient session |
| patients list endpoint | Queried coding graph for approved count | Queries patient graph |

### Status: [x] Implemented

---

## 5. Phase 8: Terminology Writeback — Implemented

### 5.1 Purpose

Feed approved reviewer corrections back into the Coding graph to improve future coding resolution (learning loop).

### 5.2 Service

**File:** `services/api/app/services/terminology_writeback_service.py`

**Logic:**
1. Read approved EncounterCandidates from Patient graph (with reviewer info)
2. Extract surface-form -> concept mappings from sentence terms
3. Normalise text (lowercase, strip punctuation)
4. Deduplicate by (normalized, concept_id) pair
5. Batch MERGE SurfaceForm nodes + MAPS_TO relationships into Coding graph

### 5.3 Endpoints

- **Automatic:** `POST /patients/{id}/sync-gold` triggers writeback after sync
- **Manual:** `POST /terminology/writeback` with optional `patient_id` filter

### 5.4 Resolver Integration

`CodingResolver` includes SurfaceForm nodes in:
- **Exact search:** Matches SurfaceForm.form exactly
- **Fulltext search:** Uses `surface_form_fulltext` index

SurfaceForm matches receive a 1.2x score boost over equivalent Term matches.

### 5.5 Coding Graph Schema

```cypher
CREATE FULLTEXT INDEX surface_form_fulltext IF NOT EXISTS
  FOR (sf:SurfaceForm) ON EACH [sf.form]

CREATE CONSTRAINT surface_form_normalized IF NOT EXISTS
  FOR (sf:SurfaceForm) REQUIRE sf.normalized IS UNIQUE
```

### Status: [x] Implemented

---

## 6. Implementation Order (Historical)

| # | Task                                      | Phase | Status |
|---|-------------------------------------------|-------|--------|
| 1 | Extend RESET: delete Patient->semantic rels | Pre   | Done |
| 2 | Add POST /exports/medspacy-training       | 5     | Done |
| 3 | Add ExportService.export_medspacy_training | 5     | Done |
| 4 | Add UI "Export MedSpaCy training" button   | 5     | Done |
| 5 | Add POST /patients/.../infer endpoint     | 6     | Done |
| 6 | Add InferenceService (real implementation) | 6     | Done |
| 7 | Add UI "Run inference" button              | 6     | Done |
| 8 | Add train_medspacy.py training script      | 5     | Done |
| 9 | Graph migration: split schema, reroute all HITL to patient graph | 7 | Done |
| 10 | Terminology writeback service              | 8     | Done |
| 11 | Resolver SurfaceForm integration           | 8     | Done |
| 12 | LLM usage tracking                         | 9     | Done |
