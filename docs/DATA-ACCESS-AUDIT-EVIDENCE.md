# Data Access Audit Evidence Pack

| Field           | Value                                                  |
| --------------- | ------------------------------------------------------ |
| Document ID     | DA-AE-001                                              |
| Version         | 1.0.0                                                  |
| Status          | Draft                                                  |
| Date            | 2026-03-03                                             |
| Classification  | QMS -- Data Governance / Information Governance         |
| Prepared by     | Quality Engineering                                    |

## Purpose

This document collates ISO-aligned evidence for audit and NHS data-access
assurance across five domains: source record governance, de-identification,
data lineage, labelling quality, and synthetic / human-in-the-loop (HITL)
data management. Each section maps what the repository currently provides,
which artefacts serve as evidence, and where gaps remain.

Standards referenced: ISO 13485:2016, IEC 62304:2006, ISO 14971:2019,
IEC 81001-5-1:2021, UK GDPR / DPA 2018, NHS DSPT.

---

## 1  Source Record

This section covers controller and processor roles, extraction scope,
cohort criteria, data-sharing agreements, and lawful basis.

### 1.1  Controller / processor roles

| Role       | Entity                           | Evidence location                         |
| ---------- | -------------------------------- | ----------------------------------------- |
| Controller | NHS Primary Care Organisation    | `design-controls/user-needs/UN-LEO-AI-015.yaml` (stakeholder: Data Protection Officer, NHS Primary Care Organisation) |
| Processor  | Platform operator (LEO AI)       | `design-controls/DC-TM-SEC-001-threat-model.yaml` (system_context.deployment, services, external_services) |

**Gap:** The threat model notes "Processor agreements for third-party data
processing -- insufficient evidence" under UK GDPR Article 28. A formal
Data Processing Agreement (DPA) document is not yet stored in the
repository. This should be added as a controlled QMS artefact.

### 1.2  Extraction date range and source system

| Parameter         | Value                                                    | Evidence                                      |
| ----------------- | -------------------------------------------------------- | --------------------------------------------- |
| Source system      | SystmOne / EMIS GP clinical record exports (FHIR R4)    | `design-controls/intended-use.md` Section 5   |
| Data format        | FHIR R4 Encounter, DocumentReference, Patient resources  | `design-controls/intended-use.md` Section 5   |
| Date range         | Retrospective; defined per programme configuration       | `design-controls/intended-use.md` Section 2.3 |
| Launch programme   | National Cancer Diagnosis Audit (NCDA)                   | `design-controls/intended-use.md` Section 1   |

### 1.3  Cohort criteria

For the NCDA launch programme, the cohort is defined as patients
registered in English primary care with suspected or confirmed cancer
across all cancer types in the NCDA value sets.

Domain configuration has been migrated to Neo4j. The primary source of
truth is FHIR ValueSet resources stored in the Knowledge Graph:

- `DomainRegistry.from_fhir()` (`libs/domain_config/registry.py`) loads
  domain definitions from `ncda-*` ValueSet nodes at startup, parsing
  `compose.include.concept` entries and `/domain-config` extensions for
  milestone types, time windows, and semantic tags.
- `AuditDomain` nodes linked to ValueSet subdomains via `HAS_SUBDOMAIN`
  (`services/analytics_api/app/routers/domains.py`) allow runtime CRUD
  of domain configuration through the Analytics API.
- `seed_fhir_config.py` seeds the initial ValueSet nodes into Neo4j.
- Fallback: when FHIR data is unavailable, `DomainRegistry.from_defaults()`
  loads from predefined Python configs; JSON mapping files in
  `configs/snomed/` serve as a secondary reference.
- `expand_domains_with_kg()` (`libs/ner/domain_loader.py`) enriches each
  domain's surface forms by querying Term and SurfaceForm nodes from the
  Knowledge Graph, adding SNOMED descendants and HITL-approved mappings.

Additional cohort evidence:

- `design-controls/intended-use.md` Section 4 -- intended patient population
- `services/analytics_api/app/data/nhs_screening_cohorts.json` -- screening cohort presets

### 1.4  Agreements

