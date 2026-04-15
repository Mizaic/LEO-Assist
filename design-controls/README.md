# Design Controls — Document Index

IEC 62304:2006+A1:2015 compliant design control documentation for the Primary Care Clinical Pathway Audit Platform.

**Software Safety Classification: Class B** (non-serious injury is possible via indirect harm pathway — see DC-SC-001)

---

## Document Register

| ID | Document | IEC 62304 Clause | Version | Status |
|----|----------|-----------------|---------|--------|
| DC-IU-001 | [Intended Use Statement](./intended-use.md) | Input to 5.2 | 0.2.0 | Draft |
| DC-SC-001 | [Safety Classification](./DC-SC-001-safety-classification.md) | 4.3 | 2.0.0 | Draft |
| DC-SDP-001 | [Software Development Plan](./DC-SDP-001-development-plan.md) | 4.4 | 2.0.0 | Draft |
| DC-SRS-001 | [Software Requirements Specification](./DC-SRS-001-software-requirements.md) | 5.2 | 1.0.0 | Draft |
| DC-ITP-001 | [Integration Test Plan](./DC-ITP-001-integration-test-plan.md) | 5.6 | 1.0.0 | Draft |
| DC-STP-001 | [System Test Plan](./DC-STP-001-system-test-plan.md) | 5.7 | 1.0.0 | Draft |
| DC-SMP-001 | [Maintenance Plan](./DC-SMP-001-maintenance-plan.md) | 6 | 1.0.0 | Draft |
| DC-RM-001 | [Risk Management](./DC-RM-001-risk-management.md) | 7 / ISO 14971 | 2.0.0 | Draft |
| DC-CM-001 | [Configuration Management](./DC-CM-001-configuration-management.md) | 8 | 1.0.0 | Draft |
| DC-SOUP-001 | [SOUP List](./DC-SOUP-001-soup-list.md) | 8.1.2 | 1.0.0 | Draft |
| DC-PR-001 | [Problem Resolution](./DC-PR-001-problem-resolution.md) | 9 | 1.0.0 | Draft |
| DC-TM-001 | [Traceability Matrix](./DC-TM-001-traceability-matrix.md) | Voluntary | 1.0.0 | Draft |
| DC-UE-001 | [Usability Engineering File](./DC-UE-001-usability-engineering.md) | IEC 62366-1 | 1.0.0 | Draft |
| -- | [Neo4j Terminology Schema](./neo4j-nlp-terminology-schema.md) | Reference | -- | Implemented |

---

## Autonomous CodingMode Engine — Design Control Summary

The autonomous coding engine enables post-deployment operation where new
encounters run without human review. Seven layered safety controls reduce
the risk of incorrect auto-coding to an acceptable level (R-LEO-AI-026).

### Design Inputs (DI-LEO-AI-036 to 041)

| ID | Title | Safety Class | Verification |
|----|-------|-------------|-------------|
| DI-LEO-AI-036 | Dual-Model Consensus Runner | B | VT-LEO-AI-021 |
| DI-LEO-AI-037 | Disorder Entity Verifier | B | VT-LEO-AI-022 |
| DI-LEO-AI-038 | Three-Tier Decision Engine | B | VT-LEO-AI-023 |
| DI-LEO-AI-039 | CodingDecision Audit Trail | B | VT-LEO-AI-024 |
| DI-LEO-AI-040 | CodingMode Pipeline Routing | B | VT-LEO-AI-025 |
| DI-LEO-AI-041 | Coding Verification Consensus | B | VT-LEO-AI-026 |

### Design Outputs (DO-LEO-AI-023 to 028)

| ID | Title | Source |
|----|-------|--------|
| DO-LEO-AI-023 | Dual-Model Consensus Runner Module | libs/llm_client/consensus.py |
| DO-LEO-AI-024 | Disorder Entity Verifier Module | libs/llm_client/disorder_verifier.py |
| DO-LEO-AI-025 | Three-Tier Decision Engine Module | libs/coding_engine/tier_classifier.py |
| DO-LEO-AI-026 | CodingDecision Audit Trail Queries | libs/cypher/coding_decision_queries.py |
| DO-LEO-AI-027 | CodingMode Pipeline Routing | services/api/app/config.py, pipeline_service.py |
| DO-LEO-AI-028 | Coding Verification Consensus | libs/llm_client/escalation.py |

### Verification Tests (VT-LEO-AI-021 to 026) -- 97 tests, all passing

| ID | Title | Test File | Tests | Status |
|----|-------|-----------|-------|--------|
| VT-LEO-AI-021 | Dual-Model Consensus Runner | tests/test_consensus.py | 12 | Passed |
| VT-LEO-AI-022 | Disorder Entity Verifier | tests/test_disorder_verifier.py | 19 | Passed |
| VT-LEO-AI-023 | Three-Tier Decision Engine | tests/test_tier_classifier.py | 28 | Passed |
| VT-LEO-AI-024 | CodingDecision Audit Trail | tests/test_coding_decision_queries.py | 14 | Passed |
| VT-LEO-AI-025 | CodingMode Pipeline Routing | tests/test_coding_mode_routing.py | 13 | Passed |
| VT-LEO-AI-026 | Coding Verification Consensus | tests/test_verify_coding_consensus.py | 12 | Passed |

### Risk (R-LEO-AI-026)

| ID | Title | Initial RPN | Residual RPN | Acceptability |
|----|-------|------------|-------------|---------------|
| R-LEO-AI-026 | Autonomous coding without human review | 27 (high) | 3 (low) | Acceptable |

---

## Surface Form Management and LLM Alias Suggestion — Design Control Summary

