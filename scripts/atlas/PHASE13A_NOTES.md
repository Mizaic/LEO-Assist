# Phase 13a - read-only file <-> Atlas DO trace audit

Status: COMPLETE (read-only)
Run date: 2026-04-20
Pre-deletion git SHA used to recover local YAMLs: `fd295e7054092dcc8e9258167beff3259c2cf487`

## Purpose

Establish the size, shape and resolvability of the gap between source
code and Atlas Design Outputs before any mutating Phase 13b/13c run.
Specifically: how many code files are traceable to an Atlas DO today,
how many can be traced via the migration ledgers, and how many cannot
be traced at all.

## Method

1. Built an authoritative `legacy_id -> atlas_dcid` map by joining
   five ledgers from the migration:
   - `atlas-id-mapping.csv` (Phases 0-3 UN/DI/DO/VT/VAL)
   - `phase10-risk-migration.csv` (Phase 4 risks)
   - `phase10-inflight-ledger.csv` (Phase 10 in-flight UN/DI/DO/VT/R)
   - `phase9-ledger.csv` (Phase 9a orphan-DI close DOs)
   - (Phase 9b only created VTs, so no DO mapping is added)
2. Recovered the file paths each Atlas DO covers from three sources:
   - The pre-deletion local DO YAMLs (`implementation.artifacts[].location`,
     `source_paths`, `implementation.technical_details.file_structure`).
   - The pre-deletion local DI YAMLs (`technical_details.file_structure`),
     used as fallback for DOs whose own YAML did not list files.
   - The Phase 8b reverse-discovery bucket ledger
     (`phase8b-ledger.csv` + `phase8a-truly-uncovered.csv`).
3. Walked every Class B+ source file in `libs/` and `services/`
   (extension `.py`, `.ts`, `.tsx`, `.js`, `.jsx`; tests, node_modules,
   `__pycache__`, `.next` excluded) and classified its trace state.

## Atlas API gap (recorded as a known limitation)

`get_design_control(dc_type="design-output", ...)` does NOT return
`source_reference` even though `create_design_output` and
`update_design_output` accept it. We can write the field but cannot
read it back via any of `get_design_control`,
`get_traceability_matrix`, or `search_design_controls`. Phase 13a
therefore reconstructs `source_reference` evidence from local
ledgers and the pre-deletion git tree rather than from Atlas live
state. Phase 13b will then use this evidence to (re)write the field
on every DO so the Atlas-side value is the canonical, current truth.

## Results

### Forward (file -> Atlas DO)

Class B+ source files scanned: **1400**

| Header state | Files | Share |
|---|---:|---:|
| `atlas` (Atlas-format dcId in file) | 24 | 1.7% |
| `legacy` (only `*-LEO-AI-N` ids in file) | 387 | 27.6% |
| `none` (no design-control reference at all) | 989 | 70.6% |

| Resolution | Files |
|---|---:|
| Resolvable to >= 1 Atlas DI/DO via the migration ledgers | 482 |
| Cannot be resolved from any ledger | 918 |

### Reverse (Atlas DO -> file)

Atlas DOs we have evidence for: **201** (out of 252 total DOs in
Atlas, per `get_design_control_stats`).

- DOs with recoverable file paths: 157
- DOs with no recoverable file paths in our ledgers: 44
- DOs with NO ledger evidence at all: 51 (likely Phase 2
  unmatched-create DOs that were stub-created in Atlas without
  being tied to a file).

## Outputs

All under `compliance/atlas-migration-evidence/`:

- `phase13a-legacy-to-atlas.csv` -- 744 rows; full
  `legacy_id -> atlas_dcid` table with `kind`, source ledger and
  migration phase. This is the canonical lookup for Phase 13b/13c.
- `phase13a-do-source-reference-audit.csv` -- 201 rows; per-Atlas-DO
  recovered file paths and which migration phase wrote them.
- `phase13a-file-trace-audit.csv` -- 1400 rows; per-file trace state,
  legacy ids found, mapped Atlas DI/DO, Phase 8 bucket info.
- `phase13a-summary.md` -- machine-rendered summary of the run.
- `phase13a-header-convention.md` -- the in-file `Atlas trace:`
  header spec the Phase 13c rewriter will follow (Python + TS).

## Gating decision for Phase 13b/13c

Phase 13a confirms the gap is real and resolvable for ~34% of files
without further Atlas changes:

- **Phase 13b is unblocked.** We have file-path evidence for 157 of
  201 Atlas DOs and can write `source_reference` immediately.
  The remaining 44 DOs (in our ledgers but with no file paths)
  and 51 DOs (with no ledger evidence) become a **review queue** -
  triage manually, then either wire to a file via `update_design_output`
  or retire via `retire_design_control` if they are stale.
- **Phase 13c is partly unblocked.**
  - 387 files (`legacy`) -- safe to rewrite legacy ids -> Atlas
    dcIds where the legacy id appears in `phase13a-legacy-to-atlas.csv`.
    The rewriter must defer (not silently strip) any unmapped legacy
    id.
  - 482 files (resolvable, regardless of header state) -- safe to
    add the canonical `Atlas trace:` block at the top of the file.
  - 918 files (unresolvable) -- do NOT auto-add a header.
    Add to `phase13c-uncovered.csv` for human triage, and to a
    backlog item for "create new Atlas DO covering these files".

## Risks identified during 13a

- The Atlas read-side `source_reference` gap (above) makes our
  Phase 13b run authoritative-by-write. If anyone has been editing
  `source_reference` via the Atlas UI directly since Phase 10,
  Phase 13b will overwrite their value with our reconstructed list.
  Mitigation: phase13b will always include the existing legacy
  source_reference text we can derive from the local YAMLs, plus
  a "Phase 13b reconstruction" tag, so any concurrent edit is
  visible in `update_design_output`'s audit trail.
- The 51 Atlas DOs with no ledger evidence at all are most likely
  Phase 2 stub DOs. Listing them up-front in 13a means 13b can
  surface them as a `cso-review-needed` row rather than try to write
  a fictional `source_reference`.
- 918 unresolvable files is large because most are `__init__.py`,
  type-only, or generated. The 13a header convention skips those
  classes by design; the residual unresolvable list (after applying
  the convention's exclusion rules) is the real backlog and will be
  tabulated in 13c, not now.

## Next step

Phase 13b (mutating, Atlas-side):

1. For every row in `phase13a-do-source-reference-audit.csv` with
   `expected_source_path_count >= 1`, call
   `update_design_output(dc_id=<atlas_dcid>, source_reference="<paths>")`.
2. For every row with `expected_source_path_count == 0`, append to
   `phase13b-review-queue.csv`.
3. For every Atlas DO not present in the audit (the 51 stubs), call
   `get_design_control` once to record current state, then add to
   `phase13b-review-queue.csv` with note `no ledger evidence; likely
   Phase 2 stub`.
4. Idempotent ledger at `phase13b-ledger.csv`.

Phase 13c (mutating, code-side) follows 13b once the source_reference
field is the canonical truth in Atlas.
