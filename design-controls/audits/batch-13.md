# Batch 13 -- Override analytics, SBAR, interpretation and related UNs

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 33 DIs across eight UNs. Given the size, this report is organised
thematically; per-DI verdicts are listed in the appendix table at the end.

## Theme A -- SBAR generation (UN-AFFA1FB3)
DIs: DI-30D9CC61, DI-8804DA01, DI-740BE510.

Evidence:
- `libs/pipeline_graph/subgraphs/sbar.py` implements an SBAR generation
  subgraph.
- `libs/pipeline_graph/state.py` carries SBAR state.

Verdicts:
- DI-30D9CC61 SBAR generation from coded encounters + pathway stage: partial
  (subgraph exists; not yet verified it covers all structured inputs).
- DI-740BE510 Provenance links on every SBAR statement: partial (provenance
  writer exists in `libs/cypher/documents_queries.py` but no regression test
  locks SBAR-level linkage).
- DI-8804DA01 Mandatory human review gate before finalisation with
  AI-original/edit delta: missing (no finalisation gate found).

## Theme B -- Clinical interpretation with safety guardrails (UN-575E8DCB)
DIs: DI-604767B1, DI-66F1B177, DI-69C29EEF, DI-DA7584D8, DI-A3107424.

Evidence:
- `libs/prompts/extraction_output_schema.py`, `libs/prompts/coding_agent_v1.py`
  contain interpretation output schemas with plain-language constraints.

Verdicts:
- DI-66F1B177 Plain-language interpretation: partial (prompts enforce; no
  automated Flesch readability check in CI).
- DI-69C29EEF Clinical-significance bounded to structured inputs: partial.
- DI-DA7584D8 Confidence displayed next to each interpretation: missing in UI.
- DI-A3107424 No diagnostic/treatment recommendations: partial (prompt
  disclaimer; no post-generation filter).
- DI-604767B1 Human-review gate blocking publication: missing.

## Theme C -- Safety netting worklist and alerts (UN-459367FA)
DIs: DI-21E93377, DI-4C73DC01, DI-520A8674, DI-0E215ADE, DI-B46AD5CE.

Evidence:
- `services/analysis_worker/app/analyzers/safety_net_detector.py`,
  `safety_net_persistence.py`.
- `libs/pipeline_graph/subgraphs/safety_net.py`.
- `scripts/delete_near_miss_alerts.py`,
  `scripts/seed_reference_ranges.py`.

Verdicts:
- DI-21E93377 Three-band severity classification vs reference range: partial
  (detector exists; ensure three-band label + severity emitted).
- DI-4C73DC01 Configurable follow-up window + outstanding worklist: partial.
- DI-520A8674 Worklist filter by severity/days/cohort: partial UI gap.
- DI-0E215ADE Auto-suppression on confirmed coded clinical response: partial.
- DI-B46AD5CE Immutable action recording with clinician identity: partial
  (audit-writer exists in `libs/audit/`).

## Theme D -- Data-quality coverage/disclosure for clinician outputs (UN-A949A642)
DIs: DI-00E16F9E, DI-098D2C0D, DI-0D7DCC52, DI-88F20177, DI-900CB621,
DI-B95A73E9, DI-CB3DF3E1.

Evidence:
- `services/analytics_api/app/routers/audit.py`, `_audit_sections.py`,
  `dashboards.py`.

Verdicts: all seven are in the data-quality + cohort disclosure surface.
Current analytics router emits aggregate audit counts but does not
consistently emit cohort metadata, small-cohort suppression, completeness
indicators, or mandatory acknowledgement gating. Marked partial for
B95A73E9 / 900CB621 / 098D2C0D (rendering present), missing for the
gate/suppression DIs (00E16F9E, 0D7DCC52, CB3DF3E1, 88F20177).

## Theme E -- Coding quality metrics + pipeline kill switch (UN-87632C9E)
DIs: DI-1126FFD1, DI-3613871E, DI-5A802C83, DI-5E1BA369, DI-D6A7A44F.

Evidence:
- `services/api/app/routers/audit_quality.py` includes drift-related
  endpoints and metrics.
- `tests/test_coding_agent.py` references kill-switch behaviour.

Verdicts: partial across the board. Metric computation exists; the
"per-programme kill switch activatable without deployment", the overcoded-
encounter SLA queue, and the automatic pipeline pause on unacknowledged
regression alerts are not wired. D6A7A44F (30-cycle history dashboard) has
groundwork via analytics_api but not confirmed complete.

## Theme F -- Override analytics and taxonomy (UN-6C8AEB83)
DIs: DI-425CA252, DI-770FD74A, DI-FFCD4F96.

Evidence: grep for `override_taxonomy|OverrideCategory|correction_category`
returns zero hits.

Verdict: missing. No structured override taxonomy capture, no runtime rule
management, no override analytics dashboard.

## Theme G -- Investigation escalation and alerts (UN-06FD3F7D)
DIs: DI-49A8F570, DI-79509E39, DI-E609C4E5.

Evidence: `services/analysis_worker/app/analyzers/abnormal_results.py`,
`libs/exclusion_detector/detector.py`.

Verdict: partial. Abnormal-results analyzer exists; alert fatigue suppression
and persistent informational disclaimer need dedicated UI/API support.

## Theme H -- Audit quality loops (UN-AE5D7812)
DIs: DI-37315D03, DI-B1E0EE52.

Evidence: `services/api/app/routers/audit_quality.py`,
`libs/audit/kg_verified_writeback.py`, `tests/test_audit_kg_verified_writeback.py`.

Verdict: partial. Drift detection exists; root-cause labelling with 2-year
immutable history is not schema-enforced.

## Appendix -- Per-DI verdict table

| DI | Theme | Verdict |
|----|-------|---------|
| DI-00E16F9E | D | missing |
| DI-098D2C0D | D | partial |
| DI-0D7DCC52 | D | missing |
| DI-0E215ADE | C | partial |
| DI-1126FFD1 | E | partial |
| DI-21E93377 | C | partial |
| DI-30D9CC61 | A | partial |
| DI-3613871E | E | missing |
| DI-37315D03 | H | partial |
| DI-425CA252 | F | missing |
| DI-49A8F570 | G | partial |
| DI-4C73DC01 | C | partial |
| DI-520A8674 | C | partial |
| DI-5A802C83 | E | missing |
| DI-5E1BA369 | E | partial |
| DI-604767B1 | B | missing |
| DI-66F1B177 | B | partial |
| DI-69C29EEF | B | partial |
| DI-740BE510 | A | partial |
| DI-770FD74A | F | missing |
| DI-79509E39 | G | missing |
| DI-8804DA01 | A | missing |
| DI-88F20177 | D | missing |
| DI-900CB621 | D | partial |
| DI-A3107424 | B | partial |
| DI-B1E0EE52 | H | partial |
| DI-B46AD5CE | C | partial |
| DI-B95A73E9 | D | partial |
| DI-CB3DF3E1 | D | missing |
| DI-D6A7A44F | E | partial |
| DI-DA7584D8 | B | missing |
| DI-E609C4E5 | G | missing |
| DI-FFCD4F96 | F | missing |

## Atlas actions

Umbrella DOs for themes A / C / E / H where implementation exists; themes B,
D, F, G mostly backlog. 33 backlog entries are captured below as compact
bullets to keep the backlog table readable.
