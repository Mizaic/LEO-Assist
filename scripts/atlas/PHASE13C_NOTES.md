# Phase 13c -- Closeout

## Purpose

Close the bidirectional traceability loop on the code side: every
Class B+ source file in `libs/` and `services/` either carries a
canonical `Atlas trace:` header pointing at its owning Atlas Design
Output (DO) and parent Design Input (DI), or is explicitly
allow-listed for triage.

This is the final phase of the Atlas migration. After Phase 13c, a
file's design-control ownership is greppable in O(1):

- Forward trace: `Atlas trace: \n  DO: DO-XXXXXXXX` in the file
  points to its owner DO.
- Reverse trace: `get_design_control(dc_id="DO-XXXXXXXX",
  dc_type="design-output").designOutput.source_reference` lists the
  file (set in Phase 13b).
- Test trace: VTs / VAL files are governed by their own convention
  (`vt-enforcement.mdc`).

## Method

### 1. Atlas DI/DO traceability cache

`scripts/atlas/phase13c_build_atlas_cache.py` walks every unique
DI/DO id in `phase13a-file-trace-audit.csv` and fetches each via
`get_design_control(dc_id=..., dc_type=...)`. The script cached:

- 155 unique DOs (parent DIs + linked Risks for each).
- 43 unique DIs (child DOs + linked Risks for each).

Result lives in `compliance/atlas-migration-evidence/phase13c-atlas-cache.json`.
The script is idempotent and resumes after a 401 / network error.

### 2. Stamper

`scripts/atlas/phase13c_stamp_headers.py` reads the audit CSV plus the
cache and decides, for every Class B+ file:

| Decision | Action |
|----|----|
| `excluded` | Skip (test, `__init__.py`, `.d.ts`, `conftest.py`, etc.). |
| `already_atlas` | Skip (file already has the canonical block). |
| `stamped` | Insert / update the `Atlas trace:` block. |
| `triage` | Send to `phase13c-triage-queue.csv` (DO with no parent DI in cache, or DI-only with no resolvable child DO). |
| `unresolved` | Send to `phase13c-uncovered.csv` (no Atlas DI/DO via Phase 13a evidence). |

Resolution algorithm:

1. If `header_state == "atlas"` and the file already contains the
   `Atlas trace:` marker -> `already_atlas`.
2. If the audit row has at least one `owning_atlas_dos`, use that
   set; primary DO = lex-smallest, others go on `Also implements:`.
3. If the audit row has only `owning_atlas_dis`, look up child DOs in
   the cache; if found, use them; otherwise -> `triage`.
4. Pull parent DIs and Risks from the DO cache; union with any DIs
   the audit row already had.
5. Render the trace block in Python docstring or TS JSDoc form per
   `phase13a-header-convention.md`.

The stamper supports `--apply` (mutate files) and `--show-diffs N`
(dry-run with sample diffs). It is fully idempotent: re-running
makes zero changes.

### 3. CI gate

`scripts/atlas/check_atlas_trace_headers.py` is wired into
`.github/workflows/ci-build.yml` as a build-blocking step. It:

