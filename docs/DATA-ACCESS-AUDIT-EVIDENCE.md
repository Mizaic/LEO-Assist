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

This document brings together all the proof that the system handles
patient data safely and lawfully. It covers five areas:

1. **Source record** -- where the data comes from and who is responsible
2. **De-identification** -- how we remove personal details before use
3. **Lineage log** -- how we track data as it moves through the system
4. **Labelling dossier** -- how we check the quality of human labels
5. **Synthetic / HITL register** -- how we manage computer-generated
   data and human review

Each section lists what evidence already exists, where to find it, and
what is still missing.

Standards referenced: ISO 13485:2016, IEC 62304:2006, ISO 14971:2019,
IEC 81001-5-1:2021, UK GDPR / DPA 2018, NHS DSPT.

---

## 1  Source Record

This section covers who controls the data, where it comes from, which
patients are included, what agreements are in place, and the legal
reason for processing.

### 1.1  Controller / processor roles

The **controller** decides why and how patient data is used. The
**processor** handles data on behalf of the controller.

| Role       | Organisation                     | Evidence                          |
| ---------- | -------------------------------- | --------------------------------- |
| Controller | NHS Primary Care Organisation    | `design-controls/user-needs/UN-LEO-AI-015.yaml` (stakeholder: Data Protection Officer, NHS Primary Care Organisation) |
| Processor  | Platform operator (LEO AI)       | `design-controls/DC-TM-SEC-001-threat-model.yaml` (system_context.deployment, services, external_services) |

**Gap:** The threat model says "Processor agreements for third-party
data processing -- insufficient evidence" under UK GDPR Article 28.
There is no formal Data Processing Agreement (DPA) in the repository
yet. We should add one as a controlled QMS document.

### 1.2  Where the data comes from

| What              | Detail                                                   | Evidence                                      |
| ----------------- | -------------------------------------------------------- | --------------------------------------------- |
| Source system      | SystmOne / EMIS GP clinical record exports (FHIR R4)    | `design-controls/intended-use.md` Section 5   |
| Data format        | FHIR R4 Encounter, DocumentReference, Patient resources  | `design-controls/intended-use.md` Section 5   |
| Date range         | Past records only; set for each audit programme          | `design-controls/intended-use.md` Section 2.3 |
| Launch programme   | National Cancer Diagnosis Audit (NCDA)                   | `design-controls/intended-use.md` Section 1   |

### 1.3  Which patients are included

For the NCDA programme, the system looks at patients registered with an
English GP who have suspected or confirmed cancer. The cancer types are
listed in NCDA value sets.

Domain settings (the rules that say which clinical topics to look at)
are now stored in Neo4j. The system loads them from FHIR ValueSet
nodes in the Knowledge Graph:

- At startup, `DomainRegistry.from_fhir()` reads `ncda-*` ValueSet
  nodes. It pulls out concept lists, milestone types, time windows,
  and semantic tags.
  Evidence: `libs/domain_config/registry.py`
- The Analytics API can update domain settings at any time through
  `AuditDomain` nodes linked to ValueSet nodes via `HAS_SUBDOMAIN`.
  Evidence: `services/analytics_api/app/routers/domains.py`
- The seed script `seed_fhir_config.py` loads the first set of ValueSet
  nodes into Neo4j.
- If FHIR data is not available, the system falls back to built-in
  Python settings. JSON files in `configs/snomed/` act as a backup.
- `expand_domains_with_kg()` adds extra search terms by looking up
  Term and SurfaceForm nodes in the Knowledge Graph. This adds SNOMED
  descendants and any mappings that human reviewers have approved.
  Evidence: `libs/ner/domain_loader.py`

Other evidence for patient selection:

- `design-controls/intended-use.md` Section 4 -- who the system is for
- `services/analytics_api/app/data/nhs_screening_cohorts.json` -- NHS screening group presets

### 1.4  Agreements

