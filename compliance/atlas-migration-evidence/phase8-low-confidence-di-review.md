# Phase 2 -- Low-confidence DI Review

Total: 39

## DI-LEO-AI-004
**Local title**: (blank)
**Local requirement**: The system SHALL resolve extracted clinical entities to SNOMED CT concepts using hybrid search (exact match, full-text, and vector similarity) against the Coding Neo4j database, returning ranked candidate concepts with confidence scores

**Currently proposed**: `DI-DA7584D8` -- Confidence level displayed alongside each AI-generated interpretation (old sim=0.217, new max=0.293)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-DA7584D8 | Confidence level displayed alongside each AI-generated interpretation | 0.293 | 0.277 | 0.293 |
| DI-F8634363 | Terminology search API with hybrid SNOMED CT search | 0.051 | 0.183 | 0.183 |
| DI-31126C6C | NER-to-SNOMED entity extraction with confidence score and full provenance metada | 0.042 | 0.144 | 0.144 |
| DI-B7FEA996 | Terminology mapping writeback for reviewer-approved SurfaceForms | 0.117 | 0.078 | 0.117 |
| DI-143F69EB | Multi-mode encounter shortlisting: keyword, full-text, and vector similarity sea | 0.032 | 0.102 | 0.102 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-005
**Local title**: (blank)
**Local requirement**: The system SHALL classify the context of each extracted clinical entity as patient, family, resolved, plan, negated, or uncertain using MedSpaCy ConText and custom UK primary care context detection rules. The "discussed" ConText rule SHALL NOT be used because discussion of a condition in UK GP notes

**Currently proposed**: `DI-9843D732` -- NICE catalogue: domain taxonomy classification and three-state coverage status against act (old sim=0.241, new max=0.236)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-9843D732 | NICE catalogue: domain taxonomy classification and three-state coverage status a | 0.236 | 0.234 | 0.236 |
| DI-DFAF200B | ConText rule management: full parameter CRUD with test-run gate before activatio | 0.032 | 0.091 | 0.091 |
| DI-C7A810AA | Low-confidence entity flagging and intra-episode coding contradiction detection | 0.020 | 0.087 | 0.087 |
| DI-31126C6C | NER-to-SNOMED entity extraction with confidence score and full provenance metada | 0.062 | 0.085 | 0.085 |
| DI-21E93377 | Safety netting: result-to-reference-range comparison with three-band severity cl | 0.045 | 0.083 | 0.083 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-021
**Local title**: (blank)
**Local requirement**: The system SHALL authenticate service-to-service API calls using managed identity tokens, ensuring that internal services cannot be accessed without valid service credentials

**Currently proposed**: `DI-4DBE1A18` -- OAuth2/OIDC-aligned authentication with documented scopes and token lifetimes (old sim=0.200, new max=0.399)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-4DBE1A18 | OAuth2/OIDC-aligned authentication with documented scopes and token lifetimes | 0.399 | 0.296 | 0.399 |
| DI-091CBBAB | Unified pipeline-jobs queue with PipelineJobMessage dispatch and progress events | 0.088 | 0.025 | 0.088 |
| DI-87CCCB18 | Multi-tenancy: tenant token validation before query execution with architectural | 0.065 | 0.071 | 0.071 |
| DI-69CE20C1 | Mission Control: failed encounter list with failure reason and one-click re-queu | 0.071 | 0.017 | 0.071 |
| DI-DB62EF12 | Credential scope and conflict checks before approval actions | 0.054 | 0.028 | 0.054 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-025
**Local title**: (blank)
**Local requirement**: The system SHALL identify patients who presented with cancer-relevant symptoms but lack expected follow-up actions (referral, investigation) within configurable timeframes, generating safety-net alerts with risk prioritisation

**Currently proposed**: `DI-49403C92` -- Post-treatment recovery markers and comparable trajectories (old sim=0.214, new max=0.401)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-79509E39 | Alert fatigue suppression for normal-range investigation results with configurab | 0.055 | 0.122 | 0.122 |
| DI-4C73DC01 | Safety netting: configurable follow-up time window with worklist of outstanding  | 0.011 | 0.083 | 0.083 |
| DI-EF37BDF9 | Authoritative source change detection with routed alerts | 0.055 | 0.064 | 0.064 |
| DI-CFA65509 | Automated training-label audit with bounded auto-fix and review queues | 0.063 | 0.000 | 0.063 |
| DI-49A8F570 | Present investigation escalation thresholds and comparable cohort trajectories | 0.052 | 0.049 | 0.052 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-029
**Local title**: (blank)
**Local requirement**: The system SHALL deploy pipeline workers as independently scalable container instances that auto-scale based on message queue depth, supporting at least 10 concurrent pipeline jobs with full pipeline completion for a single patient within 2 minutes

**Currently proposed**: `DI-620FE631` -- End-to-end single-patient pipeline processing within 10 seconds at the 95th percentile (old sim=0.217, new max=0.268)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-620FE631 | End-to-end single-patient pipeline processing within 10 seconds at the 95th perc | 0.223 | 0.268 | 0.268 |
| DI-067E471A | Mission Control: per-programme per-tenant pipeline KPI dashboard with auto-refre | 0.041 | 0.069 | 0.069 |
| DI-5E25E872 | Guideline evaluation completion within 5 seconds per patient at p95 | 0.024 | 0.065 | 0.065 |
| DI-091CBBAB | Unified pipeline-jobs queue with PipelineJobMessage dispatch and progress events | 0.059 | 0.061 | 0.061 |
| DI-452D4303 | PII detection gate: training export aborted and logged if patient identifiers de | 0.056 | 0.035 | 0.056 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-034
**Local title**: (blank)
**Local requirement**: The system SHALL provide CRUD operations for SNOMED CT value sets and concept maps, supporting creation, editing, versioning, and validation of terminology resources used by programme configurations

