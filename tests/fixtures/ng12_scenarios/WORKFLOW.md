# NG12 scenario fixtures -- author workflow

This folder holds **348** paired scenario rows across three JSON files.
IDs share the same numeric suffix:

- `NG12-GDL-NNN` -- [`ng12_guideline_scenarios.json`](ng12_guideline_scenarios.json)
- `NG12-EXT-NNN` -- [`ng12_extraction_scenarios.json`](ng12_extraction_scenarios.json)
- `NG12-SBR-NNN` -- [`ng12_sbar_scenarios.json`](ng12_sbar_scenarios.json)

Source clinical text: [`reports/nice_ng12_raw/ng12_full.json`](../../reports/nice_ng12_raw/ng12_full.json).

## 1) SurfaceForm lookup (knowledge graph)

Use the **`user-leo-neo4j`** MCP server (Cursor MCP). Prefer named tools over raw Cypher.

1. Call **`search_surface_forms`** with the plain phrase you plan to put in an
   `encounter_note` (e.g. `haemoptysis`, `rectal mass`, `visible haematuria`).
2. If no hit, try a shorter head term, then call **`run_cypher_knowledge`**
   only when no named tool covers the question.

**Never invent a fake surface form** only to make tests pass. If the graph has
no form, record the gap in a backlog item and leave `_graph_status: not_coded`
or omit the phrase until terminology authors add the form.

## 2) Field: `surface_forms_in_graph` (EXT rows)

Optional but required for **non-stub** extraction rows once the phrase is
verified in Neo4j.

Shape (array of objects):

```json
[
  {"form": "haemoptysis", "concept_id": "66857006", "concept_fsn": "Hemoptysis (finding)"}
]
```

Use `concept_id` as the SNOMED CT identifier string (digits). Use `concept_fsn`
from the graph `Concept` node when available; otherwise a standard preferred
term is acceptable for fixture documentation.

## 3) Field: `expected_entities` (EXT rows)

Each object links parser output to terminology:

- `text` -- substring aligned with the LLM `text` field
- `lookup_term` -- normalised resolver key (must match graph SurfaceForm when present)
- `semantic_tag` -- `finding` / `disorder` / `situation` as emitted by the extractor test payload

## 4) Field: `_graph_status` (GDL rows)

Enum:

- `active` -- an `AppropriatenessRule` with this `graph_rule_id` is **active**
  in Neo4j **and** the CI bitmap tests compile this rule (see
  `tests/test_ng12_scenario_bitmaps.py`).
- `pending_review` -- rule exists but is not `active`, or not yet in the golden
  bitmap harness.
- `not_coded` -- no authored AppropriatenessRule; bitmap assertions are skipped.

## 5) Field: `expect_graph_match` (GDL rows)

- `true` -- patient_age + `patient_snomed_codes` must satisfy the compiled rule.
- `false` -- same rule id applies but this branch is a **negative** case.
- `null` / omitted -- do not run bitmap assertion for this row (rule not in harness).

## 6) Regenerating rows from definitions

After editing branch logic in
[`scripts/rebuild_ng12_scenario_fixtures.py`](../../scripts/rebuild_ng12_scenario_fixtures.py),
run:

```bash
.venv/bin/python scripts/rebuild_ng12_scenario_fixtures.py
```

Then run:

```bash
.venv/bin/python -m pytest tests/test_ng12_scenario_*.py -v
```

## 7) Optional live terminology check

Set **`TERMINOLOGY_API_URL`** (non-empty) so `tests/test_ng12_scenario_live_resolver.py`
resolves **every** unique `lookup_term` from EXT rows against that API base.

If `TERMINOLOGY_API_URL` is unset or blank, pytest **skips** the live test with
a clear reason (NG12-AT-optional-live).

## 8) Surface form backlog -- chapter 1.1 (NG12-AT-005)

These EXT rows (paired GDL 001-037) intentionally have **empty**
`surface_forms_in_graph` until `search_surface_forms` confirms a graph form:

- NG12-EXT-001 (cxr_suggests_lung_cancer)
- NG12-EXT-007 (cxr_finding_encoded_not_plain_cough)
- NG12-EXT-017 (supraclavicular_nodes_age_40_plus)
- NG12-EXT-018 (cervical_lymphadenopathy_age_40_plus)
- NG12-EXT-019 (chest_signs_lung_cancer_age_40_plus)
- NG12-EXT-020 (thrombocytosis_age_40_plus)
- NG12-EXT-023 (cxr_suggests_mesothelioma_refer)
- NG12-EXT-031 (pleural_disease_signs_age_40)
- NG12-EXT-034 (alternative_pleural_encoding_1)

Do not fake `SurfaceForm` rows for these phrases; file a terminology backlog
item and fill `surface_forms_in_graph` when the graph is updated.