| Agreement type                 | Status        | Evidence                                                       |
| ------------------------------ | ------------- | -------------------------------------------------------------- |
| Data Processing Agreement      | **GAP**       | Referenced in threat model Article 28 but not yet formalised    |
| Data Protection Impact Assessment (DPIA) | Draft | `design-controls/user-needs/UN-LEO-AI-021.yaml` (use case step 7: "Officer signs off the DPIA") |
| NHS DSPT compliance            | Planned       | `design-controls/user-needs/UN-LEO-AI-021.yaml`               |

### 1.5  Lawful basis

| Basis                                | Evidence                                                        |
| ------------------------------------ | --------------------------------------------------------------- |
| UK GDPR Article 9 (special category) | `DC-TM-SEC-001-threat-model.yaml` (data_classifications)       |
| UK GDPR Article 25 (by design)       | `UN-LEO-AI-015.yaml` (derived_from)                            |
| UK GDPR Article 32 (security)        | `UN-LEO-AI-021.yaml` (derived_from)                            |
| UK GDPR Article 28 (processor)       | `DC-TM-SEC-001-threat-model.yaml` (**gap noted**)              |
| UK GDPR Article 35 (DPIA)            | `DC-TM-SEC-001-threat-model.yaml` (referenced; draft)          |

**Gap:** A formal Lawful Basis Assessment document (specifying the exact
Article 6 and Article 9 conditions relied upon) is not yet in the
repository. The threat model references the relevant articles but does
not record the specific condition (e.g. Article 9(2)(h) health care,
Article 9(2)(j) research).

---

## 2  De-identification

### 2.1  Automated de-identification steps

The platform applies a layered de-identification pipeline. Three
modules work together:

**Layer 1 -- Regex de-identification** (`libs/utils/deidentify.py`)

Strips the following PII patterns from GP encounter text before it
reaches any external LLM or is stored in training artefacts:

| Pattern               | Replacement     |
| --------------------- | --------------- |
| SURNAME, Forename (SystmOne Role) | `[PERSON]`   |
| SURNAME, Forename (Title)         | `[PERSON]`   |
| Dr/Mr/Mrs/Ms/Miss/Prof Surname    | `[PERSON]`   |
| ALL-CAPS surname, Firstname       | `[PERSON]`   |
| Named healthcare facilities        | `[LOCATION]` |
| Deployment-specific organisations  | `[ORGANISATION]` |
| NHS numbers (10-digit)             | `[NHS_NUMBER]` |
| UK postcodes                       | `[POSTCODE]` |
| UK phone numbers                   | `[PHONE]`    |
| Email addresses                    | `[EMAIL]`    |
| UK street addresses                | `[ADDRESS]`  |
| Dates (DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD) | `[DATE]` |

Intentionally preserved (clinical utility): coded terms, medication
names, clinical values, units, times.

**Layer 2 -- Pipeline de-identification** (`libs/deid/deid.py`)

Applied before NER extraction (GAP-008). Handles NHS numbers, postcodes,
dates, phone, email, and configurable organisation names via
`DEID_LOCAL_ORGS` environment variable. Returns a `DeidResult` with
replacement tracking for offset adjustment.

**Layer 3 -- Export safety net** (`services/api/app/services/export_service.py`)

Re-applies `deidentify_text()` at export time as a secondary safety net,
catching any text processed by an older version of the patterns.

### 2.2  Human review sampling

- De-identification validation test suite with known PHI patterns
  (`R-LEO-AI-009.yaml`, mitigation measure 3)
- Monthly scanning of outputs and logs for PHI patterns
  (`R-LEO-AI-009.yaml`, monitoring section)
- Training record de-identification validator (`libs/ner/deid_validator.py`)
  scans text and metadata for residual identifiers after the de-id pass

**Gap:** No documented sampling plan specifying what percentage of
de-identified records are manually reviewed, by whom, and at what
frequency. The validator is automated but manual spot-check procedures
are not formalised.

### 2.3  Residual re-identification risk assessment

From risk management (`R-LEO-AI-009.yaml`):

| Metric         | Initial | Residual |
| -------------- | ------- | -------- |
| Severity       | 4       | 4        |
| Probability    | 2       | 1        |
| Detectability  | 2       | 1        |
| RPN            | 16      | 4        |
| Risk level     | High    | Low      |
| Acceptability  | --      | Acceptable |

