# NLP Training and Inference Pipeline — Software Architecture Design

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-ARCH-001                    |
| Version          | 2.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-25                              |

---

## 1. Architecture Overview

The system uses a **two-pipeline, dual-Neo4j, learning-loop** architecture:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        NLP PIPELINE ARCHITECTURE                             │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐                  ┌──────────────────────┐         │
│  │   TRAINING PIPELINE   │                  │   RUNTIME PIPELINE    │         │
│  │   (LLM-driven)       │                  │   (MedSpaCy-driven)   │         │
│  │                       │                  │                       │         │
│  │  • De-identify       │                  │  • MedSpaCy NER       │         │
│  │  • Sentence split    │                  │  • ConText / rules   │         │
│  │  • LLM extract       │  reads           │  • Entity linking    │         │
│  │  • Neo4j resolve ◄───┼──────────┐       │                       │         │
│  │  • LLM disambiguate  │          │       └──────────┬───────────┘         │
│  │  • Validate           │          │                   │                    │
│  └──────────┬───────────┘          │                   │ writes             │
│             │                       │                   │                    │
│             │  writes               │                   │                    │
│             ▼                       │                   ▼                    │
│  ┌──────────────────────────────────┼───────────────────────────┐           │
│  │        PATIENT NEO4J (NEO4J_URI)  │                           │           │
│  │                                   │                           │           │
│  │  • Patient, Encounter (source)   │                           │           │
│  │  • EncounterCandidate (HITL)     │                           │           │
│  │  • ReviewTask, Approval, Change  │                           │           │
│  │  • DOCUMENTS (audit output)      │                           │           │
│  │  • LLM usage per candidate       │                           │           │
│  └──────────┬───────────────────────┘                           │           │
│             │                                                    │           │
│             │  sync-gold + writeback                             │           │
│             ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │        CODING NEO4J (CODING_GRAPH_NEO4J_URI)                  │           │
│  │        Terminology only — NO patient data                     │           │
│  │                                                               │           │
│  │  • Term, Concept, ReadCode, Icd10Code (SNOMED base)          │           │
│  │  • SurfaceForm ──[MAPS_TO]──> Concept (from writeback)       │           │
│  │  • Fulltext, vector indexes                                   │           │
│  └──────────────────────────────────────────────────────────────┘           │
│                                                                              │
│                         ┌─────────────────────┐                              │
│                         │   LEARNING LOOP      │                              │
│                         │                      │                              │
│                         │  1. LLM extracts     │                              │
│                         │  2. Human reviews     │                              │
│                         │  3. Approved terms    │                              │
│                         │     written back as   │                              │
│                         │     SurfaceForm nodes │                              │
│                         │  4. Resolver uses     │                              │
│                         │     SurfaceForm for   │                              │
│                         │     future coding     │                              │
│                         │  5. MedSpaCy trained  │                              │
│                         │     from gold export  │                              │
│                         └─────────────────────┘                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Responsibilities

### 2.1 Training Pipeline (LLM)

| Component        | Responsibility                                      |
| ---------------- | --------------------------------------------------- |
| De-identifier   | PHI removal (names, dates, NHS numbers, etc.)        |
| SentenceSplitter| Segment text (PyRuSH / spaCy / regex), deduplicate  |
| LLMExtractor    | Extract clinical terms in batches (AWS Bedrock)     |
| CodingResolver  | Map terms to SNOMED via hybrid search (exact + fulltext + vector), including SurfaceForm nodes |
| CodingDisambiguator | Choose best SNOMED when multiple candidates (LLM) |
| Validator       | Schema, context, ontology checks                     |
| Persistence     | Write EncounterCandidate + ReviewTask to Patient graph |

**Reads** from Coding graph (terminology). **Writes** to Patient graph (HITL data).

### 2.2 Runtime Pipeline (MedSpaCy)

| Component        | Responsibility                                      |
| ---------------- | --------------------------------------------------- |
| MedSpaCy NER    | Entity extraction (rules + TF-ML)                    |
| ConText          | Negation, uncertainty, temporality                  |
| EntityLinker     | Map spans to SNOMED (local KB + Neo4j fallback)     |
| Persistence     | Write DOCUMENTS to Patient graph (when approved)    |

**Reads** from Coding graph gold for KB; **writes** only to Patient graph.

### 2.3 Patient Neo4j (All patient data + HITL)

| Node/Relationship | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| Patient           | Patient identity                                     |
| Encounter         | Encounter text, date                                 |
| EncounterCandidate| Sentences, terms, spans, coding, context, LLM usage  |
| ReviewTask        | HITL queue per candidate                             |
| Approval          | Approve/edit/reject events                            |
| Change            | Audit trail (from audit_events)                       |
| DOCUMENTS         | Encounter -> semantic node (evidence, concept_id, etc.)|

**Role**: Source of truth for patient data, HITL workflow, and gold; sync target for DOCUMENTS; export source for MedSpaCy training.

### 2.4 Coding Neo4j (Terminology only)