Adds a surface form CRUD management API to the terminology service and an
LLM-assisted alias suggestion feature, enabling administrators to curate the
NER surface form dictionary through the Settings → Surface Forms UI.  A
concurrent blob download race condition in the model inference reload path
was also fixed (see DC-PR-001 entry PR-2026-003).

### Design Inputs

| ID | Title | Safety Class | Verification |
|----|-------|-------------|-------------|
| DI-LEO-AI-049 | Surface Form Management and Curation API | B | VT-LEO-AI-041 |
| DI-LEO-AI-050 | LLM-Assisted Alias Suggestion with Human Oversight | B | VT-LEO-AI-042 |

### Design Outputs

| ID | Title | Source |
|----|-------|--------|
| DO-LEO-AI-032 | Surface Forms Management Router | services/terminology_api/app/routers/surface_forms.py |
| DO-LEO-AI-033 | Suggest-Aliases Endpoint and Model Inference Reload Safeguard | services/terminology_api/app/routers/concepts.py; services/model_inference/app/model_loader.py |

### Verification Tests

| ID | Title | Cases | Status |
|----|-------|-------|--------|
| VT-LEO-AI-041 | Surface Forms Management API Verification | 12 | Pending |
| VT-LEO-AI-042 | LLM Alias Suggestion Verification | TBD | Pending |

### Risks

| ID | Title | Initial RPN | Residual RPN | Acceptability |
|----|-------|------------|-------------|---------------|
| R-LEO-AI-034 | LLM alias suggestion introduces incorrect surface form mappings | 12 (medium) | 2 (low) | Acceptable |

### Why This Matters for Safety

Spurious or duplicated surface form mappings cause false-positive NER hits
that flow into the HITL review queue or, in autonomous mode, into auto-coded
encounters.  The management interface provides the corrective control; the
LLM suggestion feature has a mandatory human acceptance gate that prevents
any alias from being written without deliberate admin action.  No patient
data is transmitted to the LLM.

---

## Pathway Canvas Redesign — Design Control Summary

Port-based, no-code pathway canvas replacing the wizard-in-drawer model. Clinical
informaticists wire AI pipeline steps via named port handles without writing code.
Node configuration opens in a Dialog wizard with proper pickers (no raw ID fields).

### Design Inputs

| ID | Title | Safety Class | Verification |
|----|-------|-------------|-------------|
| DI-LEO-AI-060 | FHIR PlanDefinition/ActivityDefinition-driven Pathway Orchestration | B | VT-LEO-AI-063 |
| DI-LEO-AI-061 | No-code Pathway Builder with Visual PlanDefinition Editor | B | VT-LEO-AI-063 |
| DI-LEO-AI-063 | Pathway Canvas Redesign with Port-Based Node Editing and Connector Framework | B | VT-LEO-AI-063 |

### Design Outputs

| ID | Title | Source |
|----|-------|--------|
| DO-LEO-AI-060 | Unified Pipeline Worker Service | libs/workflow/engine.py, services/fhir_api/app/routers/plan_definition.py, libs/pipeline_graph/ |
| DO-LEO-AI-061 | FHIR Workflow Engine | services/ui/src/app/admin/pathways/[id]/page.tsx, services/ui/src/components/pathway/ |
| DO-LEO-AI-063 | Pathway Canvas Redesign Implementation | All of the above plus integrations admin page |

### Verification Tests

| ID | Title | Cases | Status |
|----|-------|-------|--------|
| VT-LEO-AI-063 | Pathway Canvas — Ports, Config Persistence, Condition Routing, Connectors | 16 | Pending |

### Key Technical Changes

| Component | Change |
|-----------|--------|
| `libs/workflow/engine.py` | Graph-edge traversal replaces sequence ordering; condition port routing; config injection from dynamicValues; queue_publish async dispatch |
| `services/fhir_api/app/routers/plan_definition.py` | `_ui_actions_to_fhir` creates ActivityDefinitions with dynamicValues; persists nodeType, sourceHandle, targetHandle |
| `libs/pipeline_graph/subgraphs/rest_connector.py` | REST connector subgraph with response field mapping |
| `libs/pipeline_graph/subgraphs/queue_publish.py` | Queue publish connector subgraph |
| `services/api/app/routers/pipeline.py` | `GET /pipeline/subgraphs` endpoint for dynamic subgraph discovery |
| `services/ui/src/app/admin/pathways/[id]/page.tsx` | Dialog-based wizard; port-to-port edges; grouped node palette |
| `services/ui/src/components/pathway/` | Modular node/edge/hook/wiring components; Zustand store |

### Risk

| ID | Title | Initial RPN | Residual RPN | Acceptability |
|----|-------|------------|-------------|---------------|
| R-LEO-AI-015 | Incorrect pipeline configuration causes wrong clinical output | existing | Reduced by port validation | Acceptable |

---

## WorkflowEngine Production Coding Cutover — Design Control Summary

Routes production coding jobs through WorkflowEngine and removes encounter text
from queue payloads by loading text at runtime using an encounter_loader step.

### Traceability

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-012 | implemented | Composable pipeline architecture |
| Design Input | DI-LEO-AI-094 | draft | Production coding jobs SHALL route through WorkflowEngine |
| Design Output | DO-LEO-AI-092 | draft | Job handler cutover, encounter_loader, seed updates, payload hardening |
| Risk | R-LEO-AI-015 | analyzed | Data loss during sync / orchestration transitions |
| Verification Test | VT-LEO-AI-094 | passed | Integration verification for engine routing and progress events |

---

## Bulk Reset and Reprocess Guardrails — Design Control Summary

Adds an admin-only bulk recovery flow to reset and reprocess all patients in a
selected organization, with explicit destructive-operation guardrails.

