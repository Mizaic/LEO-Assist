# Phase 7 - Reverse Traceability Discovery (closeout)

Read-only audit. No Atlas mutations. Re-runnable via:

```bash
python3 scripts/atlas/phase7_reverse_discovery.py
```

## Inputs

- Atlas baseline snapshot: `design-controls/atlas-baseline-2026-04-19/traceability-matrix.json`
  (866 nodes: 262 DI, 159 R, 156 DO, 89 UN, 21 VAL, 179 VT)
- Local artefact YAMLs: `design-controls/{design-inputs,design-outputs,verification-tests}/`
  - All local DOs were migrated to Atlas in Phase 3 (130 DOs in
    `phase9-do-migration.csv`, 100% with `atlas_id`).
  - All local DIs/VTs were migrated in Phases 1/2/3.
- Repo source manifest from `services/`, `libs/`, `scripts/`, `services/ui/src/`.

## Coverage rule

A source file is "covered" if any local DI/DO/VT YAML references either:

1. The exact relative path, or
2. A directory ancestor (path with no recognised file extension).

A bare file reference does **not** cover its parent directory; only explicit
directory references do (this fixes a previous over-coverage bug).

## Outputs

| File | Rows | Purpose |
|---|---|---|
| `design-controls/phase7-implementation-manifest.csv` | 1,562 | Every product source file with size and service bucket |
| `design-controls/phase7-reverse-traceability-gaps.md` | -- | Per-service gap report split by safety class |
| `design-controls/phase7-reverse-traceability-gaps.csv` | 654 | Machine-readable uncovered files |
| `design-controls/phase7-candidate-risks.md` | -- | Pattern-sweep candidate risks with Atlas de-dup |
| `design-controls/phase7-candidate-risks.csv` | 238 | Machine-readable risk candidates |

## Headline numbers

| Bucket | Total | Uncovered | LoC |
|---|---|---|---|
| All product code (Class B+) | 1,022 | **144** | **22,841** |
| `scripts/` (Class A, internal tooling) | 540 | 510 | 104,948 |
| `services/ui/` (covered by directory-level UI DI) | 554 | 0 | 0 |
| **Repo total** | 1,562 | 654 | 127,789 |

### Class B+ uncovered hot-spots (most LoC)

| Bucket | Files uncovered | LoC | Notes |
|---|---|---|---|
| `libs/prompts` | 30 | 4,871 | Prompt templates and few-shot examples; some genuinely undocumented |
| `libs/cypher` | 17 | 2,135 | Read query builders; org_id scoping happens at the service layer |
| `libs/ner` | 8 | 2,082 | NER post-processors and lab-triple recovery |
| `services/neo4j_mcp` | 15 | 1,900 | Neo4j MCP server (recently added) |
| `services/fhir_api` | 9 | 1,727 | Benchmark, Schema, Activity Definition routes |
| `services/analytics_api` | 6 | 1,567 | Algorithm runner condition/patient/helpers |
| `libs/model_registry` | 4 | 1,394 | Registry, neo4j_registry, training_adapter |

### Class A (informational only)

`scripts/` -- 510 uncovered files / 104,948 LoC. Per
`design-controls-first.mdc` proportionality gate, internal tooling does not
require a full DI/DO/VT chain. Phase 8 will not create artefacts for these
unless the user explicitly requests it.

## Candidate risks (pattern sweep)

Patterns scanned (in uncovered files only):

| Pattern | Hits | Notes |
|---|---|---|
| `missing_org_scope` | 227 | `MATCH (Patient)` without `org_id` in 25-line window. Most are in `libs/cypher/` query builders where the caller injects org context |
| `raw_phi_logging` | 10 | `logger.*(patient_id)`. Note: `patient_id` is an internal opaque ID, not NHS number. Still recommended to suppress in INFO logs |
| `raw_llm_passthrough` | 1 | One auto-code = True hit in scripts/ |

Zero hits at >= 0.75 similarity to existing Atlas risks. The two genuine
candidates (multi-tenant query helper de-scoping, and PHI-adjacent log
patterns) need to be re-probed against live Atlas in Phase 8 before any
`create_risk` call.

## Known false-positive sources removed

- The discovery script's own files (`scripts/atlas/phase*.py`) are excluded
  from the risk sweep so its regex literals do not match themselves.
- Lines that look like `re.compile(...)` or raw-string regex literals are
  skipped.
- `missing_org_scope` lines are skipped if `org_id` appears in a 25-line
  window before/after the `MATCH (Patient)` line.

## Phase 8 plan (next, mutating)

For each Class B+ uncovered hot-spot bucket, in priority order:

1. Re-probe Atlas via live MCP (search_design_controls + suggest_merge) for
   each uncovered file's likely DI title; create only the genuinely missing
   ones.
2. Bucket files into capability-grouped DIs (avoid one DI per file when
   files form a single feature, e.g. all `libs/cypher/*_queries.py` for a
   single read-side concern roll up to one DI).
3. Create matching DOs and link `IMPLEMENTS` to parent DI.
4. Create VT shells for any tests already passing in `tests/` that exercise
   the new DI; call `record_verification_run` for each pass.
5. Re-probe each candidate risk against live Atlas; create only the ones
   that survive a second similarity check at >= 0.55 (looser than discovery
   threshold because live corpus may have drifted).

Phase 8 will produce its own ledger CSVs and PHASE8_NOTES.md.