- Walks `libs/**` and `services/**` for `*.py | *.ts | *.tsx`.
- Skips the same exclusions the stamper uses.
- Loads two allow-lists:
  - `phase13c-uncovered.csv` (591 files Phase 13a couldn't resolve).
  - `phase13c-allow-list.csv` (8 files added after the Phase 13a
    snapshot; hand-maintained).
- Fails CI if any other file lacks the `Atlas trace:` marker.

### 4. Cursor rule

`.cursor/rules/atlas-trace-headers.mdc` documents the format, the
field rules, the create / move workflow, the exclusion list, and
the allow-list policy for in-IDE guidance.

## Results

| | Count |
|---|---|
| Class B+ files scanned | 1,400 |
| Excluded (tests / init / .d.ts) | 334 |
| Already had canonical Atlas block | 0 (post-stamp) |
| **Stamped with Atlas trace header** | **460** |
| Triage queue (3-way ambiguity) | 3 |
| Uncovered (no Atlas DI/DO in evidence) | 603 |
| Manual allow-list (post-13a-snapshot) | 8 |

CI gate verification: `python3 scripts/atlas/check_atlas_trace_headers.py`
returns:

```
Allow-list (uncovered): 599
Triage list:            3
Scanning 1073 Class B+ files...

Results:
  with Atlas trace:        460
  skipped (allow-list):    610
  skipped (triage queue):  3
  MISSING:                 0

OK: every Class B+ source file is traced or allow-listed.
```

## Outputs

- `compliance/atlas-migration-evidence/phase13c-atlas-cache.json`
  -- DI/DO traceability cache (155 DOs, 43 DIs).
- `compliance/atlas-migration-evidence/phase13c-ledger.csv`
  -- 1,400 rows; 1 per file decision.
- `compliance/atlas-migration-evidence/phase13c-triage-queue.csv`
  -- 3 rows: do-no-parent-di or di-only-no-child-do.
- `compliance/atlas-migration-evidence/phase13c-skipped.csv`
  -- 334 rows: tests, init files, declarations.
- `compliance/atlas-migration-evidence/phase13c-uncovered.csv`
  -- 603 rows: files with no migration ledger evidence (top buckets:
  `services/ui` 419, `services/api` 55, `services/design-system` 17).
- `compliance/atlas-migration-evidence/phase13c-allow-list.csv`
  -- 8 rows: files added after Phase 13a; need owning-DO triage.
- `scripts/atlas/phase13c_build_atlas_cache.py` -- pre-pass cacher.
- `scripts/atlas/phase13c_stamp_headers.py` -- the rewriter.
- `scripts/atlas/check_atlas_trace_headers.py` -- CI gate.
- `.cursor/rules/atlas-trace-headers.mdc` -- developer guidance.
- `.github/workflows/ci-build.yml` -- new "Atlas trace headers" step.

## Verification

- All 306 stamped Python files parse cleanly via `ast.parse` (no
  syntax breakage from the docstring rewrite).
- `npx tsc --noEmit` on `services/design-system` after stamping 149
  TS files: clean compile.
- Stamper idempotency: a second `--apply` run produces zero diff.
- CI gate: passes locally on the post-13c tree.

## Risks / known limitations

1. **603 uncovered files (43 % of Class B+)** are allow-listed but
   not traced. The vast majority are in `services/ui` and
   `services/api`. They were never linked to a local DI/DO in any
   migration ledger. Recommended follow-up: a bounded triage sprint
   per service (UI first, then API), where each service team adds
   the missing DO + DI in Atlas, then re-runs the stamper.
2. **8 post-snapshot files** in `phase13c-allow-list.csv` reference
   Atlas DIs inline but were added after Phase 13a ran. These need
   manual owning-DO triage; until then, the allow-list keeps CI
   green.
3. **3 triage queue files** flag real cache gaps:
   - `services/analysis_worker/app/analyzers/cancer_site_terms.py`
     and `_site_resolution.py`: their owning DO (DO-0DFA6961) has no
     parent DI in Atlas. Add a parent DI in Atlas and rerun.
   - `services/ui/src/app/care/encounters/page.tsx`: its DI
     (DO-F78C84A6, mis-keyed in audit) has no resolvable child DO.
4. **Inline dcId comments are not authoritative.** The stamper does
   NOT infer ownership from comments inside the code body; only the
   migration ledgers count. This is conservative on purpose.
5. **Phase 13b reconstruction tag.** All 157 DOs touched in Phase 13b
   carry the `[phase13b]` marker on `source_reference`. If a
   developer subsequently updates the DO with a fresher path list,
   they should drop the marker so a future drift detector can tell
   "reconstructed" vs "kept fresh."

## What's next

The Atlas migration is functionally complete. Open follow-ups, in
priority order:

1. **UI / API ownership triage** (the 603 uncovered files). This is
   Atlas-side work: create the missing DOs, link them to DIs, then
   re-run `phase13c_stamp_headers.py`.
2. **Triage queue resolution** (3 files). Add the missing parent DI
   / child DO links in Atlas; re-run the stamper.
3. **Allow-list churn-down** (8 post-snapshot files). For each row in
   `phase13c-allow-list.csv`, identify the owning DO in Atlas, set
   `source_reference`, then add the trace header and remove the
   allow-list row.
4. **Drift detector** (optional). A nightly job that diffs every
   Atlas DO's `source_reference` against the trace headers in the
   live tree. Files in the trace block but not in
   `source_reference` (or vice versa) become a small triage queue.
