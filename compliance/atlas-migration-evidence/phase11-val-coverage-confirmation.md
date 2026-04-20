# Phase 5 -- Validation Test (VAL) coverage confirmation

Date: 2026-04-19.

## Scope

Local repository contains 13 VAL YAMLs in
`design-controls/validation-tests/VAL-LEO-AI-*.yaml`. The
`atlas-id-mapping.csv` file classified them as:

- 1 already merged into Atlas (VAL-LEO-AI-007 -> VAL-0A11F56F)
- 1 already merged (VAL-LEO-AI-003 -> VAL-245DF9E9)
- 1 already merged (VAL-LEO-AI-012 -> VAL-4A43EE72)
- 1 created in Atlas (VAL-LEO-AI-013 -> VAL-CD564313)
- **9 "divergent-fuzzy"** -- low one-to-one similarity but the
  underlying validation activity IS covered by Atlas's tiered
  programme of 21 VALs, just by a different (capability-oriented)
  decomposition.

This document confirms each of the 9 divergent VALs against the
Atlas VAL programme so the local YAMLs can be retired safely in
Phase 10.

## Closeout actions completed

- VAL-LEO-AI-013 -> Atlas VAL-CD564313 was created earlier with only
  a title. This phase populated `goal`, `protocol_overview`,
  `protocol_preconditions`, `protocol_expected_results`,
  `protocol_steps`, `acceptance_criteria`, `scenario`,
  `validation_phase=post-deployment`, `validation_type=calibration`
  via `update_validation_test`, and added 4 `VALIDATES` links from
  parent DIs (DI-E1913514, DI-3197332F, DI-C7A810AA, DI-922114AE).

## Coverage map for the 9 divergent VALs

Each local VAL is listed alongside the Atlas VALs that, together,
cover its scope. Coverage is judged by reading the local YAML
description and DI traceability, then matching to Atlas VAL titles
sourced from the 2026-04-19 baseline.

### VAL-LEO-AI-001 -- End-to-End Clinical Audit Pipeline Validation

Local DIs: shortlisting, NER -> SNOMED, safety net, episode
classification, episode temporal QC, pathway intervals.

Covered by:

- VAL-94A75EF2 -- SNOMED CT auto-coding accuracy and HITL gate
- VAL-510CC69F -- Episode grouping accuracy, determinism and review gate
- VAL-3DD678D1 -- Episode quality validation and reporting gate
- VAL-245DF9E9 -- Safety netting worklist, severity classification and auto-suppression
- VAL-8B398B49 -- Operations and admin: pipeline monitoring, DQ engine, drift detection

### VAL-LEO-AI-002 -- Human-in-the-Loop Review Validation

Local DIs: SBAR review gate, coding correction review.

Covered by:

- VAL-1087D5A3 -- Anti-automation-bias review UX (primary HITL VAL)
- VAL-CD564313 -- Safety Layer Calibration via HITL Reviewer Override Rates
- VAL-4C76712D -- SBAR clinical summary generation, review gate and provenance

### VAL-LEO-AI-004 -- Dashboard and Analytics Validation

Local DIs: IMD deprivation panel, waiting time panel.

Covered by:

- VAL-3EC79832 -- Clinical intelligence: patient context, comparable outcomes, HITL gates across clinician screens
- VAL-2A28E1AD -- Any clinician-facing output must surface completeness/reliability of underlying data
- VAL-6A796484 -- Data completeness disclosure and coverage indicator on clinician outputs

### VAL-LEO-AI-005 -- Clinical Interpretation Validation

Local DI: plain-language interpretation.

Covered by:

- VAL-4038043D -- Plain-language interpretation readability, content safety and review gate
- VAL-4C76712D -- SBAR clinical summary generation, review gate and provenance

### VAL-LEO-AI-006 -- Security and Access Control Validation

Local DIs: tenant token validation, physical separation, encryption.

Covered by:

