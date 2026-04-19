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
| Design Input | DI-LEO-AI-213 | draft | Mission Control patient detail Encounter text overlay-first navigation: scope chips and Other-encounters / All-other-encounters accordions removed in favour of a single chronological encounter list filtered ONLY by the histogram brush; brush defaults to the padded episode-linked window; linked encounter cards carry an "In episode" chip and 3px accent; histogram renders three episode overlays (tightened band first-linked..last-linked, per-encounter linked tick markers along the bottom axis, and labelled milestone markers along the top axis); every jump path (milestone chips, single-bin click, popover row, milestone marker) clears brush, coded-only and search filters; Coded only switch and Search field retained; EncounterTextTab.tsx <=500 LOC |
| Design Output | DO-LEO-AI-210 | draft | EncounterTextTab.tsx (472 LOC) refactor: scope state and accordions removed; splitEncounters helper deleted; applyCommonFilters drives the single chronological list; defaultRangeAppliedRef seeds the brush to the padded episode-linked window; jumpToEncounter clears all filters before scrolling. New TimelineOverlays.tsx renders LinkedEncounterTicks (bottom axis) and MilestoneMarkers (top axis with tooltips and keyboard activation). EncounterTimelineScrubber.tsx tightens its windowBand to the first-linked..last-linked range and threads the milestones prop. EncounterCard.tsx renders the "In episode" chip + accent when isLinkedToEpisode is true. New useEncounterRecode.ts hook lifts the reset-and-recode flow so EncounterTextTab.tsx stays under the 500 LOC ceiling |
| Verification Test | VT-LEO-AI-205 | passed | 65 targeted tests / 113 mission-control suite tests: EncounterTextTab.test.tsx (scope chips and accordions removed, Coded only + Search retained, "In episode" chip on linked cards, jumps clear brush/coded-only/search), EncounterTextTab-timeline-filter.test.tsx (default padded brush, brush-driven list filtering, single-bin click clears the filter, milestone-marker jumps clear the filter), EncounterTextTab-scrubber-chrome.test.ts (legacy UI strings absent, milestones prop wired, linkedTicks/milestoneMarkers used, updated caption "drag the focus band to widen or narrow your view", 472 <= 500 LOC), EncounterTimelineScrubber.test.tsx (tightened first-linked..last-linked windowBand, LinkedEncounterTicks render, MilestoneMarkers render with keyboard activation) |
| Design Input | DI-LEO-AI-214 | draft | Mission Control /care/patients KPI strip MUST present audit headline figures in the same unit (patients) as the label and tooltip claim AND surface the cohort denominator so hidden patients are discoverable. GET /mission-control/kpis MUST return both episode counts and patient counts for confirmed_cancer and pathway_closures, plus a "cohort" block with total + 3 excluded buckets (no pathway / missing referral date / outside window) scoped by org/scope only. KPIStrip MUST render the patient count as the headline and the pathway count as a sub-line; tooltips MUST describe the metric as a count of PATIENTS in plain English; a caption (data-testid="kpi-cohort-denominator") MUST appear below the strip when at least one patient is hidden, formatted "Showing <inView> of <total> patients - <hidden> hidden (<reason1>, ...)" |
| Design Output | DO-LEO-AI-211 | draft | services/analytics_api/app/routers/mission_control.py: _kpis_cypher returns confirmed_cancer_patients (DISTINCT p with confirmed_cancer_where) and pathway_closure_patients (DISTINCT p with status IN _CLOSURE_STATUSES) alongside the existing episode aliases; new _cohort_denominator_cypher helper resolves the cohort denominator + 3 excluded buckets, scoped by org/scope only (no cancer_type/closure_reason/reviewed_at predicates); get_mission_control_kpis runs both queries on a single PatientGraphClient and packs a stable "cohort" block (zero-filled when the row is absent). services/ui/src/lib/missionControlApi.ts: MissionKPIs gains confirmed_cancer_patients, pathway_closure_patients, optional cohort: MissionKPICohort. services/ui/src/components/mission-control/KPIStrip.tsx: KPICard subValue prop; patient-headline + "<N> pathways" sub-line on Confirmed cancer and Pathway closures cards; rewritten plain-English tooltips; cohort denominator caption rendered below the strip with reading-age 9-11 builder helper buildCohortDenominatorLine() |
| Risk | R-LEO-AI-201 | mitigated | Mission Control KPI strip presents episode counts under patient-unit labels and hides patients excluded by the date / referral-date filter, leading reviewers to miss real cancers (mitigated by patient-equivalent counts using confirmed_cancer_where to stay aligned with /audit/summary, plain-English tooltips, and an always-visible cohort denominator caption that lists each excluded bucket) |
| Verification Test | VT-LEO-AI-206 | passed | KPI patient-headline + cohort denominator (15/15 cases pass: 9 backend pytest cases including patient-equivalent counts, cohort fields, scope binding, endpoint cohort block + zero-fill on empty; 6 UI jest cases including patient-headline / pathway-sub-line on both cards, cohort caption with breakdown, showing-all variant, missing-cohort guard, helper pluralisation) |

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
| Verification Test | VT-LEO-AI-175 | passed | 17 tests: 12 backend pytest cases (compile_drafts global refusal + custom-scope happy path, evaluator/diagnose not_compiled, delete_scope happy path + global refusal, sandbox_replay compile+replay+cleanup happy + failure paths, diagnose passthrough, sandbox per-regression diagnostics, replay_scope propagates guideline_id as pathway_filter, pathway_filter overrides payload.pathway_id) plus 5 jest cases (banner production/sandbox/error variants + TestPatientsPanel sandbox happy + empty-compile paths + scope regression: the panel always probes the global production bitmap and never reports a false "no ruleset" warning for per-guideline rules); guidance UI suite 93/93 passing |

### April 2026 - In-place edit for saved test patients

Reviewers can now edit a saved test patient in place from the
/admin/guidance/test-patients library page -- updating the name,
description, codes, age, sex, pathway and full expectation list in
a single PATCH call -- so fixing a typo or adjusting a must-NOT-fire
assertion no longer requires the destructive delete + rebuild
workflow that broke patient ids and snapshot history.

The Cypher rewrite is atomic: a single statement updates the
TestPatient profile AND clears every existing EXPECTED_RESULT
relationship, so the patient cannot be left half-updated. Audit
trail is preserved via new `updated_at` / `updated_by` properties
on the TestPatient node.

The dialog (`BuildPatientDialog`) gains an optional `editingPatient`
prop. In edit mode it seeds the form from the saved profile +
expectations, switches title and button copy, calls
`api.updatePatient` instead of `api.savePatient`, enables Save
without a fresh dry-run (the patient already passed validation when
first saved), and preserves the saved `matched_branch_node_ids`
verbatim when the reviewer saves without re-running dry-run -- so
editing a name does not blank per-rule branch attribution.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-185 | approved | Reviewers MUST be able to edit a saved test patient in place from /admin/guidance/test-patients (PATCH endpoint + atomic Cypher rewrite + dialog edit-mode + library-page Edit button) so that fixing a typo or adjusting an expectation no longer requires delete + rebuild |
| Design Output | DO-LEO-AI-184 | approved | UPDATE_TEST_PATIENT Cypher (atomic props update + EXPECTED_RESULT clear) + update_patient service helper + PATCH /guidance/test-patients/{id} endpoint + api.updatePatient client + BuildPatientDialog editingPatient prop + page.tsx Edit button |
| Risk | R-LEO-AI-179 | mitigated | Editing a saved test patient silently drops or corrupts an EXPECTED_RESULT, masking future regressions; harm: a wrong appropriateness rule (e.g. one that over-fires the 2-week-wait recommendation) reaches production because the negative-test patient that should have caught it no longer asserts the must-NOT-fire expectation |
| Verification Test | VT-LEO-AI-179 | passed | 10 cases: 3 service pytest cases (happy path / 404 / empty expectations), 3 router cases (PATCH happy / 404 / empty), 1 api client jest case (PATCH + JSON_HEADERS), 3 static-source cases (dialog edit-mode wiring + matched_branch_node_ids preservation + page Edit button); 34 backend + 21 frontend tests passing |

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
| Design Input | DI-LEO-AI-167 | verified | Replay engine, post-compile gate and Clinical Guidelines surfacing (UN-LEO-AI-076): test_patient_service.diff_replay() buckets each asserted rule into passes / regressions / unexpected_matches and replay_scope() persists the aggregate as a :RulesetReplay node tagged with ruleset_version; services/terminology_api/app/routers/guidelines.py _trigger_test_patient_replay() POSTs to /guidance/test-patients/replay after every successful guideline compile carrying the SERVICE_AUTH_SECRET Bearer header from libs/auth/service_auth.get_service_auth_header (errors logged at WARNING, do not block the compile); services/api/app/deps.py require_admin_or_service accepts EITHER an admin session cookie OR the SERVICE_AUTH_SECRET token so the inter-service hook authenticates without leaning on LEO_LOCAL_DEV_BYPASS, and is applied to /guidance/test-patients/replay; BitmapLifecycleSection.tsx surfaces the latest report with a coloured banner and a link to the test-patient library; EditRuleDialog/TestPatientsPanel.tsx re-runs a rule-scoped replay on every change of the rule's logic-tree signature and shows a regression banner naming the affected rules in plain English (passed 2026-04-19) |
| Design Output | DO-LEO-AI-166 | approved | services/api/app/services/test_patient_service.py (replay_one, replay_scope, diff_replay, _persist_replay_report); services/terminology_api/app/routers/guidelines.py (_trigger_test_patient_replay hook on _run_compile, sends SERVICE_AUTH_SECRET Bearer header); services/api/app/deps.py (require_admin_or_service: cookie OR Bearer); services/api/app/routers/test_patients.py (/guidance/test-patients/replay protected by require_admin_or_service); services/ui/src/app/admin/guidance/test-patients/page.tsx (library page); services/ui/src/app/admin/guidance/test-patients/ReplayResultsDialog.tsx; services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx (latest replay banner); services/ui/src/app/admin/guidance/EditRuleDialog/TestPatientsPanel.tsx (per-rule auto-replay panel) |
| Verification Test | VT-LEO-AI-166 | passed | 7 jest cases (services/ui/src/__tests__/test-patients-page.test.tsx): TC-001..003 library page wires Build / Generate / Replay actions, scope filter and plain-English empty state, TC-004..005 API client targets the right endpoints with X-Requested-With on POST, TC-006..007 ReplayResultsDialog renders pass / regression / unexpected and stays jargon-free on the empty state. Plus 9 pytest cases (services/api/tests/test_require_admin_or_service.py + services/terminology_api/tests/test_post_compile_replay_hook.py): TC-008..013 cover require_admin_or_service accepting either admin session cookie or SERVICE_AUTH_SECRET Bearer (with timing-safe rejection of wrong tokens, no widening when the secret is unset, and 403 on non-admin sessions), TC-014..016 cover the post-compile replay hook sending the Bearer header in deployed envs, omitting it when the secret is unset and swallowing 401s without blocking the compile (passed 2026-04-19) |
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

## Trustworthy Gold-Label Review and Self-Consistent Training Data (April 2026)

On 2026-04-17 a reviewer reported that the Gold Label detail dialog
showed an unrelated entity (`Flexible cystoscopy`) attached to a
breast-USS sentence. Investigation surfaced two distinct defects:
(1) the React `GoldLabelDetailDialog` mounted across four list surfaces
(gold/synonym/candidate/similar) reused component instances without a
stable `key`, so the lazy `useState(() => parseEntities(...))`
initialiser captured the previously-displayed label's entities; and
(2) the SNOMED proposal validator only ran against new LLM additions,
leaving 88 critical self-consistency issues across the 967 already
persisted GoldLabels (including 7 records mapping `(qualifier value)`
SNOMED concepts onto clinical labels such as `finding`).

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-082 | approved | Reviewers and trainers need a trustworthy gold-label review UI plus self-consistent persisted training data so that no GoldLabel ever displays entities from a different label, no GoldLabel persists with a SNOMED concept whose semantic tag contradicts its label, and any drift introduced by future seed scripts or LLM augmentations is detected offline before it reaches the NER training set |
| Design Input | DI-LEO-AI-185 | verified | GoldLabelDetailDialog re-mount + state resync. Every JSX mount of <GoldLabelDetailDialog> in services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx carries a stable `key` derived from `label_id` (per-surface namespace prefixes gold-/syn-/cand-/sim-). The dialog body adds a useEffect with deps [item.label_id, item.entities_json] that re-derives entities, rejectedRelationKeys, and clears suggestion drafts, term drafts, surface-form drafts, lookup target, save state, and delete-confirm flags when label_id changes; the lazy useState fast path is preserved (passed 2026-04-17) |
| Design Input | DI-LEO-AI-186 | verified | Offline gold-label entity audit. scripts/lib/gold_label_snomed_check.py adds audit_existing_entity + audit_gold_label_entities + ENTITY_AUDIT_ISSUE_CODES + _derive_semantic_tag_from_term + _CLINICAL_LABELS + _NON_CLINICAL_SEMANTIC_TAGS auditing every persisted GoldLabel entity for self-consistency without calling the terminology service. Issue codes: missing_concept_id (critical), missing_label (critical), qualifier_value_on_clinical_label (critical), tag_label_mismatch (critical), stored_tag_drift (info), missing_snomed_term (warning), blocked_assertion_with_concept (info). CLI scripts/audit_gold_label_entities.py sweeps the live KG, writes data/audit/gold_label_entity_audit_<UTC>.jsonl + .summary.json, supports --severity, --source, --exclude-source, --limit. First sweep flagged 88 critical / 80 warning / 398 info issues across 967 GoldLabels (passed 2026-04-17) |
| Design Input | DI-LEO-AI-187 | verified | Manual gold-seed safety check. scripts/seed_manual_gold_records.py::_validate_entity derives `semantic_tag` from the SNOMED preferred-term suffix (suffix-derived tag is authoritative), rejects writes where declared semantic_tag disagrees with the suffix outside _TAG_SYNONYMS, REJECTS writes where label is in _CLINICAL_LABELS but the authoritative semantic_tag is in _NON_CLINICAL_SEMANTIC_TAGS (with R-LEO-AI-180 named in the error), and rejects writes where snomed_concept_id is set but snomed_term is empty. design-controls/training-data/manual-gold-seed-2026-04-17.yaml updated: 5 entries (NEG-04, NEG-06, NEG-07, NEG-13, NEG-17) relabelled finding -> qualifier_value and re-seeded; audit confirms zero remaining offenders from this source (passed 2026-04-17) |
| Design Output | DO-LEO-AI-184 | approved | services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx (key prop on all four GoldLabelDetailDialog mounts using gold-/syn-/cand-/sim- namespace prefixes; useEffect resync hook with deps [item.label_id, item.entities_json] resetting all entity-derived state); services/ui/src/__tests__/gold-label-detail-dialog-rekey.test.tsx (new static-source jest VT) |
| Design Output | DO-LEO-AI-185 | approved | scripts/lib/gold_label_snomed_check.py (audit_existing_entity, audit_gold_label_entities, ENTITY_AUDIT_ISSUE_CODES, EntityAuditResult, _derive_semantic_tag_from_term, _CLINICAL_LABELS, _NON_CLINICAL_SEMANTIC_TAGS, _AUDIT_AUTO_CODE_BLOCKED, _AUDIT_SEVERITY); scripts/audit_gold_label_entities.py (CLI sweeping `MATCH (g:GoldLabel) WHERE g.entities_json IS NOT NULL`, JSONL + summary report, --severity / --source / --exclude-source / --limit filters); tests/test_gold_label_existing_entities_audit.py (22 pytest cases) |
| Design Output | DO-LEO-AI-186 | approved | scripts/seed_manual_gold_records.py (_validate_entity hardened: suffix-derived semantic_tag, rejects declared/derived disagreement outside _TAG_SYNONYMS, rejects qualifier_value semantic_tag under clinical labels with R-LEO-AI-180 named, rejects missing snomed_term when snomed_concept_id is set); design-controls/training-data/manual-gold-seed-2026-04-17.yaml (5 NEG-XX entries corrected); tests/scripts/test_seed_manual_gold_records.py (6 new TC-006 cases pinning each safety branch) |
| Risk | R-LEO-AI-179 | mitigated | GoldLabelDetailDialog stale-state leak between gold/synonym/candidate/similar list surfaces displays entities from a previously viewed GoldLabel against an unrelated sentence, causing a reviewer to accept, reject, or modify entities on the wrong record. Harm: corrupted training data and wrong SNOMED-tag attribution propagating into the NER model. Severity serious. Mitigated by DI-LEO-AI-185 (stable per-label_id `key` prop forces React to remount the component tree on selection change; useEffect resync covers any future code path that retains the existing instance). Residual low |
| Risk | R-LEO-AI-180 | mitigated | Already-persisted GoldLabel entities can carry SNOMED concepts whose semantic tag contradicts their label (e.g. (qualifier value) under label='finding') because the SNOMED proposal validator was scoped to LLM additions only. Harm: NER model learns to emit clinical-label spans against qualifier-value SNOMED codes, downstream auto-coding produces clinically wrong codes. Severity serious. Mitigated by DI-LEO-AI-186 (offline audit detects every existing offender) and DI-LEO-AI-187 (seed-script safety check at write time blocks the regression class). 5 known offenders remediated; remaining 2 critical offenders flagged for triage. Residual low |
| Verification Test | VT-LEO-AI-179 | passed | 5 jest static-source tests in services/ui/src/__tests__/gold-label-detail-dialog-rekey.test.tsx: stable `key` on all four mounts, distinct namespace prefixes, useEffect deps [item.label_id, item.entities_json], state-reset coverage in the resync block, lazy useState initialiser preserved (passed 2026-04-17) |
| Verification Test | VT-LEO-AI-180 | passed | 22 pytest cases in tests/test_gold_label_existing_entities_audit.py covering all seven issue codes, severity ranking (critical > warning > info), suffix-derived tag truth, synonym tolerance, blocked-assertion info classification, stored-tag drift detection, batch audit aggregation, and a live-payload replay of the GL-d3ffb211468a5bcf record that triggered the original report (passed 2026-04-17) |
| Verification Test | VT-LEO-AI-181 | passed | 19 pytest cases in tests/scripts/test_seed_manual_gold_records.py (13 pre-existing + 6 new TC-006 cases TC-006A..F): suffix-derived tag overrides declared, qualifier_value on clinical label rejected with R-LEO-AI-180 named, declared/derived disagreement outside _TAG_SYNONYMS rejected, synonym tolerance accepted, missing snomed_term with concept_id rejected, full real-manifest seed loads after corrections (passed 2026-04-17) |

---

## Confidence-Gated TrainingCandidate Auto-Prune (April 2026)

