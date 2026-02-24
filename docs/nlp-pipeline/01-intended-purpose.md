# NLP Training and Inference Pipeline — Intended Purpose

| Field            | Value                                    |
| ---------------- | ---------------------------------------- |
| Document ID      | NLP-PIPELINE-IP-001                      |
| Version          | 1.0.0                                   |
| Status           | Draft                                   |
| Date             | 2026-02-24                              |
| Classification   | Design Controls — NLP Pipeline          |

---

## 1. Scope

This document defines the intended purpose of the **NLP Training and Inference Pipeline** within the Primary Care Clinical Pathway Audit Platform. The pipeline is responsible for:

1. Generating human-verified gold training data from GP encounter narratives
2. Building a MedSpaCy-based runtime model for entity extraction, context, and SNOMED coding
3. Providing cost-effective inference at scale via the runtime pipeline

---

## 2. Business Context

### 2.1 Problem Statement

- **LLM-based coding** produces high-quality SNOMED CT mappings but is expensive per patient
- **Scale** requires processing thousands of patients for retrospective audit
- **Quality** requires human review (HITL) before audit data is accepted
- **Sustainability** requires a path that reduces LLM cost while maintaining quality

### 2.2 Solution

A **two-pipeline architecture**:

1. **Training pipeline (LLM-driven)**: Generates gold data via LLM extraction + human review. Used for bootstrap and validation sampling.
2. **Runtime pipeline (MedSpaCy-driven)**: Performs entity extraction, context, and coding inference using local rules and TF-ML. Used for bulk processing once validated.

---

## 3. Intended Purpose

### 3.1 Primary Purpose

The NLP pipeline is intended to:

1. **Extract clinical entities** from de-identified GP encounter text (spans, semantic tags)
2. **Assign context** (negation, uncertainty, temporality, subject) to extracted entities
3. **Map entities to SNOMED CT** (and Read codes where applicable)
4. **Produce audit-grade output** suitable for clinical pathway reconstruction

### 3.2 Secondary Purpose

- **Generate training data** for MedSpaCy from human-approved gold
- **Validate** runtime pipeline against gold before deployment
- **Support correction feedback** so user corrections improve future inference

---

## 4. Intended Users

| User Role            | Interaction                                                                 |
| -------------------- | --------------------------------------------------------------------------- |
| Clinical coders      | Review LLM proposals; approve, edit, or reject; sync gold to patient graph  |
| Audit coordinators   | Run pipeline (LLM or MedSpaCy); select patients; monitor progress            |
| System operators     | Build MedSpaCy from gold; run validation; manage pipeline configuration     |

---

## 5. Intended Use Environment

- **Deployment**: On-premises or cloud (e.g. AWS)
- **Data**: De-identified GP encounter narratives (UK primary care)
- **Terminology**: SNOMED UK Clinical Edition, Read/CTV3
- **Integration**: Patient graph (Neo4j) for encounter data; Coding graph (Neo4j) for terminology and gold

---

## 6. Key Intended Behaviours

### 6.1 Training Pipeline

- **Input**: Patient ID, max encounters, worker count
- **Process**: De-identify → sentence split → LLM extract → Neo4j resolve → LLM disambiguate → validate
- **Output**: EncounterCandidate + ReviewTask in Coding graph (no writes to Patient graph)

### 6.2 Runtime Pipeline

- **Input**: Patient ID(s), encounter text
- **Process**: MedSpaCy NER + context + entity linking (rules/TF-ML)
- **Output**: DOCUMENTS in Patient graph (only after human approval or when MedSpaCy is validated)

### 6.3 Gold Sync

- **Input**: Approved EncounterCandidates for a patient
- **Output**: Patient graph DOCUMENTS replaced with gold

### 6.4 Reset

- **Input**: Patient ID
- **Output**: All DOCUMENTS removed for that patient; Patient + Encounters + text retained

---

## 7. Out of Scope

- Real-time clinical decision support
- Patient-facing interfaces
- Direct modification of SNOMED terminology (read-only)
- Full MedSpaCy relation extraction (Phase 2)

---

## 8. Success Criteria

- Gold data is produced and stored in Coding graph
- MedSpaCy runtime achieves F1 ≥ 0.90 vs gold on validation set
- Multi-select MedSpaCy run available for bulk patients once validated
- Cost per patient reduced for non-LLM path

---

## 9. Regulatory Considerations

- Gold data is reference data; MedSpaCy training is a design change (PCCP)
- LLM prompt augmentation from corrections is a data input change (lower risk)
- MedSpaCy model updates require design change control