### Traceability

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-056 | approved | Admin toolkit for safe remediation actions |
| Design Input | DI-LEO-AI-095 | draft | Preview-first bulk reset and reprocess with explicit confirmations |
| Design Output | DO-LEO-AI-093 | draft | Backend endpoint, UI warnings, and runtime tests |
| Risk | R-LEO-AI-063 | analyzed | Incorrect patient graph mutation via remediation operations |
| Verification Test | VT-LEO-AI-095 | draft | Preview count, guard rejection, and queue-success verification |

---

## Encounter Mission Control Batch Recode — Design Control Summary

Replaces the pathways care route with an encounter-centric mission control view,
adds org-scoped hybrid encounter retrieval, and introduces batch reset+recode
for selected encounters with trigger_analysis defaulting to false.

### Traceability

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-058 | draft | Mission Control review workflow for audit users |
| User Need | UN-LEO-AI-056 | approved | Safe remediation tooling for admins and operations |
| Design Input | DI-LEO-AI-099 | draft | Encounter-first hybrid retrieval with optional near-duplicate suppression, relevance-floor controls, and batch reset+recode workflow including queue-all-results |
| Design Output | DO-LEO-AI-097 | draft | Analytics APIs, batch endpoint, encounters UI, route migration, relevance-floor filtering, and all-results batch orchestration |
| Risk | R-LEO-AI-063; R-LEO-AI-065 | analyzed | Remediation mutation risk and auditor decision-quality risk |
| Verification Test | VT-LEO-AI-099 | draft | API/UI verification for hybrid search, near-duplicate suppression, relevance-floor filtering, all-results batch queueing, and progress UX |

---

## Referral Triage Programme -- User Needs (UN-030 to UN-048)

Identified through 20 structured user interviews (UR-LEO-AI-001, March 2026)
covering triage clinicians, referral management teams, pathway coordinators,
clinical directors, information analysts, patient safety leads, MDT coordinators,
junior doctors, digital transformation leads, clinical safety officers, data
protection officers, medical secretaries, clinical coders, A&E consultants,
NLP engineers, platform administrators, and commercial leads.

### Clinical and Operational User Needs

| ID | Title | Safety Class | Priority |
|----|-------|-------------|----------|
| UN-LEO-AI-030 | Referral Completeness Checking at Point of Triage | B | MUST |
| UN-LEO-AI-031 | Triage Consistency Measurement Across Clinicians | B | SHOULD |
| UN-LEO-AI-032 | Real-Time Referral Queue Management | B | MUST |
| UN-LEO-AI-033 | Referrer Quality Feedback | B | SHOULD |
| UN-LEO-AI-034 | Specialty Mis-Routing Detection | B | SHOULD |
| UN-LEO-AI-035 | Rejection Rate Analytics | A | SHOULD |
| UN-LEO-AI-036 | Triage Queue Backlog Alerting | B | MUST |
| UN-LEO-AI-037 | Code-to-Source Provenance Linking | B | MUST |
| UN-LEO-AI-038 | Structured MDT Preparation from Coded Referral Data | B | SHOULD |
| UN-LEO-AI-039 | Junior Clinician Triage Decision Support | B | MUST |
| UN-LEO-AI-040 | Detection of Patients Who Should Be on a Pathway but Are Not | C | SHOULD |
| UN-LEO-AI-041 | Pathway Segment Decomposition | A | MUST |
| UN-LEO-AI-042 | Symptom-to-Referral Interval Measurement | A | SHOULD |

### Regulatory, Technical, and Commercial User Needs

| ID | Title | Safety Class | Priority |
|----|-------|-------------|----------|
| UN-LEO-AI-043 | Pseudonymisation Before LLM Processing | B | MUST |
| UN-LEO-AI-044 | Structured Override Error Categories for Model Improvement | B | SHOULD |
| UN-LEO-AI-045 | Configuration Validation UI with Test Mode | B | SHOULD |
| UN-LEO-AI-046 | Multi-Channel Referral Ingestion | B | MUST |
| UN-LEO-AI-047 | Active Engagement Design to Prevent Automation Bias | B | MUST |
| UN-LEO-AI-048 | NHS-Specific ROI and Commercial Evidence Pack | A | SHOULD |

**Evidence source:** `reports/user-research/user-interviews-deidentified.json`
(UR-LEO-AI-001 -- 20 de-identified interviews, March 2026)

None of UN-030 to UN-048 have DIs, DOs, or VTs yet. They represent the next
prioritised development backlog for the referral triage programme.

---

## Related Documentation

| Location | Contents |
|----------|----------|
| [docs/nlp-pipeline/](../docs/nlp-pipeline/) | Software Architecture (02), Detailed Design (03), Implementation (04), V&V Procedures (05), Phase Plans (06), Verification Report |

---

## IEC 62304 Class B Compliance Checklist

| Clause | Requirement | Document | Status |
|--------|------------|----------|--------|
| 4.3 | Safety classification | DC-SC-001 | Done |
| 4.4 | Development planning | DC-SDP-001 | Done |
| 5.1 | Software development process | DC-SDP-001 | Done |
| 5.2 | Software requirements analysis | DC-SRS-001 | Done |
| 5.3 | Software architectural design | docs/nlp-pipeline/02-* | Done |
| 5.4 | Software detailed design | docs/nlp-pipeline/03-* (voluntary, not required for Class B) | Done |
| 5.5 | Software unit implementation and verification | 94+ unit tests (VT-021 to VT-028); DC-STP-001 Section 5 | Done |
| 5.6 | Software integration and integration testing | DC-ITP-001 | Done |
| 5.7 | Software system testing | DC-STP-001 | Done |
| 5.8 | Software release | DC-SDP-001 Section 11 | Done |
| 6 | Software maintenance | DC-SMP-001 | Done |
| 7 | Software risk management | DC-RM-001 | Done |
| 8 | Software configuration management | DC-CM-001 + DC-SOUP-001 | Done |
| 9 | Software problem resolution | DC-PR-001 | Done |