This programme adds a confidence-gated auto-prune workflow for the
~900 TrainingCandidate rows sitting in non-completed states
(`pending`, `processing`, `failed`) that the LLM extractor over-produced
against and that human reviewers will never get to. The same SNOMED
proposal validator that powers `R-LEO-AI-180` is rerun over each
candidate's persisted entities; candidates whose every entity fails the
validator at the supplied confidence floors are eligible for cascade
deletion (TrainingCandidate + draft GoldLabel + SurfaceFormTask).
Three safety rails force the verdict to `'review'` instead of
`'delete'`: zero-entity candidates, candidates with any entity carrying
an `_AUTO_CODE_BLOCKED` assertion (absent / refuted / declined / cancelled
/ planned / hypothetical / possible / historical / family), and
candidates sourced from `manual_gold_seed*` -- exactly the categories
where validator rejection is most likely to misread genuine signal.
Status `'completed'` (gold) is never targeted regardless of input.
The workflow is exposed on the Training Data > Candidates tab via a
new "Auto-prune low confidence" toolbar action that runs a server
preview before any destructive action is enabled, with an explicit
"permanently delete N candidates" acknowledgement checkbox gating the
final button. A CLI mirror at `scripts/prune_low_confidence_candidates.py`
provides the same preview-then-execute flow for offline operations
(defaults to dry-run; `--apply` required to delete).

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-083 | superseded | Reduce HITL backlog by auto-pruning training candidates that cannot produce defensible SNOMED codes. Superseded by UN-LEO-AI-085 (AI first-pass) which replaces "delete the unloved" with "pre-code what we can, delete what we can't, leave the rest for review". The endpoints, dialog and CLI from this section remain in place but are no longer the recommended reviewer entry point. |
| Design Input | DI-LEO-AI-196 | verified | candidate_prune service + /candidates/prune/preview + /candidates/prune/execute endpoints. services/api/app/services/candidate_prune.py implements PruneParams (default floors 0.7/0.92/0.66 mirroring R-LEO-AI-180), CandidateAssessment dataclass, assess_candidates (ThreadPoolExecutor max 8 workers; verdict ladder zero-entity/blocked-assertion/manual-seed -> review, all-rejected -> delete, all-accepted -> keep, mixed -> review), execute_prune (TOCTOU re-check via GET_TRAINING_CANDIDATE_BY_ID; reports cascade counts), summarise. Both endpoints depend on require_admin and emit INFO audit log lines (passed 2026-04-17) |
| Design Input | DI-LEO-AI-197 | verified | CandidatePruneDialog + ToolbarAction id='auto-prune' on Candidates tab. services/ui/src/components/gold-dataset/CandidatePruneDialog.tsx (471 LOC) wraps preview-then-execute, three numeric inputs for confidence floors (defaults 0.7/0.92/0.66), status multi-select (default pending+processing+failed), grouped preview table with rejection-reason chips, destructive Delete button gated on previewLoaded && deleteCount > 0 && confirmAcknowledged, "permanently delete" acknowledge checkbox, in-flight close guard (passed 2026-04-17) |
| Design Output | DO-LEO-AI-195 | draft | services/api/app/services/candidate_prune.py + 2 routes (POST /training/candidates/prune/preview, POST /training/candidates/prune/execute) in services/api/app/routers/training.py + scripts/prune_low_confidence_candidates.py CLI mirror (writes data/audit/candidate_prune_<UTC>.{preview.jsonl,summary.json,execute.json}) |
| Design Output | DO-LEO-AI-196 | draft | services/ui/src/components/gold-dataset/CandidatePruneDialog.tsx + GoldDatasetPanel.tsx ToolbarAction wiring with onPruned reloading list+stats |
| Risk | R-LEO-AI-187 | mitigated | Auto-prune deletes a TrainingCandidate that the model actually needed to learn from. Harm: slow erosion of training signal -> next NER model release degrades silently on the surface forms the curator had been collecting examples of. Severity minor. Mitigated by the three-branch verdict ladder (EXACT/SEMANTIC/SURFACE; only candidates where every entity fails ALL branches qualify for delete), the three safety rails (zero-entity/blocked-assertion/manual-seed -> review), and the two-phase preview-then-confirm UI. Residual low |
| Risk | R-LEO-AI-188 | mitigated | Auto-prune deletes the only evidence of a systemic LLM extractor regression before a human can investigate. Harm: failure pattern silently removed from the HITL queue, regressed prompt continues to run in production. Severity minor. Mitigated by grouped preview surfacing rejection-reason distribution and per-call audit logging (actor email, floors, per-verdict counts) so a sudden spike in deleted_total or tag_mismatch_all rejections is visible to the curator before they confirm. Residual low |
| Verification Test | VT-LEO-AI-182 | passed | 20 pytest cases in tests/test_candidate_prune.py (14 service: zero-entity / blocked-assertion / manual-seed safety rails, all-rejected, all-accepted, mixed, empty entity text, resolver exception, summarise, execute_prune TOCTOU re-check, not-found path, deletion + cascade counts, fetch scope guard) + services/api/tests/test_candidate_prune_endpoint.py (6 endpoint: admin gating, preview read-only, execute TOCTOU skip, empty id list 400, deleted/cascade counts, not_found path) (passed 2026-04-17) |
| Verification Test | VT-LEO-AI-183 | passed | 6 jest static-source cases in services/ui/src/__tests__/candidate-prune-dialog.test.tsx: ToolbarAction id='auto-prune' wired alongside Deduplicate similar, default floors 0.7/0.92/0.66, destructive button disabled until previewLoaded + deleteCount > 0 + confirmAcknowledged, "permanently delete" label literal, handleClose loading guard, file size <=500 LOC (passed 2026-04-17) |

---

## AI first-pass over the candidate to-do list (April 2026)

Reviewers had ~900 non-completed `TrainingCandidate` rows to work
through, which is overwhelming. UN-LEO-AI-085 replaces the
"defensive" auto-prune (UN-LEO-AI-083) with an "offensive" AI
first-pass: for every non-completed candidate, ask Haiku to extract
entities (seeded with BioClinicalBERT few-shot exemplars from the
gold pool), then ask the SNOMED resolver + validator to code each
entity, with up to N Haiku alt-search-term retries when the
validator rejects. Each candidate ends in one of three verdicts:

- `pre_done`: at least one entity was confidently coded -> overwrite
  `entities_json` with the AI suggestions, stash the original in a
  write-once `entities_json_original` audit copy, and keep the
  candidate in the reviewer queue (status stays `pending`). The
  reviewer sees an "AI suggested" chip on every entity row plus a
  "show original" toggle to flip back to the pre-AI snapshot.
- `delete`: the AI extracted entities but none could be coded, and
  no safety rails fired -> cascade-delete (TOCTOU re-checked so
  status='completed' is never touched).
- `review`: a safety rail fired (zero entities, `_AUTO_CODE_BLOCKED`
  assertion, `manual_gold_seed` source, or status flipped to
  `completed` mid-flight) -> leave it alone for the human reviewer.

The flow runs as an admin-gated background job with SSE progress
(`POST /api/training/candidates/ai-first-pass/jobs` then
`GET /jobs/{run_id}/events`). The reviewer-facing trigger is the
"AI first-pass" button on the Candidates tab toolbar. A CLI mirror
at `scripts/ai_first_pass.py` provides the same dry-run-then-apply
flow for offline operations (always runs dry-run first; `--apply`
required to write).

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-085 | approved | AI first-pass over the non-completed TrainingCandidate backlog (Haiku entity extraction + BioClinicalBERT few-shot exemplars + SNOMED resolver + Haiku alt-query smart coder); verdicts pre_done / delete / review; admin-gated background job with SSE progress; never modifies status='completed'; reviewer always sees an "AI suggested" chip and a "show original" toggle on touched candidates |
| Design Input | DI-LEO-AI-208 | approved | candidate_ai_first_pass service (extractor + smart coder + verdict ladder + writeback). services/api/app/services/candidate_ai_first_pass/ implements AIFirstPassParams (default floors 0.7/0.92/0.66, dry_run=False, haiku_tier='small', few_shot_k=5, coder_max_retries=2), ai_extract_entities (Haiku + BioClinicalBERT few-shot exemplars from the gold pool; falls back to original entities_json with extractor_error recorded), ai_code_entity (validator + Haiku alt-search-term loop), classify_candidate (verdict ladder), writeback_pre_done (UPSERT_AI_FIRST_PASS_ENTITIES sets entities_json_original write-once and refuses to write status='completed'), execute_delete (TOCTOU re-check). CLI mirror in scripts/ai_first_pass.py. |
| Design Input | DI-LEO-AI-209 | approved | AI first-pass background job + reviewer UI. services/api/app/routers/_training_ai_first_pass.py exposes admin-gated POST /candidates/ai-first-pass/jobs (queue), GET /jobs/{run_id} (status), GET /jobs/{run_id}/events (SSE candidate.processed -> job.summary). Next.js Route Handler at services/ui/src/app/api/training/candidates/ai-first-pass/jobs/[runId]/events/route.ts proxies the SSE straight to the browser. AIFirstPassDialog renders the parameter form (dry_run defaulted to true, close-while-running guard) and a live by_verdict + by_action tally. GoldDatasetPanel registers id='ai-first-pass' on the Candidates tab. CandidateReviewList shows an "AI suggested" row badge. GoldLabelDetailDialog shows a per-entity AI chip and a read-only "show original" toggle bound to entities_json_original. |
| Design Output | DO-LEO-AI-205 | draft | services/api/app/services/candidate_ai_first_pass/ (_types, _gold_pool, _extractor, _coder, _verdict, _writeback, _job_runner, __init__) + libs/cypher/training_candidate_queries.py (UPSERT_AI_FIRST_PASS_ENTITIES + READ_GOLD_POOL_FOR_FEW_SHOT + GET_TRAINING_CANDIDATE_BY_ID extension surfacing entities_json_original / ai_first_pass_run_id / ai_first_pass_at) + scripts/ai_first_pass.py CLI |
| Design Output | DO-LEO-AI-206 | draft | services/api/app/routers/_training_ai_first_pass.py (queue/status/events) + services/ui/src/app/api/training/candidates/ai-first-pass/jobs/[runId]/events/route.ts (Next.js SSE proxy) + services/ui/src/components/gold-dataset/AIFirstPassDialog.tsx + GoldDatasetPanel.tsx (toolbar id='ai-first-pass', dialog mount, GoldLabelDetailDialog AI chip + show-original toggle) + CandidateReviewList.tsx (row badge) + goldDatasetTypes.ts (Candidate / GoldLabel ai_first_pass_run_id / ai_first_pass_at / entities_json_original fields) |
| Risk | R-LEO-AI-197 | mitigated | AI first-pass overwrites entities_json and corrupts gold-bound labels. Harm: pre-existing curated entity work silently lost; reviewer cannot tell what the AI changed; downstream model trains on AI hallucinations. Severity serious. Mitigated by write-once entities_json_original audit copy (UPSERT_AI_FIRST_PASS_ENTITIES never overwrites the snapshot once set), dry-run defaulting to true in the dialog, TOCTOU re-check that excludes status='completed' immediately before any write or delete, "AI suggested" chip + "show original" toggle on every reviewer surface so the pre-AI baseline is one click away, and safety rails (zero-entity / _AUTO_CODE_BLOCKED assertion / manual_gold_seed source) that route to verdict=review without writing. Residual low |
| Verification Test | VT-LEO-AI-200 | passed | candidate_ai_first_pass pytest VT (extractor fallback, gold-pool few-shot loader, smart coder validator + retry loop, verdict ladder + safety rails, writeback invariants including entities_json_original write-once and status='completed' refusal, endpoint admin gating + queue + status + SSE event stream) |
| Verification Test | VT-LEO-AI-201 | passed | 15 jest static-source cases across services/ui/src/__tests__/ai-first-pass-toolbar-id.test.tsx + ai-first-pass-dialog-chrome.test.tsx + gold-label-detail-ai-chip-and-toggle.test.tsx: toolbar id='ai-first-pass' + dialog mount, AIFirstPassDialog SSE wiring (EventSource on /events, candidate.processed updates by_verdict/by_action, job.summary closes the source, dry_run defaults to true, handleClose no-ops while running, AIFirstPassDialog.tsx <=600 LOC), GoldLabelDetailDialog per-entity AI chip + show-original toggle (gated on isAISuggested, original list gated on showOriginalEntities, original view is read-only with no save handlers wired, toggle resets to false when item.label_id changes), CandidateReviewList row badge, Candidate + GoldLabel UI types carry the AI audit fields (passed 2026-04-17) |

---

## Dry-run NER errors to gold-label correction (April 2026)

The `/admin/console` Evaluate stage exposes a "2b) Dry run on real
encounters" workflow that surfaces NER quality issues on real patient
encounters (missing entities, wrong tagging of informational header
text, incorrect labels on long observation strings). Until now there
was no path from a failing dry-run row into the gold-label editor:
fixing a regression meant leaving the page, hand-searching for the
encounter text, and re-creating the candidate by hand. This change
adds a per-row "Open in gold editor" IconButton on every dry-run row
(both NER-only and full-pipeline blocks). One click POSTs the
encounter text and the dry-run extraction to a new endpoint that
de-identifies the text server-side, hashes the de-identified text to
`candidate_id` (matching the existing `_candidate_id` contract used
by the pipeline), upserts a `TrainingCandidate` with
`source='dry_run_correction'`, ensures a draft `GoldLabel`, and
deep-links the reviewer into `GoldLabelDetailDialog` so the
correction can be promoted to gold training data without leaving the
flow. The feature is idempotent on `candidate_id`: two reviewers
clicking the same encounter land on the same draft.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-084 | approved | One-click conversion of dry-run NER errors into gold training data (per-row "Open in gold editor" on /admin/console -> Evaluate -> 2b dry-run; deep link to GoldLabelDetailDialog; idempotent on candidate_id) |
| Design Input | DI-LEO-AI-198 | approved | POST /api/training/candidates/from-dry-run: server-side deidentify_text(ner=True) before hashing; candidate_id = sha256(deidentified text); upsert TrainingCandidate (source='dry_run_correction'); ensure draft GoldLabel; idempotent |
| Design Input | DI-LEO-AI-199 | approved | EvaluateStage 'Open in gold editor' IconButton on every dry-run row (NER-only and full-pipeline) + GoldDatasetPanel useSearchParams deep-link handler (?labelId, from=dry_run -> candidates tab) + Suspense wrapper on /gold-dataset/page |
| Design Output | DO-LEO-AI-197 | draft | services/api/app/routers/training.py (candidate_from_dry_run, _sanitise_dry_run_entities) + services/ui/src/components/console/EvaluateStage.tsx (openInGoldEditor + IconButton in both row blocks) + services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx (deep-link effect) + services/ui/src/app/gold-dataset/page.tsx (Suspense) |
| Risk | R-LEO-AI-189 | mitigated | PHI leakage into gold dataset via dry-run correction path. Harm: UK GDPR Article 9 special-category data leak from patient graph into knowledge graph and onward into model weights. Severity critical. Mitigated by server-side deidentify_text(text, ner=True) before either hashing or persisting (single point of enforcement); candidate_id = sha256(deidentified_text) matches existing _candidate_id contract so dry-run-corrected and pipeline-produced candidates collapse onto the same node; source='dry_run_correction' lets weekly audit_gold_label_entities runs segment dry-run-sourced rows; source_hint truncated to 64 characters. Residual low |
| Verification Test | VT-LEO-AI-191 | passed | 6 pytest cases in tests/test_candidate_from_dry_run.py: deidentify-before-hash, source/status pinning, entity re-anchoring with unmappable drop, idempotency on second call, 400 on empty input, source_hint truncation (passed 2026-04-18) |
| Verification Test | VT-LEO-AI-192 | passed | 8 jest static-source cases in services/ui/src/__tests__/dry-run-open-gold-editor.test.tsx: imports of IconButton/EditNoteIcon/useRouter, IconButton with aria-label='Open in gold editor' rendered in both row blocks, POST + deep-link push, disabled guards on in-flight + empty text, useSearchParams plumbing, deep-link useEffect with router.replace clear, candidates tab on dry_run, Suspense wrapper on /gold-dataset/page (passed 2026-04-18) |

---

## Strict Non-Site-Specific (NSS) Cancer Classification (April 2026)

The episode builder previously over-classified encounters as
`cancer_type='non_site_specific'` for two reasons:

1. The `_SITE_MAP` substring rule `("fast", "non_site_specific")`
   matched any text containing "fast" -- including "fasting bloods",
   "fast turnaround", and PRISM template names.
2. The generic-cancer-term fallback in `_extract_condition_key`
   mapped any unsited cancer mention ("carcinoma", "neoplasm",
   "cancer") to NSS instead of leaving it as `unknown`.

Combined with three Read-code mis-mappings (XaMeD / XaMeL / XaPyS,
all incorrectly mapped to NSS instead of childrens_tumour /
testicular), this produced 48 phantom or misclassified
`non_site_specific` `EpisodeOfCare` nodes across the live cohort.

DI-LEO-AI-200 enforces a strict rule: `cancer_type='non_site_specific'`
only when the text matches an explicit NSS surface form
(`_NSS_PHRASE_RE`, covering the SNOMED 1556551000000104 guideline
synonym list), or when the SNOMED concept_id / Read code is one of
the canonical NSS pathway codes.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-200 | approved | Strict NSS classification: only explicit NSS surface forms (`_NSS_PHRASE_RE`) or canonical NSS SNOMED/Read codes classify cancer_type='non_site_specific'; generic cancer text without a site returns 'unknown' so NSS-absorption (DI-LEO-AI-196) folds it into a typed pathway |
| Design Output | DO-LEO-AI-198 | approved | services/analysis_worker/app/analyzers/episode_builder/_site_resolution.py (`_NSS_PHRASE_RE` regex; `_SITE_MAP` cleanup; `_extract_condition_key` returns 'unknown' for generic-term fallback) + libs/domains/code_inventories.py (XaMeD->childrens_tumour, XaMeL->testicular, XaPyS->childrens_tumour) |
| Risk | R-LEO-AI-190 | mitigated | Phantom or false-positive non-site-specific cancer pathway misclassification. Harm: reviewer fatigue / loss of trust in NSS triage queue, wasted clinical time, risk of missed real NSS pathway. Severity serious. Mitigated by strict NSS rule, Read-code corrections, and coordination with NSS-absorption (DI-LEO-AI-196). Live cohort dropped from 48 phantom/misclassified NSS episodes to 0. Residual low |
| Verification Test | VT-LEO-AI-193 | passed | 18 pytest cases in tests/test_site_resolution_nss.py: 9 positive (full SNOMED phrase, '2WW NSS', 'NSS 2ww', 'fast track NSS', 'NSS referral', 'non-specific symptoms', SNOMED concept ID 1556551000000104, no-hyphen variant), 9 negative/type-clash (fasting bloods, fast turnaround, carcinoma of unknown primary, PRISM pathway names, cancer follow-up clinic, oncology surveillance, breast referral with cancer text, XaMeD->childrens_tumour, XaPyS->childrens_tumour). Live cohort wipe + rebuild produced zero NSS episodes (down from 48) |

---

## Patient 4643293950 Pattern Hardening (April 2026)

Single-patient deep dive on `4643293950` surfaced seven generalisable
detector / builder failure modes (Patterns A-G). Each pattern is
addressed at the rule layer (regex, status engine, builder context)
rather than per-patient so the fix carries across the cohort. Bundled
DIs / DOs / VTs / Risks below.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-201 | approved | Pattern B - tighten `_RE_FIRST_SEEN` so every alternation requires an attestation verb (`seen`/`attended`/`reviewed`/`assessed`/`consulted`) within proximity of the clinic / fast-track / 2WW token |
| Design Output | DO-LEO-AI-199 | approved | `_RE_FIRST_SEEN` rebuild in services/analysis_worker/app/analyzers/anchor_detector.py |
| Risk | R-LEO-AI-191 | mitigated | Open referral falsely promoted to 'completed' status via phantom first_seen anchor from narrative discussion |
| Verification Test | VT-LEO-AI-194 | passed | First-seen attestation guard - positive (clinic seen / attended) and negative (narrative discussion / awaiting / considering) cases |
| Design Input | DI-LEO-AI-202 | approved | Pattern C+D - narrative-reference referral guard suppressing `text_generic` referrals when text is purely commentary about a past referral with no structural referral evidence |
| Design Output | DO-LEO-AI-200 | approved | `_RE_NARRATIVE_REFERRAL_REFERENCE` + `_RE_STRUCTURAL_REFERRAL` + `_classify_text_encounters` suppression logic in anchor_detector.py |
| Risk | R-LEO-AI-192 | mitigated | Inflated referral count from narrative commentary about past referrals creating phantom text_generic referrals |
| Verification Test | VT-LEO-AI-195 | passed | Narrative-reference referral guard - DNA / awaiting result narratives suppressed; structural referral codes still emit referral |
| Design Input | DI-LEO-AI-203 | approved | Pattern E - PMHx history-of-cancer detection: malignancy under recognised Past medical history section header treated as historical context |
| Design Output | DO-LEO-AI-201 | approved | `_PMHX_SECTION_RX` + `_malignancy_under_pmhx_section` + `text_contains_history_of_cancer` wiring in libs/domains/code_inventories.py |
| Risk | R-LEO-AI-193 | mitigated | Open cancer pathway falsely closed as benign because PMHx malignancy line is misread as new diagnosis |
| Verification Test | VT-LEO-AI-196 | passed | PMHx history-of-cancer detection - PMHx-section malignancy treated as history; current-encounter malignancy still surfaced |
| Design Input | DI-LEO-AI-204 | approved | Pattern G - new `care_obstruction` milestone covering DNA + reason, refusal of named investigation, safeguarding, hospital retraction, family aggression, with HITL escalation on the parent EpisodeOfCare |
| Design Output | DO-LEO-AI-202 | approved | `_RE_CARE_OBSTRUCTION` + 9-tuple `_AnchorBuckets` + `_care_obstruction_link_anchors` / `_care_obstruction_hitl` wiring across anchor_detector.py + episode_builder/_builder.py |
| Risk | R-LEO-AI-194 | mitigated | Blocked / refused / safeguarding-flagged pathways swallowed by stale-close pass without HITL review |
| Verification Test | VT-LEO-AI-198 | passed | care_obstruction emission + HITL escalation on parent EpisodeOfCare |
| Design Input | DI-LEO-AI-205 | approved | Pattern A - `rejected_no_followup` status engine surfacing referrals rejected with no follow-up referral within 90 days as a discrete HITL status |
| Design Output | DO-LEO-AI-203 | approved | `_has_followup_referral` + `_rejection_followup_status` + `_determine_episode_status` integration in services/analysis_worker/app/analyzers/episode_builder/_status.py |
| Risk | R-LEO-AI-195 | mitigated | Rejected referral with no follow-up silently aged out by stale-close instead of being surfaced for HITL action |
| Verification Test | VT-LEO-AI-197 | passed | rejected_no_followup status - rejection without follow-up returns rejected_no_followup; rejection followed by new referral remains in_progress |
| Design Input | DI-LEO-AI-206 | approved | Pattern F - exclusive encounter claiming via `BuildContext.claimed_encounters` + `_filter_unclaimed_link_groups` enforcing single-claim invariant per encounter / per non-referral milestone |
| Design Output | DO-LEO-AI-204 | approved | `BuildContext.claimed_encounters` in episode_builder/_types.py + `_filter_unclaimed_link_groups` + integration into `_build_open_episode` / `_build_closed_episode` in episode_builder/_builder.py |
| Risk | R-LEO-AI-196 | mitigated | Same encounter claimed by multiple EpisodeOfCare nodes causing duplicate-resolver churn and inflated milestone counts |
| Verification Test | VT-LEO-AI-199 | passed | Exclusive encounter claiming - non-referral milestone encounter claimed once; referral encounter remains protected; empty groups dropped |