| Agreement type                 | Status        | Evidence                                                       |
| ------------------------------ | ------------- | -------------------------------------------------------------- |
| Data Processing Agreement      | **GAP**       | Mentioned in threat model (UK GDPR Article 28) but not yet written |
| Data Protection Impact Assessment (DPIA) | Draft | `design-controls/user-needs/UN-LEO-AI-021.yaml` (use case step 7: "Officer signs off the DPIA") |
| NHS DSPT compliance            | Planned       | `design-controls/user-needs/UN-LEO-AI-021.yaml`               |

### 1.5  Legal basis for processing

| Legal basis                          | Evidence                                                  |
| ------------------------------------ | --------------------------------------------------------- |
| UK GDPR Article 9 (special category health data) | `DC-TM-SEC-001-threat-model.yaml` (data_classifications) |
| UK GDPR Article 25 (data protection by design)   | `UN-LEO-AI-015.yaml` (derived_from)                      |
| UK GDPR Article 32 (keeping data secure)         | `UN-LEO-AI-021.yaml` (derived_from)                      |
| UK GDPR Article 28 (processor duties)            | `DC-TM-SEC-001-threat-model.yaml` (**gap noted**)        |
| UK GDPR Article 35 (DPIA)                        | `DC-TM-SEC-001-threat-model.yaml` (referenced; draft)    |

**Gap:** There is no standalone document that says exactly which
Article 6 and Article 9 conditions we rely on (for example,
Article 9(2)(h) for health care or Article 9(2)(j) for research).
The threat model mentions the articles but does not record the specific
legal ground.

---

## 2  De-identification

De-identification means removing personal details (names, addresses,
NHS numbers and so on) so the text cannot be linked back to a patient.

### 2.1  How we remove personal details (automated steps)

The system uses three layers of protection. Each layer catches anything
the previous one may have missed.

**Layer 1 -- Pattern matching** (`libs/utils/deidentify.py`)

Before any text reaches an external AI model or is saved for training,
the system scans it for common personal detail patterns and replaces
them with safe placeholder tags:

| What we look for              | What it becomes |
| ----------------------------- | --------------- |
| SURNAME, Forename (SystmOne Role) | `[PERSON]`   |
| SURNAME, Forename (Title)         | `[PERSON]`   |
| Dr/Mr/Mrs/Ms/Miss/Prof Surname    | `[PERSON]`   |
| ALL-CAPS surname, Firstname       | `[PERSON]`   |
| Named hospitals and clinics        | `[LOCATION]` |
| Local organisation names           | `[ORGANISATION]` |
| NHS numbers (10 digits)            | `[NHS_NUMBER]` |
| UK postcodes                       | `[POSTCODE]` |
| UK phone numbers                   | `[PHONE]`    |
| Email addresses                    | `[EMAIL]`    |
| UK street addresses                | `[ADDRESS]`  |
| Dates (DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD) | `[DATE]` |

The system keeps clinical terms, medicine names, test values, and units
because they are needed for the audit.

**Layer 2 -- Pipeline cleaning** (`libs/deid/deid.py`)

This runs before the Named Entity Recognition (NER) extraction step
(GAP-008). It handles NHS numbers, postcodes, dates, phone numbers,
emails, and local organisation names set via the `DEID_LOCAL_ORGS`
setting. It tracks which parts of the text were changed so that
character positions can be adjusted later.

**Layer 3 -- Export safety net** (`services/api/app/services/export_service.py`)

When data is exported, the system runs the cleaning step again. This
catches any text that was processed by an older version of the patterns.

### 2.2  Human review sampling

- An automated test suite checks de-identification against known
  personal detail patterns.
  Evidence: `R-LEO-AI-009.yaml`, mitigation measure 3
- Outputs and logs are scanned for personal details every month.
  Evidence: `R-LEO-AI-009.yaml`, monitoring section
- A strict validator (`libs/ner/deid_validator.py`) checks training
  records for any personal details that survived the cleaning step.

**Gap:** There is no written plan saying what share of cleaned records
a person reviews, who does it, or how often. The validator is automated
but the manual spot-check process is not written down.

### 2.3  How much risk remains (re-identification risk)

From the risk register (`R-LEO-AI-009.yaml`):

| Measure        | Before controls | After controls |
| -------------- | --------------- | -------------- |
| Severity       | 4               | 4              |
| Probability    | 2               | 1              |
| How easy to spot | 2             | 1              |
| Risk score (RPN) | 16            | 4              |
| Risk level     | High            | Low            |
| Acceptable?    | --              | Yes            |

