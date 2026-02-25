# NLP Training and Inference Pipeline — Intended Purpose

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-IP-001                      |
| Version          | 2.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-25                              |
| Classification   | Design Controls — NLP Pipeline          |

---

## 1. Scope

This document defines the intended purpose of the **NLP Training and Inference Pipeline** within the Primary Care Clinical Pathway Audit Platform. The pipeline is responsible for:

1. Generating human-verified gold training data from GP encounter narratives
2. Building a MedSpaCy-based runtime model for entity extraction, context, and SNOMED coding
3. Providing cost-effective inference at scale via the runtime pipeline
4. Feeding reviewer corrections back into the terminology graph to improve future coding (learning loop)

---

## 2. Business Context

### 2.1 Problem Statement

- **LLM-based coding** produces high-quality SNOMED CT mappings but is expensive per patient
- **Scale** requires processing thousands of patients for retrospective audit
- **Quality** requires human review (HITL) before audit data is accepted
- **Sustainability** requires a path that reduces LLM cost while maintaining quality
- **Continuous improvement** requires a feedback loop so reviewer corrections improve future results

### 2.2 Solution

A **two-pipeline, learning-loop architecture**:

1. **Training pipeline (LLM-driven)**: Generates gold data via LLM extraction + human review. Used for bootstrap and validation sampling. Writes HITL data to the Patient graph.
2. **Runtime pipeline (MedSpaCy-driven)**: Performs entity extraction, context, and coding inference using local rules and TF-ML. Used for bulk processing once validated.
3. **Terminology writeback**: Approved surface-form-to-SNOMED mappings are written back to the Coding graph as SurfaceForm nodes, enriching the resolver for future coding runs.

---

## 3. Intended Purpose

### 3.1 Primary Purpose

The NLP pipeline is intended to:

1. **Extract clinical entities** from de-identified GP encounter text (spans, semantic tags)
2. **Assign context** (negation, uncertainty, temporality, subject) to extracted entities
3. **Map entities to SNOMED CT** (and Read codes where applicable) via hybrid resolution (exact, fulltext, vector search)
4. **Produce audit-grade output** suitable for clinical pathway reconstruction

### 3.2 Secondary Purpose

- **Generate training data** for MedSpaCy from human-approved gold
- **Validate** runtime pipeline against gold before deployment
- **Support correction feedback** so user corrections improve future inference via terminology writeback (SurfaceForm nodes)
- **Track LLM usage and cost** per encounter for operational visibility

---

## 4. Intended Users

| User Role            | Interaction                                                                 |
| -------------------- | --------------------------------------------------------------------------- |
| Clinical coders      | Review LLM proposals; approve, edit, or reject; sync gold to patient graph  |
| Audit coordinators   | Run pipeline (LLM or MedSpaCy); select patients; monitor progress            |
| System operators     | Build MedSpaCy from gold; run validation; manage pipeline configuration; trigger terminology writeback |

---

## 5. Intended Use Environment

- **Deployment**: On-premises or cloud (e.g. AWS)
- **Data**: De-identified GP encounter narratives (UK primary care)
- **Terminology**: SNOMED UK Clinical Edition, Read/CTV3
- **Integration**: Patient graph (Neo4j) for encounter data and HITL workflow; Coding graph (Neo4j) for terminology only (no patient data)

---

## 6. Key Intended Behaviours

### 6.1 Training Pipeline

- **Input**: Patient ID, max encounters, worker count
- **Process**: De-identify → sentence split → LLM extract → Neo4j resolve (hybrid) → LLM disambiguate → validate
- **Output**: EncounterCandidate + ReviewTask in Patient graph; LLM usage tracked per encounter
- **Reads**: Patient graph (encounters), Coding graph (terminology)
- **Writes**: Patient graph only (EncounterCandidate, ReviewTask)

### 6.2 Runtime Pipeline

- **Input**: Patient ID(s), encounter text
- **Process**: MedSpaCy NER + context + entity linking (rules/TF-ML)
- **Output**: DOCUMENTS in Patient graph (only after human approval or when MedSpaCy is validated)

### 6.3 Gold Sync

- **Input**: Approved EncounterCandidates for a patient (from Patient graph)
- **Output**: Patient graph DOCUMENTS replaced with gold; SurfaceForm nodes written to Coding graph (terminology writeback)

### 6.4 Reset

- **Input**: Patient ID
- **Output**: All DOCUMENTS removed for that patient; Patient + Encounters + text retained

### 6.5 Terminology Writeback

- **Input**: Approved EncounterCandidates (from Patient graph)
- **Output**: SurfaceForm nodes in Coding graph with MAPS_TO relationships to Concept nodes
- **Purpose**: Enriches the resolver so human-approved surface forms are prioritised in future coding runs

---

## 7. Out of Scope

- Real-time clinical decision support
- Patient-facing interfaces
- Full MedSpaCy relation extraction (Phase 2)

---

## 8. Success Criteria

- Gold data is produced and stored in Patient graph (EncounterCandidate nodes)
- Approved surface forms are written back to Coding graph for resolver enrichment
- MedSpaCy runtime achieves F1 >= 0.90 vs gold on validation set
- Multi-select MedSpaCy run available for bulk patients once validated
- Cost per patient reduced for non-LLM path
- LLM usage and cost tracked per encounter

---

## 9. Regulatory Considerations

- Gold data is reference data; MedSpaCy training is a design change (PCCP)
- LLM prompt augmentation from corrections is a data input change (lower risk)
- Terminology writeback (SurfaceForm nodes) enriches the resolver but does not modify base SNOMED terminology
- MedSpaCy model updates require design change control

---

## 10. Data Governance

- **Patient graph**: Contains all patient-identifiable data (Patient, Encounter, EncounterCandidate, ReviewTask, Approval, Change, DOCUMENTS)
- **Coding graph**: Contains only terminology data (Term, Concept, ReadCode, SurfaceForm) — **no patient IDs, no encounter IDs**
- This separation ensures the Coding graph can never be used to re-identify patients