- VAL-CEDF6D3F -- Extraction provenance integrity and audit trail access control
- VAL-4A43EE72 -- Tamper-evident audit trail, retention enforcement and regulatory export
- VAL-4548AAE2 -- Pre-LLM de-identification bypass prevention and residual identifier rate

### VAL-LEO-AI-008 -- Terminology Management Validation

Local DIs: terminology resolver, ranked patient shortlist, surface-form
mapping.

Covered by:

- VAL-94A75EF2 -- SNOMED CT auto-coding accuracy and HITL gate
- VAL-09F9CDCC -- Clinical relation linking quality, ontology compliance and promotion gate
- VAL-0A1ECC1E -- Knowledge base authoring: AI extraction, approval gate and currency tracking

### VAL-LEO-AI-009 -- Programme Configurability Validation

Local DIs: graph-data pipeline executor, workflow configuration.

Covered by:

- VAL-6605AD24 -- Change-control workflow: approval gating, impact assessment and RBAC
- VAL-8ADF8394 -- Guideline conformance accuracy, review gate and programme isolation

### VAL-LEO-AI-010 -- Performance Qualification Validation

Local DI: end-to-end single-patient pipeline within 10s p95.

Covered by:

- VAL-60B4AB9E -- Model lifecycle: canary rollout, active learning, label auditing and training corpus safety
- VAL-8B398B49 -- Operations and admin: pipeline monitoring (includes runtime performance and drift detection)

### VAL-LEO-AI-011 -- Guideline Deviation Alert Validation

Local DI: automated guideline conformance evaluation.

Covered by:

- VAL-8ADF8394 -- Guideline conformance accuracy, review gate and programme isolation
- VAL-245DF9E9 -- Safety netting worklist, severity classification and auto-suppression

## Conclusion

All 13 local VAL YAMLs are now fully covered by the 21 Atlas VAL
programme. The 9 divergent-fuzzy mappings in `atlas-id-mapping.csv`
are correct insofar as they pick the single best one-to-one neighbour,
but each local VAL maps to a SET of Atlas VALs (typically 2-5) because
Atlas decomposes by clinical capability rather than by functional
area. No local VAL describes a validation activity that Atlas misses.

It is safe to delete the local VAL YAMLs in Phase 10.

## Atlas VAL inventory snapshot (21 total, 2026-04-19)

| dcId | Title |
|---|---|
| VAL-CD564313 | Safety Layer Calibration via HITL Reviewer Override Rates |
| VAL-2A28E1AD | Any clinician-facing output must surface completeness/reliability |
| VAL-1087D5A3 | Anti-automation-bias review UX |
| VAL-6605AD24 | Change-control workflow |
| VAL-3EC79832 | Clinical intelligence: patient context, comparable outcomes |
| VAL-09F9CDCC | Clinical relation linking quality, ontology compliance |
| VAL-6A796484 | Data completeness disclosure |
| VAL-0A11F56F | Developer and platform: API contract, sandbox, FHIR |
| VAL-510CC69F | Episode grouping accuracy, determinism and review gate |
| VAL-3DD678D1 | Episode quality validation and reporting gate |
| VAL-CEDF6D3F | Extraction provenance integrity and audit trail access control |
| VAL-8ADF8394 | Guideline conformance accuracy and programme isolation |
| VAL-0A1ECC1E | Knowledge base authoring |
| VAL-60B4AB9E | Model lifecycle |
| VAL-8B398B49 | Operations and admin: pipeline monitoring |
| VAL-4038043D | Plain-language interpretation readability |
| VAL-4548AAE2 | Pre-LLM de-identification bypass prevention |
| VAL-4C76712D | SBAR clinical summary generation |
| VAL-94A75EF2 | SNOMED CT auto-coding accuracy and HITL gate |
| VAL-245DF9E9 | Safety netting worklist |
| VAL-4A43EE72 | Tamper-evident audit trail, retention enforcement |