**Known remaining risk:** First names written inside free text
(for example "discussed with Christopher") cannot be caught by
pattern matching alone. The threat model says an NER-based name
detection step should be added (GAP-008).

The threat model (`DC-TM-SEC-001`) also lists "Incomplete removal
of special category data before third-party processing" as a threat.
Controls include stripped-down containers and the cleaning pipeline.

### 2.4  Sign-off for each release

| What we check                                      | Evidence                                    |
| -------------------------------------------------- | ------------------------------------------- |
| Cleaning step is logged before data reaches the Coding layer | `VAL-LEO-AI-006.yaml`             |
| Raw patient text is never written to the Coding graph | `R-LEO-AI-009.yaml` mitigation 2        |
| Data governance tests pass at 100%                 | `VT-LEO-AI-014.yaml`                       |

**Gap:** There is no sign-off checklist for each release that covers
de-identification test results. We should add one as a release gate.

---

## 3  Lineage Log

Lineage means tracking data from its source through every step of
processing, so we can always explain where a result came from.

### 3.1  How text is split into sentences

The sentence splitter lives in
`services/coding_worker/app/pipeline/sentence_splitter.py`.

- **First choice:** MedSpaCy PyRuSH, which understands clinical text.
- **Backup:** A simple pattern that splits on full stops, question
  marks, exclamation marks, or new lines.
- **Which one runs:** The system picks PyRuSH if it is installed.
  Otherwise it uses the backup.
- **Position tracking:** Every sentence chunk records its start and end
  position in the original text.
- **Tests:** `tests/test_sentence_splitter.py` checks deduplication,
  empty text, single and multiple sentences, newline splits, and
  position accuracy.

### 3.2  Filters

- **Encounter text sorting:** `libs/classifiers/` with
  `encounter_rules.json` uses rules and a model to remove admin,
  admission, and workflow entries. The V3 validation report documents
  this.
- **Domain filtering:** FHIR ValueSet resources in Neo4j say which
  SNOMED clinical topics are in scope for each programme (see
  Section 1.3). JSON files in `configs/snomed/` serve as a backup.
- **Exclusion detection:** `libs/exclusion_detector/` spots clinical
  exclusion patterns (for example "cancer excluded").

### 3.3  Removing duplicates

- **Line-level:** `deduplicate_lines()` in `sentence_splitter.py`
  removes lines that repeat one after another. This is common in
  electronic health record exports.
- **Training label level:** `libs/ner/training_label_writer.py` creates
  a unique key for each label using
  `SHA-256(encounter_id + entity fingerprint)`. If the same encounter
  with the same entities is saved again, it overwrites rather than
  creating a duplicate.

### 3.4  Dataset version IDs

Every output carries a version stamp so we can trace it back to the
code and data that produced it.

| What                      | How it is versioned                                       | Evidence                                    |
| ------------------------- | --------------------------------------------------------- | ------------------------------------------- |
| Extraction contract       | `CONTRACT_VERSION = "1.1"` stamped on every `:DOCUMENTS` link and `EncounterCandidate` node | `libs/ner/extractor_contract.py` |
| Training label schema     | `SCHEMA_VERSION = "1.0"` on every `TrainingLabel` node    | `libs/ner/training_label_writer.py`         |
| NER model version         | `model_version` + `training_dataset_version` + `schema_version` + `deid_version` | `libs/model_registry/registry.py` |
| Export manifest            | SHA-256 hash of train/validation splits, candidate IDs, and timestamp | `services/api/app/services/export_service.py` |
| Annotation guidelines     | `GUIDELINES_VERSION = "exclusion-domain-v1"`              | `scripts/generate_exclusion_training.py`    |
| Links in the graph        | `model_name`, `model_version`, `contract_version`, `run_id` on every `:DOCUMENTS` link | `libs/cypher/documents_queries.py` |

### 3.5  Access controls