**Currently proposed**: `DI-4746A178` -- Ranked patient shortlist with fused relevance score and supporting evidence spans (old sim=0.188, new max=0.303)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-4746A178 | Ranked patient shortlist with fused relevance score and supporting evidence span | 0.303 | 0.247 | 0.303 |
| DI-F8634363 | Terminology search API with hybrid SNOMED CT search | 0.093 | 0.091 | 0.093 |
| DI-B954388C | PromptConfig with smart few-shot selection and prompt caching | 0.075 | 0.014 | 0.075 |
| DI-2E40F292 | Isolated test credential environment with per-scope credentials and full OAuth 2 | 0.072 | 0.034 | 0.072 |
| DI-520A8674 | Safety netting: worklist filter by severity, days outstanding, and patient cohor | 0.068 | 0.017 | 0.068 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-038
**Local title**: (blank)
**Local requirement**: The system SHALL classify each extracted entity into one of three confidence tiers based on assertion status, context detection success, terminology match score, surface form approval status, and disorder verdict -- with mode-aware routing: Tier 1 auto-codes, Tier 2 codes with audit flag (autonomous

**Currently proposed**: `DI-C7A810AA` -- Low-confidence entity flagging and intra-episode coding contradiction detection (old sim=0.217, new max=0.472)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-C7A810AA | Low-confidence entity flagging and intra-episode coding contradiction detection | 0.472 | 0.373 | 0.472 |
| DI-3197332F | Disorder verifier classifies active/informational/historical/uncertain with mode | 0.048 | 0.131 | 0.131 |
| DI-48AD06E5 | LLM extractor emits self-rated assertion and confidence per entity | 0.020 | 0.128 | 0.128 |
| DI-F298AE65 | Assertion parity check between LLM extractor and ConText post-processing | 0.023 | 0.117 | 0.117 |
| DI-E0D60B50 | Terminology index match verifier with mode-aware fail behaviour | 0.028 | 0.115 | 0.115 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-039
**Local title**: (blank)
**Local requirement**: The system SHALL record every autonomous-mode coding decision as a CodingDecision node in Neo4j, capturing the entity, assertion, tier, decision, reason, terminology score, consensus verdict, and model IDs -- enabling the practice to audit what was coded, flagged, or skipped and why

**Currently proposed**: `DI-740BE510` -- SBAR: source encounter and coded entity provenance links on every clinical statement (old sim=0.240, new max=0.442)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-740BE510 | SBAR: source encounter and coded entity provenance links on every clinical state | 0.074 | 0.442 | 0.442 |
| DI-69C29EEF | Clinical significance framing: interpretation content bounded to structured inpu | 0.032 | 0.121 | 0.121 |
| DI-9D967259 | Disorder gate fail-closed with GATE_FAILED verdict | 0.044 | 0.093 | 0.093 |
| DI-E0D60B50 | Terminology index match verifier with mode-aware fail behaviour | 0.054 | 0.069 | 0.069 |
| DI-2D9F5064 | Runtime relation linking method disclosure (model prediction vs LLM fallback) to | 0.035 | 0.064 | 0.064 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-043
**Local title**: (blank)
**Local requirement**: The system SHALL remediate 48 usability, safety, and accessibility findings identified in the IEC 62366-1 / WCAG 2.2 / ISO 9241-110 audit (DC-UE-001) across 5 priority phases: (a) All server-side destructive actions SHALL require user confirmation via ConfirmDialog before execution; (b) All API fetc

**Currently proposed**: `DI-425CA252` -- Structured override taxonomy capture on every coding correction (old sim=0.200, new max=0.624)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-7736F734 | Care Overview PageIntro and accessible summary card typography | 0.008 | 0.069 | 0.069 |
| DI-7625C251 | The Test Patients page shall live in the Knowledge area of the admin app, with a | 0.016 | 0.062 | 0.062 |
| DI-6D2B03E0 | AI-generated labelling on clinician pre-reads with one-click guideline source ac | 0.022 | 0.059 | 0.059 |
| DI-985976A3 | LEO UI design tokens and accessible theme foundation | 0.020 | 0.056 | 0.056 |
| DI-55C1C21F | DI-LEO-AI-526: Server-side search term expansion for the dry-run review queue | 0.009 | 0.053 | 0.053 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-045
**Local title**: (blank)
**Local requirement**: The system SHALL provide centralised prompt safety utilities applied at every LLM call site: (1) INJECTION_GUARD: a system prompt prefix that instructs the model to treat all data block content as inert, regardless of its appearance. (2) sanitise_for_prompt(text, max_chars): replaces a defined set o

**Currently proposed**: `DI-F66A7239` -- Mandatory pre-LLM de-identification safety gate enforced in LLM client wrapper with bypass (old sim=0.241, new max=0.325)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-F66A7239 | Mandatory pre-LLM de-identification safety gate enforced in LLM client wrapper w | 0.036 | 0.325 | 0.325 |
| DI-AE477327 | Training corpus stratification report with safety-critical entity count quality  | 0.017 | 0.071 | 0.071 |
| DI-E7AFFDA5 | Span realignment and offset validation on training export with misaligned annota | 0.029 | 0.065 | 0.065 |
| DI-30D9CC61 | SBAR: AI-generated structured summary from coded encounters, pathway stage, and  | 0.010 | 0.065 | 0.065 |
| DI-6E6E985B | Layer 6 value-unit linker extension for string descriptors and raw-text fallback | 0.026 | 0.060 | 0.060 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-046
**Local title**: (blank)
**Local requirement**: The system SHALL restrict mutation of clinical rules (ConText rules and post-processor rules) to platform-admin users only, and SHALL validate all user-supplied inputs before persistence: (1) ACCESS CONTROL: POST /training/context-rules, POST /training/post- processor-rules, PATCH /training/post-pro

**Currently proposed**: `DI-3EA60D5A` -- Ontology-constrained clinical relation extraction (old sim=0.200, new max=0.300)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-FC80B65A | DQ engine: configurable rules with per-episode persistence of pass/fail and reme | 0.024 | 0.080 | 0.080 |
| DI-87CCCB18 | Multi-tenancy: tenant token validation before query execution with architectural | 0.010 | 0.074 | 0.074 |
| DI-922114AE | Safety gate: SNOMED coding defects in training labels always routed to human rev | 0.016 | 0.068 | 0.068 |
| DI-3FDBB57B | Unified LangGraph coding agent as the single execution path for all coding and p | 0.042 | 0.066 | 0.066 |
| DI-F66A7239 | Mandatory pre-LLM de-identification safety gate enforced in LLM client wrapper w | 0.016 | 0.064 | 0.064 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-055
**Local title**: (blank)
**Local requirement**: The system SHALL split training data into TrainingCandidate and GoldLabel nodes, enforce DI-ID validation before persistence, and prevent any patient, encounter, tenant, organisation, or user identifier fields in learning-loop and knowledge-graph training artifacts. The admin gold-dataset workflow S

**Currently proposed**: `DI-AF5A1668` -- Multi-tenancy: dedicated Neo4j patient graph per tenant with automated provisioning (old sim=0.240, new max=0.500)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-AF5A1668 | Multi-tenancy: dedicated Neo4j patient graph per tenant with automated provision | 0.478 | 0.500 | 0.500 |
| DI-3DFEE507 | Knowledge Graph GoldLabel as single source of truth for training data | 0.069 | 0.110 | 0.110 |
| DI-12015DBC | SNOMED coding accuracy quality gate: minimum F1 0.85 on gold-standard dataset | 0.010 | 0.070 | 0.070 |
| DI-10BB41E9 | Shortlisting recall quality gate: minimum 95% recall on gold-standard labelled d | 0.041 | 0.068 | 0.068 |
| DI-067E471A | Mission Control: per-programme per-tenant pipeline KPI dashboard with auto-refre | 0.026 | 0.065 | 0.065 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-061
**Local title**: (blank)
**Local requirement**: The system SHALL provide a no-code Pathway Builder with a visual PlanDefinition editor, enabling users to design and configure clinical pathways without writing code, with changes persisted as valid FHIR PlanDefinition resources.

**Currently proposed**: `DI-8CE01B3E` -- Encounter classification: managed rules with per-encounter decision persistence and test-p (old sim=0.197, new max=0.651)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-B0A1E549 | FHIR PlanDefinition/ActivityDefinition pathway orchestration | 0.007 | 0.068 | 0.068 |
| DI-FE3FFE50 | Cohort builder: rule-based inclusion/exclusion across coded entities, pathway st | 0.024 | 0.066 | 0.066 |
| DI-FAF97A8C | RoleGate, RolePicker, RoleSwitcher primitives with feature-flagged role-first sh | 0.042 | 0.059 | 0.059 |
| DI-AA8014F9 | Programme-level guideline rule set configuration without code deployment | 0.019 | 0.055 | 0.055 |
| DI-AA9F5EDA | Clinical Guidelines orchestrator chrome on @leo/design-system primitives | 0.017 | 0.054 | 0.054 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-064
**Local title**: (blank)
**Local requirement**: The system SHALL provide a rule generation service that reads Recommendation nodes from Neo4j and uses the existing dual-model consensus pipeline (AWS Bedrock Haiku + Azure GPT-5-mini with Sonnet arbitration) to produce candidate AppropriatenessRule nodes with SNOMED-coded CriteriaGroup entries. Gen

**Currently proposed**: `DI-69C29EEF` -- Clinical significance framing: interpretation content bounded to structured input facts (old sim=0.220, new max=0.497)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-A3107424 | Diagnostic and treatment recommendation exclusion from generated interpretations | 0.016 | 0.111 | 0.111 |
| DI-E1913514 | Dual-model consensus with Sonnet arbitration for safety-critical decisions | 0.042 | 0.092 | 0.092 |
| DI-4247C7E5 | HITL gate: SNOMED coding proposals require individual reviewer decision before e | 0.013 | 0.078 | 0.078 |
| DI-80DD8A47 | Configurable single-vs-dual-model LLM consensus runner | 0.021 | 0.076 | 0.076 |
| DI-147C8EF0 | Guidance rule extraction: AI-generated structured candidates with source section | 0.024 | 0.071 | 0.071 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-065
**Local title**: (blank)
**Local requirement**: The system SHALL provide a bitmap-based guideline evaluation service in the terminology_api. A BitmapStore SHALL use pyroaring to build and retrieve Roaring bitmaps from Redis, keyed by a deterministic BLAKE2b hash. A GuidelineCompiler SHALL read AppropriatenessRule nodes (status: active) from Neo4j

**Currently proposed**: `DI-5E25E872` -- Guideline evaluation completion within 5 seconds per patient at p95 (old sim=0.217, new max=0.487)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-5E25E872 | Guideline evaluation completion within 5 seconds per patient at p95 | 0.487 | 0.367 | 0.487 |
| DI-AA8014F9 | Programme-level guideline rule set configuration without code deployment | 0.016 | 0.076 | 0.076 |
| DI-FC80B65A | DQ engine: configurable rules with per-episode persistence of pass/fail and reme | 0.021 | 0.075 | 0.075 |
| DI-E5609239 | Knowledge base currency dashboard with exportable surveillance evidence | 0.018 | 0.074 | 0.074 |
| DI-693FFEEA | Async fire-and-track job pattern with consistent status model for all long-runni | 0.017 | 0.065 | 0.065 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-070
**Local title**: (blank)
**Local requirement**: The system SHALL provide configurable report templates aligned to NCDA (National Clinical Data Audit) output specifications, enabling clinical audit teams to generate standardised reports from pathway audit data without manual formatting or data transformation.

**Currently proposed**: `DI-916BD8C8` -- Benchmark comparison charts in audit exports (old sim=0.182, new max=0.260)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-B954388C | PromptConfig with smart few-shot selection and prompt caching | 0.098 | 0.054 | 0.098 |
| DI-1501326A | Programme inclusion criteria stored as versioned configuration applied without c | 0.017 | 0.084 | 0.084 |
| DI-E609C4E5 | Persistent informational-only disclaimer on all clinician-facing clinical intell | 0.047 | 0.080 | 0.080 |
| DI-88F20177 | Data-gap detection and mandatory disclosure for clinician-facing outputs derived | 0.013 | 0.075 | 0.075 |
| DI-ED0D477A | Per-pathway NICE alignment status report with exportable post-market surveillanc | 0.025 | 0.068 | 0.068 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-072
**Local title**: (blank)
**Local requirement**: The system SHALL execute an automated weekly audit of NER coding quality by running the audit LLM (Claude Sonnet via AWS Bedrock eu-west-2) against all encounters ingested in the preceding 7 days, recording results as immutable AuditRun and DriftMetric nodes in the patient graph, and supporting a de

**Currently proposed**: `DI-3613871E` -- Per-programme AI processing kill switch activatable without code deployment (old sim=0.200, new max=0.602)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-AF5A1668 | Multi-tenancy: dedicated Neo4j patient graph per tenant with automated provision | 0.026 | 0.070 | 0.070 |
| DI-143F69EB | Multi-mode encounter shortlisting: keyword, full-text, and vector similarity sea | 0.019 | 0.065 | 0.065 |
| DI-067E471A | Mission Control: per-programme per-tenant pipeline KPI dashboard with auto-refre | 0.022 | 0.053 | 0.053 |
| DI-091CBBAB | Unified pipeline-jobs queue with PipelineJobMessage dispatch and progress events | 0.052 | 0.014 | 0.052 |
| DI-80DD8A47 | Configurable single-vs-dual-model LLM consensus runner | 0.016 | 0.051 | 0.051 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-075
**Local title**: (blank)
**Local requirement**: The system SHALL create pending SurfaceFormTask nodes from three input streams -- audit gaps (Stream A), reviewer corrections (Stream B), and LLM high-confidence lookup terms (Stream C) -- enforce a two-reviewer gate such that no MAPS_TO relationship is created until a second reviewer approves the S

**Currently proposed**: `DI-A0579B64` -- Episode quality gate: flagged episodes blocked from reporting until flags are resolved (old sim=0.231, new max=0.559)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-A0579B64 | Episode quality gate: flagged episodes blocked from reporting until flags are re | 0.559 | 0.504 | 0.559 |
| DI-D2D0117E | Surface form revocation with cascade CodingReview creation | 0.051 | 0.098 | 0.098 |
| DI-5E1BA369 | Overcoded encounter urgent review queue with SLA and escalation | 0.009 | 0.091 | 0.091 |
| DI-922114AE | Safety gate: SNOMED coding defects in training labels always routed to human rev | 0.010 | 0.082 | 0.082 |
| DI-13F340B9 | Large-scale coding correction mandatory secondary review threshold gate | 0.008 | 0.075 | 0.075 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-080
**Local title**: (blank)
**Local requirement**: The NLP coding pipeline SHALL detect and discard administrative appointment-header sentences from clinical encounter text before passing sentences to the entity extractor, so that administrative metadata (timestamps, staff names, location entries, appointment confirmations) is never coded as a clini

**Currently proposed**: `DI-12015DBC` -- SNOMED coding accuracy quality gate: minimum F1 0.85 on gold-standard dataset (old sim=0.191, new max=0.507)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-EC96F102 | Lab-value guard prevents diagnostic inference from observable measurements | 0.021 | 0.078 | 0.078 |
| DI-31126C6C | NER-to-SNOMED entity extraction with confidence score and full provenance metada | 0.035 | 0.073 | 0.073 |
| DI-DC61F5B6 | Multi-type span classification for overlapping SNOMED concepts | 0.032 | 0.065 | 0.065 |
| DI-30D95132 | Surface form CRUD interface with match frequency display and duplicate rejection | 0.024 | 0.065 | 0.065 |
| DI-ACB587DD | Pipeline configuration dry-run validation before activation | 0.024 | 0.062 | 0.062 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-082
**Local title**: (blank)
**Local requirement**: The system SHALL provide an automated remediation script that reads audit findings from the SQLite checkpoint, fetches each encounter's text and current SNOMED coding from Neo4j, submits all proposed changes for that encounter to Claude Sonnet for independent clinical verification, and then applies 

**Currently proposed**: `DI-09E26C1D` -- Audit trail API providing provenance access without clinical record exposure (old sim=0.241, new max=0.359)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-09E26C1D | Audit trail API providing provenance access without clinical record exposure | 0.268 | 0.359 | 0.359 |
| DI-4247C7E5 | HITL gate: SNOMED coding proposals require individual reviewer decision before e | 0.011 | 0.097 | 0.097 |
| DI-22D862B0 | Reviewer engagement metrics logging and clinical safety officer monitoring view  | 0.015 | 0.090 | 0.090 |
| DI-B46AD5CE | Safety netting: immutable action recording with clinician identity and timestamp | 0.007 | 0.086 | 0.086 |
| DI-31126C6C | NER-to-SNOMED entity extraction with confidence score and full provenance metada | 0.032 | 0.081 | 0.081 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-085
**Local title**: (blank)
**Local requirement**: The episode builder SHALL detect encounters coded with SNOMED concept 395100000 (No evidence of cancer found) that occur AFTER the earliest referral date for an open cancer pathway episode AND within 365 days of that referral. When detected, the episode SHALL be closed with status='closed_benign' an

**Currently proposed**: `DI-ED3A89F5` -- Guideline monitoring registry under clinical change control with full alert context and es (old sim=0.217, new max=0.041)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-6051F076 | Specialist outcome letter inference for benign episode closure | 0.014 | 0.119 | 0.119 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.034 | 0.115 | 0.115 |
| DI-4885D9FF | Episode timeline generation with pathway gap highlighting | 0.020 | 0.101 | 0.101 |
| DI-F46D7A68 | Post-specialist outcome inference engine for stale episodes | 0.023 | 0.085 | 0.085 |
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.016 | 0.080 | 0.080 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-090
**Local title**: (blank)
**Local requirement**: The system SHALL derive and persist cancer stage at diagnosis for each EpisodeOfCare with confirmed diagnosis evidence, using a deterministic priority cascade: explicit stage string first, then site-specific TNM derivation, then text-scan fallback. The system SHALL classify stage as early/late/unkno

**Currently proposed**: `DI-23822663` -- Assertion evidence text context stored alongside assertion label (old sim=0.182, new max=0.472)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-23822663 | Assertion evidence text context stored alongside assertion label | 0.472 | 0.427 | 0.472 |
| DI-527848A8 | Staging enrichment uses post-diagnosis window with site-specialty filter | 0.041 | 0.099 | 0.099 |
| DI-82D5359B | Surface guideline treatment recommendations with comparable outcome summaries | 0.057 | 0.021 | 0.057 |
| DI-08DE2CF3 | End-to-end relation link integrity through the full processing pipeline | 0.054 | 0.037 | 0.054 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.021 | 0.054 | 0.054 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-095
**Local title**: (blank)
**Local requirement**: The system SHALL provide an admin-triggered bulk reset-and-reprocess capability for all patients in a selected organization. The operation SHALL be guarded by explicit risk controls: impact preview, three acknowledgement flags (expensive, destructive, background), and exact typed confirmation text b

**Currently proposed**: `DI-B8674FBF` -- Sandbox tenant with synthetic data and fault injection controls (old sim=0.222, new max=0.600)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-B8674FBF | Sandbox tenant with synthetic data and fault injection controls | 0.600 | 0.482 | 0.600 |
| DI-7913344A | Human-review gate blocking downstream actions from unreviewed guideline alerts | 0.078 | 0.050 | 0.078 |
| DI-ACB587DD | Pipeline configuration dry-run validation before activation | 0.034 | 0.070 | 0.070 |
| DI-A23D11FA | Active evidence engagement gate before AI recommendation confirmation with urgen | 0.023 | 0.068 | 0.068 |
| DI-DFAF200B | ConText rule management: full parameter CRUD with test-run gate before activatio | 0.043 | 0.064 | 0.064 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-096
**Local title**: (blank)
**Local requirement**: The coding pipeline SHALL support a production NER-first extraction route by calling the model inference service per sentence and SHALL apply deterministic pre-filters for non-evidence lines and administrative headers before extraction. The route SHALL be selectable through PlanDefinition ActivityDe

**Currently proposed**: `DI-702F4583` -- Programme configuration hot-reload: changes take effect at next run without service restar (old sim=0.235, new max=0.388)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-702F4583 | Programme configuration hot-reload: changes take effect at next run without serv | 0.388 | 0.370 | 0.388 |
| DI-12015DBC | SNOMED coding accuracy quality gate: minimum F1 0.85 on gold-standard dataset | 0.009 | 0.096 | 0.096 |
| DI-705C806B | Production coding worker uses WorkflowEngine + encounter_loader subgraph | 0.043 | 0.084 | 0.084 |
| DI-31126C6C | NER-to-SNOMED entity extraction with confidence score and full provenance metada | 0.026 | 0.060 | 0.060 |
| DI-A557AE91 | Model canary: configurable traffic split with audit trail tagging of canary runs | 0.006 | 0.058 | 0.058 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-098
**Local title**: (blank)
**Local requirement**: The coding pipeline SHALL run a lightweight coding quality LLM check after terminology resolution and before persistence. The check SHALL only support two actions: drop clearly unsupported coded entities and force ambiguous coded entities to human review by applying a tier override marker. Pipeline 

**Currently proposed**: `DI-F2C18D2E` -- UI-only pipeline configuration editing with override gate for failed test mode promotions (old sim=0.217, new max=0.049)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-F298AE65 | Assertion parity check between LLM extractor and ConText post-processing | 0.019 | 0.111 | 0.111 |
| DI-922114AE | Safety gate: SNOMED coding defects in training labels always routed to human rev | 0.018 | 0.086 | 0.086 |
| DI-80DD8A47 | Configurable single-vs-dual-model LLM consensus runner | 0.021 | 0.081 | 0.081 |
| DI-705C806B | Production coding worker uses WorkflowEngine + encounter_loader subgraph | 0.011 | 0.071 | 0.071 |
| DI-7A7BFA0C | Terminology hybrid retrieval skips vector search only when top lexical score >=  | 0.024 | 0.071 | 0.071 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-099
**Local title**: (blank)
**Local requirement**: The system SHALL provide an encounter-centric Mission Control workflow at /care/encounters that supports org-scoped hybrid search (fulltext plus vector), optional near-duplicate suppression for high-similarity encounter text, configurable relevance floors (minimum combined score, optional minimum ve

**Currently proposed**: `DI-DD67ACFF` -- Guided population research workspace with plain-English scoping (old sim=0.208, new max=0.037)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-143F69EB | Multi-mode encounter shortlisting: keyword, full-text, and vector similarity sea | 0.017 | 0.089 | 0.089 |
| DI-7A7BFA0C | Terminology hybrid retrieval skips vector search only when top lexical score >=  | 0.017 | 0.071 | 0.071 |
| DI-067E471A | Mission Control: per-programme per-tenant pipeline KPI dashboard with auto-refre | 0.026 | 0.067 | 0.067 |
| DI-55C1C21F | DI-LEO-AI-526: Server-side search term expansion for the dry-run review queue | 0.026 | 0.066 | 0.066 |
| DI-F8634363 | Terminology search API with hybrid SNOMED CT search | 0.033 | 0.065 | 0.065 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-101
**Local title**: (blank)
**Local requirement**: The system SHALL detect and correct double negation that arises when ConText assigns assertion=absent to a SNOMED situation concept whose preferred term (PT) already encodes a negative (e.g. "No suicidal thoughts (situation)" 134420004, "No thoughts of deliberate self harm (situation)" 401228008). I

**Currently proposed**: `DI-04105500` -- Coding correction request structured display schema (original, replacement, concept, ratio (old sim=0.217, new max=0.054)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-F298AE65 | Assertion parity check between LLM extractor and ConText post-processing | 0.018 | 0.105 | 0.105 |
| DI-3FDBB57B | Unified LangGraph coding agent as the single execution path for all coding and p | 0.037 | 0.096 | 0.096 |
| DI-48AD06E5 | LLM extractor emits self-rated assertion and confidence per entity | 0.024 | 0.093 | 0.093 |
| DI-922114AE | Safety gate: SNOMED coding defects in training labels always routed to human rev | 0.009 | 0.078 | 0.078 |
| DI-375C7EB1 | Assertion context label and evidence display on SNOMED coding review card | 0.026 | 0.073 | 0.073 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-120
**Local title**: (blank)
**Local requirement**: The LEO UI SHALL pass WCAG 2.1 AA conformance at the app-shell and on every patient-reachable route, enforced by both static analysis (eslint-plugin-jsx-a11y) and runtime testing (@axe-core/playwright and jest-axe). The AppShell SHALL provide a working skip-link, landmark roles (main, nav, complemen

**Currently proposed**: `DI-B0832A64` -- Deprecation and sunset response headers with integrator notification subscription for depr (old sim=0.205, new max=0.522)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-FAF97A8C | RoleGate, RolePicker, RoleSwitcher primitives with feature-flagged role-first sh | 0.010 | 0.067 | 0.067 |
| DI-522BBCC4 | LEO UI density modes (Compact, Comfortable, Spacious) with patient-route safe de | 0.015 | 0.057 | 0.057 |
| DI-DA7584D8 | Confidence level displayed alongside each AI-generated interpretation | 0.022 | 0.049 | 0.049 |
| DI-7625C251 | The Test Patients page shall live in the Knowledge area of the admin app, with a | 0.021 | 0.049 | 0.049 |
| DI-21946271 | Training Data tab chrome migrates to design-system primitives | 0.019 | 0.046 | 0.046 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-122
**Local title**: (blank)
**Local requirement**: The Operations workspace (/admin/operations) SHALL introduce the shared PageIntro primitive so that, on first load, a junior staff member sees a plain-language explanation of why they are on this page, how the four-section workflow fits together, and what will happen next. The workspace SHALL migrat

**Currently proposed**: `DI-B95A73E9` -- Plain-language coverage indicator explanation reachable in one action (old sim=0.217, new max=0.475)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-B95A73E9 | Plain-language coverage indicator explanation reachable in one action | 0.475 | 0.432 | 0.475 |
| DI-7736F734 | Care Overview PageIntro and accessible summary card typography | 0.151 | 0.213 | 0.213 |
| DI-29EEE9C3 | Five reusable explanation primitives (PageIntro, HelpPopover, CoachMark, Progres | 0.062 | 0.137 | 0.137 |
| DI-AA9F5EDA | Clinical Guidelines orchestrator chrome on @leo/design-system primitives | 0.018 | 0.088 | 0.088 |
| DI-EA432FDA | Coding-review bulk modal split with plain-language explanations | 0.018 | 0.086 | 0.086 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-127
**Local title**: (blank)
**Local requirement**: Per-patient safety-net signals produced by detect_safety_net_signals SHALL be persisted as SafetyNetAlert nodes linked to their Patient via a HAS_SAFETY_NET_ALERT edge and, when the signal is episode-scoped, to the EpisodeOfCare via a FOR_EPISODE edge. Every SafetyNetAlert node SHALL carry a stable 

**Currently proposed**: `DI-CE0A08E5` -- Per-entity-type precision/recall/F1 metrics stored per training job and accessible via mod (old sim=0.211, new max=0.043)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.022 | 0.067 | 0.067 |
| DI-4885D9FF | Episode timeline generation with pathway gap highlighting | 0.006 | 0.062 | 0.062 |
| DI-F46D7A68 | Post-specialist outcome inference engine for stale episodes | 0.012 | 0.061 | 0.061 |
| DI-AF5A1668 | Multi-tenancy: dedicated Neo4j patient graph per tenant with automated provision | 0.019 | 0.055 | 0.055 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.034 | 0.055 | 0.055 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-129
**Local title**: (blank)
**Local requirement**: The system SHALL expose each practitioner's selected UI role and the set of roles they are allowed to use. Switching role SHALL update the Practitioner node and write an append-only audit node capturing who switched, from which role, to which role, when, and under which session.

**Currently proposed**: `DI-D49BCE55` -- Structured approval capture with immutable audit and deploy interlock (old sim=0.200, new max=0.619)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-D49BCE55 | Structured approval capture with immutable audit and deploy interlock | 0.619 | 0.500 | 0.619 |
| DI-FAF97A8C | RoleGate, RolePicker, RoleSwitcher primitives with feature-flagged role-first sh | 0.033 | 0.099 | 0.099 |
| DI-740BE510 | SBAR: source encounter and coded entity provenance links on every clinical state | 0.015 | 0.094 | 0.094 |
| DI-710D5213 | FHIR R4: coded findings as Observation, milestones as EpisodeOfCare, audit resul | 0.044 | 0.073 | 0.073 |
| DI-080A2454 | Provenance record immutable retention policy enforcement (7-year minimum) | 0.013 | 0.063 | 0.063 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-135
**Local title**: (blank)
**Local requirement**: The admin information architecture SHALL expose a single "Knowledge" hub that contains both the curation sub-pages (training data, surface forms, context rules, AI instructions, clinical guidelines) and the clinical setup sub-pages (pathways, domains, terminology) as tabs of one page at /admin/knowl

**Currently proposed**: `DI-5E7E8CEF` -- Global active training job indicator visible from all admin pages (old sim=0.200, new max=0.044)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-7625C251 | The Test Patients page shall live in the Knowledge area of the admin app, with a | 0.048 | 0.153 | 0.153 |
| DI-AA9F5EDA | Clinical Guidelines orchestrator chrome on @leo/design-system primitives | 0.018 | 0.089 | 0.089 |
| DI-21946271 | Training Data tab chrome migrates to design-system primitives | 0.023 | 0.065 | 0.065 |
| DI-FC4CA3C1 | Guideline withdrawal notification to prior users and permanent audit-trail reten | 0.009 | 0.063 | 0.063 |
| DI-3DFEE507 | Knowledge Graph GoldLabel as single source of truth for training data | 0.012 | 0.062 | 0.062 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-139
**Local title**: (blank)
**Local requirement**: Every top-level area landing page SHALL open with a role-aware IntroCard sourced from a centralised AREA_INTRO_COPY map, rendered through a small AreaIntro wrapper that reads the session role and hands the copy to <IntroCard> from @leo/design-system. The areas in scope are: /care/dashboard (Care Ove

**Currently proposed**: `DI-900CB621` -- Prominent data completeness and reliability indicators on clinician outputs (old sim=0.182, new max=0.030)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-7736F734 | Care Overview PageIntro and accessible summary card typography | 0.028 | 0.118 | 0.118 |
| DI-F0846E55 | Role-first shell rollout cleanup (flag removal, duplicates, lint) | 0.006 | 0.092 | 0.092 |
| DI-425CA252 | Structured override taxonomy capture on every coding correction | 0.022 | 0.083 | 0.083 |
| DI-985976A3 | LEO UI design tokens and accessible theme foundation | 0.021 | 0.077 | 0.077 |
| DI-29EEE9C3 | Five reusable explanation primitives (PageIntro, HelpPopover, CoachMark, Progres | 0.016 | 0.074 | 0.074 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-142
**Local title**: (blank)
**Local requirement**: Before any Knowledge tab body is rebuilt, the shared visual building blocks SHALL be implemented once in @leo/design-system and re-exported from the package root. The new primitives are: MetricTile (single stat cell), ProgressStrip (labelled horizontal progress bar), SegmentedTabs (pill-style segmen

**Currently proposed**: `DI-C5A523A7` -- Reference range change control gate: activation blocked without approval record (old sim=0.220, new max=0.652)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-21946271 | Training Data tab chrome migrates to design-system primitives | 0.019 | 0.141 | 0.141 |
| DI-985976A3 | LEO UI design tokens and accessible theme foundation | 0.022 | 0.088 | 0.088 |
| DI-39C53CDA | Centralised MUI theme factory (createLeoTheme) sourced from design-system tokens | 0.013 | 0.085 | 0.085 |
| DI-21C63B6A | Single @leo/design-system workspace package for tokens, primitives, motion, copy | 0.025 | 0.080 | 0.080 |
| DI-AA9F5EDA | Clinical Guidelines orchestrator chrome on @leo/design-system primitives | 0.029 | 0.079 | 0.079 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-145
**Local title**: (blank)
**Local requirement**: The anchor detector SHALL detect "Seen in fast-track / 2WW clinic" encounter text as a distinct first_seen milestone bucket and the episode builder SHALL write an IS_PART_OF {milestone_type: 'first_seen'} edge and a first_seen_date property on the EpisodeOfCare node for each such encounter claimed w

**Currently proposed**: `DI-080A2454` -- Provenance record immutable retention policy enforcement (7-year minimum) (old sim=0.192, new max=0.049)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.015 | 0.135 | 0.135 |
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.011 | 0.119 | 0.119 |
| DI-6051F076 | Specialist outcome letter inference for benign episode closure | 0.015 | 0.104 | 0.104 |
| DI-4885D9FF | Episode timeline generation with pathway gap highlighting | 0.009 | 0.101 | 0.101 |
| DI-FF9C74E2 | Deterministic episode construction from related encounters | 0.015 | 0.092 | 0.092 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-147
**Local title**: (blank)
**Local requirement**: The four CRUD-style Knowledge tabs -- Context Rules, Surface Forms, Domains and Terminology -- SHALL be rebuilt onto the shared @leo/design-system chrome primitives (KnowledgePageLayout supplies the wrapper; each page renders StatHero, ToolbarActions and either SegmentedTabs or FilterBar internally)

**Currently proposed**: `DI-340279C1` -- Reference range CRUD: structured entry with mandatory source traceability and unit of meas (old sim=0.221, new max=0.598)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-AA9F5EDA | Clinical Guidelines orchestrator chrome on @leo/design-system primitives | 0.012 | 0.093 | 0.093 |
| DI-21946271 | Training Data tab chrome migrates to design-system primitives | 0.034 | 0.092 | 0.092 |
| DI-7625C251 | The Test Patients page shall live in the Knowledge area of the admin app, with a | 0.028 | 0.083 | 0.083 |
| DI-6424B6FC | Knowledge tabs unified width and DomainCard/PackageCard visual contract parity | 0.013 | 0.081 | 0.081 |
| DI-BCDC245C | DI-LEO-AI-527: Similar-candidates batch dialog highlighter + match rationale chi | 0.009 | 0.058 | 0.058 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-148
**Local title**: (blank)
**Local requirement**: The AI Instructions list page (services/ui/src/app/admin/prompts/page.tsx) SHALL be rebuilt onto the shared @leo/design-system chrome primitives (StatHero, FilterBar, SegmentedTabs, ToolbarActions) and the ReviewListCard body primitive, replacing the bespoke PromptCard grid + raw chip-strip filter +

**Currently proposed**: `DI-553F50A2` -- Active SNOMED CT version endpoint for downstream integrator technical file documentation (old sim=0.200, new max=0.022)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-21946271 | Training Data tab chrome migrates to design-system primitives | 0.035 | 0.125 | 0.125 |
| DI-AA9F5EDA | Clinical Guidelines orchestrator chrome on @leo/design-system primitives | 0.067 | 0.123 | 0.123 |
| DI-7625C251 | The Test Patients page shall live in the Knowledge area of the admin app, with a | 0.014 | 0.082 | 0.082 |
| DI-7736F734 | Care Overview PageIntro and accessible summary card typography | 0.033 | 0.062 | 0.062 |
| DI-39C53CDA | Centralised MUI theme factory (createLeoTheme) sourced from design-system tokens | 0.018 | 0.062 | 0.062 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-150
**Local title**: (blank)
**Local requirement**: The episode builder SHALL rescue 'open' (referral-only) episodes from being auto-closed as stale when a confirmed cancer diagnosis anchor exists inside the episode window. Specifically, in ``_build_open_episode``, immediately before persisting the episode node, the builder SHALL: 1. Check whether th

**Currently proposed**: `DI-6C5D77CA` -- Referral triage view with eligibility rules and comparable outcomes (old sim=0.188, new max=0.444)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-6051F076 | Specialist outcome letter inference for benign episode closure | 0.017 | 0.213 | 0.213 |
| DI-147F7B47 | Per-episode temporal claiming of specialist visit anchors | 0.021 | 0.173 | 0.173 |
| DI-F46D7A68 | Post-specialist outcome inference engine for stale episodes | 0.012 | 0.130 | 0.130 |
| DI-FC264BBF | Two-pass referral matching with strict-then-fallback claim and honest NULL | 0.014 | 0.130 | 0.130 |
| DI-527848A8 | Staging enrichment uses post-diagnosis window with site-specialty filter | 0.004 | 0.090 | 0.090 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

## DI-LEO-AI-154
**Local title**: (blank)
**Local requirement**: The system SHALL allow an authorised reviewer to edit the logic tree, name, and recommended action of a pending AppropriatenessRule from a centred dialog before approval. The dialog SHALL provide live SNOMED concept search and SHALL persist any edit as a new versioned rule that supersedes the origin

**Currently proposed**: `DI-A3107424` -- Diagnostic and treatment recommendation exclusion from generated interpretations (old sim=0.192, new max=0.556)

**Top-5 alternatives (after AC fetch)**:

| dcId | Title | seq | jac | max |
|---|---|---|---|---|
| DI-7625C251 | The Test Patients page shall live in the Knowledge area of the admin app, with a | 0.025 | 0.077 | 0.077 |
| DI-B88F2A76 | Audit trail 10-year retention enforcement with platform version recording and su | 0.026 | 0.075 | 0.075 |
| DI-1B8AC856 | Coding correction review with dependency and terminology validation | 0.015 | 0.069 | 0.069 |
| DI-8CE01B3E | Encounter classification: managed rules with per-encounter decision persistence  | 0.033 | 0.065 | 0.065 |
| DI-F94EB13F | Guidance rule review queue: per-candidate mandatory decision with bidirectional  | 0.025 | 0.062 | 0.062 |

**DECISION**: _confirm | remap=<dcId> | create | skip_

