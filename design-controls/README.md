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
| DC-TM-001 | [Traceability Matrix (narrative)](./DC-TM-001-traceability-matrix.md) | Voluntary | 1.0.0 | Draft |
| DC-TM-002 | [Atlas UN -> DI -> DO -> VT -> VAL Matrix (CSV, generated)](./DC-TM-002-traceability-matrix.csv) | Voluntary | 2.0.0 | Generated |
| DC-UE-001 | [Usability Engineering File](./DC-UE-001-usability-engineering.md) | IEC 62366-1 | 1.0.0 | Draft |
| -- | [Atlas / Local ID Mapping (CSV)](./atlas-id-mapping.csv) | Reference | -- | Generated |
| -- | [Atlas / Local ID Mapping Gaps](./atlas-id-mapping-gaps.md) | Reference | -- | Generated |
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

## Encounter Timeline Scrubber for Mission Control Patient Detail -- Design Control Summary

Adds a persistent horizontal timeline scrubber to the Mission Control patient
detail Encounter text tab so reviewers can see and reach surrounding-context
encounters in one click instead of switching scope and scrolling. Also
modularises EncounterTextTab.tsx (1014 -> 498 LOC) to comply with the project
500-LOC ceiling.

### Traceability

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-077 | approved | Cancer auditors and clinical reviewers need to navigate every encounter in a patient's history without losing the focused episode, so surrounding context is one click away rather than hidden behind scope toggles and date guesswork |
| Design Input | DI-LEO-AI-179 | draft | Persistent horizontal timeline scrubber on the Mission Control patient detail Encounter text tab: one dot per encounter on a real date axis, linked-vs-other styling, episode-window band, hover preview, click/keyboard jump with framer-motion shared-layout indicator (layoutId="timeline-active"), IntersectionObserver scroll-sync, auto-hide for short histories (< 5 encounters), full keyboard accessibility (Tab/Arrow/Enter), reduced-motion honoured via useMotion() |
| Design Output | DO-LEO-AI-178 | draft | EncounterTimelineScrubber.tsx primitive plus modular refactor of EncounterTextTab.tsx into focused siblings: EncounterCard.tsx, EncounterCodesPanel.tsx, encounterStyles.ts, encounterTextUtils.tsx, encounterRecodeProgress.ts |
| Risk | R-LEO-AI-174 | analyzed | Reviewer skips surrounding-context check during episode review because the affordance is hidden behind scope toggle plus manual scroll; mitigation: persistent spatial timeline removes the multi-step interaction |
| Verification Test | VT-LEO-AI-173 | passed | 25 jest cases: 11 live-render (dot rendering, linked-vs-other, window band, click + Enter + ArrowRight activation, aria-pressed, data-active), 11 static-source chrome (layoutId, useMotion, framer-motion primitives, MIN_ENCOUNTERS threshold, EncounterTextTab wiring, IntersectionObserver scroll-sync, 498 <= 500 LOC), 3 regression cases for milestone-jump and tooltip behaviour |

### Test-Patient Diagnostic Source-of-Truth (April 2026)

Replay Results dialog now uses the production roaring-bitmap evaluator
to diagnose regressions. Previously the UI ran a duplicate, naive
`cid in patient.codes` walker that disagreed with production whenever a
CONCEPT criterion relied on the SNOMED IS_A descendant closure. The
duplicate has been removed and the dialog calls
`/api/guidance/test-patients/diagnose` for each regression, rendering
the annotated logic_tree hierarchically (AND / OR / NOT / AT_LEAST
counts visible).

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-076 | approved | Reviewers must confirm that previously approved patient profiles still reach the same recommendation after any rule edit, deploy or rebuild |
| Design Input | DI-LEO-AI-180 | approved | Test-patient regression diagnostics MUST use the same roaring-bitmap evaluator as production firing. Per-rule diagnose() returns an annotated logic_tree (matched + matched_count + min) so the UI can render it hierarchically and the reviewer's verdict can never disagree with the live firing decision |
| Design Output | DO-LEO-AI-179 | approved | GuidelineEvaluator.diagnose() + POST /terminology/guidelines/diagnose + test_patient_service.diagnose_rule_against_patient + POST /guidance/test-patients/diagnose + ReplayResultsDialog hierarchical render via RegressionDetail / DiagnoseNodeRow; legacy client-side evaluateLogicTree.ts deleted |
| Risk | R-LEO-AI-175 | mitigated | Reviewer diagnostic disagrees with the production rule firing decision; harm: silently approving a regression that disables a 2-week wait recommendation, or blocking a benign edit |
| Verification Test | VT-LEO-AI-174 | passed | 9 tests: 7 backend pytest cases (parity v1+v2, AT_LEAST counts, missing bitmap, no ruleset, unknown rule) plus 2 jest cases for the dialog (diagnose fetch + hierarchical render, recompile-hint on failure); guidance UI suite 105/105 passing |

### April 2026 - Sandbox draft replay AND explicit "no ruleset compiled" signalling

Reviewers can now compile UNSAVED draft appropriateness rules into an
isolated bitmap scope, replay the saved test-patient library through
that scope, and discard the sandbox -- all without saving the rule or
recompiling production. The same change makes "no ruleset is loaded"
a loud, first-class state across every bitmap-backed surface so a
reviewer cannot mistake a missing ruleset for a clean pass.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-181 | approved | Sandbox replay of UNSAVED draft rules MUST reuse the production compiler in an isolated custom scope (refusing global) AND every bitmap-backed surface MUST signal `not_compiled` + `recompile_hint` when no ruleset is loaded, instead of returning a silent zero-match |
| Design Output | DO-LEO-AI-180 | approved | GuidelineCompiler.compile_drafts + BitmapStore.delete_scope/set_scope_ttl + evaluator/diagnose `not_compiled` payload + POST /guidelines/bitmap/compile-draft + DELETE /guidelines/scopes + test_patient_service.sandbox_replay + POST /guidance/test-patients/sandbox-replay + RulesetNotCompiledBanner + Test draft button in EditRuleDialog |
| Risk | R-LEO-AI-176 | mitigated | Reviewer interprets a silent zero-match as "rule does not match" when no ruleset is compiled; harm: approving a regressing edit because the empty ruleset is indistinguishable from a clean pass |
| Verification Test | VT-LEO-AI-175 | passed | 13 tests: 8 backend pytest cases (compile_drafts global refusal + custom-scope happy path, evaluator/diagnose not_compiled, delete_scope happy path + global refusal, sandbox_replay compile+replay+cleanup happy + failure paths, diagnose passthrough) plus 5 jest cases (banner production/sandbox/error variants + TestPatientsPanel sandbox happy + empty-compile paths); guidance UI suite 93/93 passing |

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
| Design Input | DI-LEO-AI-097 | draft | Pre-terminology relation_linking plus extraction quality check (drop/correct/add/relation fixes) with provenance, extraction condition routing to HITL queue, referral-procedure assertion guard, side-effect counselling suppression, gold-training write gating, sentence-level candidate entities_json persistence, unsafe terminology mapping blocklist, and shared annotation-guideline prompt composition |
| Design Input | DI-LEO-AI-098 | draft | Post-terminology coding quality check (drop/force_review), coding condition routing to HITL queue, tier override enforcement, and patient-graph hold on coding issues |
| Design Output | DO-LEO-AI-094 | draft | Extraction routing, model provider integration, and sentence pre-filter implementation |
| Design Output | DO-LEO-AI-095 | draft | relation_linking and extraction_check v2 subgraphs, extraction route condition branch, referral-procedure assertion guard, side-effect counselling suppression, candidate entities_json persistence, unsafe terminology mapping blocklist, shared annotation-guideline composition in check/link prompt resolvers, and prompt seeding implementation |
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
| User Need | UN-LEO-AI-061 | draft | Clinicians need NER to classify the same span under multiple SNOMED semantic types |
| Design Input | DI-LEO-AI-107 | draft | Multi-label NER via spancat, refined nesting suppression, and canonical shared annotation-guideline reuse across prompt paths and reviewer UI |
| Design Output | DO-LEO-AI-105 | draft | spancat config/export/inference updates plus shared annotation-guideline composition and Gold Dataset reviewer guidance surfaces |
| Risk | R-LEO-AI-073 | analyzed | Spurious additional NER label inflates false positive SNOMED coding rate |
| Verification Test | VT-LEO-AI-107 | passed | Multi-label export, inference fallback, refined nesting, and prompt-preservation checks |
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

