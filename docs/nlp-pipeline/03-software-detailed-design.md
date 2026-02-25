# NLP Training and Inference Pipeline — Software Detailed Design

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-DD-001                      |
| Version          | 2.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-25                              |

---

## 1. Data Models

### 1.1 EncounterCandidate (Patient Graph)

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
├── llm_usage_json: JSON string (LLMUsage)
└── created_at, updated_at: datetime
```

### 1.2 LLMUsage (stored as JSON in llm_usage_json)

```
LLMUsage
├── input_tokens: int
├── output_tokens: int
├── cached_input_tokens: int
├── total_tokens: int
├── llm_calls: int
└── cost_usd: float (estimated)
```

### 1.3 EncounterSentence

```
EncounterSentence
├── sentence_id: string (e.g. "s0")
├── start: int (char offset)
├── end: int (char offset)
├── text: string
├── section: string | null
└── terms: EncounterTerm[]
```

### 1.4 EncounterTerm

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
├── extraction_confidence: float
├── semantic_tag: string
└── modifiers: {}
```

### 1.5 HITL Workflow Nodes (Patient Graph)

```
ReviewTask
├── task_id: string (UUID)
├── priority: int
├── status: "pending" | "approved" | "rejected" | "escalated"
├── assigned_reviewer: string | null
├── warning_count: int
└── created_at, updated_at: datetime

Approval
├── approval_id: string (UUID)
├── action: "approve" | "edit" | "reject" | "escalate"
├── reviewer: string
├── reason: string
├── status_after: string
├── before_hash, after_hash: string
└── timestamp: datetime

Change
├── change_id: string (UUID)
├── event_type: string
├── actor: string
├── reason: string
├── before_hash, after_hash: string
├── version_bundle_json: string
└── timestamp: datetime
```

**Relationships (Patient Graph):**
- `(EncounterCandidate)-[:HAS_TASK]->(ReviewTask)`
- `(ReviewTask)-[:HAS_APPROVAL]->(Approval)`
- `(EncounterCandidate)-[:HAS_CHANGE]->(Change)`

### 1.6 SurfaceForm (Coding Graph)

```
SurfaceForm
├── form: string (original surface text)
├── normalized: string (unique, lowercase, punctuation stripped)
├── source: "hitl_approved"
├── status: "approved"
├── created_by: string (reviewer)
├── created_at: datetime
└── last_seen_at: datetime
```

**Relationships (Coding Graph):**
- `(SurfaceForm)-[:MAPS_TO]->(Concept)` with properties: confidence, approved_by, approved_at, provenance

### 1.7 DOCUMENTS Relationship (Patient Graph)