---

## Suppress Form Safety Guard -- Design Control Summary

Extends the Coding Review UI to prevent accidental global suppression of clinical
terms when LEO has identified a specific non-codeable context.

### Change Overview

| Component | Change |
|-----------|--------|
| `CodingReviewCasesModal.tsx` | `extractSuggestedPhrase` helper extracts the key phrase LEO quoted in its `assertion_warning`; pre-fills the context phrase field on suppress form open; guards "Confirm suppress" button (disabled when `assertion_warning` is present and context phrase is empty); explanatory copy tells reviewer why a phrase is required |

### Updated Design Input

| ID | Title | Change |
|----|-------|--------|
| DI-LEO-AI-016 | Coding Review UI | Extended: suppress form context-phrase guard and LEO phrase suggestion added to requirements, constraints, and acceptance criteria; confidence display changed to low/medium/high plain-language bands in operations review UI; `CodingReviewCasesModal.tsx` added to file structure; risk R-LEO-AI-027 added |

### New Risk

| ID | Title | Initial RPN | Residual RPN | Acceptability |
|----|-------|------------|-------------|---------------|
| R-LEO-AI-027 | Overly broad suppress rule causes systematic under-coding | 27 (high) | 6 (low) | Acceptable |

### Why This Is Safety-Critical

A suppress rule without a context phrase silences a clinical term in **every**
future encounter. For a common term like "biopsy" or "hypertension", this would
cause systematic under-coding that is invisible to reviewers (the term simply
never appears in the queue again). The UI guard makes the error technically
impossible when LEO has provided its reasoning.

---

## Declined/Cancelled Assertion Lifecycle -- Design Control Summary

Fixes a safety-critical bug where `declined` and `cancelled` assertion values
were silently coerced to `present` at multiple pipeline layers, causing
non-events to be auto-coded as if they had occurred.

### Change Overview

| Component | Change |
|-----------|--------|
| `llm_extractor.py` | Added `declined` and `cancelled` to `_VALID_ASSERTIONS` and `_ASSERTION_TO_CONTEXT` (with `declined: True` / `cancelled: True` flags; `negated: False`) |
| `schema_mapper.py` | Added both values to the assertion allowlist; unknown values still coerced to `present` |
| `context_engine.py` | Added `CANCELLED` span attribute, `is_cancelled` extension, and `_span_to_assertion` branch |
| `uk_primary_care_context_rules.json` | Added `CANCELLED` rules: `cancelled`, `patient cancelled`, `appointment cancelled`, `did not attend`, `dna`, `dna'd` |
| `extractor_contract.py` | Updated assertion docstring; bumped `CONTRACT_VERSION` to `"1.2"` |
| `pipeline_service.py` | Added `cancelled` and `historical` to surface form exclusion set |
| `documents_queries.py` | Added `declined`/`cancelled` to `_NON_PRESENT` and `_assertion_context`; gated patient shortcut `MERGE` with `FOREACH` so shortcuts are only written for `present`/`historical`; added `GET_PATIENT_CODING_TIMELINE` query |
| `tier_classifier.py` | Added `cancelled` to `_AUTO_CODE_BLOCKED` and Tier 3 assertion gate |
| `label_verifier.py` | Added `declined` and `cancelled` to `_AUTO_CODE_BLOCKED` and `_ASSERTION_QUEUE_SET` |
| `patients.py` (router) | New `GET /patients/{patient_id}/timeline` endpoint |
| `AssertionChip.tsx` | New reusable chip component; colour-coded per assertion type |
| `PatientTimeline.tsx` | New patient coding timeline view with `AssertionChip` integration |
| `ReviewView.tsx`, `CodedLinksSection.tsx`, `EncounterList.tsx`, `TrainingDataPanel.tsx` | Integrated `AssertionChip` throughout existing views |

### New Design Input

| ID | Title | Safety Class | Verification |
|----|-------|-------------|-------------|
| DI-LEO-AI-042 | Declined/Cancelled Assertion Lifecycle | B | VT-LEO-AI-028 |

### New Verification Test

| ID | Title | Test File | Tests | Status |
|----|-------|-----------|-------|--------|
| VT-LEO-AI-028 | Declined/Cancelled Assertion Lifecycle | tests/test_assertion_pipeline_fix.py | 36 | Passed |

### Safety Impact

The patient shortcut gate (`FOREACH` in `_build_upsert_query`) is the key
safety control: it prevents `HAS_PROCEDURE` / `HAS_FINDING` relationships from
being written for declined or cancelled events, so population prevalence queries
do not count non-events as performed procedures.

---

## UI Safety, Accessibility, and Usability Remediation -- Design Control Summary

Comprehensive remediation of 48 usability, safety, and accessibility findings
identified by an IEC 62366-1 / WCAG 2.2 / ISO 9241-110 audit of the clinical
coding review UI.

### Audit Reference

| ID | Document | Standard |
|----|----------|----------|
| DC-UE-001 | [Usability Engineering File](./DC-UE-001-usability-engineering.md) | IEC 62366-1:2015 (+AMD1:2020), WCAG 2.2, ISO 9241-110:2020 |

### Design Input

| ID | Title | Safety Class | Verification |
|----|-------|-------------|-------------|
| DI-LEO-AI-043 | UI Safety, Accessibility, and Usability Remediation | B | VT-LEO-AI-029 |

### Design Output

| ID | Title | Source |
|----|-------|--------|
| DO-LEO-AI-029 | UI Safety Remediation Implementation | services/ui/src/ (48 files) |

### Verification Test

