# NLP Training and Inference Pipeline — Software Architecture Design

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-ARCH-001                    |
| Version          | 1.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-24                              |

---

## 1. Architecture Overview

The system uses a **two-pipeline, dual-Neo4j** architecture:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           NLP PIPELINE ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────────────┐                    ┌──────────────────────┐           │
│  │   TRAINING PIPELINE   │                    │   RUNTIME PIPELINE    │           │
│  │   (LLM-driven)       │                    │   (MedSpaCy-driven)   │           │
│  │                       │                    │                       │           │
│  │  • De-identify       │                    │  • MedSpaCy NER       │           │
│  │  • Sentence split    │                    │  • ConText / rules   │           │
│  │  • LLM extract       │                    │  • Entity linking    │           │
│  │  • Neo4j resolve      │                    │  • (Neo4j fallback)  │           │
│  │  • LLM disambiguate   │                    │                       │           │
│  │  • Validate           │                    │                       │           │
│  └──────────┬───────────┘                    └──────────┬───────────┘           │
│             │                                            │                        │
│             │  writes                                    │  writes                │
│             ▼                                            ▼                        │
│  ┌──────────────────────┐                    ┌──────────────────────┐           │
│  │   CODING NEO4J       │   gold export     │   PATIENT NEO4J       │           │
│  │   (Gold Store)       │ ───────────────► │   (Runtime Output)    │           │
│  │                      │   MedSpaCy       │                       │           │
│  │  • EncounterCandidate│   training        │  • Patient            │           │
│  │  • ReviewTask        │                   │  • Encounter         │           │
│  │  • Approval          │   sync gold       │  • DOCUMENTS          │           │
│  │  • Term, Concept     │ ◄──────────────── │    (evidence→SNOMED)  │           │
│  └──────────────────────┘                   └──────────────────────┘           │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Responsibilities

### 2.1 Training Pipeline (LLM)

| Component        | Responsibility                                      |
| ---------------- | --------------------------------------------------- |
| De-identifier   | PHI removal (names, dates, NHS numbers, etc.)        |
| SentenceSplitter| Segment text (PyRuSH / spaCy / regex)               |
| LLMExtractor    | Extract clinical terms in batches (AWS Bedrock)     |
| CodingResolver  | Map terms to SNOMED via Neo4j terminology            |
| CodingDisambiguator | Choose best SNOMED when multiple candidates (LLM) |
| Validator       | Schema, context, ontology checks                     |
| Persistence     | Write EncounterCandidate + ReviewTask to Coding graph |

**Does NOT write to Patient graph.**

### 2.2 Runtime Pipeline (MedSpaCy)

| Component        | Responsibility                                      |
| ---------------- | --------------------------------------------------- |
| MedSpaCy NER    | Entity extraction (rules + TF-ML)                    |
| ConText          | Negation, uncertainty, temporality                  |
| EntityLinker     | Map spans to SNOMED (local KB + Neo4j fallback)     |
| Persistence     | Write DOCUMENTS to Patient graph (when approved)    |

**Reads from Coding graph gold for KB; writes only to Patient graph.**

### 2.3 Coding Neo4j (Gold Store)

| Node/Relationship | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| EncounterCandidate| Sentences, terms, spans, coding, context, audit       |
| ReviewTask        | HITL queue per candidate                             |
| Approval          | Approve/edit/reject events                            |
| Change            | Audit trail (from audit_events)                       |
| Term, Concept     | SNOMED terminology (read-only for pipeline)         |

**Role**: Source of truth for gold; training data export; review workflow.

### 2.4 Patient Neo4j (Runtime Output)

| Node/Relationship | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| Patient           | Patient identity                                     |
| Encounter         | Encounter text, date                                 |
| DOCUMENTS         | Encounter → semantic node (evidence, concept_id, etc.)|

**Role**: Clinical record; persistent output of runtime pipeline only.

---

## 3. Data Flow

### 3.1 Training Flow

```
Patient Graph (read)          Training Pipeline              Coding Graph (write)
       │                              │                              │
       │  encounter text               │                              │
       │◄─────────────────────────────│                              │
       │                               │   EncounterCandidate         │
       │                               │   ReviewTask                 │
       │                               │─────────────────────────────►│
       │                               │                              │
       │                               │   [HITL Review]              │
       │                               │   [Approval]                 │
       │                               │                              │
```

### 3.2 Sync Flow

```
Coding Graph (read)            Sync Service                Patient Graph (write)
       │                              │                              │
       │  approved gold               │                              │
       │◄─────────────────────────────│                              │
       │                               │   delete old DOCUMENTS       │
       │                               │   create new DOCUMENTS       │
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
       │  gold / KB                    │
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
│  • /patients/{id}/encounters/{eid}/coded-links                   │
└────────────────────────────┬────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Patient Neo4j   │  │ Coding Neo4j    │  │ AWS Bedrock     │
│ (NEO4J_URI)     │  │ (CODING_GRAPH_  │  │ (LLM only)      │
│                 │  │  NEO4J_URI)     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## 5. Technology Stack

| Layer        | Technology                                      |
| ------------ | ------------------------------------------------ |
| API          | FastAPI                                          |
| Training NLP | spaCy, PyRuSH, AWS Bedrock (LLM)                  |
| Runtime NLP | MedSpaCy, spaCy, scispaCy                        |
| Terminology  | Neo4j (Coding graph)                             |
| Patient data | Neo4j (Patient graph)                            |
| UI           | Next.js, React                                   |

---

## 6. Key Design Decisions

| Decision                    | Rationale                                              |
| -------------------------- | ------------------------------------------------------ |
| Dual Neo4j                 | Separate gold/training from patient clinical data      |
| Training writes Coding only | Patient graph stays runtime output; no pre-review poll |
| Sync as explicit step      | User controls when gold is applied to patient record  |
| Reset before run           | Clean slate for re-processing                          |
| MedSpaCy from gold         | Rules + TF-ML from validated data; no LLM at runtime   |
