# NLP Training and Inference Pipeline — Step-by-Step Implementation

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-IMPL-001                    |
| Version          | 1.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-24                              |

---

## 1. Implementation Phases Overview

| Phase | Scope | Dependencies |
| ----- | ----- | ------------ |
| 1 | Stop pre-review writes to Patient graph | None |
| 2 | Reset patient endpoint + service | Phase 1 |
| 3 | Sync gold to Patient endpoint + service | Phase 1 |
| 4 | UI: Reset and Sync buttons | Phase 2, 3 |
| 5 | MedSpaCy training export script | Phase 3 |
| 6 | MedSpaCy runtime pipeline (future) | Phase 5 |

---

## 2. Phase 1: Stop Pre-Review Writes to Patient Graph

### 2.1 Objective

Training pipeline writes only to Coding graph. Patient graph receives no DOCUMENTS until explicit sync.

### 2.2 Steps

#### Step 1.1: Modify V3PipelineService._persist()

**File:** `services/api/app/services/v3/pipeline_service.py`

**Change:** Remove the block that writes DOCUMENTS to Patient graph (lines ~509–529).

**Before:**
```python
# Write semantic links to patient graph for discoverability/correction UX.
with self.patient_graph.session() as patient_session:
    encounter_id = str(candidate["encounter_id"])
    for link in semantic_links:
        ...
        self.graph_writer.upsert_documents_link(payload, session=patient_session)
```

**After:** Delete this block. Keep only Coding graph writes (upsert_candidate, create_review_task).

#### Step 1.2: Update SSE event semantics

**Change:** `persist_completed` event — `queued` indicates review task created, not Patient graph write.

#### Step 1.3: Run smoke test

**Command:** `python scripts/smoke_v3_pipeline.py --patient-id 4202301609 --dry-run`

**Verify:** No Patient graph DOCUMENTS created when `dry_run=False` (after removing dry_run for a real run, confirm Patient graph unchanged).

---

## 3. Phase 2: Reset Patient

### 3.1 Objective

User can remove all DOCUMENTS for a patient, leaving Patient + Encounters + text.

### 3.2 Steps

#### Step 2.1: Add Neo4j query for reset

**File:** `services/api/app/models/neo4j_schema.py` (or `patient_graph_writer.py`)

**Add:**
```python
RESET_PATIENT_DOCUMENTS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
FOREACH (_ IN CASE WHEN r IS NOT NULL THEN [1] ELSE [] END | DELETE r)
"""
```

*Note: Refine based on whether semantic nodes are shared. If nodes are encounter-specific, add logic to delete orphaned nodes.*

#### Step 2.2: Add ResetService

**File:** `services/api/app/services/reset_service.py` (new)

```python
"""Reset patient DOCUMENTS for re-processing."""

def reset_patient(patient_id: str, session) -> dict:
    # Run RESET_PATIENT_DOCUMENTS
    # Return { "patient_id": ..., "encounters_cleared": N }
```

#### Step 2.3: Add API endpoint

**File:** `services/api/app/routers/patients.py`

```python
@router.post("/{patient_id}/reset")
def reset_patient(patient_id: str):
    # PatientGraphClient session
    # Call reset_service.reset_patient
    # Return result
```

#### Step 2.4: Add tests

**File:** `services/api/tests/test_reset_service.py`

- Create patient + encounter + DOCUMENTS
- Call reset
- Verify DOCUMENTS gone, Patient and Encounter remain

---

## 4. Phase 3: Sync Gold to Patient

### 4.1 Objective

User can apply approved gold from Coding graph to Patient graph DOCUMENTS.

### 4.2 Steps

#### Step 3.1: Add query for approved candidates by patient

**File:** `services/api/app/services/neo4j_store.py`

**Add:**
```python
def list_approved_candidates_for_patient(patient_id: str, session) -> list[dict]:
    """Return approved EncounterCandidates for a patient."""
    # Query Coding graph: approval_status = 'approved', patient_id = $patient_id
```

#### Step 3.2: Add SyncService

**File:** `services/api/app/services/sync_service.py` (new)

**Logic:**
1. Get approved candidates for patient (Coding graph)
2. For each candidate (encounter):
   - Delete existing DOCUMENTS for that encounter (Patient graph)
   - For each term with snomed_concept_id: call PatientGraphWriter.upsert_documents_link
3. Return sync summary

#### Step 3.3: Add API endpoint

**File:** `services/api/app/routers/patients.py`

```python
@router.post("/{patient_id}/sync-gold")
def sync_gold_to_patient(patient_id: str):
    # CodingGraphClient: get approved candidates
    # PatientGraphClient: delete + create DOCUMENTS
    # Return { "patient_id", "encounters_synced", "links_created" }
```