| ID | Title | Cases | Status |
|----|-------|-------|--------|
| VT-LEO-AI-036 | UI Safety and Accessibility Verification | 18 | Passed |

### Risk

| ID | Title | Initial RPN | Residual RPN | Acceptability |
|----|-------|------------|-------------|---------------|
| R-LEO-AI-028 | UI use errors from unconfirmed destructive actions, silent failures, accessibility barriers | 27 (high) | 3 (low) | Acceptable |

### Findings Summary

| Category | CRITICAL | MAJOR | MINOR | Total |
|----------|----------|-------|-------|-------|
| Safety | 5 | 3 | 0 | 8 |
| Usability | 3 | 6 | 3 | 12 |
| Accessibility | 5 | 8 | 5 | 18 |
| Information Architecture | 0 | 3 | 7 | 10 |
| **Total** | **13** | **20** | **15** | **48** |

### Key Safety Controls

- All destructive actions gated by `ConfirmDialog` (5 actions)
- Keyboard reject shortcut requires confirmation
- Dashboard and operations errors surfaced to user (no silent swallowing)
- Next.js error boundaries for unhandled failures
- `.cursor/rules/ui-safety.mdc` prevents regression in future development

---

## Per-Tenant Billing, Margin Configuration, and Discount Management — Design Control Summary

Adds an admin-only billing subsystem with configurable gross margin, per-tenant discount
management (promo and life-of-contract), and platform operating cost visibility.
Safety class **A** — purely commercial/financial feature, no patient data in pricing calculations.

### User Need

| ID | Title |
|----|-------|
| UN-LEO-AI-029 | Platform administrators need per-tenant AI spend visibility with configurable margin and discount management |

### Design Inputs

| ID | Title | Safety Class | Verification |
|----|-------|-------------|-------------|
| DI-LEO-AI-068 | Per-Tenant Billing, Margin Configuration, and Discount Management | A | VT-LEO-AI-068 |
| DI-LEO-AI-069 | ModelConfig Create and Delete via Admin API | A | VT-LEO-AI-069 |

### Design Outputs

| ID | Title | Source |
|----|-------|--------|
| DO-LEO-AI-068 | Billing Subsystem Implementation | libs/cypher/pricing_queries.py · services/api/app/routers/pricing.py · services/ui/src/app/admin/billing/page.tsx |
| DO-LEO-AI-069 | ModelConfig Create/Delete | libs/cypher/model_config_queries.py · services/api/app/routers/model_configs.py · services/ui/src/app/admin/models/page.tsx |

### Verification Tests

| ID | Title | Test File | Cases | Status |
|----|-------|-----------|-------|--------|
| VT-LEO-AI-068 | Per-Tenant Billing and Pricing Router Verification | services/api/tests/test_pricing_router.py | 16 | Pending |
| VT-LEO-AI-069 | ModelConfig Create and Delete Router Verification | services/api/tests/test_model_configs_router.py | 6 | Pending |

### Risk

| ID | Title | Residual | Acceptability |
|----|-------|---------|---------------|
| R-LEO-AI-045 | Unauthorized access to commercial pricing and margin data | Low | Acceptable |

### Infrastructure Bug Fixes (Problem Resolution entries — no new design controls required)

The following corrections were made to existing implemented features. Each is recorded
as a problem resolution entry in DC-PR-001 rather than requiring a new DI/DO/VT chain,
as they correct defects in already-approved design outputs.

| Fix | File(s) | Root Cause |
|-----|---------|------------|
| PromptConfig seed missing `description` and `max_few_shot` parameters | `services/api/app/services/tenant_seed.py` | Parameters referenced in Cypher query but not passed to `client.run()` |
| ModelConfig EU pricing defaults (all models showing $0.00 or US rates) | `services/api/app/services/model_config_seed.py` | Seed defaulted to `"0"` for all costs; EU cross-region profiles carry 10% premium over US |
| `azure:max` duplicate removed from seed | `services/api/app/services/model_config_seed.py` | Previously seeded as duplicate of `azure:big`; no corresponding device or use case |
| `SECRET_MAP` missing Neo4j usernames | `libs/keyvault/loader.py` | `NEO4J_USER` and `KNOWLEDGE_GRAPH_NEO4J_USERNAME` were not in KV secret map; loaded from `.env` only |
| `ods_sync` private KV loader used wrong secret/env var names | `services/ods_sync/app/main.py` | Loaded into `NEO4J_PATIENT_URI` but `PatientGraphClient` reads `NEO4J_URI`; replaced with shared `load_keyvault_secrets()` |
| `neo4j_client` module-level dotenv missing `.env.config` | `libs/neo4j_client/client.py` | Scripts importing this lib without running a service `main.py` did not get config-only env vars |
| Proxy routes missing for `/api/analytics/`, `/api/model-configs`, `/api/pricing/` | `services/ui/src/proxy.ts` | Three API prefixes not registered in Next.js middleware; requests fell through to 404 silently |

---

## Stage-at-Diagnosis Enrichment -- Design Control Summary

Adds a first-class staging engine for episode-level stage-at-diagnosis:
explicit stage extraction, site-specific TNM derivation, and source/confidence
tracking exposed in analytics and audit UI.

### Traceability

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-052 | draft | Domain-driven episode detector extended with stage-at-diagnosis enrichment |
| Design Input | DI-LEO-AI-090 | draft | Deterministic stage-at-diagnosis engine and persistence fields |
| Design Output | DO-LEO-AI-088 | draft | TNM parser, staging engine, staging enrichment subgraph, analytics and UI changes |
| Risk | R-LEO-AI-064 | analyzed | Incorrect stage derivation from explicit stage or TNM evidence |
| Verification Test | VT-LEO-AI-090 | passed | 7 automated tests for parser and engine priority cascade |