| Node/Relationship | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| Term              | SNOMED term descriptions (with embeddings)           |
| Concept           | SNOMED concepts (active, FSN, semantic_tag)          |
| ReadCode          | Read/CTV3 codes                                      |
| Icd10Code         | ICD-10 mappings                                      |
| SurfaceForm       | Human-approved surface text -> Concept mappings (from writeback) |

**Role**: Read-only terminology lookup for pipeline and resolver. SurfaceForm nodes are the only writes, created by terminology writeback from approved gold. **Contains no patient IDs or encounter IDs.**

---

## 3. Data Flow

### 3.1 Training Flow

```
Patient Graph (read)          Training Pipeline              Patient Graph (write)
       │                              │                              │
       │  encounter text               │                              │
       │◄─────────────────────────────│                              │
       │                               │                              │
       │                          Coding Graph (read)                │
       │                               │  terminology                │
       │                               │◄────────────                │
       │                               │                              │
       │                               │   EncounterCandidate         │
       │                               │   ReviewTask                 │
       │                               │   LLM usage                  │
       │                               │─────────────────────────────►│
       │                               │                              │
       │                               │   [HITL Review]              │
       │                               │   [Approval / Change]        │
       │                               │                              │
```

### 3.2 Sync + Writeback Flow

```
Patient Graph (read+write)     Sync Service                 Coding Graph (write)
       │                              │                              │
       │  approved candidates          │                              │
       │◄─────────────────────────────│                              │
       │                               │                              │
       │  delete old DOCUMENTS         │                              │
       │  create new DOCUMENTS         │                              │
       │◄─────────────────────────────│                              │
       │                               │                              │
       │  approved surface forms       │                              │
       │◄─────────────────────────────│                              │
       │                               │   SurfaceForm nodes          │
       │                               │   MAPS_TO relationships      │
       │                               │─────────────────────────────►│
```

### 3.3 Runtime Flow (MedSpaCy)

```
Patient Graph (read)          Runtime Pipeline             Patient Graph (write)
       │                              │                              │
       │  encounter text               │                              │
       │◄─────────────────────────────│                              │
       │                               │   MedSpaCy inference         │
       │                               │   DOCUMENTS                  │
       │                               │─────────────────────────────►│
       │                               │                              │
Coding Graph (read)                    │
       │  gold / KB / SurfaceForm      │
       │◄─────────────────────────────│
```

---

## 4. Deployment Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  API Service (FastAPI)                                           │
│  • /pipeline/run, /pipeline/stream                               │
│  • /review/tasks, /review/tasks/{id}/decision                    │
│  • /patients/{id}/reset, /patients/{id}/sync-gold               │
│  • /patients/{id}/reset-review-queue                             │
│  • /patients/{id}/encounters/{eid}/coded-links                   │
│  • /patients/{id}/encounters/{eid}/infer                         │
│  • /terminology/search, /terminology/writeback                   │
│  • /exports/medspacy-training                                    │
└────────────────────────────┬────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Patient Neo4j   │  │ Coding Neo4j    │  │ AWS Bedrock     │
│ (NEO4J_URI)     │  │ (CODING_GRAPH_  │  │ (LLM only)      │
│                 │  │  NEO4J_URI)     │  │                 │
│ Patients,       │  │ Terms,          │  │ Claude Haiku    │
│ Encounters,     │  │ Concepts,       │  │ (extraction +   │
│ Candidates,     │  │ ReadCodes,      │  │  disambiguation)│
│ ReviewTasks,    │  │ SurfaceForms    │  │                 │
│ DOCUMENTS       │  │ (no patient IDs)│  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## 5. Technology Stack

| Layer        | Technology                                      |
| ------------ | ------------------------------------------------ |
| API          | FastAPI                                          |
| Training NLP | spaCy, PyRuSH, AWS Bedrock (Claude Haiku 4.5)   |
| Runtime NLP  | MedSpaCy, spaCy, scispaCy                        |
| Terminology  | Neo4j (Coding graph) — hybrid search (exact + fulltext + vector) |
| Patient data | Neo4j (Patient graph) — encounter data + HITL workflow |
| Embeddings   | Bio_ClinicalBERT (sentence-transformers), CUDA GPU with CPU fallback |
| UI           | Next.js, React, MUI                              |

---

## 6. Key Design Decisions

| Decision                    | Rationale                                              |
| -------------------------- | ------------------------------------------------------ |
| Dual Neo4j                 | Separate terminology from patient clinical data for data governance |
| Training writes Patient only | All HITL data co-located with patient data; Coding graph has no patient IDs |
| Coding graph read-only     | Except for SurfaceForm writeback from approved gold   |
| Sync as explicit step      | User controls when gold is applied to patient record  |
| Terminology writeback      | Approved surface forms enrich the resolver for future runs (learning loop) |
| Hybrid resolution          | Exact + fulltext + vector search with score fusion and semantic tag re-ranking |
| LLM usage tracking         | Per-encounter token counts and cost estimates persisted on EncounterCandidate |
| Reset before run           | Clean slate for re-processing                          |
| MedSpaCy from gold         | Rules + TF-ML from validated data; no LLM at runtime   |
| SurfaceForm score boost    | Human-approved mappings get 1.2x boost in resolver    |