Known residual risk: First names embedded in free-text narrative
(e.g. "discussed with Christopher") are not catchable by regex alone.
The threat model recommends an NER-based name detection pass (GAP-008).

From the threat model (`DC-TM-SEC-001`): "Incomplete pseudonymisation
of special category data before third-party processing" is listed as a
threat, with distroless containers and de-identification pipeline as
mitigations.

### 2.4  Sign-off for each release

| Control                              | Evidence                                         |
| ------------------------------------ | ------------------------------------------------ |
| De-id step logged before data reaches Coding layer | `VAL-LEO-AI-006.yaml`               |
| Source encounter text never written to Coding graph | `R-LEO-AI-009.yaml` mitigation 2    |
| Data governance verification (VT-014) | `VT-LEO-AI-014.yaml` -- 100% pass threshold     |

**Gap:** No per-release sign-off document or checklist for
de-identification adequacy. Recommend adding a release-gate checklist
that includes de-identification regression test results.

---

## 3  Lineage Log

### 3.1  Sentence-splitting rules

Implemented in `services/coding_worker/app/pipeline/sentence_splitter.py`:

- **Primary mode:** MedSpaCy PyRuSH sentencizer (clinical-aware rules)
- **Fallback mode:** Regex split on `(?<=[.!?])\s+|\n+`
- **Mode selection:** Automatic; PyRuSH if `medspacy` is importable
- **Offsets preserved:** Each `SentenceChunk` carries `start` and `end`
  character positions relative to the source document
- **Tests:** `tests/test_sentence_splitter.py` covers deduplication,
  empty text, single/multiple sentences, newline-separated, offset
  preservation

### 3.2  Filters

- **Encounter text classification:** `libs/classifiers/` with
  `encounter_rules.json` -- rule-based + model-based filtering of
  admin, admission, workflow entries (documented in V3 validation report)
- **Domain filtering:** FHIR ValueSet resources in Neo4j define which
  SNOMED domains are in scope per programme (see Section 1.3); fallback
  JSON files in `configs/snomed/` serve as secondary reference
- **Exclusion detection:** `libs/exclusion_detector/` identifies
  clinical exclusion patterns

### 3.3  Deduplication

- **Line-level deduplication:** `deduplicate_lines()` in
  `sentence_splitter.py` removes consecutive duplicate lines (common in
  EHR exports)
- **Training label deduplication:** `libs/ner/training_label_writer.py`
  uses `label_id = SHA-256(encounter_id + canonical_entities_fingerprint)`
  as the deduplication key. A record with the same encounter and
  identical entity spans is idempotent.

### 3.4  Dataset version IDs

| Artefact                  | Versioning mechanism                                      | Evidence                                    |
| ------------------------- | --------------------------------------------------------- | ------------------------------------------- |
| Extraction contract       | `CONTRACT_VERSION = "1.1"` stamped on every `:DOCUMENTS` relationship and `EncounterCandidate` node | `libs/ner/extractor_contract.py`           |
| Training label schema     | `SCHEMA_VERSION = "1.0"` on every `TrainingLabel` node    | `libs/ner/training_label_writer.py`         |
| NER model version         | `ModelRecord.model_version` + `training_dataset_version` + `schema_version` + `deid_version` | `libs/model_registry/registry.py`          |
| Export manifest            | SHA-256 hash of train/validation splits, candidate IDs, timestamp | `services/api/app/services/export_service.py` |
| Annotation guidelines     | `GUIDELINES_VERSION = "exclusion-domain-v1"`              | `scripts/generate_exclusion_training.py`    |
| Provenance on graph links | `model_name`, `model_version`, `contract_version`, `run_id` on every `:DOCUMENTS` relationship | `libs/cypher/documents_queries.py`         |

### 3.5  Access controls