| User Need | UN-LEO-AI-065 | draft | Patient-facing LEO surfaces usable ages 8 to 80 at WCAG 2.1 AA |
| User Need | UN-LEO-AI-066 | draft | Carer-facing LEO surfaces make patient context and permission scope explicit |
| User Need | UN-LEO-AI-067 | draft | Junior / trainee staff can self-onboard through in-product explanation |
| User Need | UN-LEO-AI-068 | draft | Older clinicians work at full speed with larger default text, high contrast, and keyboard alternatives |
| Design Input | DI-LEO-AI-118 | draft | Inclusive design token system (type, space, radius, motion, focus, density, contrast pairs) |
| Design Input | DI-LEO-AI-119 | draft | Density modes with >=44px touch targets on patient-reachable routes |
| Design Input | DI-LEO-AI-120 | draft | Global WCAG 2.1 AA baseline across AppShell and primitives with eslint-a11y and axe-core gates |
| Design Input | DI-LEO-AI-121 | draft | Explanation pattern framework (PageIntro, HelpPopover, CoachMark, ProgressiveReveal, GlossaryTerm) and FK grade <=9 gate |
| Design Output | DO-LEO-AI-115 | draft | services/ui/src/theme/{tokens.ts, tokens.css} and theme.ts consume tokens with AA pairs |
| Design Output | DO-LEO-AI-116 | draft | DensityProvider + useDensity/useDensityTokens with localStorage and patient-route override |
| Design Output | DO-LEO-AI-117 | draft | AppShell landmarks, ConfirmDialog aria, StatusDot shape encoding, eslint and axe-core CI wiring |
| Design Output | DO-LEO-AI-118 | draft | Explanation pattern components plus glossary.ts and readability.ts utilities |
| Risk | R-LEO-AI-078 | analyzed | Low-contrast text or unchecked motion causes missed safety information |
| Risk | R-LEO-AI-079 | analyzed | Dense UI causes mis-taps for touch / low-dexterity users |
| Risk | R-LEO-AI-080 | analyzed | Assistive-tech users cannot perceive navigation state or status information |
| Risk | R-LEO-AI-081 | analyzed | Patients and juniors misunderstand clinical terms without in-product explanation |
| Verification Test | VT-LEO-AI-113 | passed | 5 Jest cases: token groups, WCAG AA pairs, focus ring, readable typography, tokens.css |
| Verification Test | VT-LEO-AI-114 | passed | 5 Jest cases: density defaults, patient-route override, 44px target, persistence, staff preference |
| Verification Test | VT-LEO-AI-115 | partial_pass | 5 Jest cases pass; axe-core e2e wired and pending CI run |
| Verification Test | VT-LEO-AI-116 | passed | 6 Jest cases: PageIntro, HelpPopover, ProgressiveReveal, GlossaryTerm known+unknown, FK grade gate |
| Design Input | DI-LEO-AI-122 | draft | OperationsWorkspace inclusive redesign (PageIntro, shared StatusDot, aria-expanded/controls on SectionRow) |
| Design Output | DO-LEO-AI-119 | draft | OperationsWorkspace.tsx renders PageIntro screenId=admin-operations, local StatusDot removed, SectionRow aria linkage |
| Risk | R-LEO-AI-082 | analyzed | Operations workspace misread by junior staff or older clinicians due to jargon and colour-only status cues |
| Verification Test | VT-LEO-AI-117 | passed | 7 Jest cases: PageIntro renders with h2, collapse persists, why/how/what FK <=9, SectionRow aria toggle, local StatusDot removed |
| Design Input | DI-LEO-AI-123 | draft | CodingReviewCasesModal split into eight modules each <=500 LOC with PageIntro + GlossaryTerm + HelpPopover |
| Design Output | DO-LEO-AI-120 | draft | CodingReviewCasesModal.tsx (389) + CodingReviewCasesModalTitle.tsx (213) + CaseCard.tsx (461) + CaseCardLeoResult.tsx (174) + CaseCardSuppressForm.tsx (175) + EncounterContextPanel.tsx (133) + codingReviewUtils.ts (135) + codingReviewCopy.ts (44); glossary expanded with six new terms |
| Risk | R-LEO-AI-083 | analyzed | Junior operator makes wrong coding-review decision due to unexplained clinical terms |
| Verification Test | VT-LEO-AI-118 | passed | 19 Jest cases: eight split modules <=500 LOC, CODING_REVIEW_INTRO FK <=9, seven glossary terms <=9, CodingReviewCasesModal empty-state Props preserved |
| Design Input | DI-LEO-AI-124 | draft | Milestone temporal integrity: MIN_REFERRAL_TO_DIAG_DAYS gap + PRISM authoritative primacy over generic text referrals |
| Design Output | DO-LEO-AI-121 | draft | _config.MIN_REFERRAL_TO_DIAG_DAYS; _grouping._find_best_referral gap guard; anchor_detector._RE_REFERRAL_PRISM + referral_subtype dedupe |
| Risk | R-LEO-AI-084 | analyzed | False same-day referral-to-diagnosis interval misleads quality improvement decisions |
| Verification Test | VT-LEO-AI-119 | passed | 11 pytest cases: same-day skip, earlier-referral preference, env override, PRISM regex positive/negative, PRISM primacy, generic fallback, parametrised gap checks |
| Design Input | DI-LEO-AI-125 | draft | NCDA interval KPIs computed and persisted as named properties on every EpisodeOfCare with prerequisite milestones |
| Design Output | DO-LEO-AI-122 | draft | kpi_calculator.calculate_kpis wired into build_episodes; _DIAGNOSIS_MILESTONES / _TREATMENT_MILESTONES accept canonical + legacy keys; MATCH-only persistence |
| Design Output | DO-LEO-AI-125 | approved | libs/metrics consolidation; kpi_calculator and scripts/build_ncda_export.py delegate to shared interval KPI math |
| Risk | R-LEO-AI-085 | analyzed | Inconsistent interval KPIs across dashboards when computed ad-hoc per router |
| Verification Test | VT-LEO-AI-120 | passed | Covers complete milestone set, missing milestones, idempotency, build_episodes integration, null-safety; 37 cases including libs/metrics parity |
| Design Input | DI-LEO-AI-126 | draft | Staging enrichment uses diagnosis + 90 day window and filters evidence rows by cancer-type specialty markers |
| Design Output | DO-LEO-AI-123 | draft | libs/clinical_scoping specialty markers; staging_enrichment._choose_window and filter_rows_by_specialty integration |
| Risk | R-LEO-AI-086 | analyzed | Staging cross-contamination between concurrent cancer pathways for the same patient |
| Verification Test | VT-LEO-AI-121 | passed | Marker coverage, window calculation, filtering, fallback when no rows match marker |
| Design Input | DI-LEO-AI-127 | draft | Safety-net alert persistence with Patient edge + canonical alert_id in analytics router |
| Design Output | DO-LEO-AI-124 | draft | services/analysis_worker/app/analyzers/safety_net_persistence.py; subgraph wiring; dashboards.py alert_id cleanup |
| Risk | R-LEO-AI-087 | analyzed | Safety-net alerts lost (never persisted) or silently unactionable (router matches wrong key) |
| Verification Test | VT-LEO-AI-122 | passed | 11 pytest cases: persistence, Patient edge, FOR_EPISODE link, idempotency, alert_id in router SELECT/MATCH/SET, subgraph wiring |
| Verification Test | VT-LEO-AI-124 | passed | 17 pytest cases: NCDA ground-truth regression harness - cardinality/join integrity, schema validity, distribution tripwires, interval KPI parity via libs.metrics |
| Design Input | DI-LEO-AI-134 | draft | Canonical NCDA 'Confirmed Cancer' cohort shared by every analytics endpoint via libs.analytics.cohorts |
| Design Output | DO-LEO-AI-131 | draft | libs/analytics/cohorts.py helpers; audit.py, _audit_sections.py, dashboards.py, mission_control.py refactored to use canonical cohort |
| Risk | R-LEO-AI-092 | mitigated | Divergent 'confirmed cancer' definitions gave 17 vs 91 on the same NCDA dashboard; consolidated to the NCDA publication cohort |
| Verification Test | VT-LEO-AI-130 | passed | 14 pytest cases: cohort-helper unit tests, router-import enforcement, live 91 baseline pin for 2025 (passed 2026-04-17) |
| Verification Test | VT-LEO-AI-163 | passed | 6 pytest cases: regression for the 2026-04-17 cohort refinement -- in_progress + diagnosis_confirmed IS counted, closed_benign + spurious diagnosis_confirmed is NOT counted, all four excluded statuses (merged, closed_phantom, closed_related, closed_benign) enforced; live-DB parity confirmed 47 -> 50 in the 2024-2026 window and 80 -> 83 all-time |
| Design Input | DI-LEO-AI-136 | verified | Episode builder two-pass referral matching with fallback-any-site claim + honest NULL referral_date for truly floating episodes (2026-04-16 rebuild: 2025 2WW rate 17.6% -> 49.1%) |
| Design Input | DI-LEO-AI-137 | verified | Evidence-wins duplicate-episode merger with IS_PART_OF edge migration via MOVE_LINKS_Q; NSS clusters participate (2026-04-16 rebuild: 210 duplicates consolidated, 2025 eps/patient 1.52 -> 1.15) |
| Design Input | DI-LEO-AI-138 | verified | Broadened SPECIALTY_MARKERS['breast'] regex (endocrine therapy, invasive ductal/lobular, BRCA, axilla, sentinel node, fast-track phrasing) + childrens_tumour regex tightening. Recognises "Fast track referral for suspected <site>" canonical SNOMED phrasing end-to-end |
| Design Output | DO-LEO-AI-133 | approved | Episode builder _grouping/_auto_close/_cypher/_persistence changes implementing fallback-claim + evidence-wins merge; libs/episodes/duplicate_resolver.py |
| Design Output | DO-LEO-AI-134 | approved | libs/clinical_scoping/specialty_markers.py broadened breast regex + childrens_tumour tightening |
| Risk | R-LEO-AI-096 | mitigated | NCDA 2WW referral under-counting (16 of 91, 17.6%) caused by strict same-site matching + tight breast regex + diagnosis-date back-fill (post-fix 26 of 53, 49.1%) |
| Risk | R-LEO-AI-097 | mitigated | Over-aggressive duplicate-merge could collapse a genuine second-primary cancer; mitigated by evidence-wins rule + reversibility via merged_into chain |
| Verification Test | VT-LEO-AI-137 | passed | 9 pytest cases pass 2026-04-16: two-pass referral match (strict + fallback), honest NULL referral_date, MIN_REFERRAL_TO_DIAG_DAYS gate, DIAG_LOOKBACK_DAYS gate, strict precedence, idempotency, referral_match_method graph persistence |
| Verification Test | VT-LEO-AI-138 | passed | 22 pytest cases pass 2026-04-16: pure-logic evidence-wins (cluster, evidence_cancer_type, pick_winner, tie-breakers, ambiguous-skip) + integration (MOVE_LINKS_Q then MARK_MERGED_Q, idempotency, retry-on-failure) |
| Verification Test | VT-LEO-AI-139 | passed | 23 pytest cases pass 2026-04-16: broadened breast regex (legacy anchors, new anchors, fast-track phrasing, real-text corpus >=18/20 recall, negative-corpus specificity); end-to-end verified against live graph encounter text |
| Design Input | DI-LEO-AI-145 | verified | first_seen milestone: _RE_FIRST_SEEN detects "Seen in fast-track/2WW clinic" attendance text; AnchorResult gains first_seen_anchors; _build_closed/open_episode writes IS_PART_OF {milestone_type: 'first_seen'} + first_seen_date on EpisodeOfCare; MIN_REFERRAL_TO_DIAG_DAYS=0 for same-day PRISM referrals (2026-04-17) |
| Design Output | DO-LEO-AI-141 | draft | anchor_detector.py + episode_builder _config/_types/_cypher/_persistence/_builder first_seen wiring |
| Verification Test | VT-LEO-AI-143 | passed | 14 pytest cases pass 2026-04-17: _RE_FIRST_SEEN corpus, priority-over-generic-referral, 8-tuple bucket routing, _first_seen_link_anchors window claiming (6 sub-cases), MIN_REFERRAL_TO_DIAG_DAYS=0 |
| Design Input | DI-LEO-AI-146 | verified | Wave E Phase 2a-iv GoldLabelDetailDialog chrome rebuild on @leo/design-system: title strip + actions bar + suggestions panel + delete confirm extracted to GoldLabelDetailDialog/; single primary action with morphing label; status pill; kebab-disclosed delete (passed 2026-04-17) |
| Design Output | DO-LEO-AI-142 | approved | Five chrome sub-components under services/ui/src/components/gold-dataset/GoldLabelDetailDialog/: DialogTitleStrip, DialogActionsBar, SuggestionsPanel, DeleteConfirmPanel, AddTermPopover |
| Verification Test | VT-LEO-AI-144 | passed | 9 jest cases: panel imports + JSX usage assertions, status pill ready/work-counts, single primary footer + kebab disclosure, primary label morph, suggestions panel collapse, delete confirm label toggle (passed 2026-04-17) |
| Risk | R-LEO-AI-100 | mitigated | Wave E Phase 3 chrome unification trade-off: destructive / write controls (Deactivate rule, Delete concept group, Cancel sync, Create area gating) could be demoted by single-primary ToolbarActions. Mitigated by leaving destructive controls visible in chrome rather than overflow kebabs, preserving showCreateButton role gating, and statically asserting every legacy handler in VT-LEO-AI-145 |
| Design Input | DI-LEO-AI-147 | verified | Wave E Phase 3 CRUD Knowledge tabs (Context Rules + Surface Forms + Domains + Terminology) on @leo/design-system: StatHero + ToolbarActions + SegmentedTabs/FilterBar chrome on every page; per-page body primitive (ReviewListCard + ProgressiveReveal for Context Rules, restyled concept-group cards for Surface Forms, framer-motion DomainCard grid for Domains, tone-accented PackageCard list + LogPanel for Terminology); legacy Breadcrumbs / h5 page titles / "Domain Configuration" heading removed; every legacy handler preserved (passed 2026-04-17) |
| Design Output | DO-LEO-AI-143 | approved | Four redesigned Next.js pages under services/ui/src/app/settings/: context-rules/page.tsx, surface-forms/page.tsx, domains/page.tsx, terminology/page.tsx |
| Verification Test | VT-LEO-AI-145 | passed | 20 jest cases (services/ui/src/__tests__/crud-tabs-chrome.test.tsx): primitive imports per page, legacy chrome removal (Breadcrumbs / h5 / "Domain Configuration"), handler preservation (loadRules / handleAdd / handleDeactivate / exportContextRulesPdf / handleAuditDuplicates / handleDeduplicate / handleSuggest / handleDeleteGroup / handleAddAlias / loadDomains / createDomain / fetchStatus / startSync / cancelSync / EventSource), single-primary ToolbarActions per page, body primitive selection per page (passed 2026-04-17) |
| Risk | R-LEO-AI-101 | mitigated | Wave E Phase 4 AI Instructions list redesign trade-off: ReviewListCard rebuild risks dropping the only entry points to author or edit AI instructions (router.push to /admin/prompts/:id and /admin/prompts/new). Mitigated by single-primary ToolbarAction for the new-instructions route and ReviewListCard.onSelect wiring to the same router contract; VT-LEO-AI-146 statically asserts both routes |
| Design Input | DI-LEO-AI-148 | verified | Wave E Phase 4 AI Instructions list redesign on @leo/design-system: StatHero (4 tiles) + FilterBar + SegmentedTabs (counts per category) + ToolbarActions (single primary "New instructions") + ReviewListCard (grouped or flat); legacy h4 page title + PromptCard grid + raw TextField search removed; existing /api/prompts fetch and router.push routes preserved; detail-page editor rebuild deferred (passed 2026-04-17) |
| Design Output | DO-LEO-AI-144 | approved | Single redesigned Next.js page services/ui/src/app/admin/prompts/page.tsx (~470 LOC) using StatHero + FilterBar + SegmentedTabs + ToolbarActions + ReviewListCard with the original categorise / humanName / formatDate helpers retained |
| Verification Test | VT-LEO-AI-146 | passed | 8 jest cases (services/ui/src/__tests__/prompts-list-chrome.test.tsx): primitive + type-alias imports, legacy-chrome removal (h4 / PromptCard / CardActionArea / TextField), handler preservation (api.get('/api/prompts') / router.push to /admin/prompts/:id and /admin/prompts/new / sortByIsoDateDesc), grouped vs flat modes, single-primary ToolbarAction, loading/empty/no-match states, four canonical stat-tile labels, SegmentedTabs API correctness (passed 2026-04-17) |
| Risk | R-LEO-AI-102 | mitigated | Histology vocabulary expansion may mis-classify suspected/non-cancer text as confirmed cancer (e.g. "Fast track referral for suspected invasive ductal carcinoma" or "PRISM 2WW: ?DCIS"). Mitigated by upstream _is_referral_enc / _has_no_cancer guards in _classify_text_encounters which run BEFORE _RE_CONFIRMED_CANCER bucket routing; VT-LEO-AI-147 TC-007 statically asserts the suspected-DCIS guard and TC-002 asserts 0/6 false-positives on suspected/referral corpus |
| Design Input | DI-LEO-AI-149 | verified | Histology vocabulary expansion in services/analysis_worker/app/analyzers/anchor_detector.py: _RE_CONFIRMED_CANCER + _RE_CANCER_TERM extended with histology-letter terms (invasive ductal/lobular, adenocarcinoma, DCIS/LCIS, BCC/SCC, Gleason, Dukes, FIGO with letter suffix, Breslow, Clark level, TNM staging, grades 1-3, differentiation grades, in-situ, metastatic). _RE_NO_CANCER extended with benign-histology vocabulary (lipoma, fibroadenoma, sebaceous/epidermal cyst, seborrhoeic/actinic keratosis, skin tag, dermatofibroma, no malignant cells, no atypia, unremarkable biopsy, hyperplastic/inflammatory polyp, fibrocystic change, hamartoma, discharge back to GP, reassurance given). Closes 24/79 missed-diagnosis and 19/79 missed-benign-closure auto-close failures (passed 2026-04-17) |
| Design Output | DO-LEO-AI-145 | approved | Three regex constants in services/analysis_worker/app/analyzers/anchor_detector.py (_RE_CONFIRMED_CANCER, _RE_CANCER_TERM, _RE_NO_CANCER) routing histology-letter and benign-result vocabulary into the diagnosis and benign-closure buckets respectively. No Cypher / persistence changes |
| Verification Test | VT-LEO-AI-147 | passed | 7 pytest cases (tests/test_histology_vocabulary.py): TC-001 18 histology-positive phrases all match _RE_CONFIRMED_CANCER, TC-002 0/6 false-positives on suspected/referral corpus, TC-003 18 benign phrases all match _RE_NO_CANCER, TC-004 0/6 false-positives on malignant corpus, TC-005 4 histology cancers route to diagnosis bucket idx 1, TC-006 4 benign encounters route to benign-closure bucket idx 4, TC-007 referral guard preserves "Fast track referral for suspected invasive ductal carcinoma" and PRISM-DCIS guard (passed 2026-04-17) |
| Risk | R-LEO-AI-103 | mitigated | Diagnosis-aware open-episode rescue may pair a confirmed cancer diagnosis with the wrong open episode (cross-site contamination, late-stage diagnosis attached to old referral). Mitigated by site_keys_compatible site check (specific site must match), STALE_HARD_DAYS window cap, exclusion of pathway-completion and non-present assertion anchors, hitl_flag=True forcing reviewer confirmation; VT-LEO-AI-148 TC-003/TC-004/TC-005 statically assert each constraint |
| Design Input | DI-LEO-AI-150 | verified | Diagnosis-aware open-episode completion rescue + first_seen_date persistence defect fix in services/analysis_worker/app/analyzers/episode_builder/_builder.py. Adds _rescue_diagnosis_for_open_episode() and integrates it into _build_open_episode so in_progress episodes with a site-compatible confirmed diagnosis anchor in [ref_date, ref_date+STALE_HARD_DAYS] are promoted to 'completed' (with end_date = earliest diag date and hitl_flag=True) BEFORE the stale auto-close pass can mark them stale_post_specialist or stale_no_diagnosis. Reorders _first_seen_link_anchors() to run before _write_episode so first_seen_date persists on EpisodeOfCare. Post-rebuild 2026-04-17: auto_closed 79->44 (-44%), completed 52->109 (+110%), with_first_seen 31->130 (+319%) (passed 2026-04-17) |
| Design Output | DO-LEO-AI-146 | approved | _rescue_diagnosis_for_open_episode() helper (~30 LOC) and rescue branch (~12 LOC) inside _build_open_episode in services/analysis_worker/app/analyzers/episode_builder/_builder.py. Also reorders _first_seen_link_anchors() to compute fs_date BEFORE _write_episode and pipes fs_date through WriteEpisodeParams.first_seen_date. STALE_CLOSE_Q in _cypher.py is unchanged (already filters status='in_progress', so cannot touch the rescued completed episodes) |
| Verification Test | VT-LEO-AI-148 | passed | 17 pytest cases (tests/test_open_episode_diagnosis_rescue.py): TC-001 earliest in-window date returned, TC-002 (4 sub-cases) empty/before-ref/after-window/None ref_date all return None, TC-003 (3 sub-cases) lung-on-breast None / NSS-on-breast rescued / breast-on-breast rescued, TC-004 pathway-completion + possible-assertion both filtered, TC-005 status='completed' + end_date set + hitl_flag=True + hitl_reason starts with "Auto-completed: confirmed cancer diagnosis", TC-006 LINK_ENCOUNTERS includes ('d-001','diagnosis_confirmed') alongside ('ref-001','referral'), TC-007 first_seen_date persists when anchor present and is None when absent (DI-LEO-AI-145 defect fix verified) (passed 2026-04-17) |
| Design Input | DI-LEO-AI-151 | verified | Wave E polish: Knowledge tab width parity (TAB_WIDTH map promotes ai-instructions and clinical-guidelines from 'reading' to 'wide' so all eight Knowledge tabs render at 1600px) + DomainCard / PackageCard visual consistency (canonical 12px radius / 18px padding / 3px tone-coded accent strip / 168px minHeight / canonical knowledge tone palette) + Domains responsive grid capped at 3 columns (passed 2026-04-16) |
| Design Output | DO-LEO-AI-147 | approved | TAB_WIDTH map update in services/ui/src/app/admin/knowledge/page.tsx; DomainCard re-laid-out in services/ui/src/app/settings/domains/page.tsx with header (icon + title + tone chip), description body, and footer (subdomain count + chevron); grid capped at 3 cols; PackageCard radius / padding / minHeight aligned in services/ui/src/app/settings/terminology/page.tsx |
| Verification Test | VT-LEO-AI-149 | passed | 6 jest cases (services/ui/src/__tests__/knowledge-tab-width-and-cards.test.tsx): TC-001 every Knowledge tab maps to 'wide', TC-002 DomainCard 12px/18px/3px tokens, TC-003 PackageCard 12px/18px/3px tokens, TC-004 Domains grid capped at 3 cols (no lg:4), TC-005 minHeight >= 160 on both cards, TC-006 DomainCard tone chips use the canonical knowledge palette (passed 2026-04-16) |
| Design Input | DI-LEO-AI-152 | verified | Wave E Phase 5 Clinical Guidelines orchestrator on @leo/design-system: sticky SegmentedTabs jump strip (Load / Review / Compile) + four motion-enabled StepCards (12px radius, 3px tone-coded accent strip, framer-motion stagger entry) wrapping the unchanged child sections; legacy 4px-accent SectionBox / Card chrome removed; loadedRefreshKey + ruleRefreshKey state bridges preserved verbatim (passed 2026-04-16) |
| Design Output | DO-LEO-AI-148 | approved | services/ui/src/app/admin/guidance/page.tsx rebuilt: SegmentedTabs sticky jump strip + StepCard primitive (fm.section, 12px radius, 1px divider border, 3px tone-coded accent strip, motion stagger) wrapping NiceLoaderSection / LoadedGuidelinesPanel / RuleReviewSection / BitmapLifecycleSection unchanged. handleJump scrolls the matching StepCard into view. Numbered 28px pip rendered inside each StepCard header |
| Verification Test | VT-LEO-AI-150 | passed | 9 jest cases (services/ui/src/__tests__/guidance-page-chrome.test.tsx): TC-001 SegmentedTabs imported, TC-002 framer-motion imported, TC-003 legacy 4px-accent + Card / CardContent imports gone, TC-004 StepCard 12px radius + 3px accent strip, TC-005 all four child sections preserved, TC-006 both refresh-key state bridges preserved (R-104 mitigation), TC-007 sticky guidance-jump-strip with three steps, TC-008 SegmentedTabs API correct, TC-009 step ids + step props {1}/{2}/{3} (passed 2026-04-16) |
| Risk | R-LEO-AI-104 | mitigated | Wave E Phase 5 Clinical Guidelines redesign could silently break the loadedRefreshKey / ruleRefreshKey state bridges, leaving QA reviewers staring at stale Loaded-guidelines / Rule-review panes after loading a new NICE guideline or generating new rules. Mitigated by preserving the prop contract verbatim, the static CI gate in VT-LEO-AI-150 TC-006, and the always-visible sticky jump strip; severity minor (no patient-data write path); residual risk low |
| Design Input | DI-LEO-AI-153 | verified | Wave E Phase 6 Pathways admin list on @leo/design-system: 815 LOC monolith split into page.tsx orchestrator + PathwayCard.tsx + dialogs.tsx + templates.ts + types.ts; StatHero (4 tiles) + SegmentedTabs status filter (All / Live / Drafts / Retired with counts) + ToolbarActions ("New pathway" single primary); PathwayCard rebuilt on the canonical 12px / 18px / 3px-accent / motion-stagger pattern; all FHIR + routing handlers (api.get/post/put/delete on /fhir/PlanDefinition, router.push to /admin/pathways/:id) preserved; type-the-name delete confirm gate + explicit publish dialog preserved; all four starter templates (blank, extraction-only, extraction-verify-persist, training-audit) preserved; detail-page canvas editor explicitly deferred (passed 2026-04-16) |
| Design Output | DO-LEO-AI-149 | approved | services/ui/src/app/admin/pathways/{page.tsx, PathwayCard.tsx, dialogs.tsx, templates.ts, types.ts}: page orchestrator owns state + handlers; PathwayCard is presentational with motion stagger; dialogs.tsx exports NewPathwayDialog (template picker), PublishDialog (with optional version notes), DeletePathwayDialog (with type-the-name confirm gate); templates.ts ships PATHWAY_TEMPLATES catalogue (4 starter templates + baseConfig helper); types.ts exports the shared PlanDefinition shape |
| Verification Test | VT-LEO-AI-151 | passed | 11 jest cases (services/ui/src/__tests__/pathways-list-chrome.test.tsx): TC-001 page imports design-system primitives + sibling modules, TC-002 legacy h5 page header replaced by StatHero, TC-003 FHIR + routing handlers preserved, TC-004 SegmentedTabs API correct, TC-005 single primary action, TC-006 four canonical stat tiles, TC-007 PathwayCard 12px / 18px / 3px-accent + framer-motion stagger, TC-008 full per-card action surface preserved, TC-009 dialog exports + delete-name-gate (R-105 mitigation), TC-010 four starter templates ship, TC-011 loading / empty / no-match copy strings reachable (passed 2026-04-16) |
| Risk | R-LEO-AI-105 | mitigated | Wave E Phase 6 Pathways list redesign could weaken the destructive-action confirmation gates (publish / retire / delete) and let an operator misclick an active runtime pathway into deletion. Mitigated by preserving the type-the-name delete confirm gate, keeping Publish behind an explicit dialog with optional version notes, restricting variant 'primary' on ToolbarActions to 'New pathway' (no destructive primary), disabling per-card destructive actions while busy / for seeded pathways, and gating future regressions through the static CI checks in VT-LEO-AI-151 TC-008 + TC-009; residual risk low |
| Design Input | DI-LEO-AI-154 | verified | Manual review-time editing of AI-generated guidance rules: centred MUI Dialog (~1100px) with two-column layout (editable logic tree + debounced SNOMED concept search), replaces the prior read-only side drawer. Reviewers can replace / add / remove SNOMED concepts, edit AT_LEAST minimums and demographic checks, and switch group kinds; edits persist as a NEW versioned :AppropriatenessRule that supersedes the predecessor (status='superseded') with an immutable GuidanceAuditEvent. Server-side validation enforces depth <= 6, node count <= 80, NOT arity 1, AT_LEAST min in [1, children], and verifies every SNOMED concept exists in the knowledge graph. The duplicated NICE recommendation block and redundant plain-English summary in the prior drawer were removed (passed 2026-04-17) |
| Design Output | DO-LEO-AI-150 | approved | services/api/app/services/guidance_rule_edit.py (LogicNode/RuleUpdates models, validate_logic_tree, apply_rule_edit), services/api/app/routers/guidance_rules.py (extended RuleDecisionRequest.updates, _decide_rule_with_edits dispatch), services/ui/src/app/admin/guidance/EditRuleDialog/{index.tsx, LogicTreeEditor.tsx, ConceptSearchPanel.tsx, treeOps.ts, types.ts}; integrated into RuleReviewSection.tsx (drawer removed, plain-English summary on session-approved card removed) |
| Verification Test | VT-LEO-AI-152 | passed | 18 pytest cases (services/api/tests/test_guidance_rule_edit.py) covering validate_logic_tree, apply_rule_edit, and the router edit-path; 13 jest cases (services/ui/src/app/admin/guidance/EditRuleDialog/__tests__/) covering tree operations, save gating, concept removal, and SNOMED-search-driven concept replacement (passed 2026-04-17) |
| Risk | R-LEO-AI-106 | mitigated | Reviewer-edited guidance rule could contain an incorrect or misclassified SNOMED concept leading to wrong patient match decisions (delayed diagnosis or inappropriate referral). Mitigated by versioned write-back (predecessor preserved as 'superseded' so any incorrect edit is rollback-safe), server-side rejection of unknown SNOMED concept ids and structurally invalid trees, required >= 3 char "Reason for edit" recorded on an immutable GuidanceAuditEvent, and a "View NICE source" link inside the dialog so the reviewer can compare against the verbatim recommendation; severity serious, residual risk low (acceptable) |
| Design Input | DI-LEO-AI-155 | verified | Text-based cancer-site classification using a gold-mined surface-form dictionary (services/analysis_worker/app/analyzers/cancer_site_terms.py): 955 unique lower-case literals across 29 NCDA-aligned site keys mined by scripts/_mine_cancer_site_terms.py from 1,620 GoldLabel entities and 4,956 SurfaceForm-MAPS_TO-Concept edges in the knowledge graph; surface-form anatomy-stem filter rejects noise such as "cramps" / "amy was not elevated" / "abnormal lfts"; anchor_detector.py _classify_text_encounters now tags each text anchor with site_key + site_hits via match_cancer_site(text), and episode_builder/_site_resolution.py _extract_condition_key_from_anchor prefers explicit site_key over the generic "Text: ..." sentinel concept_name. Post-rebuild cancer_type coverage 0/230 (0%) -> 148/183 (80%) on active episodes, exceeding the >=70% acceptance criterion (passed 2026-04-17) |
| Design Output | DO-LEO-AI-151 | approved | services/analysis_worker/app/analyzers/cancer_site_terms.py (CANCER_SITE_TERMS dict, _CANCER_SITE_REGEXES, match_cancer_site() helper - all auto-generated); services/analysis_worker/app/analyzers/anchor_detector.py (_classify_text_encounters writes site_key/site_hits onto every text anchor base); services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py (_extract_condition_key_from_anchor prefers anchor['site_key'] before falling back to concept_id / concept_name); scripts/_mine_cancer_site_terms.py (regenerator that pulls from KnowledgeGraphClient, applies the malignancy + anatomy-stem filter, and writes the dictionary module) |
| Verification Test | VT-LEO-AI-153 | passed | 13 pytest cases (tests/test_cancer_site_terms.py): TC-001 specific cancer text yields breast key, TC-002 highest-hit site wins on mixed text (incidental organ mention outweighed), TC-003 empty / no-cancer text returns None, TC-004 every dictionary key is a canonical NCDA key (no drift), TC-005 noise filter drops generic findings ("cramps", "amy was not elevated", "abnormal lfts"), TC-006 _extract_condition_key_from_anchor prefers explicit site_key, plus a non-regression check that coded anchors still resolve correctly, plus 6 parametrised smoke cases (breast, prostate, colorectal, melanoma, ovarian, myeloma) (passed 2026-04-17) |
| Risk | R-LEO-AI-107 | mitigated | Text-mined surface forms could mis-classify the cancer site of an episode (e.g. a single "breast" mention in a colorectal patient's family-history note). Mitigated by the surface-form anatomy-stem filter (the surface itself must contain an anatomy/histology stem, not just the parent concept FSN), the highest-hit-wins selection rule (a single incidental organ mention is outweighed by the cluster of on-topic terms), and the procedural HITL review path that always shows the reviewer the source encounter text alongside the classification. Severity minor (no patient harm; report slice only), residual risk low (acceptable) |
| User Need | UN-LEO-AI-072 | active | Pathway editor must feel safe and predictable for QA-RA leads building clinical pipelines: every save / publish / retire / delete action must announce its outcome, every node must offer the same configure interaction surface, and load failures must surface inline rather than leaving an empty canvas |
| Design Input | DI-LEO-AI-156 | verified | Wave E Phase 6b-ii pathway editor chrome decomposition: services/ui/src/app/admin/pathways/[id]/page.tsx (5,960 LOC orchestrator) extracted into stateless prop-driven sibling modules under services/ui/src/app/admin/pathways/[id]/editor/ -- PathwayToolbar.tsx (top toolbar: back/name/status/save/publish/retire/add-node/auto-layout/test/history/delete), PathwaySaveBar.tsx (sticky bottom save state idle|dirty|saving|saved|error), dialogs/EdgeDeleteConfirm.tsx, dialogs/PublishDialog.tsx (pipeline preview + version notes), dialogs/DeletePathwayDialog.tsx (type-the-name confirm gate) and editor/utils.ts (formatSaveTime + lifecycleLabel + lifecycleColor); legacy inline JSX + unused MUI imports (SaveIcon, CloudUploadIcon, AccountTreeIcon) removed; every existing save/publish/delete/add-node handler preserved verbatim; orchestrator state remains the single source of truth (passed 2026-04-16) |
| Design Output | DO-LEO-AI-152 | approved | services/ui/src/app/admin/pathways/[id]/editor/PathwayToolbar.tsx (toolbar shell, prop-driven, no useState beyond local UI menu anchors); services/ui/src/app/admin/pathways/[id]/editor/PathwaySaveBar.tsx (sticky save-state ribbon, fully prop-driven); services/ui/src/app/admin/pathways/[id]/editor/dialogs/EdgeDeleteConfirm.tsx + PublishDialog.tsx + DeletePathwayDialog.tsx (each one prop-driven, single primary action, destructive primary disabled until confirmation gate satisfied); services/ui/src/app/admin/pathways/[id]/editor/utils.ts (pure helpers); services/ui/src/app/admin/pathways/[id]/page.tsx orchestrator updated to render the new modules and own all state |
| Verification Test | VT-LEO-AI-154 | passed | 13 jest cases (services/ui/src/__tests__/pathway-canvas-chrome.test.tsx): TC-001 every editor module exists on disk, TC-002 page.tsx imports the new modules, TC-003 page.tsx renders PathwayToolbar/EdgeDeleteConfirm/PublishDialog/DeletePathwayDialog, TC-004 legacy inline toolbar/dialog markup removed, TC-005 unused MUI icon imports removed, TC-006 PathwayToolbar is prop-driven (no internal data fetches), TC-007 dialogs are prop-driven (no internal mutators), TC-008 all canonical save/publish/delete handlers reach the new components, TC-009 every IconButton in PathwayToolbar carries an aria-label, TC-010 PathwaySaveBar exposes the SaveBarState union, TC-011 utils.ts exports the canonical helper set, TC-012 every chrome module stays under 500 LOC hard limit, TC-013 page.tsx no longer defines formatSaveTime locally (passed 2026-04-16) |
| Risk | R-LEO-AI-108 | mitigated | Decomposing the pathway editor chrome (~5,960 LOC orchestrator) could silently change save / publish / delete semantics or weaken the destructive-action confirmation gates and let an operator mis-click an active runtime pathway into deletion. Mitigated by keeping every extracted component fully prop-driven (orchestrator state is the only source of truth), preserving the type-the-name delete confirm gate, keeping Publish behind an explicit dialog with optional version notes, restricting variant 'primary' on the toolbar to non-destructive actions, and gating future regressions through the static CI checks in VT-LEO-AI-154 (legacy markup removal, prop-driven verification, handler preservation, aria-label coverage); residual risk low (acceptable) |
| Design Input | DI-LEO-AI-157 | verified | Wave E Phase 6b-iii pathway canvas node primitives: all 10 pathway node types (action, condition, rest_connector, queue_publish, trigger, parallel, merge, transform, source, output, viewer) refactored onto a shared BaseNode + NodeHandle + NodeStatusStrip + NodeHeader contract under services/ui/src/components/pathway/nodes/_base/. Canonical 12px borderRadius / 2px border / single-click + Enter/Space activation are applied centrally. Every React Flow Handle gains a generated aria-label of the form 'input port <id>' / 'output port <id>'. Double-click configure migrated to single-click on SourceNode / OutputNode / MiniHitlNode (with matching helper text). resolveRunStatus() centralises raw step result -> NodeRunStatus mapping for ActionNode (the only node consuming live test trace today). All previous data-shape contracts are preserved (passed 2026-04-16) |
| Design Output | DO-LEO-AI-153 | approved | services/ui/src/components/pathway/nodes/_base/BaseNode.tsx (canonical shell, single-click + keyboard activation, halted/running animations); _base/NodeHandle.tsx (Handle wrapper with auto-generated aria-label, PORT_COLORS by dataType); _base/NodeHeader.tsx (icon + bold h3 title + trailing slot); _base/NodeStatusStrip.tsx (idle / queued / running / completed / halted / error / skipped); _base/index.ts barrel; ActionNode.tsx + ConditionNode.tsx + ConnectorNode.tsx + TriggerNode.tsx + ParallelNode.tsx + MergeNode.tsx + TransformNode.tsx + SourceNode.tsx + OutputNode.tsx + MiniHitlNode.tsx all refactored to use the shared primitives |
| Verification Test | VT-LEO-AI-155 | passed | 15 jest cases (services/ui/src/__tests__/pathway-canvas-nodes.test.tsx): TC-001 _base primitive files exist, TC-002 _base/index.ts re-exports the four primitives, TC-003 every node imports from ./_base, TC-004 every node renders <BaseNode> as the wrapper, TC-005 every node uses NodeHandle (zero raw <Handle ... />), TC-006 NodeHandle always sets aria-label, TC-007 BaseNode unifies single-click + Enter/Space activation, TC-008 zero nodes bind onDoubleClick to onConfigure, TC-009 every interactive node forwards onConfigure to onActivate, TC-010 BaseNode pins canonical 12px / 2px tokens, TC-011 NodeStatusStrip exposes the canonical run states, TC-012 ActionNode delegates run state to NodeStatusStrip via resolveRunStatus, TC-013 nodeTypes registry still exposes all 11 keys, TC-014 every file < 500 LOC hard limit, TC-015 SOURCE_DEFINITIONS / OUTPUT_DEFINITIONS registries preserved (passed 2026-04-16) |
| Risk | R-LEO-AI-109 | mitigated | Replacing 10 hand-rolled pathway node shells with a shared BaseNode + NodeHandle + NodeStatusStrip could regress connection routing (NodeHandle accidentally overriding Handle.position), dry-run feedback (halted glow replaced by a generic error pip), or accessibility (aria-label drift). Mitigated by NodeHandle never overriding the Handle position / top / right / transform fields React Flow needs, NodeStatusStrip retaining all six visual states verbatim, BaseNode binding onClick + onKeyDown together so every clickable node is also keyboard-operable, and static-source VT-LEO-AI-155 asserting no node still uses raw <Handle /> JSX or onDoubleClick configure. Residual risk low (acceptable) |
| User Need | UN-LEO-AI-074 | active | Hand-authored gold seed for cancer / benign discrimination: when the NER model is trained, it must learn from a small but precise hand-authored seed of cancer-positive and benign / excluded / normal control sentences taken from real GP records, so that the spancat head reliably distinguishes a confirmed malignancy from a normal investigation, an excluded cancer or a benign finding |
| Design Input | DI-LEO-AI-163 | verified | Manual gold seed for cancer / benign discrimination: design-controls/training-data/manual-gold-seed-2026-04-17.yaml carries 21 hand-authored records (4 cancer-positive + 17 benign / excluded / normal control) drawn from real GP encounters with every sentence already de-identified and re-validated against libs.utils.deidentify.deidentify_text + libs.ner.deid_validator.DeIdValidator; scripts/seed_manual_gold_records.py loads the manifest, re-derives entity start/end via libs.ner.span_finder.find_span, computes deterministic candidate_id (sha256 of text) and label_id (GL- + first 16 hex of sha256(text + sorted entity texts)), enforces lowercase SNOMED semantic-tag labels and the canonical assertion vocabulary, and idempotently UPSERTs one TrainingCandidate (status=completed) + one linked GoldLabel per record into the Knowledge Graph with the (:TrainingCandidate)-[:PRODUCED]->(:GoldLabel) edge (passed 2026-04-17) |
| Design Output | DO-LEO-AI-159 | approved | design-controls/training-data/manual-gold-seed-2026-04-17.yaml (21-record manifest); scripts/seed_manual_gold_records.py (load_manifest, prepare_record, prepare_all, _candidate_id, _label_id, write_records helpers; dry-run by default with --commit gating Knowledge Graph writes); idempotent UPSERT of TrainingCandidate (status='completed', schema_version='v4') and linked GoldLabel (schema_version='2.0') via UPSERT_TRAINING_CANDIDATE / UPSERT_GOLD_LABEL Cypher |
| Verification Test | VT-LEO-AI-160 | passed | 13 pytest cases (tests/scripts/test_seed_manual_gold_records.py): TC-001 real manifest loads + every entity span aligns to its surface, TC-002 postcode and email injections raise before any KG write and the real manifest passes, TC-003 candidate_id and label_id are deterministic and order-independent across re-runs, TC-004 unknown assertions raise and every canonical assertion is accepted, TC-005 unknown labels raise / uppercase labels are normalised / real manifest only uses VALID_LABELS + VALID_ASSERTIONS, plus a missing-surface guard test (passed 2026-04-17) |
| Risk | R-LEO-AI-003 | mitigated | NLP could assign the wrong context to an extracted entity (e.g. negated cancer mention coded as confirmed malignancy or a screening result coded as a procedure-only line with no DISORDER span). Mitigated by the unified ConText engine + post-processing pipeline plus the new hand-authored gold seed (DI-LEO-AI-163) which teaches the spancat / ConText pipeline the cancer-vs-benign and present-vs-refuted boundary on UK primary-care phrasing ("Cancer excluded - discharge to GP", "FOBT Normal - negative result", "nil concerns raised about malignancy"). Re-applied at every training run via the seeder script. Severity serious, residual risk low (acceptable) |
| Design Input | DI-LEO-AI-161 | verified | Stale-detector five fixes (UN-LEO-AI-006): the 41-episode 2026-04-17 deep-read of stale 2024+2025 patients identified five recurring root-causes that the episode builder needed to address. (1) libs/domains/code_inventories.py centralises curated MALIGNANCY_READ_CODES (e.g. X78WM breast, BB5j2 / X78XO endometrial), BENIGN_EXPLANATION_READ_CODES (XaK99 LPR, F5801 presbyacusis), FAST_TRACK_REFERRAL_READ_CODES (XaMeC breast, XaMeB gynaecological), BENIGN_INVESTIGATION_PHRASES ("mammogram normal", "cancer excluded - discharge to GP"), and LETTER_STUB_PATTERNS plus typed lookup helpers; (2) anchor_detector._classify_text_encounters consumes those helpers to emit diagnosis_confirmed and benign_closure anchors with explicit diagnosis_source / benign_source provenance and tags site_key + site_source="explicit_2ww_code" on referral anchors when an explicit 2WW code is present; (3) _site_resolution._extract_condition_key_from_anchor prefers explicit_2ww_code / explicit_malignancy_code over generic surface-form / SNOMED resolution; (4) episode_builder/_cypher.STALE_CLOSE_Q gains an EXISTS guard so episodes with diagnosis / diagnosis_confirmed / benign_closure / treatment_started milestones are never auto-stamped stale; (5) outcome_inference extends POST_CANCER + POST_BENIGN with the new code/phrase signals (with overlap filtering to preserve the inference engine's HITL_REQUIRED tie-break behaviour). Live-corpus wipe-and-rebuild via scripts/_wipe_episodes_and_rebuild.py 2026-04-17: total EpisodeOfCare 518 -> 360 (phantoms + duplicates resolved), stale_post_specialist + stale_no_diagnosis distinct patients 36 -> 6 (well below the <=12 acceptance threshold), closed_benign patients 41 -> 81 (>=25 increase met) (passed 2026-04-17) |
| Design Output | DO-LEO-AI-161 | approved | libs/domains/code_inventories.py (MALIGNANCY_READ_CODES, BENIGN_EXPLANATION_READ_CODES, FAST_TRACK_REFERRAL_READ_CODES, BENIGN_INVESTIGATION_PHRASES, LETTER_STUB_PATTERNS plus find_malignancy_code / find_benign_explanation_code / find_fast_track_referral_site / match_benign_investigation_phrase / looks_like_letter_stub helpers); services/analysis_worker/app/analyzers/anchor_detector.py _classify_text_encounters (problem-list code/phrase recognition, explicit-2ww site tagging, diagnosis_source / benign_source provenance fields); services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py _extract_condition_key_from_anchor (explicit_2ww_code precedence); services/analysis_worker/app/analyzers/episode_builder/_cypher.py STALE_CLOSE_Q (EXISTS guard for diagnosis / benign / treatment milestones); libs/pipeline/outcome_inference.py POST_CANCER + POST_BENIGN extension with overlap filtering; scripts/_wipe_episodes_and_rebuild.py orchestration |
| Design Input | DI-LEO-AI-162 | verified | DQ alert dq_letter_stub_unfilled in services/neo4j_mcp/tools/query_pack_safety.py (UN-LEO-AI-054): surfaces incoming Encounter records whose body matches LETTER_STUB_PATTERNS (e.g. "Urology to Greenfields Surgery"), is shorter than max_chars (default 200), is older than days_threshold (default 7), and whose patient has at least one EpisodeOfCare in stale_post_specialist or stale_no_diagnosis; result envelope uses the standard MCP _result helper (category="safety", summary "Found N letter stubs (>X days old) on stale episodes."); Cypher is read-only with no MERGE / SET / DELETE / CREATE; tool is auto-registered through the existing TOOLS dynamic-load path in services/neo4j_mcp/server.py (passed 2026-04-17) |
| Design Output | DO-LEO-AI-162 | approved | services/neo4j_mcp/tools/query_pack_safety.py dq_letter_stub_unfilled function and TOOLS entry; libs/domains/code_inventories.py LETTER_STUB_PATTERNS plus looks_like_letter_stub helper |
| Verification Test | VT-LEO-AI-161 | passed | 29 pytest cases (tests/test_stale_detector_fixes.py): TC-001..008 inventory helper unit tests (find_malignancy_code, find_benign_explanation_code, find_fast_track_referral_site, match_benign_investigation_phrase, looks_like_letter_stub) including positive, negative and ordering cases; TC-009..012 anchor emission for malignancy CTV3 codes (X78WM breast, BB5j2 + X78XO endometrial) plus the referral-encounter safety guard; TC-013..015 anchor emission for benign codes and investigation phrases; TC-016..018 site reconciliation and resolver precedence; TC-019..020 STALE_CLOSE_Q regression (EXISTS guard present, status assignment unchanged); TC-021..023 dq_letter_stub_unfilled MCP-tool registration, descriptor and runtime envelope; TC-024..029 outcome-inference defence-in-depth and inventory completeness (passed 2026-04-17) |
| Risk | R-LEO-AI-163 | analyzed | Curated Read/CTV3 code matching could misclassify an episode outcome (false benign closure or false diagnosis). Mitigated by clinically reviewed code inventories, diagnosis_source / benign_source provenance on every anchor, the milestone-fusion rules that still gate episode promotion, and the existing HITL operations queue. Severity serious, residual risk medium (acceptable) |
| Risk | R-LEO-AI-164 | analyzed | dq_letter_stub_unfilled may produce too many or too few alerts and delay triage of real letter-ingestion gaps. Mitigated by hand-anchored regex patterns in LETTER_STUB_PATTERNS (verified by tests), the stale-episode precondition that bounds the alert queue, and tunable days_threshold / max_chars parameters. Severity minor, residual risk low (acceptable) |
| User Need | UN-LEO-AI-075 | active | Operations users need a clear, consistent Intelligence Console: when staff and the QA/RA lead open /admin/console the page must look and behave like the rest of the redesigned admin surfaces (Knowledge tabs, Pathways list) so the AI learning loop is easy to read at a glance, the next-best action is obvious, and the underlying training/evaluation/deployment data is presented in the same visual language used elsewhere in the platform |
| Design Input | DI-LEO-AI-164 | verified | Wave E Phase 8a Intelligence Console redesign on @leo/design-system: services/ui/src/app/admin/console/page.tsx is wrapped in KnowledgePageLayout (width="wide", screenId="admin-console") so the page picks up the same 1600 px column, gutter, motion and density contracts as the Knowledge tabs and the Pathways list; the legacy HealthBar import is replaced by a new PipelineRail primitive in services/design-system/src/primitives/PipelineRail.tsx (role="tablist" pills with framer-motion stagger, status-token dots, Enter/Space activation, reduced-motion aware); the legacy NudgeBanner import is replaced by a new NudgeStrip primitive in services/design-system/src/primitives/NudgeStrip.tsx (severity in {info, warning, danger}, role="status" + aria-live="polite", color.status.* tones); a new ConsoleStagePanel module in services/ui/src/components/console/ConsoleStagePanel.tsx renders each stage body inside a design-system-tokenised card while preserving the existing accentColor + actionLabel + onAction contract; the new computeConsoleStats(state) helper in services/ui/src/components/console/useConsoleState.ts returns three live StatTile entries (gold labels, candidate queue, latest F1 or live model) for the StatHero spine; the existing stage modules (DiscoverStage, CurateStage, TrainStage, EvaluateStage, DeployStage, MonitorStage), useConsoleState public API, deriveStageHealth status mapping, deriveNudge severity mapping and the 10s polling cadence are all preserved (passed 2026-04-16) |
| Design Output | DO-LEO-AI-163 | approved | services/design-system/src/primitives/PipelineRail.tsx + NudgeStrip.tsx (re-exported via services/design-system/src/primitives/index.ts); services/ui/src/components/console/ConsoleStagePanel.tsx (design-system-tokenised stage card preserving accentColor + actionLabel + onAction + defaultExpanded); services/ui/src/components/console/useConsoleState.ts computeConsoleStats(state) helper (additive, returns 3 StatTile entries); services/ui/src/app/admin/console/page.tsx refactored onto KnowledgePageLayout(width="wide", screenId="admin-console") with AreaIntro + StatHero + NudgeStrip + PipelineRail + ConsoleStagePanel column |
| Verification Test | VT-LEO-AI-162 | passed | 10 jest cases (services/ui/src/__tests__/console-chrome.test.ts): TC-001 page imports KnowledgePageLayout + StatHero + PipelineRail + NudgeStrip from @leo/design-system, TC-002 legacy HealthBar / NudgeBanner imports removed, TC-003 KnowledgePageLayout invoked with screenId="admin-console" + width="wide", TC-004 computeConsoleStats helper exported with >= 3 tiles (gold + queue + model), TC-005 PipelineRail exposes role="tablist" + Enter/Space + useMotion, TC-006 NudgeStrip exposes role="status" + aria-live="polite" + severity {info, warning, danger} + color.status.* tones, TC-007 ConsoleStagePanel preserves accentColor + actionLabel + onAction + defaultExpanded, TC-008 design-system index re-exports PipelineRail + NudgeStrip, TC-009 page preserves stage handlers + 10s polling contract, TC-010 page still renders AreaIntro for the operations area (preserves VT-LEO-AI-135 TC-004) (passed 2026-04-16) |
| Risk | R-LEO-AI-165 | mitigated | Re-skinning /admin/console onto the design-system may misrepresent the AI pipeline status (PipelineRail showing wrong status dot), hide critical nudges (NudgeStrip mapping the wrong severity), or break the existing train / cancel / inspect workflow (handler not plumbed into the new ConsoleStagePanel). Mitigated by preserving the public surface of useConsoleState, mirroring the existing deriveStageHealth status mapping and deriveNudge severity mapping in the new primitives, preserving the existing handler contract on ConsoleStagePanel (action button, toggle, accentColor), and pinning the import + screenId/width contract via the static-source VT-LEO-AI-162. Severity minor, residual risk low (acceptable) |
| User Need | UN-LEO-AI-076 | active | Persistent test patient library for guideline regression: when clinical leads or QA reviewers edit, deploy or rebuild the appropriateness-guideline ruleset, they must be able to confirm that previously approved patient profiles still reach the same recommendation, so that no rule edit silently changes a clinical outcome |
| Design Input | DI-LEO-AI-165 | verified | Persistent test patient library schema + content_hash dedup (UN-LEO-AI-076): libs/cypher/test_patient_queries.py defines :TestPatient and :RulesetReplay constraints + indexes and the CREATE_TEST_PATIENT / WRITE_EXPECTED_RESULT / LIST_TEST_PATIENTS / FIND_BY_CONTENT_HASH / WRITE_REPLAY_REPORT / LIST_REPLAY_REPORTS / GET_REPLAY_REPORT Cypher; libs/cypher/schema_constraints.py applies them on startup; services/api/app/services/test_patient_service.py builds the PatientPayload dataclass (blake2b 16-byte hash over normalised codes + age + lowercase sex + pathway_id), confirm_and_save() with idempotent skip_if_exists, dry_run() that walks each matched rule's logic tree to produce branch_paths, and the /api/guidance/test-patients FastAPI router gated by require_admin (passed 2026-04-17) |
| Design Output | DO-LEO-AI-164 | approved | libs/cypher/test_patient_queries.py (TEST_PATIENT_CONSTRAINTS + Cypher); libs/cypher/schema_constraints.py (imports the constraints into the Coding graph schema); services/api/app/services/test_patient_service.py (PatientPayload, dry_run, confirm_and_save, list_patients, delete_patient, diff_replay, replay_one, replay_scope, _persist_replay_report, list_replay_reports, get_replay_report); services/api/app/routers/test_patients.py (FastAPI router for /guidance/test-patients/*) |
| Verification Test | VT-LEO-AI-164 | passed | 14 pytest cases (services/api/tests/test_test_patient_service.py): TC-001..003 content_hash determinism, TC-004..007 _walk_satisfied AND/OR/AT_LEAST/NOT and _check_demographic, TC-008..009 dry_run branch_paths and RuntimeError surfacing, TC-010..011 confirm_and_save idempotent on duplicate hash and writes one CREATE + N expectation rels, TC-012 diff_replay bucketing, TC-013..014 replay_scope persistence on/off (passed 2026-04-17) |
| Design Input | DI-LEO-AI-166 | verified | Test patient generator + dry-run preview (UN-LEO-AI-076): services/api/app/services/test_patient_generator.py emits Proposal records (kind happy / fail / branch / boundary) per rule, walking AND / OR / AT_LEAST / NOT subtrees with _collect_satisfying() and DEMOGRAPHIC nodes with _collect_demographic(); boundary_plus_pairs depth emits at-boundary and just-below-boundary patients per age node and one happy patient per top-level OR branch; _dedup() drops proposals whose content_hash already exists in the same guideline; BuildPatientDialog.tsx reuses ConceptSearchPanel and gates Save behind a successful dry-run, GeneratePatientsDialog.tsx bulk-saves selected proposals with skip_if_exists=True (passed 2026-04-17) |
| Design Output | DO-LEO-AI-165 | approved | services/api/app/services/test_patient_generator.py (Proposal dataclass + scope-aware generator); services/ui/src/app/admin/guidance/test-patients/BuildPatientDialog.tsx (hand-build dialog with dry-run gate); services/ui/src/app/admin/guidance/test-patients/GeneratePatientsDialog.tsx (bulk proposal review + save); services/ui/src/app/admin/guidance/test-patients/api.ts (frontend client) |
| Verification Test | VT-LEO-AI-165 | passed | 12 pytest cases across services/api/tests/test_test_patient_generator.py and services/api/tests/test_test_patient_router.py: TC-001..002 generator emits happy/fail and branch/boundary proposals, TC-003 exclude_existing dedup, TC-004 scope_type='all' selects every active rule, TC-005..012 router contract for dry-run / save / delete (404 + 200) / replay / generate / replay-reports (passed 2026-04-17) |
| Design Input | DI-LEO-AI-167 | verified | Replay engine, post-compile gate and Clinical Guidelines surfacing (UN-LEO-AI-076): test_patient_service.diff_replay() buckets each asserted rule into passes / regressions / unexpected_matches and replay_scope() persists the aggregate as a :RulesetReplay node tagged with ruleset_version; services/terminology_api/app/routers/guidelines.py _trigger_test_patient_replay() POSTs to /guidance/test-patients/replay after every successful guideline compile (errors logged at WARNING, do not block the compile); BitmapLifecycleSection.tsx surfaces the latest report with a coloured banner and a link to the test-patient library; EditRuleDialog/TestPatientsPanel.tsx re-runs a rule-scoped replay on every change of the rule's logic-tree signature and shows a regression banner naming the affected rules in plain English (passed 2026-04-17) |
| Design Output | DO-LEO-AI-166 | approved | services/api/app/services/test_patient_service.py (replay_one, replay_scope, diff_replay, _persist_replay_report); services/terminology_api/app/routers/guidelines.py (_trigger_test_patient_replay hook on _run_compile); services/ui/src/app/admin/guidance/test-patients/page.tsx (library page); services/ui/src/app/admin/guidance/test-patients/ReplayResultsDialog.tsx; services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx (latest replay banner); services/ui/src/app/admin/guidance/EditRuleDialog/TestPatientsPanel.tsx (per-rule auto-replay panel) |
| Verification Test | VT-LEO-AI-166 | passed | 7 jest cases (services/ui/src/__tests__/test-patients-page.test.tsx): TC-001..003 library page wires Build / Generate / Replay actions, scope filter and plain-English empty state, TC-004..005 API client targets the right endpoints with X-Requested-With on POST, TC-006..007 ReplayResultsDialog renders pass / regression / unexpected and stays jargon-free on the empty state (passed 2026-04-17) |
| Risk | R-LEO-AI-166 | analyzed | A rule edit, guideline redeploy or scheduled bitmap rebuild could silently change which patients trigger which appropriateness rules so a clinically required recommendation is no longer raised. Mitigated by reviewer-confirmed :TestPatient cohorts with EXPECTED_RESULT snapshots (DI-LEO-AI-165), generator-produced happy/fail/branch/boundary proposals (DI-LEO-AI-166), and automatic post-compile + per-edit replay with a regression banner on the Clinical Guidelines page (DI-LEO-AI-167). Severity serious, residual risk low (acceptable) |
| Design Input | DI-LEO-AI-168 | verified | Wave E Phase 6b-vi pathway probe surface decomposition (UN-LEO-AI-072): the legacy services/ui/src/components/pathway/edges/PortEdge.tsx (1781 LOC) split into a thin barrel + PortEdge/{utils,diff,TreeNode,SemanticSection,ProbeInspectorDrawer,ProbeMonitor,ProbeMonitorBanners,ProbeMonitorChanges,ProbeMonitorData,ProbeMonitorValidate,index}.tsx with each module <=500 LOC; services/ui/src/components/pathway/edges/probeStrategies.tsx (1048 LOC) split into a 158-LOC barrel + probes/{_shared,extraction,verification,persist,connectors,guidance}.tsx; dead services/ui/src/components/pathway/panel/{InputsTab,OverviewTab,ReviewTab,TriggerContextPanel}.tsx removed; services/ui/eslint.config.mjs gains a no-restricted-imports rule scoped to pathway/** that warns on direct @mui/* imports; services/ui/e2e/pathway-editor.spec.ts adds a Playwright + axe baseline for /admin/pathways (passed 2026-04-16) |
| Design Output | DO-LEO-AI-167 | approved | services/ui/src/components/pathway/edges/PortEdge.tsx (thin barrel); services/ui/src/components/pathway/edges/PortEdge/ (eleven focused modules under 500 LOC each); services/ui/src/components/pathway/edges/probes/ (six per-domain probe strategy modules); services/ui/eslint.config.mjs (no-restricted-imports rule for pathway/**); services/ui/src/__tests__/pathway-canvas-cleanup.test.ts (VT-167 jest cases); services/ui/e2e/pathway-editor.spec.ts (Playwright + axe baseline) |
| Verification Test | VT-LEO-AI-167 | passed | 6 jest cases (services/ui/src/__tests__/pathway-canvas-cleanup.test.ts): TC-001 file size limits across PortEdge/* and probes/*, TC-002 dead panel/* removal, TC-003 ESLint guard for pathway/** @mui imports, TC-004 PortEdge.tsx thin-barrel structure, TC-005 probeStrategies.tsx barrel imports each per-domain module, TC-006 per-domain modules expose the expected strategy symbols. Plus pathway-editor.spec.ts smoke + axe baseline. (passed 2026-04-16) |
| Risk | R-LEO-AI-167 | analyzed | Decomposing a 1781-LOC component into eleven sibling modules risks introducing a subtle behavioural drift in the probe surface that masks coding errors before they reach the patient record. Mitigated by preserving the import path through a thin barrel, static-source assertions on file size and import structure (VT-LEO-AI-167), continued passing of VT-LEO-AI-158 popover safety cases, and a Playwright + axe baseline for the pathway editor route. Severity serious, residual risk low (acceptable) |
| Design Input | DI-LEO-AI-170 | verified | Editable SNOMED procedure (action) on a pending guidance rule (UN-LEO-AI-028): closes a gap left by DI-LEO-AI-154 by exposing the recommended SNOMED procedure (the action that fires when a rule matches a patient) on the EditRuleDialog and letting reviewers swap it via the existing concept search panel. Backend (services/api/app/routers/guidance_rules.py, services/api/app/services/guidance_rule_edit.py) parses actionJson into a structured action field on every rule response, accepts an optional action: LogicCriterion on RuleUpdates, verifies the new SNOMED concept exists in the knowledge graph alongside logic-tree concepts, and persists actionJson via _INSERT_EDITED_RULE using coalesce($action_json, pred.actionJson) so omitting the field preserves the predecessor's value. Frontend (services/ui/src/app/admin/guidance/EditRuleDialog/{ActionPanel.tsx,index.tsx,ConceptSearchPanel.tsx}, services/ui/src/app/admin/guidance/RuleReviewSection.tsx) renders the procedure as a chip with the SNOMED tooltip, routes the chip click into the ConceptSearchPanel under a new replace_action mode (heading "Swap the recommended procedure"), tracks an actionDirty flag, and only includes action in the save payload when the reviewer touched it (passed 2026-04-17) |
| Design Output | DO-LEO-AI-169 | approved | services/api/app/services/guidance_rule_edit.py (RuleUpdates.action, _action_payload, apply_rule_edit action validation + persistence, _INSERT_EDITED_RULE coalesce); services/api/app/routers/guidance_rules.py (_format_rule action exposure, _parse_action_json); services/ui/src/app/admin/guidance/EditRuleDialog/ActionPanel.tsx (new); services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx (action state, replace_action SearchTarget, handleSelectAction, handlePick branch, payload conditional); services/ui/src/app/admin/guidance/EditRuleDialog/ConceptSearchPanel.tsx (replace_action heading); services/ui/src/app/admin/guidance/RuleReviewSection.tsx (Rule.action, payload forwarding) |
| Verification Test | VT-LEO-AI-168 | passed | 8 pytest cases (services/api/tests/test_guidance_rule_edit_action.py): TC-001 RuleUpdates accepts optional action, TC-002 apply_rule_edit rejects unknown SNOMED concept in action, TC-003 apply_rule_edit persists supplied actionJson, TC-004 omitted action preserves predecessor actionJson, plus _format_rule parsing and _parse_action_json malformed-input handling. 4 jest cases (services/ui/src/app/admin/guidance/EditRuleDialog/__tests__/EditRuleDialog.action.test.tsx): TC-005 chip renders friendly term + SNOMED tooltip, empty-state warning chip when action is null, TC-006 picking a search hit updates the chip and the save payload, untouched action is omitted from the save payload (passed 2026-04-17) |
| Risk | R-LEO-AI-169 | analyzed | Wrong SNOMED procedure attached to an approved guidance rule: a reviewer could select an inappropriate or off-formulary SNOMED procedure when swapping the action, causing the rule to recommend a clinically incorrect investigation or referral when it later matches a patient. Mitigated by required selection from the ConceptSearchPanel (no free-text path), backend verification that the action's snomed_concept_id exists in the SnomedConcept knowledge graph (DI-LEO-AI-170), versioned write-back so the predecessor remains queryable as 'superseded' for rapid rollback, and the immutable GuidanceAuditEvent capturing reason for edit. Severity serious, residual risk low (acceptable) |
| Design Input | DI-LEO-AI-174 | verified | Wave E Phase 4b AI Instructions editor decomposition (UN-LEO-AI-061): the legacy services/ui/src/app/admin/prompts/[id]/page.tsx (1110 LOC) split into a 406-LOC orchestrator that owns data fetching + save + sandbox state, plus dedicated tab body and helper modules under _components/ - IdentitySection, InstructionsTab, OutputFormatTab, TeachingExamplesTab, SandboxTab, SandboxCostTable, ExampleCard (with internal ExampleEditMode + ExamplePreviewMode), InputDisplay, OutputPreview, and a single types.ts holding CATEGORY_OPTIONS, SCOPE_OPTIONS, TAG_COLORS, ASSERTION_COLORS, categoryLabel, categoryColor, FewShotExample, PromptConfigData, CostEstimate, SandboxResult, PresetItem, SandboxProvider, SandboxTier, DEFAULT_MAX_FEW_SHOT. Every module stays inside the 500 LOC hard cap, the orchestrator imports each tab body from ./_components/, and the save payload contract (name, description, systemPrompt, outputSchema, verification, fewShotExamples, maxFewShot) is preserved byte-for-byte (passed 2026-04-16) |
| Design Output | DO-LEO-AI-173 | approved | AI Instructions editor decomposition (Wave E Phase 4b). Splits prompts/[id]/page.tsx into the orchestrator + ten extracted modules under _components/. Total surface 2089 LOC; orchestrator 406 LOC; largest extracted module SandboxTab.tsx 381 LOC. |
| Verification Test | VT-LEO-AI-169 | passed | 4 jest cases (services/ui/src/__tests__/prompts-editor-decomposition.test.ts): TC-001 all ten _components modules exist, TC-002 page.tsx + each module <=500 LOC, TC-003 page.tsx imports IdentitySection / InstructionsTab / OutputFormatTab / TeachingExamplesTab / SandboxTab from ./_components/, TC-004 types.ts exposes CATEGORY_OPTIONS, SCOPE_OPTIONS, TAG_COLORS, ASSERTION_COLORS, categoryLabel, categoryColor, FewShotExample, PromptConfigData, CostEstimate, SandboxResult, PresetItem (passed 2026-04-16) |
| Design Input | DI-LEO-AI-176 | verified | Wave E Phase 7 Knowledge tabs guards (UN-LEO-AI-061): services/ui/eslint.config.mjs gains a no-restricted-imports rule scoped to src/app/admin/knowledge/**/*.{ts,tsx} that warns on @mui/* imports (paired with the existing pathway/** guard), nudging contributors toward @leo/design-system primitives (KnowledgePageLayout, StatHero, ToolbarActions, FilterBar, PromptEditorCard, ReviewListCard, DataGridCard, MetricTile, NudgeStrip); services/ui/e2e/knowledge-tabs.spec.ts adds a Playwright + @axe-core/playwright spec that iterates the eight Knowledge tab keys (training-data, surface-forms, context-rules, ai-instructions, clinical-guidelines, pathways, domains, terminology) and asserts each route loads with zero critical or serious WCAG 2.0/2.1 AA violations on the wrapper chrome (passed 2026-04-16) |
| Design Output | DO-LEO-AI-175 | approved | Knowledge tabs ESLint + Playwright/axe baseline (Wave E Phase 7). Extends the flat ESLint config with the admin/knowledge/** guard and ships a single Playwright spec that smokes + axe-tests all eight tab routes. |
| Verification Test | VT-LEO-AI-171 | passed | 2 jest cases (services/ui/src/__tests__/knowledge-tabs-guards.test.ts): TC-001 ESLint flat config carries the admin/knowledge guard with the @mui/* pattern, TC-002 e2e/knowledge-tabs.spec.ts iterates the eight Knowledge tab keys with paired smoke + AxeBuilder blocks tagged wcag2a/wcag2aa/wcag21a/wcag21aa (passed 2026-04-16) |
| Design Input | DI-LEO-AI-171 | verified | Problem-list malignancy term + active-care + history-of-cancer recognition + Read appendix sweep + silent-closure provenance fix (UN-LEO-AI-005, UN-LEO-AI-006). Extends libs/domains/code_inventories.py with corpus-confirmed Xa-prefix codes (X78Y6 prostate, Ya0ln breast, ...), new ACTIVE_CANCER_CARE_CODES (XaIph "Cancer confirmed", XaN5C MDT meeting, 8BAD0 chemotherapy and ~25 others), HISTORY_OF_CANCER_CODE_PREFIXES (ZV10, B934, XaXGk and related personal-history prefixes), MALIGNANCY_TERM_PATTERNS (regex pairs that only fire on PROBLEM_LIST_LINE_PREFIX-anchored lines), and removes the buggy `B5...` -> head_and_neck mapping (only B57.. -> brain remains valid). anchor_detector._classify_text_encounters wires text_contains_history_of_cancer / find_malignancy_term_in_problem_line / find_active_cancer_care_code as new diagnosis paths with diagnosis_source provenance and hitl_required=True for all new sources. _builder.py adds the silent-closure provenance fix: every closed_benign episode now writes a benign_closure IS_PART_OF edge via the new _benign_closure_link_anchors helper (passed 2026-04-17) |
| Design Output | DO-LEO-AI-170 | approved | libs/domains/code_inventories.py (MALIGNANCY_READ_CODES extension, ACTIVE_CANCER_CARE_CODES, HISTORY_OF_CANCER_CODE_PREFIXES, MALIGNANCY_TERM_PATTERNS, helpers); services/analysis_worker/app/analyzers/anchor_detector.py (history guard + new diagnosis paths); services/analysis_worker/app/analyzers/episode_builder/_builder.py (_benign_closure_link_anchors + closed_benign milestone link wiring) |
| Design Input | DI-LEO-AI-172 | verified | Adjuvant cancer-therapy diagnosis inference with co-condition guard (UN-LEO-AI-005, UN-LEO-AI-055). libs/domains/code_inventories.py adds ADJUVANT_THERAPY_DRUG_PATTERNS (letrozole/anastrozole/exemestane/tamoxifen/fulvestrant -> breast; goserelin/leuprorelin/triptorelin/bicalutamide/enzalutamide/abiraterone -> prostate; trastuzumab -> breast; capecitabine -> non_site_specific HITL-only) and ADJUVANT_THERAPY_ISSUE_MARKERS (regex such as "newly issued", "first prescription", "initiated on") plus find_adjuvant_therapy_drug and adjuvant_therapy_is_newly_issued. anchor_detector._classify_text_encounters fires diagnosis_source=adjuvant_therapy_drug ONLY when an issue marker, an active-cancer-care code, or a malignancy term/code is also present (drug-alone never fires); confidence=0.75 and hitl_required=True on every adjuvant-derived anchor; the history-of-cancer guard from DI-LEO-AI-171 short-circuits the path so survivors on long-term hormone therapy are not re-diagnosed (passed 2026-04-17) |
| Design Output | DO-LEO-AI-171 | approved | libs/domains/code_inventories.py (ADJUVANT_THERAPY_DRUG_PATTERNS, ADJUVANT_THERAPY_ISSUE_MARKERS, helpers); services/analysis_worker/app/analyzers/anchor_detector.py (adjuvant-therapy diagnosis path with co-condition guard) |
| Design Input | DI-LEO-AI-173 | verified | Site reconciliation in episode build (UN-LEO-AI-006). _site_resolution._extract_condition_key_from_anchor short-circuits to the diagnosis anchor's site_key when site_source is one of {explicit_2ww_code, explicit_malignancy_code, malignancy_term_problem_line} and site_key is well-defined. _builder._build_closed_episode adds a reconciliation block: if any diagnosis anchor in a diagnosis-led group carries an explicit site_source and a well-defined site_key that differs from the episode's referral-derived site_key, the builder adopts the diagnosis site, sets hitl_flag=True, and appends "site_reconciliation_hitl: <ref_site> -> <diag_site>" to hitl_reason. Verified live: post-rebuild 2026-04-17 the canonical confirmed-cancer cohort for 2025 rises from 24 to 27 (+3) and 2024 from 23 to 26 (+3) (passed 2026-04-17) |
| Design Output | DO-LEO-AI-172 | approved | services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py (explicit site_source short-circuits); services/analysis_worker/app/analyzers/episode_builder/_builder.py (_build_closed_episode site reconciliation block + hitl_flag/hitl_reason) |
| Risk | R-LEO-AI-170 | analyzed | Free-text malignancy term recognition or explicit-site short-circuit could misclassify a non-cancer encounter as a confirmed cancer or attach the wrong cancer site. Mitigated by anchoring MALIGNANCY_TERM_PATTERNS to PROBLEM_LIST_LINE_PREFIX (so free prose mentions are ignored), the history-of-cancer guard, hitl_required=True on every new diagnosis source, and the canonical cohort excluding closed_benign so a single false positive on a benign-closed episode cannot inflate the cancer headline. Severity serious, residual risk low (acceptable) |
| Risk | R-LEO-AI-171 | analyzed | Adjuvant-therapy drug detection could produce false-positive cancer diagnoses (e.g. tamoxifen for primary prevention in high-risk patients) or wrong-site classifications (e.g. goserelin for endometriosis classified as prostate). Mitigated by mandatory co-condition guard (drug + issue marker / active-care code / malignancy term required), hitl_required=True on every adjuvant anchor, history-of-cancer suppression, and quarterly precision audits with an 85% precision floor. Severity minor, residual risk low (acceptable) |
| Verification Test | VT-LEO-AI-170 | passed | 63 pytest cases (tests/test_stale_detector_fixes.py): 30 cases across the new test classes TestMissedCancerInventories, TestHistoryOfCancerGuard, TestActiveCancerCareCode, TestMalignancyTermProblemLine, TestAdjuvantTherapyInference, TestSiteReconciliationInBuilder, TestB5MappingBugFixed, TestRegressionMissedCancers, TestSilentBenignClosureProvenance plus 33 carried over from VT-LEO-AI-161. Live verification 2026-04-17: scripts/_wipe_episodes_and_rebuild.py executed twice (second run after the silent-closure fix landed); canonical 2025 confirmed cancers 24 -> 27, 2024 23 -> 26, closed_benign episodes carrying a benign_closure IS_PART_OF milestone 0/77 -> 77/77 (100% provenance) (passed 2026-04-17) |
| Design Input | DI-LEO-AI-175 | verified | Skin / melanoma inventory completeness (UN-LEO-AI-005, UN-LEO-AI-006). The 2026-04-17 audit of patient 4921442355 (lentigo maligna melanoma) found XaMeA "Fast track referral for suspected skin cancer" missing from FAST_TRACK_REFERRAL_READ_CODES, XaPyd "Seen in fast track suspected skin cancer clinic" missing from SPECIALIST_CLINIC_READ_CODES, the entire B32.. CTV3 family (B320.-B325., B32y., B32z., B32A0-B32A2) missing from MALIGNANCY_READ_CODES, and Xa99Y "Lentigo maligna melanoma" plus melanoma histological subtypes (lentigo maligna, superficial spreading, nodular, acral lentiginous, desmoplastic) not on MALIGNANCY_TERM_PATTERNS. libs/domains/code_inventories.py adds all of these plus a new CANCER_TREATMENT_PROCEDURE_CODES set ({7G055, X90PX}) and find_cancer_treatment_procedure_code helper. anchor_detector wires find_specialist_clinic_site so XaPyd-style codes emit first_seen anchors with first_seen_source=specialist_clinic_code (and back-fill site_key); the treatment branch ORs _RE_TREATMENT with the procedure-code path and labels procedure-code-derived treatments with treatment_source=procedure_code (passed 2026-04-17) |
| Design Output | DO-LEO-AI-174 | approved | libs/domains/code_inventories.py (XaMeA, XaPyd, B32.. family, Xa99Y, melanoma histological subtypes, CANCER_TREATMENT_PROCEDURE_CODES, find_cancer_treatment_procedure_code, find_specialist_clinic_site); services/analysis_worker/app/analyzers/anchor_detector.py (specialist-clinic first_seen path; procedure-code treatment path) |
| Design Input | DI-LEO-AI-177 | verified | Cancer follow-up template recogniser (UN-LEO-AI-005, UN-LEO-AI-006). UHL Dermatology surveillance encounters use a "Skin Cancer Follow Up" template that on its own should imply an established cancer diagnosis but did not match any anchor pattern. libs/domains/code_inventories.py adds CANCER_FOLLOW_UP_PHRASES (regex+site_key for skin/melanoma, breast, prostate, lung, lower GI, upper GI, head and neck, urological, gynaecological, haematological, brain, thyroid, sarcoma, plus a generic "cancer follow up clinic" -> non_site_specific) and find_cancer_follow_up_phrase. anchor_detector forces has_cancer/has_confirmed True when _follow_up_hit fires (gated by the history-of-cancer guard), emits diagnosis_confirmed with diagnosis_source=cancer_follow_up_template, hitl_required=True, confidence=0.8, and back-fills site_key when no other source set one. Site reconciliation precedence accepts cancer_follow_up_template (passed 2026-04-17) |
| Design Output | DO-LEO-AI-176 | approved | libs/domains/code_inventories.py (CANCER_FOLLOW_UP_PHRASES, find_cancer_follow_up_phrase); services/analysis_worker/app/analyzers/anchor_detector.py (cancer_follow_up_template diagnosis path; site reconciliation entry) |
| Design Input | DI-LEO-AI-178 | verified | Benign-investigation phrase scope guard / day-17 closure bug fix (UN-LEO-AI-005, UN-LEO-AI-006, UN-LEO-AI-054). Patient 4921442355's confirmed melanoma episode was prematurely closed as closed_benign on day 17 because an unrelated CKD/blood-pressure review on 2024-11-18 contained the generic phrase "no further action" that satisfied two broad regexes (BENIGN_INVESTIGATION_PHRASES and _RE_NO_CANCER) and emitted a benign_closure that the episode builder attached to the parallel skin-cancer episode. libs/domains/code_inventories.py adds BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT (frozenset of broad phrase labels: "no further action", "discharged from clinic", "discharged from care") and CANCER_PATHWAY_CONTEXT_REGEX (a strict regex matching only cancer/carcinoma/malignan*/tumour/melanoma/lymphoma/leukaemia/sarcoma/2WW/two-week wait/fast track/oncology/chemo*/radiotherapy/MDT meeting|review/suspected <site> cancer) plus text_has_cancer_pathway_context. anchor_detector rewires the benign_closure emission to require ONE of: a benign Read-code hit, a tier-1 phrase hit, a tier-2 phrase hit that passes the gate, OR has_no_cancer with cancer-pathway context already in the encounter. The gate deliberately EXCLUDES match_cancer_site() because the gold-mined dictionary contains incidental terms (e.g. "chronic kidney disease stage 3" under the renal site) that would re-open the day-17 bug. Verified end-to-end: post-rebuild 2026-04-17 episode 42b722eb6082a4b7 reclassifies from closed_benign to completed/melanoma; global benign_outcome cohort drops from 67 -> 41 distinct patients (-26) while diagnosed_or_treated rises from 82 -> 83 (passed 2026-04-17) |
| Design Output | DO-LEO-AI-177 | approved | libs/domains/code_inventories.py (BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT, CANCER_PATHWAY_CONTEXT_REGEX, text_has_cancer_pathway_context); services/analysis_worker/app/analyzers/anchor_detector.py (benign-closure emission re-gate; documentation block explaining why match_cancer_site is NOT trusted as gate evidence) |
| Risk | R-LEO-AI-172 | analyzed | Residual missed-cancer risk on the skin / melanoma pathway: corpus-confirmed Read codes for melanoma exist outside the B32.. and Xa99Y family (e.g. B312., B311., B310.), specialist clinic vocabulary for non-skin sites (XaMxx codes) is partial, and the cancer follow-up template recogniser only catches commonly-named templates. Mitigated by find_specialist_clinic_site helper (extensible via SPECIALIST_CLINIC_READ_CODES dict), the procedure-code treatment path, hitl_required=True on every new diagnosis source (cancer_follow_up_template, specialist_clinic_code path), and a quarterly closed_benign skin-cohort audit that compares post-rebuild episode status against documented diagnostic codes. Severity serious, residual risk low (acceptable) |
| Risk | R-LEO-AI-173 | analyzed | False benign-closure from scope-violating phrase match in unrelated encounter: a generic phrase ("no further action", "discharged from clinic") fires a benign_closure on a CKD / mental-health / chronic-disease review encounter that happens to share a date window with a parallel cancer episode, causing the cancer episode to be silently closed as benign. Mitigated by BENIGN_PHRASE_REQUIRES_CANCER_CONTEXT gate that requires cancer-pathway tokens in the same encounter for tier-2 phrases, the strict CANCER_PATHWAY_CONTEXT_REGEX (deliberately excluding the loose match_cancer_site gold-mined dictionary), and a regression test (TestBenignPhraseScopeGuard.test_harold_ckd_encounter_does_not_emit_benign_closure) that asserts the exact CKD encounter from patient 4921442355's case never produces a benign_closure anchor. Severity critical (missed cancer diagnosis), residual risk low (acceptable) |
| Verification Test | VT-LEO-AI-172 | passed | 27 pytest cases across TestSkinMelanomaInventory (12 cases on inventory + helpers + procedure-code treatment + specialist-clinic first_seen), TestCancerFollowUpTemplate (6 cases on helper recognisers + diagnosis emission + history guard), TestBenignPhraseScopeGuard (8 cases including the gold-mined-renal regression and the exact Harold Allwyn CKD encounter regression), and TestRegressionHaroldAllwyn (5 end-to-end-ish cases on referral / first_seen / problem-line diagnosis / wide-excision treatment / surveillance template). Live end-to-end verification 2026-04-17 after scripts/_wipe_episodes_and_rebuild.py: episode 42b722eb6082a4b7 (Mr Harold Allwyn) reclassifies from closed_benign to completed/melanoma with referral_route=two_week_wait, referral_date=2024-11-01, first_seen_date=2024-11-13, end_date=2025-01-28, presenting_complaint="bleeding, skin lesion"; cohort-wide closed_benign 77 -> 49 (-28), benign_outcome patients 67 -> 41 (-26), in_progress 14 -> 22 (+8) (passed 2026-04-17) |
| Design Input | DI-LEO-AI-182 | verified | Detect 2WW referral rejection and resubmission as auditable workflow events (UN-LEO-AI-041). _classify_text_encounters in services/analysis_worker/app/analyzers/anchor_detector.py adds three regex families (_RE_REFERRAL_REJECTED, _RE_REFERRAL_MARKED_IN_ERROR, _RE_REFERRAL_RESUBMITTED) and a priority branch that emits the encounter as a referral anchor with referral_subtype 'rejected' or 'resubmitted', suppressing diagnosis / benign_closure emission on the same row. services/analysis_worker/app/analyzers/episode_builder/_persistence.py and _cypher.py persist anchor.referral_subtype on the IS_PART_OF edge via LINK_ENCOUNTERS. New MCP tool dq_rejected_referrals_resubmission_delay in services/neo4j_mcp/tools/query_pack_pathway.py reports rejection-to-resubmission delay in calendar days for 2WW pathways, excluding status='merged' episodes. Pattern-level test class TestReferralRejectionAndResubmission in tests/test_anchor_detector.py covers Choose-and-book rejection, Marked-in-Error referral, resubmission with referral context, suppression of diagnosis/benign on referral lifecycle rows, PRISM and text_generic regression, and three negative tests for transplant rejection, lab-sample resubmission, and BP value Marked-in-Error (passed 2026-04-17) |
| Design Output | DO-LEO-AI-181 | approved | services/analysis_worker/app/analyzers/anchor_detector.py (_RE_REFERRAL_REJECTED, _RE_REFERRAL_MARKED_IN_ERROR, _RE_REFERRAL_RESUBMITTED, referral lifecycle priority branch in _classify_text_encounters); services/analysis_worker/app/analyzers/episode_builder/_persistence.py + _cypher.py (referral_subtype on IS_PART_OF); services/neo4j_mcp/tools/query_pack_pathway.py (dq_rejected_referrals_resubmission_delay; status='merged' filter on dq_missing_milestone_chains) |
| Verification Test | VT-LEO-AI-176 | passed | 9 pytest cases in TestReferralRejectionAndResubmission covering Choose-and-book rejection, Marked-in-Error referral, resubmission with referral context, suppression of diagnosis/benign on referral lifecycle rows, PRISM and text_generic regression, plus three negative tests (transplant rejection, lab-sample resubmission, BP value Marked-in-Error) (passed 2026-04-17) |
| Design Input | DI-LEO-AI-137 (revised) | verified | Multi-distinct-type guard added to libs/episodes/duplicate_resolver.py.pick_evidence_winner: when a cluster carries >=2 distinct known cancer types and the diagnosis text does not uniquely name one of them, the merge is skipped instead of being forced by alphabetical tie-break. Five new regression tests in tests/test_episode_duplicate_resolver.py::TestMultiDistinctTypeGuard pin the rule. scripts/backfill_unmerge_unsafe_episodes.py reverts pre-existing unsafe merges to status='reopened_for_rebuild'. R-LEO-AI-097 mitigation extended with the new design feature (passed 2026-04-17) |
| Verification Test | VT-LEO-AI-138 (revised) | passed | TC-009 to TC-013 added to cover the multi-distinct-type guard: skip on two-known-types-no-text, skip on text naming an outsider type, merge when text uniquely identifies one of three distinct types, merge NSS shadows into a single known type when no text evidence is present, skip when text matches an outsider in a three-type cluster (passed 2026-04-17) |

### April 2026 - Calibrated SNOMED resolver scoring + LLM proposal validator

The terminology resolver previously emitted a per-term-relative score
inflated by a multiplicative 1.3x tag boost: every top-1 candidate
reported ~1.0-1.3 regardless of whether the underlying retrieval
evidence was a curated SurfaceForm exact match or a one-token Lucene
partial match. Reviewers and downstream gates could not tell strong
from weak. The 2026-04-17 audit of the LLM-driven gold-label backfill
surfaced four clinically wrong proposals that would have entered the
gold training set with score=1.3 attached -- "cancer free" coded as
"Seizure free", "rising PSA" coded as "Slow rising pulse", "nipple
inversion on the right breast" coded as "Pendulous right breast",
"worsened over the last six months" coded as "Sexually active in last
six months". The resolver's `_fuse_and_rank` was rewritten to compute a
calibrated absolute confidence in `[0, 1]` and a separate proposal
validator was added to gate every LLM-generated entity addition before
it touches the GoldLabel set.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-078 | approved | Clinical leads, QA reviewers, and the runtime coding pipeline need every SNOMED candidate to carry a calibrated absolute confidence in [0, 1] AND need a separate validator that re-checks LLM-proposed entities against that confidence before they enter the gold training data, so that weak fulltext token matches cannot masquerade as high-confidence codes and the NER model is not taught to emit spans the downstream coder cannot represent |
| Design Input | DI-LEO-AI-183 | verified | Calibrated absolute confidence scoring in the SNOMED resolver. services/terminology_api/app/services/coding_resolver.py rewrites HybridCodingResolver._fuse_and_rank so the returned `score` is a calibrated absolute confidence in [0, 1] (replacing per-term-relative normalisation + 1.3x multiplicative tag boost). lex_signal=1.0 on had_exact_match else bm25/(bm25+1); vec_signal=cosine; combined via max + 0.10 * min capped at 1.0; tag adjustment +0.10 additive on exact match, neutral same-group, *0.5 cross-group, hard-block non-clinical when clinical expected. New helpers _calibrate_confidence and _apply_tag_adjustment encapsulate the math. CodingCandidate exposes had_exact_match, lexical_raw, vector_raw alongside the calibrated score; /terminology/resolve CandidateResponse mirrors all four fields; libs/terminology/client.py ResolvedTerm parses them; cache prefix bumped v2 -> v3 to flush stale entries. Downstream gates retuned: terminology._DEFAULT_MIN_SCORE 0.70 -> 0.55, surface_form_validation_threshold 0.9 -> 0.7. Verified live: 'prostate cancer' and 'CKD' score 1.000, 'rising PSA' 0.966, 'cancer free' 0.895 (passed 2026-04-17) |
| Design Input | DI-LEO-AI-184 | verified | SNOMED proposal validator with tiered acceptance ladder. scripts/lib/gold_label_snomed_check.py implements an explicit three-branch acceptance model (EXACT on had_exact_match=True with tag compatibility; SEMANTIC on vector_raw>=0.92 AND surface_match>=0.66; SURFACE on surface_match>=0.7 AND _meets_shared_token_floor AND polarity_guard) keyed off the resolver's absolute signals, never on the fused score. Defaults tuned against the 950 HITL-completed backfill so that all four documented false positives (nipple inversion -> Pendulous right breast; worsened over the last six months -> Sexually active in last six months; sciatica feels pain back/buttocks/toes; surgery in jan to remove cyst in left kidney) are rejected. Polarity guard rejects 'no hydrocephalus' -> Hydrocephalus as polarity_mismatch; shared-token floor rejects 'cancer free' -> 'Seizure free' as shared_token_floor. scripts/validate_backfill_snomed.py CLI streams a backfill JSONL through the validator and writes *.validated.jsonl + *.validated.summary.json with structured rejection reasons. End-to-end re-validation produced 240 kept additions with resolver_score in [0.873, 1.000] (mean 0.989) (passed 2026-04-17) |
| Design Output | DO-LEO-AI-182 | approved | services/terminology_api/app/services/coding_resolver.py (rewritten _fuse_and_rank + new _calibrate_confidence and _apply_tag_adjustment helpers; _TAG_BOOST/_TAG_COMPAT_BOOST removed; _TAG_EXACT_BOOST=+0.10 and _AGREEMENT_BONUS=0.10 added; CodingCandidate gains had_exact_match/lexical_raw/vector_raw); services/terminology_api/app/routers/resolve.py (CandidateResponse exposes the new signals); libs/terminology/client.py (ResolvedTerm parses new fields, cache prefix v2 -> v3); libs/pipeline_graph/subgraphs/terminology.py (_DEFAULT_MIN_SCORE 0.70 -> 0.55); libs/pipeline_graph/subgraphs/surface_form_validation.py (default threshold 0.9 -> 0.7) |
| Design Output | DO-LEO-AI-183 | approved | scripts/lib/gold_label_snomed_check.py (validate_proposal, validate_proposals_batch, _meets_shared_token_floor, polarity_guard, _surface_overlap, ProposalValidationConfig with default thresholds min_surface_match=0.7, semantic_vector_floor=0.92, semantic_min_surface=0.66); scripts/validate_backfill_snomed.py (CLI argparse exposes --min-surface, --semantic-vector-floor, --semantic-min-surface, --workers, --max; streams JSONL, fan-out validates via TerminologyClient, writes validated JSONL + summary JSON) |
| Risk | R-LEO-AI-177 | mitigated | Per-term-relative + multiplicatively-tag-boosted resolver score made weak partial matches indistinguishable from curated exact matches, causing silent over-coding. Harm: wrong SNOMED codes attached to clinical encounters and to gold training data (cancer free -> Seizure free; rising PSA -> Slow rising pulse; no hydrocephalus losing negation). Severity serious. Mitigated by DI-183 (calibrated absolute scoring + raw signal exposure + downstream gate retuning + cache flush) and DI-184 (validator that does not consume the fused score as primary acceptance signal). Residual low (acceptable): end-to-end audit shows 0/240 kept proposals are clinically wrong; raw signals on every API response make any suspicious acceptance reproducible from logs |
| Risk | R-LEO-AI-178 | mitigated | SNOMED proposal validator over-rejects legitimate lexicon-gap matches when the surface uses lay/synonym wording, suppressing real findings from the gold training set. Harm: reduced runtime NER recall on lay/synonym surfaces (rising PSA, primary lung mass, hydronephrosis in plain English) -> missed clinical signal. Severity minor. Mitigated by the SEMANTIC branch (vector_raw>=0.92 AND surface_match>=0.66) that admits embedding-strong partial-overlap surfaces, by structured rejection reasons routed to QA review, and by audit-driven default tuning that lost only 4 marginal cases (244 -> 240 kept) -- all of which were the documented false positives |
| Verification Test | VT-LEO-AI-177 | passed | 9 critical/high pytest cases in tests/test_coding_resolver.py::TestCalibratedScoring pinning every per-branch score path: exact branch -> 1.0; weak fulltext (BM25=1) -> 0.5; strong fulltext (BM25=5) -> 0.833; vector-only -> cosine; lex+vector agreement bonus capped at 1.0; cross-group tag penalty halves; tag match additive boost not multiplicative inflation; tag-matching candidate wins tie; regression that previously-passing test_expected_tag_underscore_not_penalized still passes under new contract. Full tests/test_coding_resolver.py (35 tests) green; companion 21 validator tests in tests/test_gold_label_snomed_check.py also green (56/56 total) (passed 2026-04-17) |
| Verification Test | VT-LEO-AI-178 | passed | 21 pytest cases in tests/test_gold_label_snomed_check.py covering EXACT branch acceptance, SEMANTIC branch acceptance with high vector_raw and partial surface match, SURFACE branch acceptance with shared-token floor, polarity guard (no hydrocephalus -> reject; no hydrocephalus + Hydrocephalus absent -> accept), shared-token floor (cancer free + Seizure free -> reject), explicit refusal to accept on fused score alone, qualifier-value rejection, drifted-top1 rejection, UK/US spelling normalisation, no-candidates short-circuit, batch deduplication, synonym-tag review flag, single-token surface acceptance, higher-surface tie-break. End-to-end re-validation of 950-proposal backfill: 240 kept, all 4 documented false positives rejected, kept-set scores bounded in [0.873, 1.000] (passed 2026-04-17) |

---

## Atlas / Local YAML Reconciliation Programme (April 2026)

In April 2026 the Atlas QMS Graph came online as the canonical source of
truth for design controls. Local design-control YAMLs in `design-inputs/`,
`design-outputs/`, `verification-tests/`, `validation-tests/`,
`user-needs/` and `risks/` predate Atlas and were authored against a
finer-grained, file-structure-aware schema. A 7-phase reconciliation
programme migrated local content into Atlas while preserving the local
YAMLs as historical engineering reference. Atlas is now the system of
record; local YAMLs remain as the source of `machine_spec`,
`file_structure`, and `execution_history` data that Atlas does not
currently model.

### Phase ledger

| Phase | Scope | Outcome |
|---|---|---|
| 1 | Build local-LEO-AI <-> Atlas-hex ID map | `atlas-id-mapping.csv`, `atlas-id-mapping-gaps.md` (49/71 UNs, 109/151 DIs, 12/13 VALs initially matched via greedy 1:1 assignment) |
| 2 | UN reconciliation | 14 UNs created in Atlas, 49 fuzzy/exact matches recorded, 8 deferred for human review |
| 3 | DI reconciliation | 37 DIs created in Atlas, 49 HAS_DESIGN_INPUT links established, 5 deferred-duplicate, 109 matched DIs flagged for human triage in `phase3-di-merge-gap.md` |
| 4 | DO migration (fine-grained) | 122 DOs created in Atlas, 128 IMPLEMENTS links established, 8 deferred-no-parent |
| 5 | VT migration (fine-grained) | 137 VTs created in Atlas, 152 VERIFIES + 2 TESTS links, 9 deferred-no-parent, 3 matched-umbrella |
| 6 | VAL gap-fill | 3 strong-match Atlas VALs backfilled with AC + protocol_steps, VAL-CD564313 created (HITL Override Rates), 9 divergent-fuzzy local VALs flagged in `phase6-val-gap-report.md` |
| 7 | Documentation refresh | DC-TM-002 regenerated from live Atlas snapshot, atlas-id-mapping.csv published, README artefact register updated |

### Atlas inventory after reconciliation (2026-04-17)

| Artefact | Atlas count | Coverage |
|---|---|---|
| User Needs (UN) | 87 | 82 with at least one DI (94%) |
| Design Inputs (DI) | 258 | 254 with at least one DO (98%) |
| Design Outputs (DO) | 152 | 152 with at least one VT (100%) |
| Verification Tests (VT) | 176 | 0 recorded as `passed` in Atlas (`fresh_start` policy: only new CI runs are recorded in Atlas) |
| Validation Tests (VAL) | 21 | 0 recorded as `passed` in Atlas (post-deployment) |

### Source-of-truth policy

- **Atlas (QMS Graph) is the canonical source** for UNs, DIs, DOs, VTs, VALs
  and the linkage graph (HAS_DESIGN_INPUT, IMPLEMENTS, VERIFIES, TESTS,
  VALIDATES). All future authoring, edits and approvals MUST be applied
  in Atlas first.
- **Local YAMLs are reference** for `machine_spec`, `file_structure`,
  `estimated_loc`, `execution_history` and any other detail that Atlas
  does not model. Local YAMLs MAY still be edited when those fields
  change, but Atlas is the binding artefact for QMS purposes.
- **VT execution history**: per `fresh_start` policy, only CI runs from
  2026-04-17 onwards are recorded in Atlas via `record_verification_run`.
  Historical runs remain in local VT YAMLs (`execution_history` arrays)
  for engineering audit only.
- **Risks** are managed in a dedicated risk-management workstream; this
  reconciliation programme did not materially alter the Atlas risk
  inventory.

### Reference artefacts

- `atlas-id-mapping.csv` -- local-to-Atlas ID mapping (one row per local
  artefact, with `match_type`: exact / fuzzy / low-confidence /
  unmatched / created-in-atlas / deferred-duplicate / deferred-no-parent /
  matched-umbrella / merged-into-atlas / divergent-fuzzy)
- `atlas-id-mapping-gaps.md` -- summary of unmatched local IDs by
  artefact type
- `DC-TM-002-traceability-matrix.csv` -- flattened
  UN -> DI -> DO -> VT -> VAL matrix regenerated from the live Atlas
  traceability snapshot (279 rows over 87 UNs)
- `phase3-di-merge-gap.md` -- 109 matched DIs flagged for human
  triage (Atlas API does not currently expose `rationale` on DI updates)
- `phase6-val-gap-report.md` -- VAL backfill ledger and the 9
  divergent-fuzzy local VALs deferred for human triage against the
  consolidated tiered VAL programme
