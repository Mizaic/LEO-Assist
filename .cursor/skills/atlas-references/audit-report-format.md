# Audit Report Format

Every run of `atlas-control-author` ends with a short markdown
audit report printed to the user. The report makes the run
observable: what was created, what was linked, what gaps remain,
and what was refused.

## Template

```
## Atlas Control Author - Audit Report

- Run started: <ISO-8601 timestamp>
- Product: PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4
- Change kind: <cosmetic | internal_tooling | class_a_feature
  | class_b_feature | class_b_fix | interface_change
  | out_of_scope>
- Safety class: <A | B>
- UN cluster(s): <clinical_facts | clinical_terminology
  | pathway_match | information_completeness
  | clinician_summary | interface>

### Evidence map

- API routes: <path:function>, ...
- Workers: <path:class>, ...
- UI components: <path:component>, ...
- Prompts: <path>, ...
- Cypher / Neo4j: <path:query>, ...
- Tests already present: <path>, ...

### Decisions

- Required artefacts (from decision-engine.md): UN: <n>, DI: <n>,
  DO: <n>, Risk: <n>, VT: <n>, VAL: <n>
- Reused artefacts (existing): <list of dcIds>
- Updated artefacts: <list of dcIds>
- New artefacts: <list of dcIds>

### Atlas writes

| Step | Tool                       | Args summary           | dcId        | Result |
|------|----------------------------|------------------------|-------------|--------|
| 1    | create_user_need           | title=...              | UN-XXXX     | ok     |
| 2    | create_design_input        | title=...              | DI-YYYY     | ok     |
| 3    | link_design_controls       | UN-XXXX -> DI-YYYY     | -           | ok     |
| 4    | create_design_output       | source_reference=...   | DO-ZZZZ     | ok     |
| 5    | link_design_controls       | DO-ZZZZ -> DI-YYYY     | -           | ok     |
| 6    | create_risk                | hazard=...             | R-WWWW      | ok     |
| 7    | link_design_controls       | DI-YYYY -> R-WWWW      | -           | ok     |
| 8    | create_verification_test   | protocol=...           | VT-VVVV     | ok     |
| 9    | link_design_controls       | VT-VVVV -> DI-YYYY     | -           | ok     |
| 10   | link_design_controls       | VT-VVVV -> DO-ZZZZ     | -           | ok     |
| 11   | record_verification_run    | result=pass            | -           | ok     |

### Verification evidence

- VT-VVVV: pytest <path> -v - pass, 8 cases
- VAL-UUUU: clinician panel n=12, sites=A/B/C - pass

### Traceability gaps

- get_traceability_gaps after writes:
  - orphan_design_inputs: none of the new dcIds
  - orphan_design_outputs: none of the new dcIds
- Remaining gaps NOT introduced by this run: <list with owners>

### Refusals and warnings

- Refused: <change description, reason: out_of_scope / banned
  term / Class C escalation needed>
- Warnings: <e.g. "DO-ZZZZ source_reference required an
  update_design_output follow-up after create">
```

## Rules for the report

- The report is the last thing the orchestrator prints. Without
  it, the run is considered incomplete.
- If a step in the atomic plan failed, the table MUST show
  `failed` against that step and the orchestrator MUST stop.
- The traceability gap section MUST be populated from a real
  `get_traceability_gaps` call, not inferred.
- The refusals section MUST list any banned terms the user
  requested but the gate rejected.
- No secrets, tokens, patient identifiers, or full document
  contents in the report.
- ASCII only (project rule).