| Control                            | Evidence                                                 |
| ---------------------------------- | -------------------------------------------------------- |
| Two separate databases: Patient graph and Knowledge graph | `UN-LEO-AI-015.yaml`, `VT-LEO-AI-014.yaml` |
| Queries across the two databases are blocked | `VT-LEO-AI-014.yaml` TC-003                   |
| Users sign in through Azure AD / Entra ID | `UN-LEO-AI-021.yaml`                             |
| Role-based access (builder, reviewer, releaser, operator) | `design-controls/intended-use.md` Section 3 |
| Services use Managed Identity (no passwords in config) | `DC-TM-SEC-001` trust zones              |
| Internal services are not reachable from the internet | `DC-TM-SEC-001` T-ACA-001                |
| Data is encrypted when stored (AES-256) and when sent (TLS 1.2+) | `UN-LEO-AI-021.yaml`            |

### 3.6  SurfaceForm writeback (learning loop)

A SurfaceForm is a record that links a phrase found in clinical text
(for example "CXR" or "2WW referral") to a SNOMED code. When a human
reviewer approves a coding, the system saves that link in the Knowledge
Graph. Future coding runs then use these approved links to produce
better results. This is the learning loop.

**How SurfaceForm records are created:**

| Source                       | What triggers it                                     | Evidence                                                    |
| ---------------------------- | ---------------------------------------------------- | ----------------------------------------------------------- |
| Human review writeback       | A reviewer approves a coding proposal                | `services/terminology_api/app/services/writeback_service.py` |
| Coding review recheck        | The system saves terms it resolved automatically     | `services/api/app/routers/training.py` (`_writeback_recheck_surface_form`) |
| Manual mapping               | A user creates a mapping through the API             | `POST /terminology/surface-forms/upsert-mapping`            |
| NCDA pre-approved load       | A bulk load of guideline terms                       | `scripts/load_preapproved_surface_forms.py`                 |

**How they are stored (Knowledge Graph only -- no patient data):**

- Node: `(:SurfaceForm {form, normalized, source, status, created_by, created_at, last_seen_at})`
- Link: `(SurfaceForm)-[:MAPS_TO {confidence, approved_by, approved_at, provenance}]->(Concept)`
- Constraints: `normalized` must be unique; full-text index on `form`;
  vector index on `embedding`
- Evidence: `libs/cypher/schema_constraints.py`,
  `services/terminology/scripts/loaders/schema.py`

**How the coding pipeline uses them:**

The hybrid coding resolver
(`services/terminology_api/app/services/coding_resolver.py`) searches
for matches in four ways:

1. **Exact match** on the normalised form
2. **Full-text search** using the `surface_form_fulltext` index
3. **Vector search** using the `surface_form_embedding_idx` index
4. **Term-based search** (used when no SurfaceForm nodes exist yet)

Matches from SurfaceForm nodes get a 1.2x score boost because
human-approved mappings are more trustworthy than automated ones.

**How domains grow over time:**

`expand_domains_with_kg()` (`libs/ner/domain_loader.py`) looks up both
Term and SurfaceForm nodes to add extra search terms to each domain.
This means a correction made for one patient helps the system recognise
the same term for all future patients in the same domain.

**Why this matters for the audit trail:**

Every SurfaceForm records who approved it, when they approved it, where
it came from, and how confident the mapping is. This creates a complete
chain from the original text, through human review, to the improved
coding that results.

### 3.7  How long we keep data

| What                   | How long          | Evidence                                    |
| ---------------------- | ----------------- | ------------------------------------------- |
| Audit evidence         | 7 years           | `VT-LEO-AI-014.yaml` (evidence.retention_period) |
| Evidence is read-only  | Yes               | `VT-LEO-AI-014.yaml` (evidence.immutability) |
| Right to erasure       | Within 24 hours   | `UN-LEO-AI-015.yaml` (success_metrics)      |
| Data deletion target   | Within 24 hours   | `UN-LEO-AI-015.yaml`                        |
| Where evidence is kept | `/evidence-bundles/LEO-AI/` on Azure Blob    | `VAL-LEO-AI-002.yaml` (evidence_bundle) |

**Gap:** There is no standalone data retention schedule that lists how
long each type of data is kept (patient data, training data, audit logs,
model files). The 7-year figure only appears in one verification test.
We should create a separate Data Retention Schedule document.

