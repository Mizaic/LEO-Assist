# NLP Training and Inference Pipeline — Software Detailed Design

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-DD-001                      |
| Version          | 1.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-24                              |

---

## 1. Data Models

### 1.1 EncounterCandidate (Coding Graph)

```
EncounterCandidate
├── candidate_id: string (UUID5)
├── patient_id: string
├── encounter_id: string
├── date: string
├── source_hash: string
├── deidentified_hash: string
├── deidentified_text: string
├── approval_status: "pending" | "approved" | "rejected" | "escalated"
├── hard_fail_reasons: string[]
├── warning_reasons: string[]
├── sentences_json: JSON string (EncounterSentence[])
└── created_at, updated_at: datetime
```

### 1.2 EncounterSentence

```
EncounterSentence
├── sentence_id: string (e.g. "s0")
├── start: int (char offset)
├── end: int (char offset)
├── text: string
├── section: string | null
└── terms: EncounterTerm[]
```

### 1.3 EncounterTerm

```
EncounterTerm
├── term_id: string (e.g. "s0_t0")
├── text: string (evidence span)
├── span_start: int
├── span_end: int
├── context: { negated, uncertain, historical, subject, temporality }
├── coding: { snomed_concept_id, read_code, snomed_term, score, source }
├── evidence_text: string
├── extraction_method: string ("v3_llm_batch" | "manual" | "inline_read_code")
└── extraction_confidence: float
```

### 1.4 DOCUMENTS Relationship (Patient Graph)

```
(Encounter)-[DOCUMENTS]->(SnomedConcept | Clinical_finding | Disease | ...)
  r.evidence: string (text span)
  r.confidence: float
  r.domain: string
  r.context: JSON
  r.modifiers: JSON
  r.source: string ("v3_pipeline" | "manual" | "medspacy_runtime")
  r.coded_at: datetime

(SnomedConcept)
  conceptId: string
  name: string (PT)
  readCode: string | null
  semanticTag: string
```

---

## 2. API Endpoints

### 2.1 Pipeline

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| POST | `/pipeline/run` | Run training pipeline (LLM), sync |
| GET | `/pipeline/stream` | SSE stream of training pipeline progress |

**Request (POST /pipeline/run):**
```json
{
  "patient_ids": ["4202301609"],
  "max_encounters_per_patient": 10,
  "dry_run": false
}
```

### 2.2 Patient Operations (New)

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| POST | `/patients/{patient_id}/reset` | Remove all DOCUMENTS for patient |
| POST | `/patients/{patient_id}/sync-gold` | Sync approved gold from Coding to Patient graph |

### 2.3 Review

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| GET | `/review/tasks` | List review tasks |
| GET | `/review/tasks/{task_id}` | Get task detail + candidate |
| POST | `/review/tasks/{task_id}/decision` | Approve / edit / reject |

### 2.4 Runtime Pipeline (Future)

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| POST | `/pipeline/run-medspacy` | Run MedSpaCy on selected patients |
| GET | `/pipeline/validate-medspacy` | Dry run MedSpaCy vs gold for a patient |

---

## 3. Service Layer

### 3.1 V3PipelineService (Training)

**Key methods:**
- `run(patient_ids, max_encounters_per_patient, dry_run, workers, progress_hook)` → run_id, stats
- `_process_encounter(patient_id, encounter, run_id, dry_run, stats, ...)`
- `_persist(candidate, semantic_links, dry_run, hard_fail, base, progress_hook)` — **writes Coding only** (Patient writes removed)

**Dependencies:** PatientGraphClient (read), CodingGraphClient (write), LLMExtractor, CodingResolver, CodingDisambiguator, SentenceSplitter

### 3.2 SyncService (New)

**Methods:**
- `sync_gold_to_patient(patient_id: str) -> SyncResult`
  - Query Coding graph: approved EncounterCandidates for patient
  - For each encounter: delete DOCUMENTS in Patient graph
  - For each term in gold: create DOCUMENTS in Patient graph

### 3.3 ResetService (New)

