# Intended Use Statement

| Field            | Value                                               |
| ---------------- | --------------------------------------------------- |
| Document ID      | DC-IU-001                                           |
| Version          | 0.2.0-draft                                         |
| Status           | Draft                                               |
| Date             | 2026-02-23                                          |
| Classification   | QMS -- Design Controls                              |

---

## 1  Product Identity

**Product name:** Primary Care Clinical Pathway Audit Platform (working title)

**Regulatory context:** The product is software that processes clinical
records and applies AI-assisted coding and pathway reconstruction for
retrospective audit purposes. It does not provide real-time clinical
decision support and is not intended to influence individual patient
treatment decisions. Classification under MHRA / UKCA guidance for
Software as a Medical Device (SaMD) should be assessed, but the intended
output -- structured audit data for population-level quality improvement
-- places it toward the lower-risk end of the SaMD spectrum.

**Platform model:** The system is a programme-agnostic clinical pathway
audit platform. A **Programme** is a clinical audit with its own domain
definitions, milestone definitions, guideline rules, quality targets,
and pipeline configurations -- all stored as data, not code. Adding
support for a new clinical programme requires configuration changes
only, with no modifications to the platform software.

**Launch programme:** National Cancer Diagnosis Audit (NCDA). The NCDA
collects data on cancer patients' routes to diagnosis in primary care,
examining the period from first presentation of relevant symptoms through
referral, diagnosis, and first definitive treatment.

---

## 2  Intended Purpose

The system performs **retrospective, AI-assisted analysis of primary care
encounter records** to reconstruct structured clinical pathways for
national clinical audit programmes.

The platform provides a set of composable **capabilities** that can be
assembled into different **pipelines** per programme and use case:

### 2.1  Core capabilities

1. **Encounter shortlisting** -- searches a patient's GP record across
   programme-defined clinical domains using hybrid retrieval (keyword
   matching, full-text search, and clinical vector embeddings via
   scispaCy).

2. **SNOMED CT coding** -- assigns standardised clinical terminology
   codes to free-text encounter narratives using a spaCy-based NLP
   pipeline with biomedical NER (scispaCy), UMLS entity linking to
   SNOMED CT, negation detection (negspaCy), context classification
   (patient / family / resolved / plan), and confidence scoring. LLM
   disambiguation is used as a fallback for low-confidence or ambiguous
   cases only.

3. **Abnormal detection** -- flags abnormal laboratory and investigation
   results against reference ranges.

4. **Guideline compliance checking** -- matches coded encounter patterns
   against programme-specific clinical guidelines and generates alerts
   where pathways deviate from expected practice.

5. **Anchor detection** -- identifies the key milestone events that
   structure a clinical episode, using programme-defined milestone
   definitions and coded concepts.

6. **Episode building** -- constructs a `ClinicalEpisode` for each
   distinct pathway, linking encounters to milestones and classifying
   the episode status as *confirmed*, *excluded*, or *inconclusive*
   using rule-based classification with LLM fallback for edge cases.

7. **Quality validation** -- checks completed episodes for duration
   outliers, missing milestones, temporal anomalies, low-confidence
   classifications, coding contradictions, and unactioned alerts.

8. **Metrics calculation** -- calculates pathway durations against
   programme-defined targets (e.g., NHS waiting time standards).

9. **Interpretation** -- LLM-assisted clinical interpretation of
   findings, with mandatory human review gate.

### 2.2  Composable pipelines

Capabilities are assembled into pipelines defined as workflow graphs.
Pipelines support branching, fan-out/fan-in, conditional edges, and
cross-pipeline triggers. Example configurations:

- **Full audit** -- all capabilities in sequence for complete pathway
  reconstruction
- **Quick code** -- encounter shortlisting and SNOMED coding only
- **Screen and alert** -- coding, abnormal detection, and guideline
  checking, with conditional branching to an interpretation pipeline
  when critical findings are detected

All pipeline outputs are proposals that require human review before
they are accepted as audit data.

### 2.3  NCDA launch configuration

For the NCDA programme, the platform is configured with:

- 20+ clinical domains (cancer types, fast-track referrals, treatment,
  symptoms, comorbidities, investigations, demographics, risk factors)
- Milestone definitions: first presentation, referral, specialist visit,
  investigation, diagnosis, treatment
- Quality targets: Faster Diagnosis Standard (FDS) 28 days,
  Decision-to-Treat (DTT) 31 days, Referral-to-Treatment (RTT) 62 days
- Guideline rules: NICE NG12 (Suspected cancer: recognition and referral)
  and Cancer Signal Surveillance (safety-net) patterns

---

## 3  Intended Users

| User role                             | Interaction                                                                                     |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Clinical audit teams                  | Review AI-generated episode timelines and coded encounter data; approve, edit, or reject labels. |
| Pathway coordinators                  | Investigate wait-time breaches, outlier episodes, and alerts flagged by quality checks.          |
| Primary care quality improvement leads | Use aggregated audit outputs to identify systemic pathway delays and improvement opportunities. |
| Human reviewers (clinical coders)     | Validate SNOMED CT coding proposals per encounter; corrections feed back to improve the system.  |
| Programme administrators              | Configure programmes: domain definitions, milestone types, guideline rules, quality targets.     |
| System administrators                 | Configure platform infrastructure, pipeline definitions, and AI model parameters.               |

The system enforces role-based access (builder, reviewer, releaser,
operator) so that no AI-generated output can be finalised without
appropriate human authorisation.