---

## HITL Safety Layer Tier Reasoning -- Design Control Summary

Running the three-tier safety classifier in HITL mode and surfacing its reasoning
to human reviewers, with override tracking for real-world calibration.

### Change Overview

| Component | Change |
|-----------|--------|
| `label_verifier.py` | Calls `classify_tier()` for each entity entering the coding review queue; stores `decision_tier`, `tier_reason`, `tier_decision` on `CodingReview` nodes |
| `coding_review_queries.py` | `UPSERT_CODING_REVIEW` stores tier fields; `GET_CODING_REVIEW_QUEUE` and `GROUP_CODING_REVIEWS_BY_ENTITY` return them; `RESOLVE_CODING_REVIEW` sets `reviewer_tier_override`; new `GET_TIER_OVERRIDE_STATS` for calibration |
| `training.py` (router) | New `GET /training/coding-review/tier-calibration` endpoint |
| `ReviewCard.tsx` | Tier badge with tooltip on each review card |
| `ReviewSection.tsx` | Tier filter chips; items sorted by tier then by count |
| `types.ts` | `DecisionTier`, `TierInfo`, `TIER_META` |

### Updated Design Input

| ID | Title | Change |
|----|-------|--------|
| DI-LEO-AI-040 | CodingMode Pipeline Routing | Extended: HITL mode writes tier fields to `CodingReview` nodes; override rate tracked for calibration |

### New Validation Test

| ID | Title | Purpose |
|----|-------|---------|
| VAL-LEO-AI-013 | Safety Layer Calibration via HITL Override Rates | Post-deployment monitoring; Tier 1 override rate < 5%, Tier 3 false-block < 10% |

### New Verification Test

| ID | Test File | Covers |
|----|-----------|--------|
| VT-LEO-AI-027 | `tests/test_hitl_tier_integration.py` | `_build_review_item` tier fields; `_check_terminology_coding` calls `classify_tier`; all Cypher queries include tier params; `reviewer_tier_override` logic; `GET_TIER_OVERRIDE_STATS` structure; calibration endpoint wiring |

---

## Three Learning Loops (Pre-Sprint) -- Design Control Summary

Coding quality audit (Loop 1), surface form vocabulary growth (Loop 2),
and NER training data collection (Loop 3). Created 2026-04-03 as Pre-Sprint
artefacts per the Three Learning Loops Production Plan v3.0.

### User Needs

| ID | Title | Safety Class | Priority |
|----|-------|-------------|----------|
| UN-LEO-AI-049 | Operations team coding quality monitoring and continuous improvement | B | MUST |
| UN-LEO-AI-050 | NER team labelled training data with protected holdout set | B | MUST |

### Design Inputs

| ID | Title | UN | Safety Class | Risk | VT |
|----|-------|----|-------------|------|----|
| DI-LEO-AI-072 | Loop 1: Automated Audit Execution | UN-049 | B | R-047 | VT-072 |
| DI-LEO-AI-073 | Loop 1: Drift Detection and Alerting | UN-049 | B | R-047, R-048 | VT-073 |
| DI-LEO-AI-074 | Loop 1: Overcoded Item Remediation | UN-049 | B | R-049 | VT-074 |
| DI-LEO-AI-075 | Loop 2: Surface Form Task Creation (Streams A/B/C) | UN-049 | B | R-050 | VT-075 |
| DI-LEO-AI-076 | Loop 2: Surface Form Revocation and Cascade | UN-049 | B | R-051 | VT-076 |
| DI-LEO-AI-077 | Loop 3: De-identified Evidence Collection | UN-050 | B | R-052 | VT-077 |
| DI-LEO-AI-078 | Loop 3: Holdout Set Integrity | UN-050 | B | R-053 | VT-078 |
| DI-LEO-AI-079 | Loop 3: Training Data Export and PII Gate | UN-050 | B | R-052 | VT-079 |

### Design Outputs

| ID | Title | DI | Key Files |
|----|-------|----|-----------|
| DO-LEO-AI-070 | Automated Audit Execution Implementation | DI-072 | audit_encounter_coding.py, schema_constraints.py |
| DO-LEO-AI-071 | Drift Detection and Alerting Implementation | DI-073 | audit_quality.py router, QualitySection.tsx |
| DO-LEO-AI-072 | Overcoded Item Remediation Implementation | DI-074 | coding_review_queries.py, ReviewSection.tsx |
| DO-LEO-AI-073 | Surface Form Task Creation Implementation | DI-075 | training.py, llm_extractor.py, ReviewCard.tsx |
| DO-LEO-AI-074 | Surface Form Revocation and Cascade Implementation | DI-076 | training.py, coding_review_queries.py |
| DO-LEO-AI-075 | De-identified Evidence Collection Implementation | DI-077 | deidentify.py, documents_queries.py |
| DO-LEO-AI-076 | Holdout Set Integrity Implementation | DI-078 | select_holdout_set.py, documents_queries.py |
| DO-LEO-AI-077 | Training Data Export and PII Gate Implementation | DI-079 | export_ner_training.py |

### Risks (ISO 14971)

| ID | Title | Category | Initial RPN | Residual | Acceptability |
|----|-------|----------|-------------|----------|--------------|
| R-LEO-AI-047 | Coding quality regression goes undetected | clinical_safety | 18 | 6 | acceptable |
| R-LEO-AI-048 | Alert fatigue causes regression to be ignored | use_error | 12 | 3 | acceptable |
| R-LEO-AI-049 | False clinical record persists (overcoded) | clinical_safety | 18 | 3 | acceptable |
| R-LEO-AI-050 | Incorrect surface form propagates to future encounters | clinical_safety | 27 | 6 | acceptable |
| R-LEO-AI-051 | Revoked mapping leaves historical records incorrect | data_integrity | 18 | 4 | acceptable |
| R-LEO-AI-052 | PII leaks into training corpus | security_breach | 16 | 4 | conditionally_acceptable |
| R-LEO-AI-053 | Training/test contamination inflates evaluation metrics | data_integrity | 18 | 6 | acceptable |