**Methods:**
- `reset_patient(patient_id: str) -> ResetResult`
  - Match Patient → Encounters → DOCUMENTS → semantic nodes
  - Delete DOCUMENTS relationships
  - Delete orphaned semantic nodes (only connected via DOCUMENTS for this patient)

### 3.4 MedSpaCyRuntimeService (Future)

**Methods:**
- `run(patient_ids: list[str], dry_run: bool) -> RunResult`
- `validate_vs_gold(patient_id: str) -> ValidationMetrics`

---

## 4. Neo4j Queries

### 4.1 Reset Patient

```cypher
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(s)
WHERE s IS NOT NULL
WITH e, collect({r: r, s: s}) AS links
UNWIND links AS link
WITH link WHERE link.r IS NOT NULL
DELETE link.r
WITH DISTINCT link.s AS node
WHERE node IS NOT NULL
  AND NOT (node)-[:DOCUMENTS]-()
DELETE node
```

*Note: Refine based on schema — semantic nodes may be shared. Safer: delete only relationships, leave nodes if shared.*

### 4.2 Sync Gold — Get Approved Candidates

```cypher
MATCH (c:EncounterCandidate)
WHERE c.patient_id = $patient_id AND c.approval_status = 'approved'
RETURN c
ORDER BY c.encounter_id
```

### 4.3 Sync Gold — Delete DOCUMENTS for Encounter

```cypher
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
MATCH (e)-[r:DOCUMENTS]->()
DELETE r
```

### 4.4 Sync Gold — Create DOCUMENTS

Use existing `PatientGraphWriter.upsert_documents_link()` with payload from gold terms.

---

## 5. Training Pipeline Stages (Detail)

| Stage | Input | Output | Component |
| ----- | ----- | ------ | ---------- |
| 1. Fetch | patient_id | encounters[] | PatientGraphClient |
| 2. Deidentify | encounter.text | deidentified_text | training_v2_utils.deidentify_text |
| 3. Sentence split | deidentified_text | SentenceChunk[] | SentenceSplitter |
| 4. Term extract | chunks | ExtractedTerm[] | LLMExtractor (batches of 5) |
| 5. Resolve | term texts | candidates_by_text | CodingResolver (Neo4j) |
| 6. Disambiguate | candidates | best CodingCandidate | CodingDisambiguator (LLM) |
| 7. Inline Read | sentence text | additional terms | READ_CODE_RE |
| 8. Validate | candidate | GateResult | validate_encounter_payload |
| 9. Persist | candidate | — | upsert_candidate, create_review_task |

---

## 6. MedSpaCy Training Export Format (Target)

From gold (EncounterCandidate sentences), produce:

**Entity training (spaCy format):**
```
("Patient has diabetes mellitus.", {"entities": [(12, 28, "DISORDER")]})
```

**Context training (ConText):**
- Negation rules from gold context.negated
- Section boundaries from sentence structure

**Entity linker KB:**
- (evidence_text, snomed_concept_id, snomed_term) from gold terms

---

## 7. Configuration

| Env Var | Purpose |
| ------- | ------- |
| NEO4J_URI | Patient graph |
| NEO4J_USERNAME, NEO4J_PASSWORD | Patient graph auth |
| CODING_GRAPH_NEO4J_URI | Coding graph |
| CODING_GRAPH_NEO4J_USERNAME, _PASSWORD | Coding graph auth |
| AWS_REGION | Bedrock |
| MODEL_ID | Bedrock model (e.g. anthropic.claude-3-sonnet) |

---

## 8. Error Handling

| Scenario | Behaviour |
| -------- | --------- |
| Patient not found | 404 |
| No encounters | Empty run, 0 processed |
| LLM failure | encounter_error event, continue other encounters |
| Validation hard_fail | Reject, no review task |
| Sync: no approved gold | 400 or empty sync |

---

## 9. Concurrency

- Training pipeline: ThreadPoolExecutor (workers 1–8)
- Sync: Single-threaded per patient
- Reset: Single-threaded per patient