---

## 4  Labelling Dossier

This section covers how we label training data, who does it, how good
the labels are, and how we track corrections.

### 4.1  Labelling schema

The NER annotation schema defines what labels can be applied to text:

- **Entity types:** `disorder`, `finding`, `procedure`, `substance`,
  `observable_entity`, `situation`, `product`, `regime/therapy`,
  `qualifier_value`, plus pathway-specific types: `X_PATHWAY_MILESTONE`,
  `X_NEGATION_CUE`, `X_TEMPORAL`, `X_DOSAGE`, `X_FREQUENCY`, `X_ROUTE`
- **Assertion statuses** (is the thing present or not):
  `present`, `absent`, `possible`, `historical`, `hypothetical`, `family`
- **Relations between entities:** `triggers`, `negates`, `treats`,
  `dosage_of`, `frequency_of`, `diagnoses`
- **Standard codes:** SNOMED CT with `code` and `display`
- **Schema evidence:** `scripts/generate_exclusion_training.py`
  (creates example training data),
  `libs/ner/extractor_contract.py` (`ExtractionItem` data structure)

### 4.2  Labelling guidance

| Guidance document              | Version                  | Evidence                                       |
| ------------------------------ | ------------------------ | ---------------------------------------------- |
| Exclusion domain guidelines    | `exclusion-domain-v1`    | `scripts/generate_exclusion_training.py` (GUIDELINES_VERSION) |
| LLM extraction prompt          | Built into `llm_extractor.py` | UK GP abbreviation lists, assertion rules, semantic tag rules, exclusion rules |
| HITL review training           | Staff must have "clinical coding experience or anchor review training" | `VAL-LEO-AI-002.yaml` |
| Labelling instructions         | Labels used: TRUE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE, NOT_APPLICABLE | `scripts/vnv_anchor_report.py` |

### 4.3  Who labels the data (annotator competence)

| Requirement                    | Detail                                                  |
| ------------------------------ | ------------------------------------------------------- |
| Who can label                  | QA staff with clinical coding experience or anchor review training |
| How many people (validation)   | 5 internal QA staff                                     |
| Training needed                | Staff must be trained on the review interface and the approve/reject workflow |

Evidence: `VAL-LEO-AI-002.yaml` (metadata.participants)

**Gap:** There is no formal test that labellers must pass before they
are allowed to label real data. We should add a qualification test
with a minimum pass score.

### 4.4  How well labellers agree with each other

| Measure                         | Target                | Evidence                                      |
| ------------------------------- | --------------------- | --------------------------------------------- |
| Review decision accuracy        | 90% or higher vs known answers | `VAL-LEO-AI-002.yaml` SCENARIO-001    |
| Anchor review accuracy          | 90% or higher vs known answers | `VAL-LEO-AI-002.yaml` SCENARIO-002    |
| Edit quality                    | 85% or higher produce a correct final code | `VAL-LEO-AI-002.yaml` SCENARIO-001 |

**Gap:** We do not yet calculate a formal agreement score between
labellers (for example Cohen's kappa or Fleiss' kappa). The validation
measures each person's accuracy against a known answer set, but does
not compare labellers with each other. We should add this.

### 4.5  Quality checks and corrections history

| Quality check                   | Evidence                                                 |
| ------------------------------- | -------------------------------------------------------- |
| Gold-standard labelled dataset   | `VT-LEO-AI-002.yaml`, `VT-LEO-AI-003.yaml`             |
| Accuracy per entity type (precision and recall) | `VT-LEO-AI-002.yaml` |
| Failing tests block releases    | `.cursor/rules/code-quality.mdc` ("Regression tests block deploys if accuracy drops below baseline") |
| Corrections feed back into the model | `design-controls/intended-use.md` Section 6.2     |
| Every label records its source   | `TrainingLabel.source`: `hitl_approval`, `coding_correction`, `anchor_mining`, or `seed` |
| Quality score on every label     | `quality_score` (0.0 to 1.0) on every `TrainingLabel` node |
| Every review action is logged    | `VAL-LEO-AI-002.yaml`: "100% of review actions have a recorded audit entry" |