### Verification Tests

| ID | Title | Test File | Safety Class | Status |
|----|-------|-----------|-------------|--------|
| VT-LEO-AI-070 | NCDA Report Template Generation (stub for DI-070) | services/api/tests/test_ncda_report_generator.py | A | Draft |
| VT-LEO-AI-071 | Avoidable Delay Assessment (stub for DI-071) | services/api/tests/test_delay_assessor.py | B | Draft |
| VT-LEO-AI-072 | Loop 1 Automated Audit Execution | tests/test_audit_execution.py | B | Draft |
| VT-LEO-AI-073 | Loop 1 Drift Detection, Alert Dedup, and Escalation | tests/test_drift_detection.py | B | Draft |
| VT-LEO-AI-074 | Loop 1 Overcoded Item Remediation and 48h SLA | tests/test_overcoded_remediation.py | B | Draft |
| VT-LEO-AI-075 | Loop 2 Surface Form Task Creation and Two-Reviewer Gate | tests/test_surface_form_tasks.py | B | Draft |
| VT-LEO-AI-076 | Loop 2 Surface Form Revocation and Cascade | tests/test_surface_form_revocation.py | B | Draft |
| VT-LEO-AI-077 | Loop 3 De-identified Evidence Collection and Zero-PII | tests/test_deidentify_evidence.py | B | Draft |
| VT-LEO-AI-078 | Loop 3 Holdout Set Integrity and Export Exclusion | tests/test_holdout_integrity.py | B | Draft |
| VT-LEO-AI-079 | Loop 3 Training Export PII Gate and Safety Block | tests/test_ner_training_export.py | B | Draft |

---

## GDPR-Isolated Candidate Ops (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-027 | implemented | AI-augmented training data quality assurance with terminology verification |
| Design Input | DI-LEO-AI-055 | draft | Extended with candidate cascade delete and manual similarity-dedupe controls |
| Design Output | DO-LEO-AI-055 | draft | Includes candidate delete plus dedupe preview/apply in router and admin UI |
| Risk | R-LEO-AI-039; R-LEO-AI-040; R-LEO-AI-041 | analyzed | Existing mitigations retained |
| Verification Test | VT-LEO-AI-096 | passed | API delete and dedupe preview/apply controls verified for admin gold-dataset workflow |

---

## Double-Negation Guard for Pre-Negated SNOMED Situations (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-002 | implemented | SNOMED CT coding with negation detection |
| Design Input | DI-LEO-AI-101 | draft | Post-SNOMED guard corrects assertion inversion when ConText sets absent on a PT that starts with "No" / "Absence of" / "Not" |
| Design Output | DO-LEO-AI-099 | draft | fix_double_negated_situations() in post_processing.py + terminology._resolve_terms wiring |
| Risk | R-LEO-AI-069 | analyzed | Clinical inversion of mental health risk screen documentation (suicidal ideation, self-harm) |
| Verification Test | VT-LEO-AI-101 | passed | 15 automated tests: correction, non-interference, idempotency, runtime path |
| Design Input | DI-LEO-AI-102 | draft | Analytics assertion filter - CCI and cohort queries exclude absent/hypothetical codes |
| Design Output | DO-LEO-AI-100 | draft | _CONFIRMED_ASSERTIONS guard in cci.py and cohorts.py with coalesce fallback |
| Risk | R-LEO-AI-070 | mitigated | Absent-coded condition inflates CCI score or incorrectly matches cohort filter |
| Verification Test | VT-LEO-AI-102 | passed | 12 automated tests: query structure, present/historical scoring, absent exclusion |
| Design Input | DI-LEO-AI-104 | draft | Episode closure from benign/normal qualifier plus site-related finding within 90 days |
| Design Output | DO-LEO-AI-102 | draft | BENIGN_QUALIFIER_CLOSURE_QUERY and closed_benign_qualifier status with HITL |
| Risk | R-LEO-AI-071 | mitigated | Unrelated benign qualifier closes active cancer pathway episode |
| Verification Test | VT-LEO-AI-104 | passed | 11 automated tests including site mismatch rejection and diagnosis suppression |

---

## GoldLabel Training Source Consolidation (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-050; UN-LEO-AI-027 | draft/implemented | Consolidates training to a single verified gold source and aligns operations UX |
| Design Input | DI-LEO-AI-100 | draft | GoldLabel single source of truth for training, migration of include=true TrainingLabel, and operations redesign |
| Design Output | DO-LEO-AI-098 | draft | Migration script, GoldLabel exporter path, and simplified operations training workflow |
| Risk | R-LEO-AI-052; R-LEO-AI-053; R-LEO-AI-039 | analyzed | PII leak, holdout contamination, and data quality controls preserved |
| Verification Test | VT-LEO-AI-100 | passed | Exporter query path, minimum gate, and operations UI workflow verification |

---