#### Step 3.4: Map gold terms to SemanticLinkPayload

Gold terms have: text, span_start, span_end, coding.snomed_concept_id, coding.snomed_term, coding.read_code, context, extraction_method.

Build SemanticLinkPayload:
- evidence = term.text
- concept_id = term.coding.snomed_concept_id
- term = term.coding.snomed_term
- read_code = term.coding.read_code
- context = term.context (as dict)
- source = "gold_sync"

#### Step 3.5: Add tests

**File:** `services/api/tests/test_sync_service.py`

- Create approved candidate in Coding graph
- Create encounter in Patient graph (no DOCUMENTS)
- Call sync
- Verify DOCUMENTS created with correct evidence/concept_id

---

## 5. Phase 4: UI Updates

### 5.1 Objective

User can trigger Reset and Sync from the UI.

### 5.2 Steps

#### Step 4.1: Add API client functions

**File:** `services/ui/src/lib/api.ts` (or equivalent)

```typescript
export async function resetPatient(patientId: string): Promise<ResetResult>;
export async function syncGoldToPatient(patientId: string): Promise<SyncResult>;
```

#### Step 4.2: Add Reset button

**Location:** Patient detail page or pipeline panel

**Behaviour:** Call resetPatient, show success/error, refresh encounter list.

#### Step 4.3: Add Sync gold button

**Location:** Patient detail page (when patient has approved tasks)

**Behaviour:** Call syncGoldToPatient, show success/error, refresh.

#### Step 4.4: Update copy

- "Run Pipeline" → clarify it creates review tasks, not final coding
- Add tooltip: "Sync gold applies approved coding to the patient record"

---

## 6. Phase 5: MedSpaCy Training Export (Future)

### 6.1 Steps

#### Step 5.1: Export script

**File:** `scripts/export_medspacy_training.py`

**Input:** Coding graph (approved candidates)

**Output:**
- `entities.jsonl` — spaCy NER format (text, entities)
- `context_rules.json` — ConText rules from gold
- `entity_kb.jsonl` — (evidence, concept_id, term) for linker

#### Step 5.2: Build MedSpaCy pipeline

**File:** `nlp/pipeline.py` (new)

- Load MedSpaCy
- Add EntityRuler or trainable NER from entities
- Add ConText from rules
- Add EntityLinker from KB

---

## 7. Phase 6: MedSpaCy Runtime Pipeline (Future)

### 7.1 Steps

#### Step 6.1: MedSpaCyRuntimeService

**File:** `services/api/app/services/v3/medspacy_runtime_service.py`

- Load trained MedSpaCy pipeline
- Process encounter text → entities + context + codes
- Return or persist DOCUMENTS

#### Step 6.2: Dry run validation

- Run MedSpaCy on encounter text
- Compare output to gold (from Coding graph)
- Compute precision, recall, F1

#### Step 6.3: Multi-select run

- POST /pipeline/run-medspacy with patient_ids[]
- Run MedSpaCy on all, write to Patient graph (or staged)

---

## 8. Implementation Order Checklist

- [ ] Phase 1.1: Remove Patient graph writes from _persist()
- [ ] Phase 1.2: Update persist_completed semantics
- [ ] Phase 1.3: Smoke test
- [ ] Phase 2.1: RESET_PATIENT_DOCUMENTS query
- [ ] Phase 2.2: ResetService
- [ ] Phase 2.3: POST /patients/{id}/reset
- [ ] Phase 2.4: Reset tests
- [ ] Phase 3.1: list_approved_candidates_for_patient
- [ ] Phase 3.2: SyncService
- [ ] Phase 3.3: POST /patients/{id}/sync-gold
- [ ] Phase 3.4: Gold-to-payload mapping
- [ ] Phase 3.5: Sync tests
- [ ] Phase 4.1: API client (reset, sync)
- [ ] Phase 4.2: Reset button
- [ ] Phase 4.3: Sync button
- [ ] Phase 4.4: Copy updates

---

## 9. Rollback Plan

| Phase | Rollback |
| ----- | -------- |
| 1 | Restore Patient graph writes in _persist() |
| 2 | Remove reset endpoint; no data impact |
| 3 | Remove sync endpoint; no data impact |
| 4 | Remove UI buttons |

---

## 10. Acceptance Criteria

- [ ] Run pipeline: no DOCUMENTS written to Patient graph
- [ ] Reset: all DOCUMENTS removed for patient; text retained
- [ ] Sync: approved gold appears as DOCUMENTS in Patient graph
- [ ] UI: Reset and Sync buttons work end-to-end
- [ ] Smoke test passes with new behaviour
