# NG12 fixtures sprint -- Atlas traceability (read-only spike)

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`.

This note satisfies sprint task **NG12-AT-004** before Class B changes ship.
Use the **`user-atlas-design-controls`** MCP server for authoritative lookups.

## Surfaces touched by NG12 fixture work

| Surface | Code / data | Typical Atlas link |
|--------|-------------|--------------------|
| Guideline bitmap evaluation | `GuidelineEvaluator`, `GuidelineCompiler` | Search `design_input` for guideline / suspected cancer / NG12 |
| SNOMED extraction parsing | `LLMExtractor._parse_terms` | Search `design_input` for extraction / coding worker |
| SBAR recommendation LLM call | `call_recommendation` in `libs/sbar/prompt_calls.py` | Search `design_input` for SBAR |

## Actions before Class B code changes

1. Call `search_design_controls(query="guideline evaluator", dc_type="design_input")`
   and confirm a linked **DO** + **VT** for bitmap behaviour you change.
2. Call `search_design_controls(query="extraction", dc_type="design_input")`
   for parser or schema changes on `ExtractedTerm`.
3. Call `search_design_controls(query="SBAR", dc_type="design_input")`
   for recommendation prompt or contract changes.

If a DI exists without **VERIFIES** VT: create VT + link per
`.cursor/rules/atlas-vt-enforcement.mdc`.

## Fixture-only edits

Pure JSON updates under `tests/fixtures/ng12_scenarios/` that **do not** change
test assertions or production code still need the **nearest DI** confirmed as
non-overlapping with safety behaviour, but typically do not require new Atlas
artefacts.

## Verification tests added in this sprint

- `tests/test_ng12_scenario_fixtures.py` -- JSON schema / pairing (Class A)
- `tests/test_ng12_scenario_extraction.py` -- `_parse_terms` on 348 rows (Class B if DI covers extraction)
- `tests/test_ng12_scenario_bitmaps.py` -- bitmap assertions for `active` rows (Class B)
- `tests/test_ng12_scenario_live_resolver.py` -- optional integration (Class A)

Record `record_verification_run` against the VT UUID (not dcId) after each
Class B test file change per project rules.