| Control                            | Evidence                                                 |
| ---------------------------------- | -------------------------------------------------------- |
| Dual Neo4j (Patient graph / Knowledge graph) | `UN-LEO-AI-015.yaml`, `VT-LEO-AI-014.yaml`    |
| Cross-database queries prohibited  | `VT-LEO-AI-014.yaml` TC-003                             |
| Azure AD / Entra ID authentication | `UN-LEO-AI-021.yaml`                                    |
| Role-based access (builder, reviewer, releaser, operator) | `design-controls/intended-use.md` Section 3 |
| Managed Identity (no connection strings) | `DC-TM-SEC-001` trust zones                      |
| ACA internal-ingress (internal services not externally addressable) | `DC-TM-SEC-001` T-ACA-001 |
| Encryption at rest (AES-256) and in transit (TLS 1.2+) | `UN-LEO-AI-021.yaml`                  |

### 3.6  SurfaceForm writeback (learning loop lineage)

SurfaceForm nodes in the Knowledge Graph are the central mechanism by
which HITL corrections feed back into the terminology resolver. Each
SurfaceForm records a human-approved mapping from a clinical surface
form (e.g. "CXR", "2WW referral") to a SNOMED concept, with full
provenance.

**Creation pathways:**

| Source                       | Trigger                                              | Evidence                                                    |
| ---------------------------- | ---------------------------------------------------- | ----------------------------------------------------------- |
| HITL writeback               | Reviewer approves an EncounterCandidate              | `services/terminology_api/app/services/writeback_service.py` |
| Coding review recheck        | Auto-resolved LLM terms persisted with source tag    | `services/api/app/routers/training.py` (`_writeback_recheck_surface_form`) |
| Manual mapping               | User creates mapping via API                         | `POST /terminology/surface-forms/upsert-mapping`            |
| NCDA preapproved load        | Bulk load of guideline synonyms                      | `scripts/load_preapproved_surface_forms.py`                 |

**Storage schema (Knowledge Graph -- no patient data):**

- Node: `(:SurfaceForm {form, normalized, source, status, created_by, created_at, last_seen_at})`
- Relationship: `(SurfaceForm)-[:MAPS_TO {confidence, approved_by, approved_at, provenance}]->(Concept)`
- Constraints: unique on `normalized`, fulltext index on `form`, vector index on `embedding`
- Evidence: `libs/cypher/schema_constraints.py`, `services/terminology/scripts/loaders/schema.py`

**Usage in runtime pipeline:**

The hybrid coding resolver (`services/terminology_api/app/services/coding_resolver.py`)
uses SurfaceForm in four search branches:

1. **Exact match** on `SurfaceForm.normalized`
2. **Fulltext search** via `surface_form_fulltext` index
3. **Vector search** via `surface_form_embedding_idx`
4. **Term-based search** (fallback when no SurfaceForm nodes exist)

SurfaceForm matches receive a 1.2x score boost, reflecting the higher
trust of human-approved mappings over automated term matches.

**Domain expansion:**

`expand_domains_with_kg()` (`libs/ner/domain_loader.py`) queries both
Term and SurfaceForm nodes to enrich each domain's surface form set.
This means HITL corrections on one patient propagate as improved
recognition across all future patients in the same domain.

**Lineage significance:**

Every SurfaceForm carries `approved_by`, `approved_at`, `source`, and
`provenance` on the MAPS_TO relationship, creating a complete audit
trail from the original encounter text through HITL review to the
terminology enrichment that improves future coding runs.

### 3.7  Retention and deletion dates

| Parameter                | Value             | Evidence                                    |
| ------------------------ | ----------------- | ------------------------------------------- |
| Evidence retention       | 7 years           | `VT-LEO-AI-014.yaml` (evidence.retention_period) |
| Evidence immutability    | true              | `VT-LEO-AI-014.yaml` (evidence.immutability) |
| Right to erasure target  | Less than 24 hours | `UN-LEO-AI-015.yaml` (success_metrics)      |
| Data deletion SLA        | Less than 24 hours | `UN-LEO-AI-015.yaml`                        |
| Evidence storage         | `/evidence-bundles/LEO-AI/` on Azure Blob    | `VAL-LEO-AI-002.yaml` (evidence_bundle)    |

**Gap:** No formal data retention policy document specifying retention
periods for each data class (patient data, training data, audit logs,
model artefacts). The 7-year figure appears only in verification test
metadata. Recommend a standalone Data Retention Schedule document.