---

## Patient 4842019832 Pattern Hardening (April 2026)

Single-patient deep dive on `4842019832` surfaced three additional
generalisable detector failure modes (Patterns H, I, J). The patient
had only ONE genuine pathway (Dec 2024 head and neck 2WW seen Jan 2025
with benign LPR / chronic rhinitis outcome) but the detector had
opened THREE EpisodeOfCare nodes: a phantom prostate `closed_benign`
triggered by a normal PSA result whose auto-filed disclaimer text
contained "If the PSA value remains elevated above the age specific
threshold, refer as a 2WW" combined with "Reasons for Request:
PSA - FH prostate ca." (family history, not patient diagnosis); the
genuine head-and-neck pathway; and a phantom `unknown` in_progress
triggered by a 2025-06-30 follow-up note that read "Was seen by ENT
under 2ww in Jan ... Write to ENT to clarify that polyp requires no
FU." (narrative reference to the prior pathway plus inter-clinician
clarification, not a new referral).

Each failure mode is addressed at the regex / suppression-hook layer.
PRISM, rejection, resubmission, and Read-code referral subtypes are
deliberately unaffected -- only `text_generic` is suppressed, and
only when no structural artefact (XaY59 / PRISM / Hospital fast-track
row / "Fast track referral for suspected ...") is present.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-210 | approved | Pattern H - family-history-of-cancer guard: `_RE_FAMILY_HISTORY_CANCER` matches "FH ca", "FH of prostate ca", "FHx of breast cancer", "father had/diagnosed with cancer", "mother died of ovarian cancer" and similar shapes; `text_contains_history_of_cancer` is extended to treat FH-only mentions as historical context |
| Design Output | DO-LEO-AI-207 | approved | `_RE_FAMILY_HISTORY_CANCER` + suppression hook in `_classify_text_encounters` (anchor_detector.py) + `_FAMILY_HISTORY_CANCER_RX` + `text_contains_family_history_of_cancer` + history-of-cancer wiring (libs/domains/code_inventories.py) |
| Risk | R-LEO-AI-198 | mitigated | Family-history mention misread as a patient cancer event, opening phantom pathways for unaffected patients (e.g. PSA + FH prostate ca screening request) |
| Verification Test | VT-LEO-AI-202 | passed | Family-history guard - 5 positive FH-shape detections + false-positive guard ("Patient diagnosed with prostate cancer in 2018" still recognised as a real patient diagnosis) + end-to-end suppression on PSA + FH encounter (7/7) |
| Design Input | DI-LEO-AI-211 | approved | Pattern I - boilerplate lab-report referral guidance suppression: `_RE_BOILERPLATE_REFERRAL_GUIDANCE` matches PSA / CEA / CA125 / FIT / calprotectin disclaimer wording ("If the PSA value remains elevated...refer as a 2WW", "should be referred", "Consider 2WW referral if ...", "referrals made at the time of UTI will be rejected"); `_RE_AUTO_FILED_PREFIX` recognises the EMR auto-file prefix |
| Design Output | DO-LEO-AI-208 | approved | `_RE_BOILERPLATE_REFERRAL_GUIDANCE` + `_RE_AUTO_FILED_PREFIX` + suppression hook in `_classify_text_encounters` (anchor_detector.py) |
| Risk | R-LEO-AI-199 | mitigated | Auto-filed lab-report disclaimer text containing conditional referral guidance is mis-classified as an actual referral, opening phantom pathways for every routine PSA / CA125 / FIT / calprotectin result drop |
| Verification Test | VT-LEO-AI-203 | passed | Boilerplate lab-guidance suppression - positive boilerplate / Auto-filed detection + false-positive guard ("Refer this patient via 2WW today" still recognised as an active referral instruction) + end-to-end suppression on auto-filed PSA encounter + structural keep-list cross-check (8/8) |
| Design Input | DI-LEO-AI-212 | approved | Pattern J - extended narrative-reference guard: `_RE_NARRATIVE_REFERRAL_REFERENCE` additionally matches past-tense seen-narrative ("was seen by ENT under 2WW in Jan", "patient seen under fast track clinic last month") and inter-clinician clarification ("Write to ENT to clarify", "Letter to consultant") |
| Design Output | DO-LEO-AI-209 | approved | Extended `_RE_NARRATIVE_REFERRAL_REFERENCE` alternations covering was-seen and write-to-clinician shapes (anchor_detector.py) |
| Risk | R-LEO-AI-200 | mitigated | Past-tense seen-narrative or inter-clinician clarification text is mis-classified as a new referral, opening phantom unknown-cancer episodes from review-encounter follow-ups |
| Verification Test | VT-LEO-AI-204 | passed | Extended narrative-reference guard - 4 positive narrative shapes + structural keep-list cross-check + end-to-end suppression on patient 4842019832 follow-up encounter (6/6) |

---

## Patient 4802892365 generalisable patterns - K, L, M (April 2026)

Patient 4802892365 (confirmed lobular breast cancer; 2025-03-26 referral,
2025-04-28 first seen, 2025-07-28 mastectomy + sentinel node biopsy) was
returned by Mission Control with no `diagnosis_confirmed` milestone, no
`treatment_started` milestone, AND a phantom EpisodeOfCare opened six
months after the real referral. Three generalisable failure patterns
were extracted, each with a focused detector fix, a tightened risk
mitigation, and verification covering both the canonical patient and a
sibling cohort case from a different cancer site.

Pattern K - same-encounter referral + problem-list diagnosis: GPs
routinely add the working diagnosis to the patient's permanent problem
list ("Major: Invasive carcinoma of breast (Ya0ln) - lobular (New
Episode)") at the same time they raise the 2WW referral. The
DI-LEO-AI-145 same-encounter referral gate suppressed the diagnosis
anchor entirely. The fix introduces a strict
`find_malignancy_code_in_problem_line` helper and an `_has_hard_dx_
evidence` override gate so problem-list code, problem-list term, and
active-cancer-care code can all override the gate; surface-form code
mentions ("Considering X78WM") still respect the gate so the original
DI-LEO-AI-145 trap stays in place.

Pattern L - self-narrated past referral: The 2025-09-24 cancer-care-
review note ("Referred by me on 2ww earlier this year, confirmed
breast cancer") was matched by the structural referral cue and emitted
a fresh `text_generic` referral on the review date, opening a phantom
episode 6 months after the real referral. The fix extends
`_RE_NARRATIVE_REFERRAL_REFERENCE` with five retrospective-narration
shapes (referred by me/us/GP/Dr|Mr|Mrs|Ms|Miss; I/we referred; GP
referred; referred (on) 2WW earlier/last/previously/back/in
<Month|Year>; previously referred). Structural PRISM/EMIS referral
codes on the same encounter still fire so a real fresh referral is
not over-suppressed.

Pattern M - cancer treatment Read code coverage: The 2025-07-28
encounter recorded "Major: Mastectomy of right breast (XacLJ) (New
Episode)" and "Major: Biopsy of sentinel lymph node (XaF83) (New
Episode)" -- neither code was in `CANCER_TREATMENT_PROCEDURE_CODES`.
The fix expands the set to 19 codes spanning breast surgery (XacLJ,
XacLK, X40EC, 7H601, XaF83), bowel surgery (X20Y4, XaFB2, XaCvE,
XaZVW, 77132), prostate surgery (Y3c24), thyroid surgery (Xa8OS,
71102) and generic chemo/radiotherapy (8BAD0, 8BAD1, ZV58A). All
codes are definitive cancer treatment / staging procedures observed
in live primary-care encounters.