---

## 5  Synthetic / HITL Register

This section covers computer-generated (synthetic) training data and
human-in-the-loop (HITL) review -- where a person checks the system's
output before it is accepted.

### 5.1  Which models generate the data

| Model / tool                | How versions are tracked                    | Evidence                                     |
| --------------------------- | ------------------------------------------- | -------------------------------------------- |
| LLM extractor (main)       | AWS Bedrock Claude                          | `DC-TM-SEC-001` external_services            |
| LLM extractor (backup)     | Azure OpenAI GPT-4o                         | `DC-TM-SEC-001` external_services            |
| NER runtime model           | Lifecycle: registered -> offline_validated -> canary -> promoted | `libs/model_registry/registry.py` |
| Synthetic training data     | `ANNOTATOR_ID = "synthetic-v1"`             | `scripts/generate_exclusion_training.py`     |
| spaCy NER training config   | `temp_transformer_ner.cfg`                  | Repository root                              |

### 5.2  Prompts

| Prompt                      | Where it lives                               | What it contains                             |
| --------------------------- | -------------------------------------------- | -------------------------------------------- |
| LLM extraction system prompt | `libs/prompts/`, `services/coding_worker/`  | UK GP abbreviations, assertion rules, semantic tags, exclusion rules |
| Few-shot examples           | `libs/prompts/` (few-shot builders)          | Built on the fly from approved examples      |
| Synthetic data prompts       | Inside `scripts/generate_exclusion_training.py` | 78 hand-written clinical scenarios        |

### 5.3  Quality gates before a model goes live

| Gate                         | Minimum score                                | Evidence                                     |
| ---------------------------- | -------------------------------------------- | -------------------------------------------- |
| Offline precision            | 0.80 or higher                               | `libs/model_registry/registry.py` (`_MIN_PRECISION`) |
| Offline recall               | 0.75 or higher                               | `libs/model_registry/registry.py` (`_MIN_RECALL`) |
| Canary precision             | 0.78 or higher                               | `libs/model_registry/registry.py` (`_MIN_CANARY_PRECISION`) |
| Canary recall                | 0.72 or higher                               | `libs/model_registry/registry.py` (`_MIN_CANARY_RECALL`) |
| Force promotion              | Allowed, but the reason must be written down | `registry.py` `promote()` method             |
| Rollback                     | The system can switch back to the previous model automatically | `registry.py` `rollback()` method |

### 5.4  How synthetic data is flagged

Every piece of synthetic data is clearly marked so it cannot be confused
with real patient data.

| Flag                         | Value                                        | Evidence                                     |
| ---------------------------- | -------------------------------------------- | -------------------------------------------- |
| Annotator ID                 | `synthetic-v1`                               | `scripts/generate_exclusion_training.py`     |
| De-identification method     | `synthetic` (the data was never real)        | `generate_exclusion_training.py` metadata    |
| Test data type               | `data_type: "synthetic"`                     | `VT-LEO-AI-014.yaml` test_environment       |
| Training label source         | `seed` for synthetic, `hitl_approval` for human-reviewed | `libs/ner/training_label_writer.py` |

### 5.5  How we measure the effect on performance

| What we measure              | Evidence                                      |
| ---------------------------- | --------------------------------------------- |
| V3 training pipeline test run | `docs/nlp-pipeline/V3-TRAINING-PIPELINE-VALIDATION-REPORT.md` -- 20-encounter test, extraction quality, SNOMED resolution rate (98-100%), cost breakdown |
| Gold-standard accuracy (F1)  | `VT-LEO-AI-002.yaml`, `.cursor/rules/code-quality.mdc` (gold-standard dataset for precision, recall, and F1) |
| Failing tests block releases | Releases are blocked if accuracy drops below the previous best |
| Model lifecycle gates         | Offline test -> canary test -> promotion, each with precision and recall thresholds |
| Human corrections improve future results | Approved mappings become SurfaceForm nodes in the Knowledge Graph (see Section 3.6). These get a 1.2x score boost in the coding resolver, so future results are better. |
| SurfaceForm growth tracking  | `writeback_service.py` returns the number of SurfaceForm nodes written. Domain expansion stats are tracked in `DomainSearchConfig.stats` (`surface_form_count_before_kg`, `surface_form_count_after_kg`, `surface_forms_added_from_kg`). |