---

## 4  Labelling Dossier

### 4.1  Annotation schema

The NER annotation schema is defined across:

- **Entity types:** `disorder`, `finding`, `procedure`, `substance`,
  `observable_entity`, `situation`, `product`, `regime/therapy`,
  `qualifier_value`, plus pathway-specific types: `X_PATHWAY_MILESTONE`,
  `X_NEGATION_CUE`, `X_TEMPORAL`, `X_DOSAGE`, `X_FREQUENCY`, `X_ROUTE`
- **Assertion statuses:** `present`, `absent`, `possible`, `historical`,
  `hypothetical`, `family`
- **Relations:** `triggers`, `negates`, `treats`, `dosage_of`,
  `frequency_of`, `diagnoses`
- **Normalised codes:** SNOMED CT system with `code` and `display`
- **Schema evidence:** `scripts/generate_exclusion_training.py`
  (canonical training example generator), `libs/ner/extractor_contract.py`
  (`ExtractionItem` dataclass)

### 4.2  Annotation guidance

| Guidance artefact                | Version                  | Evidence                                       |
| -------------------------------- | ------------------------ | ---------------------------------------------- |
| Exclusion domain guidelines      | `exclusion-domain-v1`    | `scripts/generate_exclusion_training.py` (GUIDELINES_VERSION) |
| LLM extraction prompt (system)   | Embedded in `llm_extractor.py` | UK GP abbreviation lists, assertion rules, semantic tag rules, exclusion rules |
| HITL review training             | Participant criteria: "QA staff with clinical coding experience or anchor review training" | `VAL-LEO-AI-002.yaml` |
| Labelling instructions           | `manual_label` values: TRUE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE, NOT_APPLICABLE | `scripts/vnv_anchor_report.py` |

### 4.3  Annotator competence

| Requirement                      | Evidence                                                |
| -------------------------------- | ------------------------------------------------------- |
| Selection criteria               | "QA staff with clinical coding experience or anchor review training" | 
| Participant count (validation)   | 5 internal QA staff                                     |
| Training prerequisite            | "Participants trained on review interface and acceptance/rejection workflow" |

Evidence: `VAL-LEO-AI-002.yaml` (metadata.participants)

**Gap:** No formal annotator competence assessment record (e.g. a
qualification test where annotators must achieve a threshold score on a
known-answer set before they are permitted to label production data).

### 4.4  Inter-annotator agreement

| Metric                          | Target                | Evidence                                      |
| ------------------------------- | --------------------- | --------------------------------------------- |
| Review decision accuracy        | >= 90% vs ground truth | `VAL-LEO-AI-002.yaml` SCENARIO-001            |
| Anchor review accuracy          | >= 90% vs ground truth | `VAL-LEO-AI-002.yaml` SCENARIO-002            |
| Edit quality                    | >= 85% correct final code | `VAL-LEO-AI-002.yaml` SCENARIO-001         |

**Gap:** No formal Cohen's kappa or Fleiss' kappa inter-annotator
agreement score is computed or recorded. The validation protocol measures
individual accuracy against ground truth but does not compute pairwise
agreement between annotators. Recommend adding IAA computation to the
validation execution.

### 4.5  Quality checks and corrections history

| Quality mechanism               | Evidence                                                 |
| ------------------------------- | -------------------------------------------------------- |
| Gold-standard labelled dataset   | `VT-LEO-AI-002.yaml`, `VT-LEO-AI-003.yaml`             |
| Per-entity-type precision/recall | `VT-LEO-AI-002.yaml` (per-entity metrics for audit trail) |
| Regression test blocking deploys | `.cursor/rules/code-quality.mdc` ("Regression tests block deploys if accuracy drops below baseline") |
| Corrections feed back to model   | `design-controls/intended-use.md` Section 6.2 ("Corrections feed back into NLP model retraining") |
| Label source tracking            | `TrainingLabel.source` field: `hitl_approval`, `coding_correction`, `anchor_mining`, `seed` |
| Quality score                    | `quality_score` (0.0-1.0) on every TrainingLabel node   |
| Audit trail per review action    | `VAL-LEO-AI-002.yaml` acceptance criterion: "100% of review actions have a recorded audit entry" |