---

## 4  Intended Patient Population

- Patients registered in English primary care (GP) settings with
  conditions relevant to the configured clinical audit programme(s).
- For the NCDA launch programme: patients with suspected or confirmed
  cancer across all cancer types present in the NCDA value sets.
- The platform's patient population expands as new programmes are
  configured (e.g., diabetes, cardiovascular, respiratory).

### 4.1  NCDA domain set

| Domain group        | Domains                                                                                                    |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| Milestone domains   | cancer_types, fast_track_referrals, treatment, referral_outcomes, seen_by_specialist                       |
| Clinical domains    | symptoms, comorbidities, physical_signs, investigations, observable_entities, screening                    |
| Risk & history      | cancer_risk_factors, family_history, lifestyle_factors                                                     |
| Demographic domains | ethnicity, housebound_status, living_arrangement, communication_difficulty, english_language_competency    |
| Pathway domains     | place_of_presentation, temporal_analysis, performance_status (WHO)                                         |

---

## 5  Intended Use Environment

**Setting:** NHS primary care organisations participating in national
clinical audit programmes.

**Data sources:**
- Patient encounter records accessed via FHIR R4 APIs (Encounter,
  DocumentReference, Patient resources)
- UMLS Metathesaurus (filtered to UK SNOMED CT edition) as the
  terminology source
- Programme configuration resources (ValueSet, ConceptMap, Measure,
  PlanDefinition) defining domains, milestones, guidelines, and targets

**Infrastructure:**
- Neo4j graph database for clinical data, episode persistence,
  programme configuration, and workflow definitions
- spaCy + scispaCy NLP pipeline with UMLS entity linker for SNOMED CT
  coding, run locally on compute infrastructure
- LLM inference (OpenAI / Anthropic Claude) for disambiguation fallback
  and interpretation capabilities
- Azure AD for authentication and role-based access control
- Redis for task queue (Streams), distributed locking, and configuration
  caching

**Deployment:** Cloud-hosted on Azure Container Apps, multi-tenant
capable. The system is accessed via a REST API; it does not have a
direct patient-facing interface.

---

## 6  Clinical Workflow Integration

The system operates via **composable, asynchronous pipelines** triggered
per patient, per organisation, or per encounter, running as background
jobs dispatched through Redis Streams.

### 6.1  Pipeline architecture

Pipelines are directed workflow graphs defined in Neo4j. Each step
invokes a capability from the platform's registry. Steps are connected
by edges that can carry conditions, enabling branching based on the
output of the previous step.

```
Example: Screen-and-Alert pipeline

  Shortlist encounters
    │
    ▼
  Code encounters (spaCy NLP)
    │
    ├──▶ Detect abnormals
    │       │
    │       ├── (abnormals found) ──▶ Check guidelines
    │       │                            │
    │       │                            ├── (critical alerts) ──▶ Trigger: interpretation pipeline
    │       │                            │
    │       │                            └── (no critical alerts) ──▶ Done
    │       │
    │       └── (no abnormals) ──▶ Done
    │
    └──▶ Done (coding complete)
```

```
Example: Full NCDA Audit pipeline

  Shortlist encounters → Code encounters → Detect abnormals → Detect anchors
  → Build episodes → Check quality → Check guidelines → Calculate metrics → Done
```

Pipelines can trigger other pipelines asynchronously. A coding pipeline
can branch to an interpretation pipeline; an interpretation pipeline can
include a human review gate that pauses execution until a reviewer acts.

### 6.2  Human-in-the-loop review

- The pipeline generates **proposals** (coded encounters, episode
  classifications, quality issues, guideline alerts).
- A review queue presents items requiring human validation.
- Reviewers can confirm, edit, or reject each proposal.
- Corrections feed back into NLP model retraining for continuous
  improvement.
- No AI-generated output is treated as final audit data until a human
  reviewer with the appropriate role has approved it.

---

## 7  Contraindications and Exclusions

The following uses are **explicitly out of scope**:

| Exclusion                                    | Rationale                                                                                  |
| -------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Real-time clinical decision support           | The system is retrospective only; it analyses historical records after the clinical event.  |
| Clinical diagnosis                            | The system reconstructs and codes existing clinical narratives; it does not make diagnoses. |
| Treatment recommendation                      | No treatment advice is generated or implied by the pipeline outputs.                       |
| Replacement for clinical judgment              | All outputs are proposals subject to mandatory human review.                               |
| Direct patient-facing use                      | The system has no patient-facing interface; outputs are consumed by audit professionals.    |
| Screening or triage of symptomatic patients    | The system does not process live patient presentations.                                    |

---

## 8  Assumptions and Dependencies

1. Patient encounter records are available in a structured FHIR R4 format
   with free-text clinical narratives accessible via DocumentReference
   resources.
2. UMLS Metathesaurus with UK SNOMED CT edition is available and current.
3. Programme-specific value sets, concept maps, milestone definitions,
   guideline rules, and quality targets are maintained in Neo4j.
4. LLM inference (OpenAI / Anthropic) is available for disambiguation
   fallback and interpretation capabilities.
5. Human reviewers with appropriate clinical knowledge are available to
   validate pipeline outputs within a reasonable timeframe.
6. Quality target values are maintained in programme configuration and
   updated when national policy changes.

---

*This document will be refined as the production architecture is
finalised. It serves as the foundation for derived design control
documents including user needs, design inputs, risk analysis, and
verification/validation protocols.*