---

## 6  Evidence Gaps and What to Do Next

The table below lists what is missing and what we should do about it.

| ID    | Area                | What is missing                                        | What to do                                                  | Priority |
| ----- | ------------------- | ------------------------------------------------------ | ----------------------------------------------------------- | -------- |
| GAP-A | Source record       | No formal Data Processing Agreement (DPA)              | Create and store a DPA template under `design-controls/`    | High     |
| GAP-B | Source record       | No standalone legal basis document                     | Write down the exact UK GDPR Article 6 and Article 9 conditions we rely on | High |
| GAP-C | De-identification   | No written plan for manual review of cleaned records   | Set out sample size, frequency, and reviewer qualifications  | Medium   |
| GAP-D | De-identification   | No release sign-off checklist for de-identification    | Add a checklist with regression test results as a release gate | Medium |
| GAP-E | Lineage             | No standalone data retention schedule                  | Create a document listing how long each data type is kept    | Medium   |
| GAP-F | Labelling           | No formal test of labeller competence                  | Add a qualification test with a pass threshold               | Medium   |
| GAP-G | Labelling           | No agreement score between labellers (kappa)           | Add kappa calculation to the validation process              | Medium   |
| GAP-H | Source record       | DPIA not yet finished                                  | Complete and sign off the DPIA before go-live                | High     |

---

## 7  Evidence Index

A quick list of every file mentioned in this document.

| File path                                              | Sections it relates to |
| ------------------------------------------------------ | ---------------------- |
| `design-controls/intended-use.md`                      | Source, Lineage        |
| `design-controls/user-needs/UN-LEO-AI-015.yaml`       | Source, Lineage        |
| `design-controls/user-needs/UN-LEO-AI-021.yaml`       | Source, Lineage        |
| `design-controls/DC-TM-SEC-001-threat-model.yaml`     | Source, De-id          |
| `design-controls/risks/R-LEO-AI-009.yaml`             | De-id                  |
| `design-controls/verification-tests/VT-LEO-AI-014.yaml` | Lineage, De-id       |
| `design-controls/validation-tests/VAL-LEO-AI-002.yaml` | Labelling, HITL       |
| `libs/utils/deidentify.py`                             | De-id                  |
| `libs/deid/deid.py`                                    | De-id                  |
| `libs/ner/deid_validator.py`                           | De-id                  |
| `libs/ner/extractor_contract.py`                       | Lineage, Labelling     |
| `libs/ner/training_label_writer.py`                    | Lineage, Labelling     |
| `libs/audit/audit_emitter.py`                          | Lineage                |
| `libs/model_registry/registry.py`                      | Synthetic/HITL         |
| `libs/cypher/documents_queries.py`                     | Lineage                |
| `libs/domain_config/registry.py`                       | Source, Lineage        |
| `libs/ner/domain_loader.py`                            | Lineage                |
| `services/coding_worker/app/pipeline/sentence_splitter.py` | Lineage            |
| `services/api/app/services/export_service.py`          | De-id, Lineage         |
| `services/terminology_api/app/services/writeback_service.py` | Lineage, HITL    |
| `services/terminology_api/app/services/coding_resolver.py` | Lineage, HITL      |
| `services/terminology_api/app/queries/terminology.py`  | Lineage                |
| `services/analytics_api/app/routers/domains.py`        | Source                 |
| `scripts/seed_fhir_config.py`                          | Source                 |
| `scripts/generate_exclusion_training.py`               | Labelling, Synthetic   |
| `scripts/load_preapproved_surface_forms.py`            | Lineage, HITL          |
| `docs/nlp-pipeline/V3-TRAINING-PIPELINE-VALIDATION-REPORT.md` | Synthetic/HITL   |
| `configs/snomed/*.json`                                | Source (backup)        |
| `tests/test_sentence_splitter.py`                      | Lineage                |

---

*Review and update this document at each major release or when any of
the files listed above change in an important way.*
