# Phase 5 & 6 Implementation Plan

| Field   | Value                    |
| ------- | ------------------------ |
| Version | 1.0.0                    |
| Date    | 2026-02-24               |

---

## 1. Pre-requisites (from user)

### 1.1 Reset: Patient direct SNOMED relationships

**Issue:** Patient may have direct relationships to SNOMED nodes (not only via Encounter→DOCUMENTS).

**Action:** Extend RESET to also delete:
- `(Patient)-[r]->(s)` where `s` is a semantic node (SnomedConcept, Clinical_finding, Disease, etc.)
- Orphaned semantic nodes that were only reachable via this patient's encounters

**Queries to add:**
1. Delete `(Patient)-[r]->(s)` for any relationship from Patient to semantic-type nodes
2. Optionally: delete orphaned semantic nodes (no incoming DOCUMENTS from any encounter)

### 1.2 Coding graph: No re-identification

**Requirement:** Coding graph data must never be used to re-identify the patient.

**Current risk:** EncounterCandidate stores `patient_id`, `encounter_id` — if these match Patient graph IDs, linkage is possible.

**Options:**
- **A. Pseudonymize at write:** Store `patient_token` (hash or UUID) in Coding graph; maintain secure mapping for sync
- **B. One-way token:** `patient_id` in Coding = `hash(patient_id + salt)`; sync uses API that accepts real patient_id and looks up by token
- **C. Separate identity store:** Coding graph has no patient reference; sync is triggered by encounter_id only, with patient context from request

**Recommended:** Option A — when writing to Coding graph, use `pseudonymize(patient_id)` and store mapping in config/DB. Sync endpoint receives real `patient_id` from authenticated request, resolves to pseudonym for Coding graph query.

**Implementation scope:** Add pseudonymization layer; document the design. Full implementation may require identity service. **Not implemented in this phase** — design only.

---

## 2. Phase 5: MedSpaCy Training Export

### 2.1 Purpose

Export approved gold from Coding graph to MedSpaCy training artifacts when gold is available.

### 2.2 REST Endpoint

```
POST /exports/medspacy-training
Body: { "patient_ids"?: string[], "export_name": string }
```

- If `patient_ids` omitted: export all approved candidates
- If `patient_ids` provided: export only those patients' approved gold
- Returns: `{ export_id, export_path, entity_count, ... }`

### 2.3 Export Output

- `entities.jsonl` — spaCy NER format: `(text, {"entities": [(start, end, label)]})`
- `entity_kb.jsonl` — (evidence, concept_id, term) for entity linker
- `context_rules.json` — ConText rules derived from gold (optional)

### 2.4 UI Button

- Location: Patient list or Export section
- Label: "Export MedSpaCy training"
- Calls POST /exports/medspacy-training
- Shows success with export_id / download link

### 2.5 Script (optional)

- `scripts/export_medspacy_training.py` — CLI for batch export
- Used by operators; REST used by UI

---

## 3. Phase 6: MedSpaCy Runtime Inference

### 3.1 Purpose

Run MedSpaCy on encounter text for day-forward inference. Ready for when gold is available and model is built.

### 3.2 REST Endpoint

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
    { "text": "...", "span_start": 0, "span_end": 5, "concept_id": "...", "term": "...", "confidence": 0.95 }
  ],
  "written": false
}
```

### 3.3 Service

- `MedSpaCyRuntimeService` (or `InferenceService`)
- Load MedSpaCy pipeline (when available); fallback to stub that returns empty until model exists
- Fetch encounter text from Patient graph
- Run inference
- Optionally write to Patient graph

### 3.4 UI Button

- Location: Encounter view (EncounterCodedView or encounter row)
- Label: "Run inference" or "MedSpaCy inference"
- Calls infer endpoint with dry_run=true first (preview) or dry_run=false (apply)
- Shows results / refreshes coded links

---

## 4. Implementation Order

| # | Task                                      | Phase |
|---|-------------------------------------------|-------|
| 1 | Extend RESET: delete Patient→semantic rels | Pre   |
| 2 | Add POST /exports/medspacy-training       | 5     |
| 3 | Add ExportService.export_medspacy_training | 5     |
| 4 | Add UI "Export MedSpaCy training" button   | 5     |
| 5 | Add POST /patients/.../infer endpoint     | 6     |
| 6 | Add MedSpaCyRuntimeService (stub)          | 6     |
| 7 | Add UI "Run inference" button              | 6     |
| 8 | Coding graph pseudonymization (design)     | Design only; not implemented |

---

## 5. Stub Behaviour (before model exists)

- **Export:** Works — reads gold, writes JSONL. No model needed.
- **Infer:** Returns `{ entities: [], message: "MedSpaCy model not yet built" }` until pipeline exists. Endpoint and UI ready.