## NER + Dual LLM Quality Gates (April 2026)

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-012 | implemented | Composable workflow routing enables extraction/coding quality stages via PlanDefinition |
| User Need | UN-LEO-AI-049 | draft | Coding quality monitoring loop extended with runtime LLM quality gates |
| User Need | UN-LEO-AI-050 | draft | NER training feedback loop extended with extraction correction provenance |
| Design Input | DI-LEO-AI-096 | draft | NER-first extraction route and deterministic non-evidence pre-filter |
| Design Input | DI-LEO-AI-097 | draft | Pre-terminology relation_linking plus extraction quality check (drop/correct/add/relation fixes) with provenance, extraction condition routing to HITL queue, referral-procedure assertion guard, side-effect counselling suppression, gold-training write gating, sentence-level candidate entities_json persistence, and unsafe terminology mapping blocklist |
| Design Input | DI-LEO-AI-098 | draft | Post-terminology coding quality check (drop/force_review), coding condition routing to HITL queue, tier override enforcement, and patient-graph hold on coding issues |
| Design Output | DO-LEO-AI-094 | draft | Extraction routing, model provider integration, and sentence pre-filter implementation |
| Design Output | DO-LEO-AI-095 | draft | relation_linking and extraction_check v2 subgraphs, extraction route condition branch, referral-procedure assertion guard, side-effect counselling suppression, candidate entities_json persistence, unsafe terminology mapping blocklist, and prompt seeding implementation |
| Design Output | DO-LEO-AI-096 | draft | coding_check subgraph, coding route condition branch, tier override enforcement, coding HITL queue, and guarded persist routing |
| Risk | R-LEO-AI-067 | analyzed | Extraction check may drop valid entities or add unsupported mentions |
| Risk | R-LEO-AI-068 | analyzed | Coding check may suppress valid coded entities or over-escalate review |
| Verification Test | VT-LEO-AI-096 | draft | NER route + deterministic pre-filter verification |
| Verification Test | VT-LEO-AI-097 | passed | relation_linking + extraction_check parse/apply/provenance verification including referral-procedure safeguard, extraction condition routing, side-effect counselling suppression, gold-training signal gate, candidate entities_json persistence, and unsafe terminology mapping blocklist |
| Verification Test | VT-LEO-AI-098 | passed | Coding check drop/force-review, coding condition routing, tier override enforcement, and patient-write hold verification |

---

## Intelligence Console UX + Training Quality Capabilities (April 2026)

| Artefact | ID | Status | Notes |
|----------|----|--------|-------|
| User Need | UN-LEO-AI-059 | draft | Clinical informaticians need a unified Intelligence Console |
| Design Input | DI-LEO-AI-105 | draft | Intelligence Console UX - 8-item nav, 6-stage health bar, nudge banner, persistent training banner, URL migration |
| Design Output | DO-LEO-AI-103 | draft | Console page, stage components, design tokens, 301 redirects, URL audit CI test |
| Verification Test | VT-LEO-AI-105 | passed | URL audit passes with 0 deprecated admin URL violations |
| User Need | UN-LEO-AI-060 | draft | Model trainers need active learning, per-entity F1, golden set, and warm-start |
| Design Input | DI-LEO-AI-106 | draft | Span realignment, assertion filtering, per-label F1, warm-start, golden gate, active learning queue |
| Design Output | DO-LEO-AI-104 | draft | label_exporter, evaluator, trainer, job_store, golden_set_queries, active learning API endpoints |
| Risk | R-LEO-AI-072 | mitigated | Corrupt or non-present training data degrades NER model clinical coding accuracy |
| Verification Test | VT-LEO-AI-106 | passed | 21 automated tests: span realign, assertion filter, per-label F1, warm-start fallback, golden gate |
| User Need | UN-LEO-AI-062 | draft | Clinical reviewers need ontology-grounded relation linking for safe entity-to-entity semantics |
| Design Input | DI-LEO-AI-108 | draft | Canonical relations, policy validation, multi-site links, relation export/train/eval, model-first runtime fallback |
| Design Output | DO-LEO-AI-106 | draft | API/UI/runtime/training implementation for ontology-grounded relation modeling |
| Risk | R-LEO-AI-074 | analyzed | Invalid or missing relations distort coding interpretation and pathway analytics |
| Verification Test | VT-LEO-AI-108 | passed | Relation schema/policy/runtime fallback and relation training pipeline verification |
| User Need | UN-LEO-AI-063 | draft | Clinicians and service improvement leads need a guided research workspace to explore longitudinal patient data |
| Design Input | DI-LEO-AI-109 | draft | Pathway Explorer API: GDS projections, algorithm runner, research router, research worker service |
| Design Input | DI-LEO-AI-110 | draft | Pathway Explorer UI: mission cards, scoping wizard, 4-layer results, persona lens, data-gated UX |
| Design Output | DO-LEO-AI-107 | draft | Backend implementation: gds_projection_manager, algorithm_runner, headline_generator, research router, research_worker |
| Design Output | DO-LEO-AI-108 | draft | Frontend implementation: 11 React components + API client + useResearchState hook |
| Risk | R-LEO-AI-075 | analyzed | Misleading graph algorithm results acted on clinically without data coverage warning |
| Risk | R-LEO-AI-076 | analyzed | Algorithm jargon exposed in UI causes user misinterpretation of findings |
| Verification Test | VT-LEO-AI-109 | passed | Pathway Explorer API/GDS backend unit tests (pytest, 6 test cases) |
| Verification Test | VT-LEO-AI-110 | passed | Pathway Explorer UI static analysis (jest, 49 assertions across 10 suites) |
| User Need | UN-LEO-AI-064 | draft | Pipeline must completely capture string results and pre-entity values for observable entities |
| Design Input | DI-LEO-AI-111 | draft | Observable value-unit linking: string result descriptors and pre-entity raw-text fallback |
| Design Output | DO-LEO-AI-109 | draft | Extended link_observable_value_units in post_processing.py |
| Risk | R-LEO-AI-077 | analyzed | Observable value left empty for string or pre-entity results - downstream abnormal detection degraded |
| Verification Test | VT-LEO-AI-111 | passed | Four unit tests: string entity after, string entity before, numeric raw-text, string raw-text |