---

## 5  Synthetic / HITL Register

### 5.1  Generator model and version

| Model / tool                | Version tracking                            | Evidence                                     |
| --------------------------- | ------------------------------------------- | -------------------------------------------- |
| LLM extractor (primary)    | AWS Bedrock Claude                          | `DC-TM-SEC-001` external_services            |
| LLM extractor (fallback)   | Azure OpenAI GPT-4o                         | `DC-TM-SEC-001` external_services            |
| NER runtime model           | `ModelRecord.model_version` lifecycle: registered -> offline_validated -> canary -> promoted | `libs/model_registry/registry.py` |
| Synthetic training data     | `ANNOTATOR_ID = "synthetic-v1"`             | `scripts/generate_exclusion_training.py`     |
| spaCy NER training config   | `temp_transformer_ner.cfg`                  | Repository root                              |

### 5.2  Prompts

| Prompt artefact             | Location                                     | Content summary                              |
| --------------------------- | -------------------------------------------- | -------------------------------------------- |
| LLM extraction system prompt | `libs/prompts/` (prompt registry), `services/coding_worker/` | UK GP abbreviations, assertion rules, semantic tags, exclusion rules |
| Few-shot examples           | `libs/prompts/` (few-shot builders)          | Dynamically assembled from approved examples |
| Synthetic data prompts       | Inline in `scripts/generate_exclusion_training.py` | 78 hand-authored clinical scenarios         |

### 5.3  Review criteria

| Gate                         | Threshold                                    | Evidence                                     |
| ---------------------------- | -------------------------------------------- | -------------------------------------------- |
| Offline validation precision | >= 0.80                                      | `libs/model_registry/registry.py` (`_MIN_PRECISION`) |
| Offline validation recall    | >= 0.75                                      | `libs/model_registry/registry.py` (`_MIN_RECALL`) |
| Canary precision             | >= 0.78                                      | `libs/model_registry/registry.py` (`_MIN_CANARY_PRECISION`) |
| Canary recall                | >= 0.72                                      | `libs/model_registry/registry.py` (`_MIN_CANARY_RECALL`) |
| Force promotion              | Allowed with mandatory notes documenting override reason | `registry.py` `promote()` method         |
| Rollback                     | Automatic demotion of active model, restore of rollback target | `registry.py` `rollback()` method     |

### 5.4  Synthetic data flagging

| Flag                         | Value                                        | Evidence                                     |
| ---------------------------- | -------------------------------------------- | -------------------------------------------- |
| Annotator ID                 | `synthetic-v1`                               | `scripts/generate_exclusion_training.py`     |
| De-identification method     | `synthetic` (data was never real)            | `generate_exclusion_training.py` metadata    |
| Test data type               | `data_type: "synthetic"`                     | `VT-LEO-AI-014.yaml` test_environment       |
| Training label source         | `source` field on TrainingLabel: `seed` for synthetic, `hitl_approval` for human-reviewed | `libs/ner/training_label_writer.py` |

### 5.5  Performance impact analysis

| Analysis type                | Evidence                                      |
| ---------------------------- | --------------------------------------------- |
| V3 training pipeline validation | `docs/nlp-pipeline/V3-TRAINING-PIPELINE-VALIDATION-REPORT.md` -- 20-encounter diagnostic run, extraction quality, SNOMED resolution rate (98-100%), cost analysis |
| Gold-standard accuracy (F1)  | `VT-LEO-AI-002.yaml` (per-entity-type metrics), `.cursor/rules/code-quality.mdc` (gold-standard labelled dataset for precision/recall/F1) |
| Regression blocking          | Deploys blocked if accuracy drops below baseline |
| Model lifecycle gates         | Offline validation -> canary -> promotion with precision/recall thresholds at each stage |
| HITL correction feedback     | Terminology writeback creates SurfaceForm nodes in the Knowledge Graph (see Section 3.6); approved mappings receive a 1.2x score boost in the hybrid resolver, measurably improving resolution for future coding runs |
| SurfaceForm growth tracking  | `writeback_service.py` returns count of written SurfaceForm nodes; domain expansion stats tracked in `DomainSearchConfig.stats` (`surface_form_count_before_kg`, `surface_form_count_after_kg`, `surface_forms_added_from_kg`) |

