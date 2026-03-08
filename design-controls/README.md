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
| DI-LEO-AI-016 | Coding Review UI | Extended: suppress form context-phrase guard and LEO phrase suggestion added to requirements, constraints, and acceptance criteria; `CodingReviewCasesModal.tsx` added to file structure; risk R-LEO-AI-027 added |

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