```
(Encounter)-[DOCUMENTS]->(SnomedConcept | Clinical_finding | Disease | ...)
  r.evidence: string (text span)
  r.confidence: float
  r.domain: string
  r.context: JSON
  r.modifiers: JSON
  r.source: string ("v3_pipeline" | "manual" | "medspacy_runtime" | "gold_sync")
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

### 2.2 Patient Operations

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| GET | `/patients` | List patients with review progress |
| GET | `/patients/{patient_id}` | Get patient detail |
| POST | `/patients/{patient_id}/reset` | Remove all DOCUMENTS for patient |
| POST | `/patients/{patient_id}/reset-review-queue` | Remove all EncounterCandidates + ReviewTasks for patient |
| POST | `/patients/{patient_id}/sync-gold` | Sync approved gold to DOCUMENTS + terminology writeback |
| GET | `/patients/{patient_id}/encounters` | List encounters |
| GET | `/patients/{patient_id}/encounters/{eid}` | Get encounter detail |
| GET | `/patients/{patient_id}/encounters/{eid}/coded-links` | Get coded DOCUMENTS links |
| POST | `/patients/{patient_id}/encounters/{eid}/coded-links` | Add manual coded link |
| DELETE | `/patients/{patient_id}/encounters/{eid}/coded-links/{cid}` | Delete coded link |
| PATCH | `/patients/{patient_id}/encounters/{eid}/coded-links/{cid}` | Recode a link |
| POST | `/patients/{patient_id}/encounters/{eid}/infer` | Run MedSpaCy inference |

### 2.3 Review

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| GET | `/review/tasks` | List review tasks (filter by status, patient) |
| GET | `/review/tasks/{task_id}` | Get task detail + candidate |
| POST | `/review/tasks/{task_id}/decision` | Approve / edit / reject |

### 2.4 Terminology

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| GET | `/terminology/search` | Fulltext search against Coding graph |
| POST | `/terminology/writeback` | Write approved surface forms to Coding graph |

### 2.5 Exports

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| POST | `/exports/medspacy-training` | Export gold to MedSpaCy training format |
| POST | `/exports/dataset` | Export training dataset |

---

## 3. Service Layer

### 3.1 V3PipelineService (Training)

**Key methods:**
- `run(patient_ids, max_encounters_per_patient, dry_run, workers, progress_hook)` -> run_id, stats
- `_process_encounter(patient_id, encounter, run_id, dry_run, stats, ...)`
- `_persist(candidate, semantic_links, dry_run, hard_fail, base, progress_hook)` — **writes Patient graph only** (EncounterCandidate + ReviewTask)

**Dependencies:** PatientGraphClient (read encounters, write HITL), CodingGraphClient (read terminology), LLMExtractor, CodingResolver, CodingDisambiguator, SentenceSplitter

### 3.2 CodingResolver (Hybrid)

**Methods:**
- `resolve_candidates(terms, neo4j_session, expected_tags)` -> dict of term -> candidates

**Strategy:**
1. **Exact match**: Term node and SurfaceForm node (exact string match)
2. **Fulltext search**: Lucene fulltext indexes on Term and SurfaceForm
3. **Vector search**: Bio_ClinicalBERT embeddings on Term nodes
4. Score normalisation, weighted fusion, semantic tag re-ranking
5. SurfaceForm results get 1.2x score boost (human-approved)

### 3.3 SyncService

**Methods:**
- `sync_gold_to_patient(patient_id, patient_session)` -> SyncResult

**Logic:**
1. Query Patient graph: approved EncounterCandidates for patient
2. For each candidate/encounter: delete existing DOCUMENTS, create new DOCUMENTS from gold terms
3. Return sync summary

### 3.4 TerminologyWritebackService

**Methods:**
- `writeback_approved_terms(patient_session, coding_session, patient_id?)` -> WritebackStats

**Logic:**
1. Read approved EncounterCandidates from Patient graph
2. Extract surface-form -> concept mappings from sentences
3. Normalise, deduplicate
4. Write SurfaceForm nodes + MAPS_TO relationships to Coding graph in batches

### 3.5 ReviewService

**Methods:**
- `list_tasks(status, patient_id, limit)` -> task list
- `get_task(task_id)` -> task detail + candidate
- `decide(task_id, decision)` -> approval result

**Graph:** Patient graph only.

### 3.6 InferenceService (MedSpaCy Runtime)

**Methods:**
- `infer_encounter(encounter_text, encounter_id, dry_run)` -> entities + metadata

**Logic:**
- Lazy-loads trained spaCy model from `models/medspacy_clinical_ner/`
- Returns entities with span, label, concept_id
- Graceful fallback when no trained model exists

### 3.7 ExportService

**Methods:**
- `export_medspacy_training(export_name, patient_ids?)` -> export stats
- `create_export(export_name, train_ratio, seed)` -> dataset export

**Graph:** Patient graph (reads approved EncounterCandidates).

---

## 4. Neo4j Schema

### 4.1 Patient Graph Constraints

```cypher
CREATE CONSTRAINT encounter_candidate_id IF NOT EXISTS
  FOR (c:EncounterCandidate) REQUIRE c.candidate_id IS UNIQUE

CREATE CONSTRAINT review_task_id IF NOT EXISTS
  FOR (t:ReviewTask) REQUIRE t.task_id IS UNIQUE

CREATE CONSTRAINT approval_id IF NOT EXISTS
  FOR (a:Approval) REQUIRE a.approval_id IS UNIQUE

CREATE CONSTRAINT change_id IF NOT EXISTS
  FOR (chg:Change) REQUIRE chg.change_id IS UNIQUE

CREATE INDEX review_task_status IF NOT EXISTS
  FOR (t:ReviewTask) ON (t.status)

CREATE INDEX review_task_priority IF NOT EXISTS
  FOR (t:ReviewTask) ON (t.priority)
```

### 4.2 Coding Graph Constraints

```cypher
CREATE FULLTEXT INDEX surface_form_fulltext IF NOT EXISTS
  FOR (sf:SurfaceForm) ON EACH [sf.form]

CREATE CONSTRAINT surface_form_normalized IF NOT EXISTS
  FOR (sf:SurfaceForm) REQUIRE sf.normalized IS UNIQUE
```

---

## 5. Key Neo4j Queries

### 5.1 Upsert EncounterCandidate (Patient Graph)

```cypher
MERGE (c:EncounterCandidate {candidate_id: $candidate_id})
SET c.patient_id = $patient_id,
    c.encounter_id = $encounter_id,
    c.date = $date,
    c.source_hash = $source_hash,
    c.deidentified_hash = $deidentified_hash,
    c.deidentified_text = $deidentified_text,
    c.approval_status = $approval_status,
    c.hard_fail_reasons = $hard_fail_reasons,
    c.warning_reasons = $warning_reasons,
    c.sentences_json = $sentences_json,
    c.llm_usage_json = $llm_usage_json,
    c.updated_at = datetime(),
    c.created_at = coalesce(c.created_at, datetime())