Cohort impact at the time of the investigation: 5 encounters matched
Pattern K, 1 matched Pattern L, 5 matched the breast-specific Pattern
M, and 106 completed cancer episodes had no `diagnosis_date` and/or
no `treatment_started` milestone. The three fixes together remove the
underlying causes for the bulk of those 106 cases.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| Design Input | DI-LEO-AI-215 | approved | Pattern K - hard problem-list diagnosis evidence (malignancy Read code OR malignancy term on a Major:/Problem: line OR active-cancer-care code) overrides the DI-LEO-AI-145 same-encounter referral gate so confirmed-cancer additions still fire diagnosis_confirmed when the same encounter raises the 2WW |
| Design Output | DO-LEO-AI-212 | draft | `find_malignancy_code_in_problem_line` strict helper in `libs/domains/code_inventories.py` + `_has_hard_dx_evidence` override gate inside `_classify_text_encounters` (`anchor_detector.py`) |
| Risk | R-LEO-AI-202 | mitigated | Confirmed cancer diagnosis silently dropped when GP records the diagnosis on the problem list at the same encounter as the 2WW referral (cohort baseline: 106 completed cancer episodes with no `diagnosis_date`) |
| Verification Test | VT-LEO-AI-207 | passed | Pattern K - same-encounter referral + Major:/Problem: malignancy code emits diagnosis; active-care code overrides; DI-LEO-AI-145 trap preserved on bare suspected-cancer text; non-referral diagnosis path unchanged (4/4) |
| Design Input | DI-LEO-AI-216 | approved | Pattern L - extend `_RE_NARRATIVE_REFERRAL_REFERENCE` with five retrospective self-narration shapes ("Referred by me on 2ww earlier this year", "I referred her last month", "we referred him in Jan", "GP referred via 2WW back in March 2024", "previously referred") so cancer-care-review notes that narrate the original referral do not open phantom EpisodeOfCare nodes |
| Design Output | DO-LEO-AI-213 | draft | `_RE_NARRATIVE_REFERRAL_REFERENCE` alternation extension in `services/analysis_worker/app/analyzers/anchor_detector.py` |
| Risk | R-LEO-AI-203 | mitigated | Self-narration of a prior referral inside a follow-up note opens a fresh phantom EpisodeOfCare and fragments the patient pathway (patient 4802892365 cancer-care-review created phantom episode `47c987c92e50e545` six months after the real referral) |
| Verification Test | VT-LEO-AI-208 | passed | Pattern L - 5 narrative shapes match + structural fresh referral still fires (no over-suppression) + end-to-end suppression on patient 4802892365 cancer-care-review encounter (7/7) |
| Design Input | DI-LEO-AI-217 | approved | Pattern M - expand `CANCER_TREATMENT_PROCEDURE_CODES` with 17 definitive cancer treatment / staging Read codes (breast: XacLJ, XacLK, X40EC, 7H601, XaF83; bowel: X20Y4, XaFB2, XaCvE, XaZVW, 77132; prostate: Y3c24; thyroid: Xa8OS, 71102; chemo/radio: 8BAD0, 8BAD1, ZV58A) so `treatment_started` fires when these codes appear in a post-referral encounter |
| Design Output | DO-LEO-AI-214 | draft | `CANCER_TREATMENT_PROCEDURE_CODES` expansion in `libs/domains/code_inventories.py` (data-only; no detector logic change so existing pre-referral / family-history guards continue to suppress treatment emission outside a confirmed cancer context) |
| Risk | R-LEO-AI-204 | mitigated | Cancer treatment milestone silently absent because surgery Read code (mastectomy, prostatectomy, hemicolectomy, etc.) is missing from `CANCER_TREATMENT_PROCEDURE_CODES` (cohort baseline: 5 breast-specific encounters and 106 completed cancer episodes with no `treatment_started` milestone) |
| Verification Test | VT-LEO-AI-209 | passed | Pattern M - 17-code inventory membership + legacy preservation + helper resolves XacLJ + end-to-end `treatment_started` emission on patient 4802892365 mastectomy and a sibling anterior-resection case (8/8) |
| Design Input | DI-LEO-AI-225 | approved | Pattern N5 - off-pathway non-cancer Problem-header guard. New helper `encounter_problem_is_off_pathway()` in `libs/domains/code_inventories.py` (regexes `_PROBLEM_HEADER_RX`, `_PROBLEM_HEADER_CANCER_TOKEN_RX`, `_OFF_PATHWAY_PROBLEM_RX`); the Pattern G `care_obstruction` emission gate in `services/analysis_worker/app/analyzers/anchor_detector.py` is tightened to AND on `not encounter_problem_is_off_pathway(text)` so routine off-pathway primary-care encounters (foreign travel, vaccination, repeat / acute / new prescription, medication review, hot flushes, sick note / MED3 / fit note, failed encounter, telephone consultation, administration, summary care record) with incidental cancer mentions never emit a phantom `care_obstruction`. Re-instated at fresh ID DI-LEO-AI-225 because original placeholder DI-LEO-AI-219 was overwritten by gold-editor (UN-LEO-AI-088) artefacts in commit 2067a5f. |
| Design Output | DO-LEO-AI-222 | approved | `encounter_problem_is_off_pathway()` helper + supporting regexes in `libs/domains/code_inventories.py`; `care_obstruction` emission gate update in `services/analysis_worker/app/analyzers/anchor_detector.py`; verification cases in `tests/test_pattern_n5_off_pathway_guard.py`. (Re-instated at fresh ID; original DO-LEO-AI-216 was overwritten in commit 2067a5f.) |
| Risk | R-LEO-AI-209 | mitigated | Routine off-pathway primary-care encounter (foreign travel, vaccination, repeat prescription, sick note, hot flushes) with an incidental cancer mention emits a phantom `care_obstruction` milestone on the patient's cancer EpisodeOfCare (patient 4802892365 2025-07-01 MMR / Mexico travel-vaccine encounter matched `_RE_CARE_OBSTRUCTION` on `unable to attend` and emitted a phantom obstruction on the breast pathway). (Re-instated at fresh ID; original R-LEO-AI-206 was overwritten in commit 2067a5f.) |
| Verification Test | VT-LEO-AI-217 | passed | Pattern N5 - 14/14 cases pass via `python -m pytest tests/test_pattern_n5_off_pathway_guard.py -v` (10 helper unit cases + 4 integration cases through `_classify_text_encounters`; covers canonical 4802892365 2025-07-01 zero-emission, repeat-medication zero-emission, genuine cancer-pathway refusal still fires, clinic-letter without Problem header still fires; 231 passed across the regression sweep). (Re-instated at fresh ID; original VT-LEO-AI-211 was overwritten in commit 2067a5f.) |
| Design Input | DI-LEO-AI-224 | approved | Pattern N3 - structured-form-field restatement guard. New helpers `_extract_form_field_dates()` and `encounter_restates_past_event(text, encounter_date, lookback_days=14)` in `libs/domains/code_inventories.py` parse five date formats (DD MMM YYYY, DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, ISO YYYY-MM-DD) on Field-shape lines (lines containing `:`). The Pattern C+D text_generic referral suppression block in `services/analysis_worker/app/analyzers/anchor_detector.py` is extended with the new restatement flag (overrides the structural-evidence override). The first_seen emission gate (including the specialist-clinic Read code branch) is wrapped with the same guard so XaPyQ `Seen in 2WW Clinic?:` proforma updates do not double-fire first_seen weeks after the real clinic visit. Inert for prose without Field shape (Pattern L / DI-LEO-AI-216 owns narrative-referral suppression). |
| Design Output | DO-LEO-AI-221 | approved | `_extract_form_field_dates()` + `encounter_restates_past_event()` helpers and date regexes in `libs/domains/code_inventories.py`; suppression-flag wiring on the text_generic referral block and first_seen emission wrap in `services/analysis_worker/app/analyzers/anchor_detector.py`; verification cases in `tests/test_pattern_n3_form_field_restatement_guard.py` |
| Risk | R-LEO-AI-208 | mitigated | Receptionist-driven 2WW proforma update on a date later than the event the field describes creates duplicate referral / first_seen milestones on the patient's cancer EpisodeOfCare. Patient 4802892365 2025-05-13 (`Date of First outpatient appointment: 07 Apr 2025`) emitted a fresh text_generic referral; 2025-06-10 (`Seen in 2WW Clinic?: ... 28 Apr 2025`) emitted a duplicate first_seen via the XaPyQ specialist-clinic Read code. Inflates time-to-first-seen and referral-count KPIs. |
| Verification Test | VT-LEO-AI-216 | passed | Pattern N3 - 21/21 cases pass via `python -m pytest tests/test_pattern_n3_form_field_restatement_guard.py -v` (8 extractor unit cases covering all five date formats, colon-required shape, invalid-date rejection, multi-date lines; 8 guard-predicate cases covering the canonical 4802892365 2025-05-13 and 2025-06-10 restatements, the 14-day lookback edge, prose-without-colon, empty input, malformed encounter date, and the lookback_days parameter; 5 integration cases through `_classify_text_encounters` covering zero-referral on the canonical 2025-05-13 row, zero-first_seen on the canonical 2025-06-10 row, and three no-over-suppression sanity cases; 231 passed across the regression sweep) |
| Design Input | DI-LEO-AI-401 | approved | Pattern N1 - no-anchor episode rejection. New helper `encounter_diagnosis_is_narrative_restatement(text)` in `libs/domains/code_inventories.py` (regexes `_SICK_NOTE_RX` for eMED3 / MED3 / fit note / not fit for work / unfit for work / fitness for work / sickness certificate; `_KNOWN_CANCER_RESTATEMENT_RX` for "known X cancer" / "history of X carcinoma" / "PMHx history of X ca" / "previously diagnosed with X cancer" / post-treatment recovery shapes; site vocabulary mirrors `_PROBLEM_HEADER_CANCER_TOKEN_RX`). The diagnosis_confirmed emission path in `services/analysis_worker/app/analyzers/anchor_detector.py` tags anchors with `is_narrative_restatement: True` when the helper returns True. `_build_diagnosis_led_groups` in `services/analysis_worker/app/analyzers/episode_builder/_grouping.py` rejects floating diagnosis-led groups whose anchors are ALL tagged. Inert when at least one anchor is untagged or when the group has claimed a referral (referral-attached groups always materialise). |
| Design Output | DO-LEO-AI-401 | approved | `encounter_diagnosis_is_narrative_restatement()` helper + `_SICK_NOTE_RX` and `_KNOWN_CANCER_RESTATEMENT_RX` in `libs/domains/code_inventories.py`; diagnosis_confirmed tagging in `services/analysis_worker/app/analyzers/anchor_detector.py`; floating-group rejection filter in `services/analysis_worker/app/analyzers/episode_builder/_grouping.py`; verification cases in `tests/test_pattern_n1_no_anchor_episode_rejection.py` |
| Risk | R-LEO-AI-401 | mitigated | A routine sick note (eMED3 / fit note) or "known X cancer" narrative restates an existing cancer diagnosis on an encounter with no referral within the diagnosis-claim lookback window, causing the episode builder to materialise a phantom EpisodeOfCare built entirely from restatement text. Patient 4802892365 phantom episode 862a306e1ee82616 was built from the 2025-09-24 cancer-care-review (Pattern K firing on problem-list malignancy code) and the 2025-12-06 eMED3 sick-note "not fit for work ... known breast ca" -- both pure restatements of the lobular carcinoma already recorded under episode 1ecfb55618c2a6d2. |
| Verification Test | VT-LEO-AI-401 | passed | Pattern N1 - 24/25 cases pass (1 conditionally skipped) via `python -m pytest tests/test_pattern_n1_no_anchor_episode_rejection.py -v` (17 helper unit cases covering 5 sick-note shapes, 7 known-cancer narrative shapes, 5 INERT cases including fresh diagnosis, 2WW referral, routine BP check, pharmacist failed-encounter alone; 3 integration cases through `_classify_text_encounters` covering the canonical 4802892365 2025-09-24 cancer-care-review tagging, fresh diagnosis NOT tagged, and the conditional sick-note tagging case; 5 integration cases through `_build_diagnosis_led_groups` covering all-restatement floating-group rejection, mixed-anchor preservation, no-restatement preservation, referral-attached preservation, and empty inputs; 152 passed across the regression sweep over N1, N3, N5, episode_builder, episode_duplicate_resolver, first_seen_milestone, open_episode_diagnosis_rescue) |
| Design Input | DI-LEO-AI-402 | approved | Pattern N4 - cancer-care-review restatement guard. New helpers `encounter_has_new_episode_marker(text)` (regex `_NEW_EPISODE_MARKER_RX` for "(New Episode)" / "newly diagnosed" / "new diagnosis of" / "diagnosis confirmed today" / "first presentation of" / "new presentation of") and `encounter_is_cancer_care_review_restatement(text)` (regex `_CANCER_CARE_REVIEW_RX` for "cancer (care) review" plus the existing N1 `_KNOWN_CANCER_RESTATEMENT_RX`, gated INERT by the new-episode-marker exception) added to `libs/domains/code_inventories.py`. The `_classify_text_encounters` `has_cancer and has_confirmed` branch in `services/analysis_worker/app/analyzers/anchor_detector.py` gains a `_dx_cancer_review_blocked` guard that suppresses the diagnosis_confirmed anchor entirely when the helper fires. N4 sits one layer deeper than N1 (which only filters floating restatement-only groups) - it stops phantom diagnosis_confirmed milestones from polluting the timeline of REAL referral-anchored episodes (e.g. patient 4802892365 episode 1ecfb55618c2a6d2's 2025-09-24 phantom). Sick-note shape is deliberately NOT a trigger - N1 floating-group filter remains the safety net. |
| Design Output | DO-LEO-AI-402 | approved | `encounter_has_new_episode_marker()`, `encounter_is_cancer_care_review_restatement()` helpers + `_CANCER_CARE_REVIEW_RX` and `_NEW_EPISODE_MARKER_RX` in `libs/domains/code_inventories.py`; `_dx_cancer_review_blocked` guard wired into the `has_cancer and has_confirmed` emission branch in `services/analysis_worker/app/analyzers/anchor_detector.py`; verification cases in `tests/test_pattern_n4_cancer_care_review_restatement_guard.py` |
| Risk | R-LEO-AI-402 | mitigated | A routine annual cancer-care-review encounter restates an existing cancer diagnosis on a patient with a real referral-anchored cancer episode, causing Pattern K paths to emit a phantom diagnosis_confirmed anchor that attaches to the real episode timeline (e.g. patient 4802892365's real episode 1ecfb55618c2a6d2 received a phantom 2025-09-24 diagnosis_confirmed milestone five months after the real 2025-05-19 fresh diagnosis and two months after treatment_started). Causes reviewer disengagement, incorrect pathway-stage classification, inflated diagnosis-count analytics. N1 cannot help here because the restatement attaches to a real referral-anchored episode rather than forming a floating group. |
| Verification Test | VT-LEO-AI-402 | passed | Pattern N4 - 33/33 cases pass via `python -m pytest tests/test_pattern_n4_cancer_care_review_restatement_guard.py -v` (10 cancer-care-review-restatement helper unit cases; 5 inert helper cases including 2WW referral and sick-note-alone; 3 new-episode-marker exception cases; 5 `encounter_has_new_episode_marker` unit cases; 4 anchor-detector suppression integration cases including the canonical 4802892365 2025-09-24 phantom; 5 fresh-diagnosis-NOT-suppressed safety cases including the new-episode-marker exception, the newly-diagnosed phrase exception, the 2WW referral and the routine repeat prescription; 1 N4-precedence-over-N1 case). 203 passed across the broad regression sweep over N1, N3, N4, N5, episode_builder, episode_duplicate_resolver, first_seen_milestone, open_episode_diagnosis_rescue and the patient-4802892365 pattern tests. Cohort wipe-and-rebuild: total EpisodeOfCare 248 -> 244 (delta -4); patient 4802892365 phantom 2025-09-24 diagnosis_confirmed eliminated. |
| User Need | UN-LEO-AI-087 | approved | After signing in I must reach the LEO application immediately and never see a stale loading spinner cached by Cloudflare or the Next.js Full Route Cache |
| Design Input | DI-LEO-AI-218 | draft | UI shell SSR session bootstrap + cache strategy: root layout exports `dynamic="force-dynamic"`, `revalidate=0`, `fetchCache="force-no-store"` and awaits `fetchInitialSession()` to resolve the session on the server before any HTML is sent; AuthProvider hydrates straight to `authenticated`/`unauthenticated` from the server-resolved session; `/auth/login` and `/auth/callback` route handlers continue to set `Cache-Control: no-store` on every response so Cloudflare cannot cache the OAuth round-trip |
| Design Output | DO-LEO-AI-215 | approved | `services/ui/src/lib/serverSession.ts` (`fetchInitialSession`), `services/ui/src/app/layout.tsx` (force-dynamic + SSR bootstrap), `services/ui/src/lib/authContext.tsx` (`AuthProvider` accepts `initialSession`), `services/ui/src/components/AuthProviderWrapper.tsx` (server -> client forwarding), `services/ui/src/app/auth/login/route.ts` + `auth/callback/route.ts` (Cache-Control: no-store) |
| Risk | R-LEO-AI-205 | mitigated | Stale prerendered HTML served from Cloudflare or the Next.js Full Route Cache leaves authenticated users staring at a permanent loading spinner instead of the LEO application |
| Verification Test | VT-LEO-AI-210 | passed | UI shell SSR session bootstrap and cache strategy - 5/5 jest cases pass: AuthProvider hydrates to authenticated/unauthenticated from initialSession (never loading); background refetch does not regress; layout.tsx static-source contains force-dynamic + revalidate=0 + fetchInitialSession; auth/login + auth/callback contain Cache-Control: no-store |
| Design Input | DI-LEO-AI-229 | approved | Inter-service session namespace consistency (UN-LEO-AI-087): every backend service that calls `libs/redis_client/session.py::load_session` or `services/api/app/services/session_store.py::load_session` SHALL resolve the same Redis key namespace per environment; deployed configuration SHALL set `SESSION_KEY_NAMESPACE` explicitly on every backend container so namespace resolution is independent of which other env vars (`FRONTEND_URL`, `AUTH_REDIRECT_URI`, `ENVIRONMENT`, `APP_ENV`, `LEO_ENV`) reach which service. |
| Design Output | DO-LEO-AI-224 | approved | `infra/bicep/modules/container-apps.bicep` declares `sessionKeyNamespace` (split of `frontendUrl` host first label) and adds `{ name: 'SESSION_KEY_NAMESPACE', value: sessionKeyNamespace }` to `sharedEnv`; both Python namespace resolvers (`libs/redis_client/session.py` + `services/api/app/services/session_store.py`) follow the identical precedence chain; hot-fix `az containerapp update --set-env-vars SESSION_KEY_NAMESPACE=leo-ai-audit` applied to all 8 backend container apps in leo-ai-dev. |
| Risk | R-LEO-AI-210 | mitigated | Session namespace drift between core-api and downstream services causes a silent post-login redirect loop. core-api wrote sessions to one Redis namespace; analytics-api / fhir-api / terminology-api / training-worker / pipeline-worker / research-worker / model-inference looked them up in another and returned 401 on every `/api/proxy/*` call; the UI auth interceptor treated each 401 as session expiry and bounced the user to `/auth/login`. |
| Verification Test | VT-LEO-AI-217 | passed | Inter-service session namespace parity - 8/8 cases pass via `python3 -m pytest tests/test_session_namespace_parity.py -v`: explicit SESSION_KEY_NAMESPACE wins on both modules; ENVIRONMENT/APP_ENV/LEO_ENV fallback parity (parametrized x3); FRONTEND_URL host first-label parity; scheme-less AUTH_REDIRECT_URI parity; total fallback to "local"; container-apps.bicep static-source check confirms SESSION_KEY_NAMESPACE in sharedEnv bound to sessionKeyNamespace variable. |
| User Need | UN-LEO-AI-088 | approved | Reviewers must be able to edit codes on any encounter (dry-run row, candidate, search hit, live encounter) using one editor that always feeds the model. The dialog must save with surface-appropriate semantics: gold-only for /admin/training and /admin/console; dual save (live :DOCUMENTS + gold mirror) for /care/patients and /care/encounters. PHI must never enter the gold copy. |
| Design Input | DI-LEO-AI-219 | approved | Shared GoldLabelEditorDialog component (UN-LEO-AI-088): re-export of GoldLabelDetailDialog under stable name from `services/ui/src/components/gold-editor/`; optional `saveMode`/`entitySaver`/`onAfterSave`/`headerChrome` props with safe defaults so the candidates tab is unchanged; dual-save warning banner gated on `saveMode='dual'`; barrel surfaces `GoldLabelEditorDialog`, `useDualSaveAdapter`, `createGoldLabelFromDryRun`, `createGoldLabelFromEncounter`, `syncCodedLinksFromGold`, `patchGoldLabelEntities`, and shared types (`SavedGoldEntity`, `GoldDialogSaveMode`, `GoldDialogEntitySaver`, `DualSaveEncounterContext`). |
| Design Input | DI-LEO-AI-220 | approved | POST /training/gold-labels/from-encounter (UN-LEO-AI-088): server-side de-id via `deidentify_text(..., ner=True)`; span re-anchoring of live `:DOCUMENTS`/CodedLinks via `find_span`; idempotent TrainingCandidate keyed by sha256(de-id text); upsert GoldLabel; returns full GoldLabel + `baseline_concept_ids` (for optimistic concurrency) + `dropped_link_count` so reviewers see when re-anchoring lost an entity. |
| Design Input | DI-LEO-AI-221 | approved | POST /patients/{patient_id}/encounters/{encounter_id}/coded-links/sync-from-gold (UN-LEO-AI-088): optimistic concurrency by concept_id set (HTTP 409 on baseline drift); transactional add/remove/update via `PatientGraphWriter.upsert_semantic_links`/`delete_links`; whole-array gold mirror via `UPDATE_GOLD_LABEL_ENTITIES`; body_site_concept_id/body_site_term embedded into `modifiers` JSON since `_upsert_query` does not surface body_site directly. |
| Design Input | DI-LEO-AI-222 | approved | EvaluateStage inline mount (UN-LEO-AI-088): /admin/console Evaluate tab opens the shared dialog above the dry-run table (no `window.open`, no `router.push`); `POST /training/candidates/from-dry-run` extended to return a full `gold_label` payload so the dialog seeds without a second round trip; `saveMode='gold'`; legacy `/gold-dataset?labelId=` deep link still works for direct URLs. |
| Design Input | DI-LEO-AI-223 | approved | /care surfaces consume the shared dialog (UN-LEO-AI-088). `/care/patients` `EncounterCard` mounts the shared dialog in `saveMode='dual'` via `useDualSaveAdapter`. `/care/encounters` `EncounterPreviewDialog` opens as a read-only preview that renders the encounter text from `item.text` without any backend call on open and highlights search-query and `match_rationale` terms via `<mark>`; an explicit "Edit codes" footer button seeds via `createGoldLabelFromEncounter` and mounts the shared dialog in `saveMode='dual'` with rationale forwarded through `headerChrome`; seed failures keep the preview open with an inline error so the encounter text stays readable. Legacy `/patients/{id}/encounters/{eid}` and `/patients/{id}/encounters/view/{eid}` routes redirect to `/care/patients?patient={id}&tab=encounters&encounter={eid}`; `EncounterCodedView` retired. |
| Design Output | DO-LEO-AI-216 | approved | Shared GoldLabelEditorDialog module: `services/ui/src/components/gold-editor/{GoldLabelEditorDialog.tsx,index.ts,types.ts,api.ts,useDualSaveAdapter.ts}` + extended `services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx` props (`saveMode`/`entitySaver`/`onAfterSave`/`headerChrome`) and conditional dual-save banner. |
| Design Output | DO-LEO-AI-217 | approved | from-encounter endpoint in `services/api/app/routers/training.py` (`EncounterGoldLabelRequest`, `_ner_label_for_semantic_tag`, `_sanitise_live_links`, `gold_label_from_encounter`); reuses `deidentify_text` and `find_span`; idempotent candidate upsert with org/site scope. |
| Design Output | DO-LEO-AI-218 | approved | sync-from-gold endpoint in `services/api/app/routers/patients.py` (`SyncCodedLinksFromGoldRequest`, `_build_link_payload_from_gold_entity`, `_list_baseline_concept_ids`, `sync_coded_links_from_gold`); reuses `PatientGraphWriter` for transactional CodedLink CRUD; mirrors entity array to GoldLabel via `UPDATE_GOLD_LABEL_ENTITIES`. |
| Design Output | DO-LEO-AI-219 | approved | EvaluateStage inline mount: `services/ui/src/components/console/EvaluateStage.tsx` mounts `GoldLabelEditorDialog` keyed on `goldEditorTarget?.label_id`; per-row "Open in gold editor" `IconButton` POSTs to `/api/training/candidates/from-dry-run` and seeds the dialog from `data.gold_label`; per-row error banner; `services/api/app/routers/training.py` `candidate_from_dry_run` returns the full GoldLabel from `GET_GOLD_LABEL_BY_ID`. |
| Design Output | DO-LEO-AI-220 | approved | /care surfaces consume the shared dialog: `services/ui/src/components/mission-control/EncounterCard.tsx` (Edit codes -> dual-save dialog), `EncounterTextTab.tsx` (handler wiring), `EncounterMissionControl.tsx` (no longer prefetches coded links for preview; passes `onCodingChanged`), `EncounterPreviewDialog.tsx` (rewritten as a thin wrapper around the shared dialog with `headerChrome` for match rationale), legacy `/patients/{id}/encounters/{eid}` + `/patients/{id}/encounters/view/{eid}` routes replaced with `redirect()`s, `EncounterCodedView.tsx` deleted. |
| Risk | R-LEO-AI-206 | mitigated | Reviewer overwrites live encounter codes from the dual-save editor (concurrent pipeline write or peer reviewer). Mitigated by HTTP 409 optimistic concurrency on the baseline concept_id set, dual-save warning banner in the dialog, and `PatientGraphWriter` audit trail. Verified by VT-LEO-AI-212. |
| Risk | R-LEO-AI-207 | mitigated | De-identification re-anchoring drops or shifts gold entities, training the model on a corrupted version of the reviewer's correction. Mitigated by server-side `dropped_link_count` surfaced to the reviewer, whole-array overwrite contract on the gold mirror, and idempotent `candidate_id` keyed by sha256(de-id text). Verified by VT-LEO-AI-211 + VT-LEO-AI-212. |
| Verification Test | VT-LEO-AI-211 | passed | from-encounter endpoint - 6/6 pytest cases pass: happy path (de-id + re-anchoring + idempotent candidate upsert + GoldLabel returned), idempotent re-call (same candidate_id), dropped link accounting when re-anchoring fails, empty-text 400, missing-encounter 404, semantic-tag normalisation fallback. |
| Verification Test | VT-LEO-AI-212 | passed | sync-from-gold endpoint - 6/6 pytest cases pass: happy path (add/remove/update via PatientGraphWriter + GoldLabel mirror), 409 on baseline concept_id drift, empty-entities removes all live links, no-concept-id entries skipped, empty-label-id 422, missing-gold-label 502 on mirror failure. |
| Verification Test | VT-LEO-AI-213 | passed | Shared GoldLabelEditorDialog - 9/9 jest static-source cases pass: re-export of GoldLabelDetailDialog under stable name, plumbing props with safe defaults (saveMode/entitySaver/onAfterSave/headerChrome), persist branch selection, dual-save banner gating, barrel surface (api/types/useDualSaveAdapter), shared types compile, API helpers shape, useDualSaveAdapter advances baseline after each save. |
| Verification Test | VT-LEO-AI-214 | passed | EncounterPreviewDialog - 8/8 jest static-source cases pass: shared editor imports from @/components/gold-editor, read-only preview with no API call on open, on-demand 'Edit codes' button that seeds via `createGoldLabelFromEncounter` and mounts saveMode='dual' with `useDualSaveAdapter`, headerChrome rationale forwarding, search-query + match_rationale highlight via `<mark>` (`encounter-preview-highlight`), inline seed-failure error that does not hide the encounter text, GoldLabelDetailDialog headerChrome support, and host wiring (searchQuery + onCodingChanged refresh, no coded-links prefetch). |
| Verification Test | VT-LEO-AI-215 | passed | EvaluateStage inline mount - 7/7 jest static-source cases pass: imports IconButton + EditNoteIcon, no `window.open` and no `useRouter`, aria-label="Open in gold editor" on both row blocks, from-dry-run POST + gold_label seed wiring, shared dialog mount with saveMode='gold' keyed on label_id, IconButton disabled guards (in-flight + empty text), legacy /gold-dataset?labelId deep link preserved (Suspense + handledDeepLinkRef). |
| User Need | UN-LEO-AI-096 | approved | Reviewers see one consistent encounter row + search experience across `/care/encounters`, the `/care/patients` side drawer, and the `/admin/training` Candidates (dry-run) queue, so muscle memory transfers between surfaces. Dry-run row template is the visual template; patient-drawer amber `#fde68a` is the highlight token; dry-run search box (clear button + query-echoing empty state) is the search pattern. |
| Design Input | DI-LEO-AI-514 | approved | `/care/encounters` lifts the dry-run row template (`ReviewListCard` from `@leo/design-system`) and ships a unified `<HighlightedText>` primitive (UN-LEO-AI-096). Each row composes `tone` (`positive` when `coded_count >= 1`, `danger` on failed batch run, `warning` when matched but no codes, `neutral` otherwise), `chips` (match-type + `{n} coded` + status + up to 4 `match_rationale`, all sized to row), `meta` (en-GB short date + monospace patient id + match-strength bar), and `actions` (selection checkbox with `stopPropagation`). `EncounterSearchPanel` ships a clear (X) `endAdornment` IconButton when the query is non-empty; the empty state echoes the active query as `Nothing matches "<q>". Try different words.` New module `services/ui/src/components/mission-control/HighlightedText.tsx` exports `HighlightedText` + `collectHighlightTerms` (`#fde68a` amber, `MIN_HIGHLIGHT_LEN=3`, longest-first sort, case-insensitive) and is consumed by `EncounterPreviewDialog`, `EncounterCard`, and the new `EncounterResultsTable`; the orphan `highlightSearchMatches` helper in `encounterTextUtils.tsx` is removed. Pagination moves to MUI `Pagination` rendered below the list (the dry-run pattern). |
| Design Output | DO-LEO-AI-513 | draft | Implementation: `services/ui/src/components/mission-control/HighlightedText.tsx` (shared primitive); `services/ui/src/components/mission-control/EncounterResultsTable.tsx` rebuilt on `ReviewListCard` with `toneFor()`, `buildEncounterListItem()`, `rowMeta()`, `rowChips()`, `rowActions()` helpers; clear-button end-adornment + `data-testid="encounter-search-clear"` on `EncounterSearchPanel.tsx`; `EncounterMissionControl.tsx` forwards `searchQuery` and removes the duplicate host-level empty state; `EncounterPreviewDialog.tsx` and `EncounterCard.tsx` import the shared primitive (their inline copies removed); `encounterTextUtils.tsx` `highlightSearchMatches` retired. |
| Verification Test | VT-LEO-AI-512 | passed | EncounterResultsTable + shared HighlightedText - 8/8 jest static-source cases pass: shared `HighlightedText` contract (`#fde68a`, `MIN_HIGHLIGHT_LEN=3`, longest-first sort, `/gi` case-insensitive); `EncounterPreviewDialog` and `EncounterCard` import the shared primitive (no inline `collectHighlightTerms`/`HighlightedText`/`MIN_HIGHLIGHT_LEN` remain, no `highlightSearchMatches`); `EncounterResultsTable` imports `ReviewListCard` from `@leo/design-system` (no MUI Table/TableRow/TableHead remain) and exports `toneFor()` with the documented mapping (`failed -> danger`, `coded_count >= 1 -> positive`, `hasActiveQuery -> warning`); row title is `<HighlightedText text={text} terms={highlightTerms} />`; chips compose match-type + coded + status + `match_rationale.slice(0,4)`; selection checkbox lives in actions slot with `stopPropagation`; row activation calls `onOpenPreview`; search box renders `CloseIcon` end-adornment when `state.query` is truthy; empty state echoes the active query (`Nothing matches "..."`, `Try different words.`) and is gated on `rows.length === 0`. Full mission-control regression (135 tests across 14 suites) green. |
| Design Input | DI-LEO-AI-516 | approved | `/care/encounters` lifts the patient-drawer `EncounterTimelineScrubber` (DI-LEO-AI-179) onto the search-results surface (UN-LEO-AI-096). New module `services/ui/src/components/mission-control/EncounterResultsTimeline.tsx` adapts `EncounterListItem[]` to `ScrubberEncounter[]` (renaming `encounter_date` -> `date`, dropping rows whose date does not parse), passes empty `linkedEncounterIds` / `milestones` and null episode bounds, and renders nothing when fewer than 5 dated rows are loaded. `EncounterMissionControl` owns a controlled `timelineRange: { fromMs, toMs } | null` state, intersects the brush window into `filteredRows` alongside `bucketFilter` (BEFORE pagination), resets the brush on every fresh `loadAll()`, wires `activePreview?.encounter_id ?? null` into both `highlightedEncounterId` on the table AND `activeEncounterId` on the timeline, and routes timeline-bar clicks through `handleTimelineJump` -> `setActivePreview` so a histogram click opens the preview dialog. |
| Design Output | DO-LEO-AI-515 | draft | Implementation: new module `services/ui/src/components/mission-control/EncounterResultsTimeline.tsx` (default-exported wrapper with `useMemo` adapter, `MIN_DATED_ROWS=5` early-return null, controlled brush props passed straight through); `services/ui/src/components/mission-control/EncounterMissionControl.tsx` gains `timelineRange` state + `handleTimelineRangeChange` + `handleTimelineJump`, intersects the brush window into `filteredRows` alongside `bucketFilter`, resets the brush on every fresh `loadAll()`, and forwards `activePreview?.encounter_id ?? null` as both `highlightedEncounterId` and `activeEncounterId`. |
| Verification Test | VT-LEO-AI-515 | passed | EncounterResultsTimeline + host wiring - 8/8 jest static-source cases pass under jest 30 + ts-jest in 0.68s: wrapper module contract (default export, scrubber + ScrubberEncounter imports, `EMPTY_LINKED` (`new Set`) / `EMPTY_MILESTONES` / null episode bounds); adapter `useMemo` mapping `encounter_date` -> `date` with `Number.isFinite` guard; `MIN_DATED_ROWS = 5` early-return null; host `useState<{ fromMs: number; toMs: number } | null>(null)` + `setTimelineRange(null)` reset on load; `filteredRows` `useMemo` references both `bucketFilter` AND `timelineRange` and applies the timeline window to `encounter_date` BEFORE pagination; `highlightedEncounterId={activePreview?.encounter_id ?? null}` + `activeEncounterId={activePreview?.encounter_id ?? null}`; `handleTimelineJump` resolves the row via `rows.find(...)` and calls `setActivePreview(target)`; wrapper passes through `visibleFromMs` / `visibleToMs` / `onVisibleRangeChange` to the scrubber. Wider regression on encounter / mission-control suites: 143 tests across 15 suites, all green. |
| Design Input | DI-LEO-AI-520 | approved | Drawer encounter search (`/care/patients` Encounter text tab) lifts the deterministic part of the `/care/encounters` server query understanding (typo + synonym + match rationale) onto the client so the drawer matches the host vocabulary (UN-LEO-AI-096). New shared module `services/ui/src/components/mission-control/encounterRelevance.ts` mirrors the server's `_TYPO_MAP` / `_SYNONYM_MAP` / `_normalise_tokens` / `_expand_terms` / `feature_match_rationale` (pure TypeScript, no React imports so future surfaces -- dry-run candidates, gold-editor sentence search -- can reuse). `encounterFilters.applyCommonFilters` switches from a bare `text.toLowerCase().includes(query.toLowerCase())` to `hasAnyExpandedHit(text, expandSearchTerms(query))` so a query for "lump" also surfaces encounters mentioning "mass", "swelling", or "nodule". When the query expands and at least one hit term is found, `EncounterCard` renders an outlined chip row in the card header (max 4 chips, height 20, fontSize 0.65rem, `variant="outlined"`, `data-testid="encounter-card-match-rationale-chip"`) using the same chip token as the host `/care/encounters` row, and feeds `matchRationale.hitTerms` into `collectHighlightTerms(search, hitTerms)` so the amber `<HighlightedText>` paints synonyms. Synonym expansion does NOT affect coding behaviour -- only which encounters appear in the drawer list and which terms are highlighted. |
| Design Output | DO-LEO-AI-520 | draft | Implementation: new module `services/ui/src/components/mission-control/encounterRelevance.ts` exports `expandSearchTerms`, `computeMatchRationale`, `hasAnyExpandedHit`, and the `MatchRationale` interface; `encounterFilters.ts` imports the new helpers and rewires `applyCommonFilters`; `EncounterCard.tsx` computes `expandedTerms` + `matchRationale` via `useMemo`, conditionally renders a wrapped Box (`data-testid="encounter-card-match-rationale"`) containing up to 4 outlined Chip elements, and passes `matchRationale.hitTerms` into `collectHighlightTerms`. |
| Verification Test | VT-LEO-AI-519 | passed | encounterRelevance utility + applyCommonFilters rewire + EncounterCard chip integration - 8/8 jest static-source cases pass under jest 30 + ts-jest in 0.56s: shared module exports (`expandSearchTerms`, `computeMatchRationale`, `hasAnyExpandedHit`, `MatchRationale`); `TYPO_MAP` mirrors server (`breat -> breast`, `wight -> weight`, `lums -> lumps`, `tumor -> tumour`); `SYNONYM_MAP` mirrors server (`breast`, `lump`, `weight`, `loss`, `cough`, `bleeding` groups byte-for-byte); `normaliseTokens` applies `TYPO_MAP[tok] ?? tok` BEFORE the `MIN_TERM_LEN` filter; `expandSearchTerms` early-returns `[]` for blank input, declares `MAX_TERMS = 12` and `MAX_EXPANDED = MAX_TERMS * 3`, and slices/breaks accordingly; `computeMatchRationale` returns the 3-key shape, slices `hitTerms` at 8, and computes `termCoverage = hits.length / Math.max(1, expandedTerms.length)`; `applyCommonFilters` imports `expandSearchTerms` + `hasAnyExpandedHit` and no longer does a bare substring match; `EncounterCard` imports `computeMatchRationale` + `expandSearchTerms`, computes via `useMemo`, calls `collectHighlightTerms(search, matchRationale.hitTerms)`; the rationale chip row renders with `data-testid="encounter-card-match-rationale-chip"`, `variant="outlined"`, `height: 20`, `fontSize: "0.65rem"`, capped at 4 hit terms. Wider regression on encounter / mission-control / drawer suites: 151 tests across 16 suites, all green. |
| Design Input | DI-LEO-AI-523 | approved | The `/admin/training` Candidates / Verified gold / Synthetic gold sub-tabs (the dry-run review queue) lift the same shared `encounterRelevance.ts` vocabulary onto their `@leo/design-system ReviewListCard` rows so the third "encounter list with a search box" surface speaks the same vocabulary as `/care/encounters` and the `/care/patients` drawer (UN-LEO-AI-096). `CandidateReviewList` and `GoldLabelReviewList` accept a `search?: string` prop forwarded by `GoldDatasetPanel` (the panel's `debouncedSearch`), expand it once per render via `useMemo(() => expandSearchTerms(props.search))`, per-row compute `matchRationale = computeMatchRationale(text, expandedTerms)`, wrap the truncated row title in `<HighlightedText terms={collectHighlightTerms(search, hitTerms)} testId="candidate-row-highlight">`, and prepend an outlined chip row to the existing `chips:` slot capped at 4 hit terms (testid `candidate-row-match-rationale[-chip]`, `variant="outlined"`, `height: 20`, `fontSize: "0.65rem"`). The change is additive: blank queries / no expansion / no hits all fall back to the prior plain-string title and chip set with no behavioural change. |
| Design Output | DO-LEO-AI-523 | draft | Implementation: `services/ui/src/components/gold-dataset/CandidateReviewList.tsx` gains a `search?: string` prop, a memoised `expandedTerms`, a `renderRationaleChips` helper, and a `<HighlightedText>` row title; `services/ui/src/components/gold-dataset/GoldLabelReviewList.tsx` mirrors the same wiring for `item.text`; `services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx` passes `search={debouncedSearch}` to both review lists. Reuses the pure-TS `mission-control/encounterRelevance.ts` and `mission-control/HighlightedText.tsx` modules unchanged. |
| Verification Test | VT-LEO-AI-521 | passed | CandidateReviewList + GoldLabelReviewList shared highlighter + match rationale chips - 7/7 jest static-source cases pass under jest 30 + ts-jest in 0.53s: `CandidateReviewList` imports `computeMatchRationale` + `expandSearchTerms` + `MatchRationale` from `@/components/mission-control/encounterRelevance` and `HighlightedText` + `collectHighlightTerms` from `@/components/mission-control/HighlightedText`; exposes `search?: string` and memoises `expandedTerms` via `useMemo(() => expandSearchTerms(props.search))`; per-row computes `matchRationale = computeMatchRationale(candidate.text, expandedTerms)` and `highlightTerms = collectHighlightTerms(search, matchRationale.hitTerms)`; wraps the title in `<HighlightedText testId="candidate-row-highlight">` when `highlightTerms.length > 0`; `renderRationaleChips` returns null for empty input and otherwise renders a Box with `data-testid="candidate-row-match-rationale"` containing `hitTerms.slice(0, 4)` outlined Chips with `data-testid="candidate-row-match-rationale-chip"`, `height: 20`, `fontSize: "0.65rem"`; `GoldLabelReviewList` mirrors all of the above for `item.text`; `GoldDatasetPanel` passes `search={debouncedSearch}` on both `<CandidateReviewList>` and `<GoldLabelReviewList>`; the chip token (variant outlined, height 20, fontSize 0.65rem) matches the drawer's `encounter-card-match-rationale-chip` byte-for-byte. Wider regression sweep across all training-data / gold-dataset / gold-label / encounter / drawer / mission-control suites: 201 tests across 23 suites, all green. |
| Design Input | DI-LEO-AI-526 | approved | Server-side search term expansion for the dry-run review queue (UN-LEO-AI-096). `GET /api/training/candidates`, `GET /api/training/gold-labels`, and the dedupe helper SHALL expand the reviewer's free-text query using the SAME deterministic typo + synonym vocabulary as the `/care/encounters` host search before the cypher filter is applied so that a query for "lump" surfaces TrainingCandidate / GoldLabel rows whose text wrote "mass", "swelling", or "nodule" in the SAME single page. New `libs/search/term_expansion.py` holds the single source of truth for `TYPO_MAP` / `SYNONYM_MAP` / `normalise_tokens` / `expand_search_terms`; `services/analytics_api/app/services/encounter_query_understanding.py` is refactored to delegate to it so host search and dry-run cannot drift apart. `GET_TRAINING_CANDIDATES_PAGE` + `COUNT_TRAINING_CANDIDATES_PAGE` + `GET_GOLD_LABELS_PAGE` + `COUNT_GOLD_LABELS_PAGE` accept an optional `$terms` lower-case array and OR-match it against `toLower(c.text)` via `ANY(t IN $terms WHERE ...)` with a CASE fallback to the prior `$search` CONTAINS so existing callers stay byte-for-byte compatible. |
| Design Output | DO-LEO-AI-526 | draft | Implementation: new `libs/search/__init__.py` + `libs/search/term_expansion.py` (`TYPO_MAP`, `SYNONYM_MAP`, `normalise_tokens`, `expand_search_terms`); `libs/cypher/training_candidate_queries.py::GET_TRAINING_CANDIDATES_PAGE` + `COUNT_TRAINING_CANDIDATES_PAGE` and `libs/cypher/gold_label_queries.py::GET_GOLD_LABELS_PAGE` + `COUNT_GOLD_LABELS_PAGE` gain a `$terms` parameter with the `CASE` fallback; `services/api/app/routers/training.py` calls `expand_search_terms(search)` and forwards both `search` and `terms` on `list_training_candidates`, `list_gold_labels`, and `_fetch_dedupe_candidates`; `services/neo4j_mcp/tools/training.py` mirrors the wiring; `services/api/app/services/candidate_prune.py`, `services/api/app/routers/pipeline.py`, `services/pipeline_worker/app/main.py` pass `terms=[]` to the new signature without changing behaviour; `services/analytics_api/app/services/encounter_query_understanding.py` re-exports `_TYPO_MAP` / `_SYNONYM_MAP` from `libs.search.term_expansion` (single-object identity). |
| Verification Test | VT-LEO-AI-524 | passed | Server-side search term expansion for the dry-run review queue - 8/8 pytest cases pass via `pytest services/api/tests/test_training_search_term_expansion.py` in 4.33s: `expand_search_terms("breat lump")` returns `["breast","mammary","lump","mass","swelling","nodule"]` (typo correction before synonym expansion) and returns `[]` for `None` / `""` / `"   "`; `GET /training/candidates?search=lump` forwards `terms=["lump","mass","swelling","nodule"]` to BOTH `GET_TRAINING_CANDIDATES_PAGE` AND `COUNT_TRAINING_CANDIDATES_PAGE`; the no-search default request passes `terms=[]` and `search=None`; `GET /training/gold-labels?search=weight loss` forwards expanded terms (incl. `weight`, `loss`, `cachexia`) to both gold-label queries; both cypher strings contain the `ANY(t IN $terms WHERE toLower(...) CONTAINS t)` branch and a CASE fallback to `$search`; the analytics-layer `_TYPO_MAP` / `_SYNONYM_MAP` are the SAME Python objects as `libs.search.term_expansion.TYPO_MAP` / `SYNONYM_MAP` (single-source-of-truth identity check). |
| Design Input | DI-LEO-AI-527 | approved | "Apply to similar candidates" batch dialog renders shared `<HighlightedText>` titles + outlined match-rationale chip row using the same `encounterRelevance` vocabulary as DI-LEO-AI-520 / DI-LEO-AI-523 so the last "encounter list with a search box" surface speaks the same vocabulary as `/care/encounters`, the `/care/patients` drawer, and the dry-run review queue (UN-LEO-AI-096). `SimilarCandidatesBatch.tsx` accepts a `search?: string` prop forwarded by `GoldDatasetPanel.tsx` (the panel's `debouncedSearch`), expands it once per render via `useMemo(() => expandSearchTerms(search))`, per-row computes `matchRationale = computeMatchRationale(item.text, expandedTerms)` and `highlightTerms = collectHighlightTerms(search, hitTerms)`, conditionally wraps the truncated row text in `<HighlightedText testId="similar-candidate-row-highlight">`, and renders a Box (`data-testid="similar-candidate-row-match-rationale"`) of up to 4 outlined Chips (`data-testid="similar-candidate-row-match-rationale-chip"`, `variant="outlined"`, `height: 20`, `fontSize: "0.65rem"`). Additive: blank queries / no expansion / no hits all fall back to the prior plain text with no behavioural change. |
| Design Output | DO-LEO-AI-527 | draft | Implementation: `services/ui/src/components/gold-dataset/SimilarCandidatesBatch.tsx` adds `search?: string` to its `Props`, imports `computeMatchRationale` + `expandSearchTerms` from `@/components/mission-control/encounterRelevance` and `HighlightedText` + `collectHighlightTerms` from `@/components/mission-control/HighlightedText`, memoises `expandedTerms`, computes per-row rationale + highlights, and wraps the truncated title cell in a conditional `<HighlightedText>` followed by an outlined chip Box guarded by `showRationale = expandedTerms.length > 0 && matchRationale.hitTerms.length > 0`; `services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx` passes `search={debouncedSearch}` to `<SimilarCandidatesBatch>`. Reuses the pure-TS `mission-control/encounterRelevance.ts` and `mission-control/HighlightedText.tsx` modules unchanged. |
| Verification Test | VT-LEO-AI-525 | passed | Similar-candidates batch dialog highlighter + match rationale chips - 7/7 jest static-source cases pass under jest 30 + ts-jest in 0.52s: `SimilarCandidatesBatch` imports `computeMatchRationale` + `expandSearchTerms` from `@/components/mission-control/encounterRelevance` and `HighlightedText` + `collectHighlightTerms` from `@/components/mission-control/HighlightedText`; declares `search?: string` on `Props` and memoises `expandedTerms` via `useMemo(() => expandSearchTerms(search), [search])`; per-row computes `matchRationale = computeMatchRationale(item.text, expandedTerms)` and `highlightTerms = collectHighlightTerms(search, matchRationale.hitTerms)`; conditional `<HighlightedText testId="similar-candidate-row-highlight">`; rationale Box with `data-testid="similar-candidate-row-match-rationale"`, `slice(0, 4)`, chip `data-testid="similar-candidate-row-match-rationale-chip"`, `variant="outlined"`, height 20, fontSize 0.65rem; `showRationale` guard ensures empty / no-hit queries fall back to the prior plain text; `GoldDatasetPanel` forwards `search={debouncedSearch}` into `<SimilarCandidatesBatch>`. |
| User Need | UN-LEO-AI-089 | approved | Coding leads, finance teams, and downstream NHS payers need SNOMED-coded findings to be expressible as ICD-10 diagnoses and OPCS-4 procedures with their full hierarchy and human-readable titles, so the map targets surfaced in TermSearch / surface-forms / Coding Review are interpretable without leaving LEO. |
| Design Input | DI-LEO-AI-228 | approved | Ingest NHS ICD-10 5th Edition XML (TRUD item 259) into Neo4j as `(:Icd10Code {code, title, level, chapter, block, included_terms, excluded_terms, age_low, age_high, sex, edition, source})` plus `(:Icd10Code)-[:IS_A]->(:Icd10Code)` hierarchy edges. Streaming ClaML parser; MERGE on `code`; idempotent re-runs with title-drift detection. |
| Design Input | DI-LEO-AI-226 | approved | Ingest NHS OPCS-4 data files (TRUD item 119) into Neo4j as `(:OpcsCode {code, title, level, chapter, block, edition, source})` plus `(:OpcsCode)-[:IS_A]->(:OpcsCode)` hierarchy edges; extend `services/terminology/scripts/loaders/snomed_map.py` to load SNOMED -> OPCS-4 simple-map refset (id `1126491000000109`) as `(:Concept)-[:MAPS_TO_OPCS4]->(:OpcsCode)` and add explicit refset filtering to `load_simple_map` so OPCS-4 rows can no longer leak into `ReadCode` nodes. |
| Design Output | DO-LEO-AI-301 | approved | New `services/terminology/scripts/loaders/icd10_xml.py` (streaming ClaML parser + Neo4j writer); `Icd10Files` finder; `:Icd10Code(level)` index; phase 6 in `loaders/run_all.py`; `icd10` package (TRUD item 259, phase {6}) in `services/api/app/services/trud_sync.py` with new `icd10_codes` Neo4j count; API exposes `icd10_term` via `OPTIONAL MATCH (c)-[:MAPS_TO]->(ic:Icd10Code)` in `services/api/app/models/neo4j_schema.py`; UI surfaces title in TermSearch, surface-forms page, and the terminology settings page (new package card + stat tile). |
| Design Output | DO-LEO-AI-223 | approved | New `services/terminology/scripts/loaders/opcs4.py` (tab-delimited parser + chapter/block hierarchy builder); `Opcs4Files` finder; `:OpcsCode {code}` constraint and `:OpcsCode(level)` index; extension of `loaders/snomed_map.py` (`OPCS4_REFSET_ID`, `MERGE_OPCS4_MAP`, `load_opcs4_map`, mandatory `refset_filter` argument on `load_simple_map`); phase 7 in `loaders/run_all.py`; `opcs4` package (TRUD item 119, phase {7}) in `trud_sync.py` with new `opcs4_codes` and `opcs4_maps` Neo4j counts; API exposes `opcs4` and `opcs4_term` via `OPTIONAL MATCH (c)-[:MAPS_TO_OPCS4]->(op:OpcsCode)`; UI surfaces title in TermSearch, surface-forms page, and the terminology settings page. |
| Risk | R-LEO-AI-301 | mitigated | Stale, missing, or partially loaded ICD-10 / OPCS-4 reference data leads to bare codes or wrong human-readable titles being shown to clinicians and finance teams, causing miscoded discharges, payer disputes, and incorrect clinical interpretation. Mitigated by idempotent loaders with title-drift detection, package status + Neo4j counts visible in `/settings/terminology` (graceful degradation when missing), refset-id filtering on `load_simple_map` so OPCS-4 codes never leak into `ReadCode` nodes, and procedural quarterly TRUD freshness checks. |
| Verification Test | VT-LEO-AI-301 | passed | ICD-10 loader - 14/14 pytest cases pass via `python3 -m pytest tests/test_icd10_xml_loader.py -v`: code normalisation (dotted form), level classification (chapter/block/three_char/four_char/five_char), title extraction, included/excluded terms, age/sex constraints, IS_A hierarchy edges, idempotent re-runs, title-drift detection, batch-size flushing, empty-file resilience, malformed-XML resilience, age-range parsing edges, sex-coding edges, end-to-end load against synthetic ClaML fixture. Plus 6/6 jest static-source cases for the terminology page chrome and 4/4 jest static-source cases for ICD-10 title rendering in TermSearch + surface-forms. |
| Verification Test | VT-LEO-AI-302 | passed | OPCS-4 loader + SNOMED -> OPCS-4 map - 21/21 pytest cases pass via `python3 -m pytest tests/test_opcs4_loader.py tests/test_snomed_map_opcs4.py -v` covering OPCS-4 parser (code normalisation; chapter/block/three_char/four_char level classification; tab-delimited row streaming; chapter-name backfill; IS_A hierarchy edge construction; idempotent re-runs; empty-file and malformed-row resilience) and SNOMED -> OPCS-4 map (refset-id filter ensures only refset `1126491000000109` produces `MAPS_TO_OPCS4` edges; `load_simple_map(refset_filter=CTV3_REFSET_ID)` no longer leaks OPCS-4 rows into `ReadCode` nodes; idempotent re-runs; batch flushing; multi-refset RF2 input). Plus the shared 6/6 jest static-source cases for terminology page chrome and 4/4 jest static-source cases for OPCS-4 title rendering in TermSearch + surface-forms. |

### Haiku Episode Engine -- LLM-driven episode + milestone detection (April 2026)

Replaces the rule-based Pattern A..N episode-builder stack (DI/DO/Risk/VT
artefacts in the 2xx and 4xx ranges that anchored on regex / Read-code
heuristics) with a LangGraph chain of four LLM agents plus a deterministic
loader, idempotent writer, and provenance trace node. Synthetic reference
case `SYN-EE-001` is the canonical breast-cancer example used in every
prompt few-shot, fixture, and frozen-cohort baseline -- no real NHS numbers
are committed to source control or test definitions.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-090 | approved | Replace the rule-based episode detector with an LLM-driven engine that finds cancer episodes reliably, including patients with multiple episodes over time and patients with multi-site referrals that resolve to a single primary diagnosis (synthetic reference SYN-EE-001). |
| Design Input | DI-LEO-AI-500 | approved | Timeline loader -- de-noised encounter timeline with a 240-char trunk view (segmenter / classifier) and a 1200-char encounter_index (milestone extractor lookups). |
| Design Input | DI-LEO-AI-501 | approved | Segmenter agent (Haiku) -- splits the timeline into candidate episode windows with structured tool-call output and low-confidence flagging. |
| Design Input | DI-LEO-AI-502 | approved | Classifier agent (Haiku) -- labels each window cancer / multi_site / benign / non_cancer with a justification and confidence score; ties get needs_human_review=true. |
| Design Input | DI-LEO-AI-503 | approved | Milestone extractor agent (Haiku) -- finds canonical milestones with evidence quotes and explicitly avoids anchoring treatment_started on the SYN-EE-001 "Failed encounter" administrative task. |
| Design Input | DI-LEO-AI-504 | approved | Reconciler agent (Sonnet) -- merges overlapping windows that are actually one episode; surfaces low-confidence merges to HITL with merged_from audit trail. |
| Design Input | DI-LEO-AI-505 | approved | Provenance + idempotent writeback -- EpisodeEngineTrace per run captures model id, prompt version, token + latency totals, per-stage error containment; writer deletes existing EpisodeOfCare for the patient and rewrites with deterministic ids. |
| Design Output | DO-LEO-AI-500 | approved | services/analysis_worker/app/episode_engine/timeline_loader.py + schemas.py + state.py |
| Design Output | DO-LEO-AI-501 | approved | services/analysis_worker/app/episode_engine/agents/segmenter.py + libs/prompts/episode_engine/segmenter_v1.py + _shared.py (BREAST_REFERENCE_CASE / SYN-EE-001 few-shot) |
| Design Output | DO-LEO-AI-502 | approved | services/analysis_worker/app/episode_engine/agents/classifier.py + libs/prompts/episode_engine/classifier_v1.py |
| Design Output | DO-LEO-AI-503 | approved | services/analysis_worker/app/episode_engine/agents/milestone_extractor.py + libs/prompts/episode_engine/milestone_extractor_v1.py |
| Design Output | DO-LEO-AI-504 | approved | services/analysis_worker/app/episode_engine/agents/reconciler.py + libs/prompts/episode_engine/reconciler_v1.py + chain.py LangGraph wiring |
| Design Output | DO-LEO-AI-505 | approved | services/analysis_worker/app/episode_engine/{tracing,writer}.py + libs/pipeline_graph/subgraphs/episode_engine.py + registry/probe wiring |
| Risk | R-LEO-AI-500 | mitigated | Timeline loader drops critical encounter text (e.g. SYN-EE-001 "Failed encounter" or "(New Episode)" markers) (mitigated by dual-view loader + fixture-driven integration VT). |
| Risk | R-LEO-AI-501 | mitigated | Segmenter splits a single multi-site episode into multiple windows or fuses unrelated episodes (mitigated by reconciler stage + per-window low-confidence flags). |
| Risk | R-LEO-AI-502 | mitigated | Classifier mislabels a benign 2WW closure as cancer or vice versa (mitigated by required justification + confidence; ties marked needs_human_review). |
| Risk | R-LEO-AI-503 | mitigated | Milestone extractor anchors treatment_started on an administrative "Failed encounter" task instead of the real reconciliation or definitive surgery (mitigated by SYN-EE-001 reference case in the prompt + frozen-cohort regression VT). |
| Risk | R-LEO-AI-504 | mitigated | Reconciler over-merges and hides a true second cancer episode (mitigated by merged_from audit trail + reviewer split-merge in <=2 clicks). |
| Risk | R-LEO-AI-505 | mitigated | Provenance / writeback failure corrupts patient timeline OR loses cost / drift telemetry (mitigated by idempotent writer + error-contained tracing + EpisodeEngineTrace per run). |
| Verification Test | VT-LEO-AI-500 | passed | Timeline loader unit + synthetic-fixture VTs (`tests/episode_engine/test_timeline_loader.py`, `test_synthetic_fixture_loader.py`). |
| Verification Test | VT-LEO-AI-501 | passed | Segmenter agent unit VT with mocked LLM (`tests/episode_engine/test_segmenter_agent.py`). |
| Verification Test | VT-LEO-AI-502 | passed | Classifier agent unit VT with mocked LLM (`tests/episode_engine/test_classifier_agent.py`). |
| Verification Test | VT-LEO-AI-503 | passed | Milestone extractor unit VT with mocked LLM and the SYN-EE-001 anti-pattern (`tests/episode_engine/test_milestone_extractor_agent.py`). |
| Verification Test | VT-LEO-AI-504 | passed | Reconciler agent unit VT with mocked LLM (`tests/episode_engine/test_reconciler_agent.py`). |
| Verification Test | VT-LEO-AI-505 | passed | Idempotent writer VT (`tests/episode_engine/test_writer.py`). |
| Verification Test | VT-LEO-AI-506 | passed | Provenance / tracing VT -- trace ids, aggregation, persistence, error containment (`tests/episode_engine/test_tracing.py`). |
| Verification Test | VT-LEO-AI-507 | draft | Frozen-cohort regression on 20 synthetic patient ids (`SYN-EE-001..SYN-EE-020`); gated on `RUN_EPISODE_ENGINE_FROZEN_VT=1` + `secrets/episode_engine_cohort_map.json`; baseline.json keyed by synthetic id only. |
| Validation Test | VAL-LEO-AI-014 | draft | Reviewer-led clinical validation on synthetic + de-identified review cohort. SYN-EE-001 acceptance is blocking (must yield endocrine 2025-05-19 + surgery 2025-07-28; must not anchor treatment_started on the 2025-05-02 Failed encounter). |

Supersession: DI-LEO-AI-401 / DI-LEO-AI-402 / DI-LEO-AI-224 / DI-LEO-AI-225
and their DO/Risk/VT chains MUST be marked `superseded_by:
[DI-LEO-AI-500..505]` once the cutover lands (todo `supersede_dcs`).

---

## Universal LLM Cost Telemetry (April 2026)

Closes the observability gap where SBAR (and any other pipeline that
calls an LLM through the shared `invoke_llm_json` helper) wrote no
token counts and no `:AuditEvent {type:'PipelineRun'}`, leaving the
dashboard `LLMSpendPanel` and the per-tenant billing subsystem
under-counting AI spend.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-091 | draft | Platform admins can monitor LLM token usage and cost for every generation pipeline (coding, episode engine, SBAR). |
| Design Input | DI-LEO-AI-506 | draft | Universal LLM token + cost telemetry: `invoke_llm_json` extracts tokens; `LLMUsageRecorder` accumulates per-run via `contextvars`; SBAR orchestrator writes `Assessment.llm_usage_json` + a `:AuditEvent {type:'PipelineRun'}` matching the coding-pipeline wire format; `GET_PATIENT_LLM_SPEND` extended to UNION SBAR rows. |
| Design Output | DO-LEO-AI-506 | draft | `libs/llm_client/json_helper.py` token extraction + `libs/llm_client/usage_recorder.py` (`LLMUsageRecorder` + default tracking callback) + `services/pipeline_worker/app/services/sbar_orchestrator.py::_record_telemetry` + `libs/cypher/sbar_assessment_queries.py::SET_ASSESSMENT_USAGE` / `WRITE_SBAR_AUDIT_EVENT` + `libs/cypher/model_config_queries.py::GET_PATIENT_LLM_SPEND` UNION over `:Assessment`. |
| Risk | R-LEO-AI-506 | analyzed | Non-coding LLM pipelines write no cost telemetry, so per-tenant invoicing under-counts AI spend and prompt-version cost regressions go undetected (mitigated by routing every call through `invoke_llm_json` + `LLMUsageRecorder` + best-effort write at `FINALISE`). |
| Verification Test | VT-LEO-AI-508 | passed | 10/10 cases: token extraction (TC-001/002 + failed-call telemetry), recorder accumulation + concurrent isolation (TC-003/004 + ContextVar lifecycle + `to_audit_dict` shape), SBAR `Assessment.llm_usage_json` + `:AuditEvent {type:'PipelineRun'}` + telemetry-failure isolation (TC-005/006/007). |
| Design Input | DI-LEO-AI-515 | draft | Sync LLM entry-point telemetry: `LLMClient.converse` (Bedrock + Azure branches) and `providers.invoke_with_fallback` emit one `track_llm_usage` event per call -- success and failure paths -- forwarding `model_provider`, `model_name`, input / output / cache token counts, `latency_ms`, `agent_task` and `patient_id`. Adds new sync helper `track_llm_usage_sync`. Best-effort: a callback exception or missing usage object MUST NOT break the caller. Closes the audit gap exposed against `.cursor/rules/llm-cost-telemetry.mdc` for the ~14 sync caller surfaces (escalation, consensus, label_verifier, candidate_ai_first_pass, llm_extractor, training, _training_askleo, prompts, terminology, encounter_query_understanding, terminology_api/concepts, exclusion_detector, _extractor, fix_analyzer). |
| Design Output | DO-LEO-AI-514 | draft | `libs/llm_client/factory.py::LLMClient.converse` (timing, `agent_task` / `patient_id` kwargs, success + failure callback fire) + `libs/llm_client/factory.py::_fire_converse_tracking` + `libs/llm_client/providers.py::invoke_with_fallback` (per-branch timing, `extract_token_counts`, single tracking event per attempted provider with success / error tagging) + `libs/llm_client/providers.py::_fire_invoke_tracking` + `libs/llm_client/token_tracker.py::track_llm_usage_sync` (sync fire-and-forget that drains async callbacks via the running loop or `asyncio.run`). |
| Verification Test | VT-LEO-AI-513 | passed | 9/9 cases (TC-001 Bedrock success, TC-002 Azure success, TC-003 failure-path callback + re-raise, TC-004 callback-exception isolation, TC-005 `agent_task` / `patient_id` forwarding, TC-006 active `LLMUsageRecorder` accumulates two `converse` calls, TC-007 `invoke_with_fallback` primary-path single event, TC-008 fallback-path single event tagged `azure`, plus a `USE_AZURE_PRIMARY` bonus case). Pre-existing `tests/test_llm_providers.py` (16) + VT-LEO-AI-508 (10) suites pass with no regressions (62/62 across the combined run). |
| User Need | UN-LEO-AI-092 | approved | Platform admins can tune per-context SBAR Situation framing without engineering involvement, via `/admin/knowledge?tab=ai-instructions`. |
| Design Input | DI-LEO-AI-507 | approved | Per-context SBAR Situation framing snippets editable as `:PromptConfig` nodes. Each `SummarisationContext` value gets one `sbar_situation_context_<value>` v1 node with the events.py snippet as the seed text and a `[<Group>]` description prefix (Primary care / Secondary care / Statutory and social / Quality assurance). Runtime resolves Neo4j-first via `GET_PROMPT_BY_NAME` and falls back to the hardcoded dict on no-row / empty / raising sessions. Per-call cache caps a Situation to one Neo4j call per distinct context. AI Instructions categoriser groups rows by the description prefix. |
| Design Output | DO-LEO-AI-507 | draft | `scripts/seed_prompt_configs.py` (loop over `SummarisationContext` -> 34 PromptConfig entries) + `libs/sbar/source_resolver._situation_context_snippet` (Neo4j-first lookup + fallback + cache) + `libs/sbar/source_resolver.resolve_situation` (per-call cache threading) + `libs/sbar/events.SUMMARISATION_CONTEXT_GROUPS` (group mapping) + `services/ui/src/app/admin/prompts/page.tsx::categorise()` ([<Group>] parsing + `categoriseFromPrompt` wrapper) + `services/ui/src/components/sbar-playground/SummarisationContextSelect.tsx` (Acute -> Secondary care rename + 14 new options + mdt_discussion -> "MDT prep (primary care)"). |
| Risk | R-LEO-AI-507 | mitigated | An admin edits a per-context PromptConfig snippet (e.g. `sbar_situation_context_two_week_wait`) and removes safety-critical framing, causing the SBAR Situation prompt to omit the action the receiving clinician needs. Mitigated by the hardcoded fallback in `events.SUMMARISATION_CONTEXT_PROMPTS` (deletion / outage cannot regress the prompt to unframed), admin-only PromptConfig CRUD, INJECTION_GUARD on the base SBAR Situation prompt, and a procedural QA / clinical-lead sign-off step for high-stakes context wording (2WW, ED handover, palliative care MDT, SACT consent, MHA tribunal). |
| Verification Test | VT-LEO-AI-509 | passed | 8/8 cases (21/21 pytest + 11/11 jest): 34-member enum + group mapping (TC-001/002/003), `sbar_situation_context_*` seed parity with [<Group>] prefix (TC-002), source resolver Neo4j-first lookup honours admin edits (TC-003), fallback on None / no-row / empty / raising sessions (TC-004), per-call cache collapses repeat lookups (TC-005), UI Secondary-care rename + 4 groups + 34 options (TC-006), frontend / backend enum parity (TC-007), AI Instructions categoriser groups SBAR contexts by [<Group>] prefix (TC-008). |
| User Need | UN-LEO-AI-093 | approved | Clinical guideline authors can express a single rule criterion as a synonym set of equivalent SNOMED codes (e.g. `Smoker` matches `Cigarette smoker` or `Pipe smoker`), opt into descendant expansion per code, and explicitly exclude sub-codes that should not fire (e.g. `Trial of smoking`). |
| Design Input | DI-LEO-AI-508 | approved | `LogicCriterion` schema upgrade (Pydantic + TypeScript): `seeds: LogicSeed[]`, `excluded_concept_ids: string[]`, `primary_concept_id`. Each `LogicSeed` carries `snomed_concept_id` + `preferred_term` + `semantic_tag` + per-seed `include_descendants` + optional `distance_child` override. `model_validator` derives the legacy `snomed_concept_id` / `preferred_term` from the primary seed, rejects primary-not-in-seeds and rejects seed/exclusion overlap. Migration script `scripts/migrations/logic_criterion_synonym_set.py` upgrades persisted v2 rules in-place. |
| Design Input | DI-LEO-AI-509 | approved | Bitmap compiler `_compile_concept_leaf` (services/terminology_api/app/services/guideline_compiler.py) builds the union of every seed's IS_A closure (per-seed `include_descendants` + `distance_child`), subtracts `excluded_concept_ids`, and stores one bitmap per CONCEPT leaf via `BitmapStore.put_bitmap`. Echoes a sorted `seed_concept_ids` list onto the compiled tree so the evaluator can attribute hits without a reverse int->id lookup. Falls back to the primary seed when every closure is excluded. |
| Design Input | DI-LEO-AI-510 | approved | Evaluator + diagnose return per-leaf hit attribution: `matched_concept_ids` on every CONCEPT leaf in `_annotate_logic_tree` and a `matched_via: [{node_id, primary_concept_id, preferred_term, matched_concept_ids}]` array on every matched rule from `evaluate_patient`. SBAR formatter (`libs/sbar/assessment_formatter.py::_render_matched_via`) passes `matched_via` through into the rule snapshot and renders a "Matched on: ..." bullet (e.g. "Cigarette smoker (a kind of Smoker)") into the Assessment markdown. SBAR Recommendation prompt rule 13 instructs the LLM to name the specific match in plain English on first reference. |
| Design Input | DI-LEO-AI-511 | approved | UI: `SynonymChipEditor` popover (services/ui/src/app/admin/guidance/EditRuleDialog/SynonymChipEditor.tsx) for add/remove seeds, set primary, toggle `include_descendants` per seed, override `distance_child`, and search/manual-id exclude codes. Each seed row carries an inline `SeedDescendantsList` (services/ui/src/app/admin/guidance/EditRuleDialog/SeedDescendantsList.tsx, AC-007) that fetches `/api/terminology/concepts/{id}/descendants` on demand and lets the author audit and one-click block any unintended descendant before saving. `LogicTreeEditor` mounts the badge on every CONCEPT chip (`ConceptChipInline` + `ConceptNodeView`). `treeOps.ts` grows pure helpers (`addSeed`/`removeSeed`/`setPrimarySeed`/`toggleIncludeDescendants`/`setSeedDistance`/`addExcluded`/`removeExcluded`) routed through `applyUpdate`. `treeToSentence.ts` renders multi-seed chips as "is a smoker (or any kind of: smoker, cigarette smoker)" and exclusions as "except trial of smoking" via an optional `TermResolver`. `RuleReviewSection.tsx` adds an Edit button on the "Approved in this session" card (AC-010) and a Pending review / Active / Superseded `ToggleButtonGroup` (AC-011, AC-012) so any rule -- pending, active, or superseded -- can be opened in the editor; bulk Approve-all and per-row Looks right / Reject collapse outside Pending so they cannot be misapplied to live rules. |
| Design Output | DO-LEO-AI-508 | draft | `services/api/app/services/guidance_rule_edit.py` (LogicSeed + LogicCriterion + validators) + `services/ui/src/app/admin/guidance/EditRuleDialog/types.ts` (mirror) + `scripts/migrations/logic_criterion_synonym_set.py`. |
| Design Output | DO-LEO-AI-509 | draft | `services/terminology_api/app/services/guideline_compiler.py` (`_seeds_from_criterion` + `_compile_concept_leaf`). |
| Design Output | DO-LEO-AI-510 | draft | `services/terminology_api/app/services/guideline_evaluator.py` (`_matched_seed_ids`, `_collect_matched_via`, annotated `CONCEPT.matched_concept_ids`) + `libs/sbar/assessment_formatter.py` (`_render_matched_via` + snapshot pass-through) + `libs/prompts/sbar_recommendation_v1.py` (rule 13). |
| Design Output | DO-LEO-AI-511 | draft | `services/ui/src/app/admin/guidance/EditRuleDialog/SynonymChipEditor.tsx` + `LogicTreeEditor.tsx` wiring + `treeOps.ts` helpers + `treeToSentence.ts` (TermResolver). |
| Risk | R-LEO-AI-508 | mitigated | A misconfigured exclusion or synonym set silently drops clinically meaningful patient matches -- e.g. an over-broad descendant expansion masks a needed alternate diagnosis, or an excluded code blocks a legitimate hit. Mitigated by: server-side validator rejects primary-not-in-seeds and seed/exclusion overlap; UI plain-English warnings; replay-on-save against the rule's saved test cohort; evaluator surfaces `matched_via` so SBAR + audit logs name the exact code that fired; inline `SeedDescendantsList` lets the author audit every descendant the bitmap will match before saving and one-click block any unintended one (DI-511 AC-007); migration is idempotent and changes zero int-ids on read for legacy single-seed rules. Residual risk dropped from RPN 12 to RPN 6 (medium -> low) once the inline audit affordance landed. |
| Verification Test | VT-LEO-AI-510 | passed | 19 pytest + 24 jest cases. Pytest: 5 schema (legacy back-compat, derived legacy fields, validator collects every seed/exclusion id, primary-not-in-seeds rejection, seed/exclusion overlap rejection), 5 compiler (multi-seed union, per-seed include_descendants, exclusion subtraction, primary-only fallback, seed_concept_ids echoed), 5 evaluator (`matched_concept_ids` per leaf, `matched_via` per matched rule, descendant attribution, no-match leaves omitted, schema-v1 returns empty), 4 SBAR (descendant naming "a kind of <primary>", primary-only short-form, snapshot pass-through, legacy markdown unchanged). Jest: 15 treeOps (add/remove/setPrimary/toggleIncludeDescendants/setSeedDistance/addExcluded/removeExcluded + applyUpdate dispatch + findValidationError), 5 treeToSentence (legacy single-seed, multi-seed with descendants, multi-seed without descendants, exclusions resolved via TermResolver, exclusions fall back to "code <id>"), 4 SeedDescendantsList (TC-016: no-fetch when descendants off, fetch + Block on expand, Blocked badge + Unblock for excluded ids, refetch on depth change). |
| Validation Test | VAL-LEO-AI-015 | draft | Reviewer-led validation in staging: a clinical lead authors a real synonym set + exclusion on a NICE 2WW rule, runs replay on the rule's test cohort, and confirms (a) the chip label matches the primary seed, (b) descendant codes fire as expected, (c) the excluded sub-code does NOT fire, (d) the SBAR Assessment narrative names the matched code in plain English. |
| User Need | UN-LEO-AI-094 | approved | Non-specialist reviewers (audit clerks, junior coders, clinical leads with no AI / NLP background, age 8-80, UK reading age 7-11) can change a clinical guidance rule step by step in a widescreen four-step editor without ever feeling overwhelmed by the editor or saving a rule they did not understand. |
| Design Input | DI-LEO-AI-512 | draft | EditRuleDialog refactored as a widescreen split-view modal with a sticky left numbered step rail (Who / Suggest / Try / Save), a focused centre canvas that renders one step at a time, and a sticky right `LivePreviewPane`. Each rail item shows a Not started / In progress / Ready chip computed from the dialog state. The preview pane shows the rule in plain English on every step (`treeToSentence` + `STRENGTH_LABELS` recap) and swaps to a Before / After two-column variant on step 4. Save changes is the single primary action and is gated on tree validity AND `reason.trim().length >= 3`. Save payload contract is unchanged from the legacy editor (action='edit', node_ids stripped from `logic_tree`, action SNOMED criterion omitted unless the reviewer touched the action chip). All chrome copy reads at UK reading age 7-11. |
| Design Output | DO-LEO-AI-512 | draft | `services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx` orchestrator + `StepRail.tsx` + `LivePreviewPane.tsx` + `steps/Step1Who.tsx` + `steps/Step2Suggest.tsx` + `steps/Step3Try.tsx` + `steps/Step4Save.tsx` + `copy.ts` (~950 LOC). Reuses `LogicTreeEditor`, `ConceptSearchPanel`, `ConceptCoachPopover`, `TestPatientsPanel`, `ActionPanel`, `SummaryCard` and `treeToSentence` unchanged. |
| Risk | R-LEO-AI-509 | mitigated | A non-specialist reviewer saves a guidance rule edit that does not match what they intended because the legacy one-column editor presented nine concerns at once and the consequence of every edit was buried below the controls that changed it. Mitigated by the four-step wizard (Who / Suggest / Try / Save), the always-on plain-English `LivePreviewPane`, the step-4 Before / After comparison, the reason-gated single-primary Save action, and reading-age-7-to-11 chrome copy centralised in `copy.ts`. |
| Verification Test | VT-LEO-AI-511 | passed | 14 jest cases (6 suites): static-source orchestrator wiring (StepRail + LivePreviewPane + Step1-4 imports + three-column gridTemplateColumns + step files exist on disk + actionDirty save guard + stripNodeIds), rail navigation across all four steps, live preview reactivity to tree edits without a network call, before / after variant on step 4, save gating on `reason >= 3 chars` AND tree validity (and re-disabled when reason cleared), save payload omits `criterion` when action chip untouched, save payload includes `criterion` when action chip touched, `node_ids` stripped from logic_tree in payload, reading-age sweep on every chrome string in `copy.ts` (Flesch-Kincaid grade <= 6) plus per-helper sentence length sweep (<= 25 words), Cancel discards in-flight edits without calling onSave. Regression sweep: 92/92 EditRuleDialog suites green after adding rail-aware navigation helpers to the legacy tests. |

---

## SBAR Background Partition + Map + Reduce + Plain-English Error Surfacing (April 2026)

This programme contains the "Input is too long for requested model"
Bedrock failure mode without ever silently truncating or dropping a
clinical record, and removes the misleading green "Done (1 errors)"
button from the AI Summarisation playground. Three changes ship
together:

1. A pre-emptive token-budget aware **partition + map + reduce** flow
   on the SBAR Background stage. `libs/sbar/background_partitioner`
   greedy-packs the patient's resolved sources into one or more
   partitions whose serialised user message fits a per-part budget;
   oversized single records are split intra-record so even a giant
   discharge bundle survives without truncation. `call_background`
   then runs the existing `sbar_background` prompt once per
   partition (MAP), runs a new strict editor prompt
   `sbar_background_reduce` exactly once when there are two or more
   partitions and every MAP succeeded (REDUCE), and falls back to a
   deterministic stitch ("## Background -- part k of N") with a
   `reduce_failed` notice on REDUCE failure or per-part MAP failure.
   The single-partition path is a direct pass-through (one LLM call,
   no REDUCE) so the legacy success behaviour is preserved when the
   input fits in one go. A hard 8-part cap bounds cost and latency;
   if more parts would be required the system refuses with a
   `too_many_parts` error rather than dropping records.
2. The reduce prompt
   (`libs/prompts/sbar_background_reduce_v1.SBAR_BACKGROUND_REDUCE_SYSTEM_V1`)
   is a strict editor with six HARD RULES (NO NEW FACTS, NO LOSS,
   PRESERVE DATES / MEDICATIONS / VALUES verbatim, DEDUPE LITERAL
   DUPLICATES ONLY, PRESERVE CITATIONS, EDITOR-NOT-CLINICIAN). It is
   registered at version 1 in the prompt registry and gated on
   all-MAP-succeeded so it can never run over a poisoned input set.
3. Structured `errors`, `notices`, and `parts` arrays on the SSE
   wire format plus matching MUI Alerts and per-part progress Chips
   in the playground. Every `sbar_completed` event now carries
   `errors` and `notices` arrays of `{stage, code, message}` triples
   sourced from the friendly translator (no raw vendor strings),
   plus a `parts` summary for the Background stage. A new
   `sbar_stage_progress` event streams per-part / per-phase progress
   so the playground shows live "Generating Background, part 2 of
   5..." chips. The result button shifts from green to amber when
   any stage failed so a partial SBAR cannot be confused with a
   complete one.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-095 | approved | Big patient records still produce a useful SBAR, no clinical record is silently truncated or dropped to make space (the work is split across multiple LLM calls and merged back), and any failure is explained in plain English (UK reading age 9-11) naming which section / which part did not finish, never a raw AWS error. |
| Design Input | DI-LEO-AI-513 | superseded | [SUPERSEDED by DI-LEO-AI-522] Original "partition + map + reduce" Background design. The reduce LLM call was retired in favour of a pure-Python deterministic stitch so no clinical fact can be lost or invented during merge (R-LEO-AI-511 mitigated by design). |
| Design Input | DI-LEO-AI-522 | draft | SBAR Background partition + map + deterministic stitch (NO REDUCE LLM call). `libs/sbar/background_partitioner.partition_background_sources()` bin-packs `ResolvedSource` records into N <= 8 `Partition` objects respecting a per-part token budget; single oversized records are split intra-record with `part_in_record` metadata; the partitioner refuses cleanly with `too_many_parts` when N would exceed 8. `libs/sbar/prompt_calls.call_background` calls the standard `sbar_background` prompt once per Partition (sequentially) with a per-part progress callback; per-part failures render as a placeholder body that points the reviewer at the errors panel while surviving parts still land. `_stitch_partials_deterministic` concatenates partials under `### Part {i} of {N} -- records {a}-{b}` headings with one `<!-- sources: id1, id2, ... -->` HTML comment per part for traceability. There is intentionally NO second LLM call to merge partials; the merge is pure Python. The orchestrator emits an `sbar_stage_progress` SSE event per part and the SBAR Playground renders a "part i of N" chip on the Background stage card while running. |
| Design Input | DI-LEO-AI-516 | draft | Surface SBAR run errors, notices, parts, and per-part progress to the reviewer (SSE + UI). The orchestrator emits structured `errors` and `notices` arrays on every `sbar_completed` event, per-stage `error` / `notice` / `parts` keys on every `sbar_stage_completed` event, and a new `sbar_stage_progress` event per Background part / phase (`{phase, part_index, part_total, record_count, status}`) so the playground shows live "Generating Background, part 2 of 5" progress. The /admin/knowledge AI Summarisation playground renders an MUI Alert `severity="warning"` with `data-testid="sbar-errors-alert"`, an Alert `severity="info"` with `data-testid="sbar-notices-alert"`, per-part progress / reduce / parts-summary Chips (`sbar-part-progress-${stage}`, `sbar-reduce-progress-${stage}`, `sbar-parts-summary-${stage}`), and demotes the "View full SBAR" result button from `colour="success"` to `colour="warning"` when errors are present. |
| Design Input | DI-LEO-AI-521 | superseded | [SUPERSEDED by DI-LEO-AI-522] Duplicate of DI-LEO-AI-518; both retired when the reduce LLM step was removed in favour of pure-Python deterministic stitching. |
| Design Output | DO-LEO-AI-521 | draft | `libs/sbar/background_partitioner.py` (`partition_background_sources`, `_split_oversize_source`, `Partition`, `PartitionReport`, `_SourceSlice` with `record_index` / `record_range`) + `libs/sbar/prompt_calls.py` (`call_background` uses partitioner + per-part map + deterministic stitch + `progress_cb`; `_invoke_background_part`, `_stitch_partials_deterministic` writes `### Part {i} of {N} -- records {a}-{b}` headings with `<!-- sources: ... -->` comments) + `services/pipeline_worker/app/services/sbar_orchestrator.py` (`sbar_stage_progress` emission, `parts` payload, per-part FriendlyError stage labels via `background_part_failed_error`) + `libs/sbar/error_messages.py` (`background_part_failed_error`, `background_partition_overflow_error`). |
| Design Output | DO-LEO-AI-516 | draft | `services/pipeline_worker/app/services/sbar_orchestrator.py` (`SBAResult.errors_detail` / `notices`, `_record_stage_error`, `_record_background_notices`, `_record_background_part_errors`, `sbar_stage_progress` emission, `sbar_completed` and `sbar_stage_completed` payload changes including `parts` summary) + `services/ui/src/hooks/useSbarStream.ts` (`SbarErrorDetail` / `SbarNotice` / `SbarStagePart` / `SbarStagePartProgress` types, `SbarStageState.parts` / `partProgress` fields, `on('sbar_stage_progress')` handler) + `services/ui/src/app/admin/ai-summarisation/SbarPlayground.tsx` (`sbar-errors-alert` + `sbar-notices-alert` Alerts; per-stage `sbar-part-progress`, `sbar-reduce-progress`, `sbar-parts-summary` Chips; dynamic result button colour). |
| Design Output | DO-LEO-AI-522 | draft | `libs/prompts/sbar_background_reduce_v1.py::SBAR_BACKGROUND_REDUCE_SYSTEM_V1` (six HARD RULES system prompt) + `scripts/seed_prompt_configs.py` (registers `sbar_background_reduce@1`) + `libs/sbar/prompt_calls.py::_try_reduce_partials` (single reduce invocation per multi-part successful run; `_serialise_background_reduce_context` user-message serialiser). |
| Risk | R-LEO-AI-185 | analyzed | (Updated mitigations) Adds a 4th mitigation to the existing playground risk: token-budget aware partition + map + reduce flow plus structured errors / notices / per-part progress on the wire and warning / info Alerts + per-part Chips in the playground. The result button shifts from green to amber when any stage failed. Implemented_by includes DI-LEO-AI-513, DI-LEO-AI-516, and DI-LEO-AI-521; verified_by includes VT-LEO-AI-514. |
| Risk | R-LEO-AI-510 | analyzed | A reviewer mistakes a partially-failed SBAR for a complete one because errors are hidden behind a green "Done" button. Mitigated by the partition + map + deterministic stitch flow (DI-LEO-AI-522 -- removes the dominant cause without dropping records), structured errors / notices on the wire (DI-LEO-AI-516), per-part `sbar_stage_progress` SSE events, the warning Alert + amber button in the playground, and the translator-only message text invariant. Initial RPN 36 (high) -> residual RPN 6 (low). |
| Risk | R-LEO-AI-511 | mitigated (by design) | The original Background reduce LLM step could silently lose a clinical fact or invent one when merging partial Backgrounds. Mitigated by removing the reduce step entirely: DI-LEO-AI-522 stitches partials in pure Python under `### Part {i} of {N} -- records {a}-{b}` headings with `<!-- sources: ... -->` comments. Verified by VT-LEO-AI-520 (no-reduce-call invariant + deterministic stitch). Residual risk reduced to low (only nondeterminism is per-part LLM variation, contained per partition). |
| Verification Test | VT-LEO-AI-514 | passed | (Original suite -- now subsumed by VT-LEO-AI-520 for the no-reduce flow.) 18/18 cases on the legacy partition + map + reduce design. Retained for historical evidence. |
| Verification Test | VT-LEO-AI-520 | draft | New suite for DI-LEO-AI-522. `tests/sbar/test_background_partitioner.py` (record_index / record_range invariants) + `tests/sbar/test_prompt_calls_background_partitioned.py` (single-part parity, multi-part deterministic stitching with `### Part {i} of {N} -- records {a}-{b}` headings + `<!-- sources: ... -->` comments, per-part failure containment, no-reduce-call invariant, too_many_parts refusal, progress_cb emission) + `services/ui/src/__tests__/sbar-playground-chrome.test.tsx` (sbar_stage_progress chip rendering, no "reduce" phase mentions). |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-516 | Structured SBAR errors / notices / parts / progress on SSE + Playground surfacing (UN-LEO-AI-095). | R-LEO-AI-185, R-LEO-AI-510 | VT-LEO-AI-514 |
| DI-LEO-AI-522 | SBAR Background partition + map + deterministic stitch (NO REDUCE LLM call) (UN-LEO-AI-095). Supersedes DI-LEO-AI-513, DI-LEO-AI-518, DI-LEO-AI-521. | R-LEO-AI-510, R-LEO-AI-511 | VT-LEO-AI-520 |

---

## Episode Engine: Audit Relevance Filter + Window Partitioner safety net (April 2026)

This programme extends the existing Episode Engine (UN-LEO-AI-090, DI-LEO-AI-500..504) with a focus-first input pipeline so that the milestone extractor sees a tight, signal-rich set of pathway-relevant encounters on every patient -- not the long tail of routine non-cancer care and admin echoes that previously diluted the signal -- AND so that no encounter is silently truncated or dropped on patients with very large records. The architecture mirrors the SBAR Background partition + map + deterministic-stitch pattern (DI-LEO-AI-522) but applies it to the milestone extractor: focus the input first (so the common case stays a single LLM call), and keep a partition + map + deterministic-merge safety net for the rare patient whose focused set still exceeds the per-part token budget. The merge step is pure Python -- no LLM ever sees more than one part at a time and no LLM is ever in the merge path -- so editor-induced fact loss / hallucination during partition stitching is architecturally impossible (R-LEO-AI-513).

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-097 | approved | Cancer pathway audits stay focused on pathway-relevant encounters, never silently drop a relevant one, and complete for every patient regardless of record size. Sits in front of UN-LEO-AI-090 to give clinicians and QA reviewers a complete EoC for every patient in the cohort while keeping the milestone extractor's input cancer-focused. |
| Design Input | DI-LEO-AI-524 | draft | Episode Engine Audit Relevance Filter (focus-first). Two layers: (1) deterministic always-keep guards mark cancer-coded encounters, every encounter the segmenter tagged in any anchor role for this window (referral / first_seen / diagnosis_confirmed / treatment_started / treatment_completed / benign_closure / first_presentation / place_of_first_presentation / outcome_letter), and encounters already flagged by the safety-netting / disruption hint detectors as `kept_by_guard=true` -- guard decisions are final and the LLM cannot override; (2) the remaining unguarded encounters are batched in groups of `<=20` and submitted to a Bedrock Haiku call with a forced `submit_relevance` tool that returns `{encounter_id, keep, reason}` per encounter; KEEP encounters bearing on the suspected cancer / its workup / treatment / safety-netting / pathway disruptions; DROP routine non-cancer care and admin echoes. Focused set is the chronological-order union with no duplicates. Fail-open on Haiku error: every encounter in a failed batch flows through with `kept_by_fallback=true`. Each EoC records `audit_input_encounters`, `audit_kept_by_guards`, `audit_kept_by_llm`, `audit_dropped_by_llm` (up to 10 `{encounter_id, reason}` samples), and `audit_filter_failed` on its audit trace. `LLMUsage` written with `stage=audit_relevance_filter`. |
| Design Input | DI-LEO-AI-525 | draft | Episode Engine Window Partitioner safety net for milestone extraction (partition + map + deterministic merge). Mirrors DI-LEO-AI-522 (SBAR Background) for the milestone extractor schema. `partition_window()` bin-packs the focused encounter set into `N <= 8` Partitions respecting a per-part token budget; oversized single encounters are split intra-encounter with `part_in_encounter` metadata; partitioner refuses with `too_many_parts` when `N` would exceed 8 (zero LLM invocations). Chain invokes the milestone extractor once per Partition (sequentially); per-part failures contribute an empty milestone list with `needs_human_review=true` while surviving parts still contribute. `merge_milestones_deterministic` is pure Python: dedup milestones on `(type, date, encounter_id)` keeping highest confidence + longest evidence_quote, union safety_netting flags, dedup disruptions on the same key, any-true on `needs_human_review`, concatenate reasoning as `Part i of N: ...` lines. NO second LLM merge call (R-LEO-AI-513). Single-Partition runs are byte-for-byte identical to the legacy single-call extractor. EoC carries `audit_parts` and per-part trace; `too_many_parts` flips the EoC to `needs_human_review=true` + `audit_filter_overflow=true`. `timeline_loader._FULL_SNIPPET_CHARS` demoted to a corner-case fallback so the partitioner is the single point of token-budget control. |
| Design Output | DO-LEO-AI-524 | draft | `services/analysis_worker/app/episode_engine/agents/audit_relevance_filter.py` (`run`, `_apply_guards`, `_batch_unguarded`, `_call_relevance_triage`, `_merge_decisions`) + `libs/prompts/episode_engine/audit_relevance_filter_v1.py` (`SYSTEM` + `USER_TEMPLATE` + `submit_relevance` JSON Schema, reading age 9-11) + `episode_engine/chain.py` (`_node_audit_relevance_filter` wired before `_node_milestone_extractor`; `LLMUsage stage=audit_relevance_filter`) + `episode_engine/schemas.py` (`FocusedSet`, `FocusedEncounter`, `AuditFilterReport`, audit fields on `EpisodeOfCareTrace`). |
| Design Output | DO-LEO-AI-525 | draft | `services/analysis_worker/app/episode_engine/window_partitioner.py` (`partition_window`, `merge_milestones_deterministic`, `_pack_partitions`, `_intra_encounter_split`) + `episode_engine/chain.py` (`_node_milestone_extractor` wires partition + map + deterministic merge; legacy single-call pass-through when `N == 1`) + `episode_engine/schemas.py` (`WindowPartition`, `PartitionReport`, `audit_parts`, per-part trace) + `episode_engine/timeline_loader.py` (`_FULL_SNIPPET_CHARS` demoted to a corner-case fallback). |
| Risk | R-LEO-AI-512 | analyzed | The Audit Relevance Filter (Haiku triage) drops a clinically relevant encounter, leading to a missing pathway milestone, missed safety-netting note, or missed avoidable delay on the EoC audit. Mitigated by the deterministic always-keep guards (cancer-coded / anchor / deterministic-hint-flagged encounters cannot be dropped at all), plain-English `{encounter_id, reason}` samples on the EoC audit trace, and fail-open behaviour on Haiku error. Initial RPN 36 (high) -> residual RPN 6 (low). |
| Risk | R-LEO-AI-513 | analyzed | The Window Partitioner safety net cannot fit the focused encounter set in `<=8` parts, or a future LLM merge step would lose / invent a pathway fact during partition stitching. Mitigated by the deterministic Python merge (no LLM in the merge path -- editor-induced fact loss / fact invention is architecturally impossible, same architectural decision as DI-LEO-AI-522 for SBAR), explicit `too_many_parts` refusal that flips the EoC to `needs_human_review=true` + `audit_filter_overflow=true` with zero LLM invocations, per-part failure containment, and per-part `{encounter_count, milestones_count, error}` trace on every multi-part EoC. Initial RPN 24 (medium) -> residual RPN 3 (low). |
| Verification Test | VT-LEO-AI-522 | passed | `tests/episode_engine/test_audit_relevance_filter.py` -- 10/10 cases pass: cancer-coded guard cannot be overridden, anchor preservation, deterministic-hint guard cannot be overridden, Haiku batching shape (25 unguarded -> 2 batches of 20 + 5), fail-open on Haiku error, audit trace fields populated, no duplicate when guard + LLM both keep (LLM bypassed), chronological order preserved, one StageTrace per Haiku batch, `apply_guards` pure-function smoke test. Run on 2026-04-19. |
| Verification Test | VT-LEO-AI-523 | passed | `tests/episode_engine/test_window_partitioner.py` + `tests/episode_engine/test_chain.py` + `tests/episode_engine/test_milestone_extractor_agent.py` -- 14/14 cases pass: single-partition pass-through, multi-part packing preserves every focused encounter, intra-encounter split with `part_in_encounter`, `too_many_parts` refusal with friendly notice, empty focused set, deterministic merge dedup keeps highest-confidence + longest evidence_quote, safety_netting unions / disruptions de-dup, single-part legacy pass-through, empty merge, chain single-call common case, chain multi-call per-part, per-part failure containment, chain overflow refusal with zero LLM invocations + EoC flagged, milestone_extractor pass-through regression. Run on 2026-04-19. |

| Artefact | ID | Risk | VT |
|----------|----|------|-----|
| DI-LEO-AI-524 | Episode Engine Audit Relevance Filter (focus-first; always-keep guards + Haiku batched relevance) (UN-LEO-AI-097). | R-LEO-AI-512 | VT-LEO-AI-522 |
| DI-LEO-AI-525 | Episode Engine Window Partitioner safety net for milestone extraction (partition + map + deterministic merge; no LLM merge call) (UN-LEO-AI-097). | R-LEO-AI-513 | VT-LEO-AI-523 |

---

## SBAR Generation Workflow + Document Chunks (April 2026)

This programme adds an end-to-end SBAR (Situation, Background,
Assessment, Recommendation) generation workflow on top of the existing
patient graph. The Assessment section is rendered DETERMINISTICALLY from
the roaring-bitmap rule evaluator output; only the Situation, Background
and Recommendation sections use LLMs, and they are constrained by JSON
output schemas plus 12 hardening rules per prompt. The pipeline is
triggered by an `sbar_requested` message on the `pipeline-jobs` Service
Bus queue and publishes per-stage progress on Redis pub/sub
`pipeline:{run_id}` for SSE consumers (admin playground today, future
referral / encounter UIs tomorrow). Sub-document granularity is provided
by a new `:Chunk` node attached to `:DocumentReference` via `HAS_CHUNK`,
and the existing `:DOCUMENTS` writer is generalised to accept either an
`:Encounter` or a `:Chunk` as the source of coded clinical evidence.

NOTE on numbering: the YAMLs at `DI-LEO-AI-186` and `DI-LEO-AI-187`
have been re-authored against `UN-LEO-AI-082` to describe the chunk
schema foundation. The legacy gold-label entity audit (DI-186-was) and
manual-gold-seed safety check (DI-187-was) remain in code at
`scripts/lib/gold_label_snomed_check.py` and
`scripts/seed_manual_gold_records.py` and are still verified by
`VT-LEO-AI-180` and `VT-LEO-AI-181` -- their narrative description is
preserved in the section above.

| Artefact | ID | Status | Description |
|----------|----|--------|-------------|
| User Need | UN-LEO-AI-079 | draft | Make narrative document content queryable as discrete clinical evidence. Coded SNOMED facts must attach at the chunk level so a reviewer can see exactly which substring of a referral letter triggered each code |
| User Need | UN-LEO-AI-080 | draft | Generate an SBAR summary for a patient on demand. Clinicians preparing for a referral or future-dated encounter need a structured Situation/Background/Assessment/Recommendation summary with source attribution and explicit "missing data" markers |
| User Need | UN-LEO-AI-081 | draft | Reviewers can interactively test SBAR generation. QA reviewers and prompt authors need a /admin playground to validate prompt and pipeline changes against fixture data without touching production consumer surfaces |
| Design Input | DI-LEO-AI-186 | approved | :Chunk node + HAS_CHUNK relationship. libs/cypher/chunk_queries.py provides make_chunk_id (sha256 of document_reference_id + ordinal + sha256(text)), UPSERT_CHUNK Cypher, get/find helpers; libs/cypher/schema_constraints.py adds CHUNK_CONSTRAINTS (UNIQUE on Chunk.id; indexes on document_reference_id, sha256) |
| Design Input | DI-LEO-AI-187 | approved | Generalise :DOCUMENTS to accept Encounter|Chunk source. libs/cypher/documents_queries.py _build_upsert_query takes source_label parameter; the chunk path uses OPTIONAL MATCH ... <-[:HAS_CHUNK]-(:DocumentReference)<-[:HAS_DOCUMENT_REFERENCE]-(p:Patient) and guards the Patient FOREACH with `p IS NOT NULL` |
| Design Input | DI-LEO-AI-188 | approved | SBAR queue contract. libs/sbar/events.py exports SBARRequestPayload + SBARSituationInput + SBARArtifactRef + SBARBackgroundSourceRef with strict enums and an id-or-text validator per artefact type |
| Design Input | DI-LEO-AI-189 | approved | :Assessment node + HAS_ASSESSMENT relationships. libs/cypher/sbar_assessment_queries.py: CREATE_ASSESSMENT (links to Patient up-front), LINK_ASSESSMENT_TO_REFERRAL_REQUEST/_PROCEDURE_REQUEST/_ENCOUNTER, SET_SITUATION/_BACKGROUND/_ASSESSMENT_NARRATIVE/_RECOMMENDATION (incremental), FINALISE_ASSESSMENT, GET_ASSESSMENT, assessment_to_dict |
| Design Input | DI-LEO-AI-190 | approved | SBAR orchestrator. services/pipeline_worker/app/services/sbar_orchestrator.py runs Situation -> Background -> deterministic Assessment -> Recommendation, persists each section incrementally and publishes per-stage Redis events. Source resolution delegated to libs/sbar/source_resolver.py; LLM calls to libs/sbar/prompt_calls.py |
| Design Input | DI-LEO-AI-191 | approved | SBAR HTTP API + SSE relay. services/api/app/routers/sbar.py exposes POST /sbar/jobs (queues onto pipeline-jobs), GET /sbar/jobs/{run_id}/events (Redis pub/sub SSE relay with last-event catch-up + 300s idle timeout), GET /sbar/assessments/{id}. All three depend on require_admin |
| Design Input | DI-LEO-AI-192 | approved | SBAR LLM prompt suite. libs/prompts/sbar_situation_v1.py, sbar_background_v1.py, sbar_recommendation_v1.py + libs/prompts/sbar_output_schemas.py. 12 hardening rules per prompt; JSON schemas reject empty markdown. Seeded into Neo4j by scripts/seed_prompt_configs.py |
| Design Input | DI-LEO-AI-193 | approved | Deterministic Assessment formatter. libs/sbar/assessment_formatter.py wraps /terminology/guidelines/evaluate via httpx; pure function of (matched_rules, patient_codes, guideline_ids); sorts rules by action priority (2WW > urgent > routine); derives stt/rtr/alternative_pathway + *_evidence deterministically without any LLM |
| Design Input | DI-LEO-AI-194 | approved | AI Summarisation Playground. /admin/knowledge gains an "ai-summarisation" tab backed by SbarPlayground (form + per-stage progress + final Markdown), useSbarStream (POST + EventSource + final fetch), and three Next.js Route Handler proxies. Permanent "Test only" banner |
| Design Input | DI-LEO-AI-230 | draft | PatientFinder primitive + analytics-api router. MUI Dialog with Search/Filter/Saved-cohort tabs where every result row renders NHS number AND date of birth. Backed by /analytics/patient-finder/* endpoints + extended CohortFilter (imd, encounter_count, episode_*) + POST /cohorts/preview |
| Design Input | DI-LEO-AI-231 | draft | SummarisationContext enum (34 NHS-aligned reasons grouped Primary care / Secondary care / Statutory and social / Quality assurance) + SummarisationContextSelect card-grid Dialog picker (search field + responsive grid of selectable cards) + per-context prompt fragments. Replaces free-text Situation framing. Per-context snippets are now editable via DI-LEO-AI-507. Legacy fixed_text retained for one minor version |
| Design Input | DI-LEO-AI-232 | draft | BackgroundSourcePicker primitive. Patient-scoped MUI Dialog with two tabs (Encounters, Letters and documents). Document rows expand to reveal child :Chunk nodes; selecting any chunks under a document drops the parent from the emitted SBARBackgroundSourceRef[] |
| Design Input | DI-LEO-AI-233 | draft | GuidelinePicker primitive (MUI Autocomplete over /api/nice/loaded with 'Use all loaded' shortcut) + QSIR-aligned Concern field (max 500 chars, optional) forwarded into the Situation stage prompt as extra_context['concern'] |
| Design Output | DO-LEO-AI-185 | approved | libs/cypher/chunk_queries.py + ASSESSMENT/CHUNK constraints |
| Design Output | DO-LEO-AI-186 | approved | libs/cypher/documents_queries.py generalisation (source_label, OPTIONAL MATCH on Patient via DocumentReference, null-safe FOREACH) |
| Design Output | DO-LEO-AI-187 | approved | libs/sbar/events.py |
| Design Output | DO-LEO-AI-188 | approved | libs/cypher/sbar_assessment_queries.py + ASSESSMENT_CONSTRAINTS |
| Design Output | DO-LEO-AI-189 | approved | services/pipeline_worker/app/services/sbar_orchestrator.py + libs/sbar/source_resolver.py + libs/sbar/prompt_calls.py + pipeline_worker/main.py dispatch branch |
| Design Output | DO-LEO-AI-190 | approved | services/api/app/routers/sbar.py + Redis pub/sub SSE relay |
| Design Output | DO-LEO-AI-191 | approved | libs/prompts/sbar_*_v1.py + libs/prompts/sbar_output_schemas.py + scripts/seed_prompt_configs.py entries |
| Design Output | DO-LEO-AI-192 | approved | libs/sbar/assessment_formatter.py |
| Design Output | DO-LEO-AI-193 | approved | services/ui/src/app/admin/ai-summarisation/* + useSbarStream + three Next.js proxies + knowledge tab registration |
| Risk | R-LEO-AI-180 | mitigated | A Chunk node persists text that no longer matches the source DocumentReference, causing reviewers to validate coded evidence against stale text. Mitigated by deterministic Chunk.id (re-ingesting identical text is idempotent; changed text creates new chunks while preserving the old ones for audit) and by surfacing all chunks (with sha256 and char offsets) in audit-trail UIs. Residual low |
| Risk | R-LEO-AI-181 | analyzed | LLM-generated SBAR sections introduce facts/drugs/dates/recommendations not present in the resolved source data. Mitigated by 12 hardening rules per prompt, JSON schema enforcement, rule-id grounding for the Recommendation, and the fact that the Assessment substrate is rendered deterministically from the rule evaluator (no LLM in that loop). Residual medium; conditionally accepted pending golden-set sign-off (VT-LEO-AI-189 TC-009) |
| Risk | R-LEO-AI-182 | mitigated | An SBAR job that fails partway through is rendered to a consumer as if the available sections were complete. Mitigated by explicit Assessment.status (draft -> in_progress -> completed/failed), per-stage Assessment.errors[] capture, terminal SSE events on completion/failure, and a 300s idle-timeout on subscriptions. Residual low |
| Risk | R-LEO-AI-183 | mitigated | An outage of /terminology/guidelines/evaluate causes the deterministic Assessment formatter to render an empty 'no rules matched' narrative when in fact safety-critical rules were unevaluated. Mitigated by distinguishing evaluator-success-no-match from evaluator-failure (status='failed', narrative explicitly notes the outage, pathway hints set to 'unknown' rather than 'no'), plus operational alerting on terminology_api availability. Residual low |
| Risk | R-LEO-AI-184 | analyzed | Free text from a referral letter or document chunk contains prompt-injection content that hijacks the SBAR LLM into ignoring safety rules. Mitigated by hardening rule 10 in every SBAR system prompt (treat CONTEXT free text as data, not instructions), rule-id grounding for the Recommendation (an injection cannot reference a real rule_id), and JSON schema structure. Residual low; conditionally accepted pending prompt-injection cases in the golden set |
| Risk | R-LEO-AI-185 | mitigated | An admin reviewer running SBAR generation in the playground treats the output as production-ready clinical guidance. Mitigated by a permanent "Test only" Alert banner (data-testid sbar-test-only-banner) enforced by VT-LEO-AI-188, /admin/* role gate, and admin role enforcement on the underlying /sbar/* API endpoints. Also reinforced by replacing free-text Situation framing with the typed SummarisationContext enum (DI-LEO-AI-231) and adding the capped 500-char Concern field (DI-LEO-AI-233). Residual low |
| Risk | R-LEO-AI-211 | mitigated | A reviewer using the shared PatientFinder primitive selects a different patient from the one they intended and runs an SBAR (or other tool) against the wrong record. Mitigated by an always-on three-identifier row contract (display name + NHS number + DOB) enforced by VT-LEO-AI-230, an echo chip on the playground confirming NHS+DOB before Submit, and admin role gate on the analytics-api endpoints. Residual low |
| Verification Test | VT-LEO-AI-185 | passed | 7 pytest cases pinning chunk id determinism, UPSERT_CHUNK parameter shape, _build_upsert_query for source_label='Encounter' and 'Chunk' (including the OPTIONAL MATCH and null-safe FOREACH), unknown-source rejection, write_documents_from_sentences_payload source_id forwarding and CHUNK_CONSTRAINTS registration. Run via tests/test_chunk_documents_queries.py + tests/test_documents_sentence_evidence_mapping.py. 20/20 passed 2026-04-17 |
| Verification Test | VT-LEO-AI-186 | passed | 6 pytest cases pinning SBARRequestPayload validation: minimal happy path, situation artefact id-or-text rules per artefact type, BackgroundSourceType enum gate, JSON round-trip idempotence, event_type literal lock. Run via tests/test_sbar_events.py. Passed 2026-04-17 |
| Verification Test | VT-LEO-AI-187 | passed | 7 pytest cases pinning SBAROrchestrator stage ordering, draft Assessment created up-front, Cypher write sequence, per-stage Redis progress events, degrade-to-draft on LLM failure, deterministic Assessment formatter always invoked, final composed Markdown contains all four section headings, pathway hints derived from rule outputs. Run via tests/test_sbar_orchestrator.py. Passed 2026-04-17 |
| Verification Test | VT-LEO-AI-188 | passed | UI verification with two layers. (1) Jest static-source: tab registration in /admin/knowledge, 'Test only' banner present, patient-id/background-source/guideline-id inputs present, useSbarStream POSTs /api/sbar/jobs and opens EventSource on /api/sbar/jobs/{id}/events, three Next.js Route Handlers proxy to the Core API. (2) Playwright: live tab load with banner, submit-enable behaviour, axe baseline (zero critical/serious violations). Run via services/ui/src/__tests__/sbar-playground-chrome.test.tsx + services/ui/e2e/sbar-playground.spec.ts + services/ui/e2e/knowledge-tabs.spec.ts. Passed 2026-04-17 |
| Verification Test | VT-LEO-AI-189 | draft | 8 automated pytest cases (formatter purity, empty-match narrative, evaluator-outage path, 2WW pathway-hint derivation, routine-only rtr=no, prompt seed registration, JSON schema empty-rejection, hardening rule 10 presence) plus TC-009: 10 manually-curated SBAR fixtures driven end-to-end by `scripts/run_sbar_golden_set.py`, structurally pinned by `tests/test_sbar_golden_set_runner.py` (29/29 green 2026-04-17), and signed off interactively by a clinical reviewer + Clinical Safety Officer via `scripts/review_sbar_golden_set.py`. Status remains `draft` until the signed ledger lands in the evidence bundle |
| Verification Test | VT-LEO-AI-230 | draft | Two-layer verification of PatientFinder + /patient-finder router. (1) Jest static-source asserts the three-tab structure and that every result row (in every tab) carries the NHS-number and DOB markers required by R-LEO-AI-211. Live-render asserts the 250 ms typeahead debounce. (2) Pytest covers CallerScope 403 enforcement on /patient-finder/{id}/* endpoints, the extended CohortFilter clauses (imd_decile_min/max, encounter_count_min/max + window, episode_*), and POST /cohorts/preview shape |
| Verification Test | VT-LEO-AI-231 | draft | Pytest cases assert SummarisationContext has exactly 20 members and that SUMMARISATION_CONTEXT_LABELS / SUMMARISATION_CONTEXT_PROMPTS cover every value, that source_resolver injects the matching prompt fragment, and that the legacy fixed_text artefact still validates. A jest static-source case compares the SummarisationContextValue union in SummarisationContextSelect.tsx to the Python enum to prevent silent drift |
| Verification Test | VT-LEO-AI-232 | draft | Two-layer verification of BackgroundSourcePicker + chunks endpoint. (1) Jest static-source asserts the dialog has exactly two tabs (no third 'chunks' tab) and chunks render inside the document Collapse. Live-render asserts the chunk-drops-parent rule. (2) Pytest covers GET /document-references/{id}/chunks chunk_index ascending order and CallerScope enforcement |
| Verification Test | VT-LEO-AI-233 | draft | Two-layer verification of GuidelinePicker + Concern field. (1) Jest static-source asserts the Autocomplete is multiple=true loaded from /api/nice/loaded and that the Concern textarea has maxLength=500 with a visible counter. Live-render asserts the 'Use all loaded' shortcut toggle. (2) Pytest covers SBARRequestPayload.concern Pydantic 500-char cap, orchestrator forwarding of payload.concern into extra_context['concern'], and empty-string -> None coercion |

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