---

## 6  Evidence Gaps and Recommendations

The table below summarises the gaps identified across all five domains,
with recommended actions and priority.

| ID    | Domain              | Gap                                                    | Recommendation                                              | Priority |
| ----- | ------------------- | ------------------------------------------------------ | ----------------------------------------------------------- | -------- |
| GAP-A | Source record       | No formal Data Processing Agreement (DPA) in repository | Create and store a DPA template under `design-controls/`    | High     |
| GAP-B | Source record       | No formal Lawful Basis Assessment document              | Document specific Article 6 + Article 9 conditions relied upon | High     |
| GAP-C | De-identification   | No documented manual review sampling plan               | Define sample size, frequency, reviewer qualifications       | Medium   |
| GAP-D | De-identification   | No per-release de-id sign-off checklist                 | Add release-gate checklist with regression test results      | Medium   |
| GAP-E | Lineage             | No standalone Data Retention Schedule                   | Create a document specifying retention per data class        | Medium   |
| GAP-F | Labelling           | No formal annotator competence assessment record        | Implement qualification test with pass threshold             | Medium   |
| GAP-G | Labelling           | No inter-annotator agreement (kappa) computation        | Add IAA calculation to validation execution procedure        | Medium   |
| GAP-H | Source record       | DPIA not yet finalised                                  | Complete and sign off DPIA before production deployment      | High     |

---

## 7  Evidence Index

Quick reference to all artefacts cited in this document.

| Artefact ID / Path                                     | Domain(s)            |
| ------------------------------------------------------ | -------------------- |
| `design-controls/intended-use.md`                      | Source, Lineage      |
| `design-controls/user-needs/UN-LEO-AI-015.yaml`       | Source, Lineage      |
| `design-controls/user-needs/UN-LEO-AI-021.yaml`       | Source, Lineage      |
| `design-controls/DC-TM-SEC-001-threat-model.yaml`     | Source, De-id        |
| `design-controls/risks/R-LEO-AI-009.yaml`             | De-id                |
| `design-controls/verification-tests/VT-LEO-AI-014.yaml` | Lineage, De-id     |
| `design-controls/validation-tests/VAL-LEO-AI-002.yaml` | Labelling, HITL     |
| `libs/utils/deidentify.py`                             | De-id                |
| `libs/deid/deid.py`                                    | De-id                |
| `libs/ner/deid_validator.py`                           | De-id                |
| `libs/ner/extractor_contract.py`                       | Lineage, Labelling   |
| `libs/ner/training_label_writer.py`                    | Lineage, Labelling   |
| `libs/audit/audit_emitter.py`                          | Lineage              |
| `libs/model_registry/registry.py`                      | Synthetic/HITL       |
| `libs/cypher/documents_queries.py`                     | Lineage              |
| `services/coding_worker/app/pipeline/sentence_splitter.py` | Lineage          |
| `services/api/app/services/export_service.py`          | De-id, Lineage       |
| `scripts/generate_exclusion_training.py`               | Labelling, Synthetic |
| `docs/nlp-pipeline/V3-TRAINING-PIPELINE-VALIDATION-REPORT.md` | Synthetic/HITL |
| `libs/domain_config/registry.py`                       | Source, Lineage      |
| `libs/ner/domain_loader.py`                            | Lineage              |
| `services/terminology_api/app/services/writeback_service.py` | Lineage, HITL  |
| `services/terminology_api/app/services/coding_resolver.py` | Lineage, HITL    |
| `services/terminology_api/app/queries/terminology.py`  | Lineage              |
| `services/analytics_api/app/routers/domains.py`        | Source               |
| `scripts/seed_fhir_config.py`                          | Source               |
| `scripts/load_preapproved_surface_forms.py`            | Lineage, HITL        |
| `configs/snomed/*.json`                                | Source (fallback)    |
| `tests/test_sentence_splitter.py`                      | Lineage              |

---

*This document should be reviewed and updated at each major release or
when any of the cited artefacts change materially.*