```

### 5.2 Reset Patient DOCUMENTS (Patient Graph)

```cypher
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id
DELETE r
```

### 5.3 Reset Patient Direct Semantic (Patient Graph)

```cypher
MATCH (p:Patient)-[r]->(s)
WHERE toString(p.id) = $patient_id
  AND (s:SnomedConcept OR s:Clinical_finding OR s:Disease OR s:Situation
       OR s:Observable_entity OR s:Procedure)
DELETE r
```

### 5.4 List Approved Candidates (Patient Graph)

```cypher
MATCH (c:EncounterCandidate)
WHERE c.approval_status = 'approved' AND c.patient_id = $patient_id
RETURN c
ORDER BY c.encounter_id
```

### 5.5 Upsert SurfaceForm (Coding Graph)

```cypher
UNWIND $rows AS r
MATCH (c:Concept {id: r.concept_id})
MERGE (sf:SurfaceForm {normalized: r.normalized})
ON CREATE SET sf.created_at = datetime(), sf.created_by = r.approved_by
SET sf.form = r.form,
    sf.source = r.source,
    sf.status = r.status,
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.created_by = r.approved_by
SET m.confidence = r.confidence,
    m.approved_by = r.approved_by,
    m.approved_at = datetime(),
    m.provenance = r.provenance
RETURN count(sf) AS written
```

### 5.6 Delete DOCUMENTS for Encounter (Patient Graph)

```cypher
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->()
WHERE toString(p.id) = $patient_id AND toString(e.id) = $encounter_id
DELETE r
```

### 5.7 Reset Review Queue (Patient Graph)

```cypher
MATCH (c:EncounterCandidate {patient_id: $patient_id})
OPTIONAL MATCH (c)-[:HAS_TASK]->(t:ReviewTask)
OPTIONAL MATCH (t)-[:HAS_APPROVAL]->(a:Approval)
OPTIONAL MATCH (c)-[:HAS_CHANGE]->(chg:Change)
-- collects and DETACH DELETEs all nodes
```

---

## 6. Training Pipeline Stages (Detail)

| Stage | Input | Output | Component |
| ----- | ----- | ------ | ---------- |
| 1. Fetch | patient_id | encounters[] | PatientGraphClient |
| 2. Deidentify | encounter.text | deidentified_text | training_v2_utils.deidentify_text |
| 3. Deduplicate | text lines | deduplicated_text | deduplicate_lines |
| 4. Sentence split | deidentified_text | SentenceChunk[] | SentenceSplitter (PyRuSH) |
| 5. Term extract | chunks | ExtractedTerm[] | LLMExtractor (batches of 5) |
| 6. Resolve | term texts | candidates_by_text | CodingResolver (hybrid: exact + fulltext + vector + SurfaceForm) |
| 7. Disambiguate | candidates | best CodingCandidate | CodingDisambiguator (LLM) |
| 8. Inline Read | sentence text | additional terms | READ_CODE_RE |
| 9. Validate | candidate | GateResult | validate_encounter_payload |
| 10. Persist | candidate | -- | upsert_candidate, create_review_task (Patient graph) |

---

## 7. MedSpaCy Training Export Format

From gold (EncounterCandidate sentences), produce:

**Entity training (spaCy format):**
```
("Patient has diabetes mellitus.", {"entities": [(12, 28, "DISORDER")]})
```

**Entity linker KB:**
- (evidence_text, concept_id, term) from gold terms

**Training script:** `scripts/train_medspacy.py` consumes `entities.jsonl` + `kb.jsonl`, trains NER + builds KnowledgeBase.

---

## 8. Configuration

| Env Var | Purpose |
| ------- | ------- |
| NEO4J_URI | Patient graph |
| NEO4J_USERNAME, NEO4J_PASSWORD | Patient graph auth |
| CODING_GRAPH_NEO4J_URI | Coding graph |
| CODING_GRAPH_NEO4J_USERNAME, _PASSWORD | Coding graph auth |
| AWS_REGION | Bedrock |
| MODEL_ID | Bedrock model (e.g. anthropic.claude-3-5-haiku) |
| COST_PER_1K_INPUT_TOKENS | LLM cost rate (input) |
| COST_PER_1K_OUTPUT_TOKENS | LLM cost rate (output) |
| COST_PER_1K_CACHED_INPUT_TOKENS | LLM cost rate (cached input) |

---

## 9. Error Handling

| Scenario | Behaviour |
| -------- | --------- |
| Patient not found | 404 |
| No encounters | Empty run, 0 processed |
| LLM failure | Hard fail (ExtractionError), no fallback to regex |
| Validation hard_fail | Candidate persisted but no ReviewTask created |
| Sync: no approved gold | 400 with detail message |
| Missing vector index | Graceful degradation (log once, skip vector search) |
| Missing fulltext index | Graceful degradation (log once, skip SurfaceForm fulltext) |

---

## 10. Concurrency

- Training pipeline: ThreadPoolExecutor (workers 1-8)
- Sync: Single-threaded per patient
- Reset: Single-threaded per patient
- Terminology writeback: Batched (500 rows per batch)
