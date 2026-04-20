# Phase 13b -- Closeout

## Purpose

Write the recovered `source_reference` evidence from Phase 13a onto every
Atlas Design Output (DO) we have file-path evidence for, and triage the
DOs we cannot prove a file path for.

This closes one half of the bidirectional traceability loop:

```
[code file] -> (Phase 13c, next) -> [Atlas DO via Atlas dcId in header]
[Atlas DO]  -> (Phase 13b, this) -> [code file via source_reference]
```

## Method

Driver: `scripts/atlas/phase13b_write_source_reference.py`.

Inputs:

- `compliance/atlas-migration-evidence/phase13a-do-source-reference-audit.csv`
  -- 201 Atlas DOs with reconstructed file paths.
- `get_traceability_matrix(product_id)` from Atlas -- live DO index.

For each DO in the audit with `expected_source_path_count >= 1`:

```
update_design_output(
    dc_id="DO-XXXXXXXX",
    source_reference="<sorted; semicolon-separated paths> [phase13b]",
)
```

The trailing `[phase13b]` tag is the marker that:

- this value was reconstructed from migration ledgers, not authored
  directly during a code change; and
- a future drift detector can spot DOs whose `source_reference` is still
  the Phase 13b reconstruction vs DOs that have been kept fresh by
  developers as part of normal Class B work.

For each DO in the audit with `expected_source_path_count == 0`:

- skip the write;
- append to `phase13b-review-queue.csv` with category
  `ledger-but-no-paths`.

For each Atlas DO **not** present in the 13a audit:

- append to `phase13b-review-queue.csv` with category `not-in-audit` and
  the note `no ledger evidence; likely Phase 2 stub`.

The script is idempotent: every action is journalled to
`phase13b-ledger.csv` (kind = update | review | error). Re-running the
script skips DOs whose ledger row already records a successful decision.

## Atlas API gap (corrected)

Phase 13a documented an apparent gap: `source_reference` was not
returned by `get_design_control` or `get_traceability_matrix`. While
verifying the first Phase 13b write, the cause was identified:

- `get_design_control` requires **both** `dc_id` and `dc_type`. With
  `dc_type="design-output"` it returns the full record including
  `source_reference` (and the camelCase variant `sourceReference`).
- `get_traceability_matrix` does not surface `source_reference` for
  every DO -- this is still a real gap if you want to audit the
  whole product in one call -- but per-DO reads are fine.

The Phase 13a evidence files remain authoritative because:

- they were reconstructed from local YAMLs and ledgers, not from Atlas;
- they are the single source we can prove is *complete* for the 201
  DOs that originated from migration phases.

## Results

- Atlas DOs (live): 253
- DOs in 13a audit: 201
- DOs updated with `source_reference [phase13b]`: **157**
- DOs skipped (audit row has no file paths): 44
- DOs not in audit (likely Phase 2 stubs): 52
- Errors: 0

Spot check: `get_design_control(dc_id="DO-0289F3A5", dc_type="design-output")`
returns:

```
source_reference: libs/pipeline_graph/subgraphs/_extractor.py;
  libs/prompts/extraction_v1.py;
  services/coding_worker/app/pipeline/llm_extractor.py [phase13b]
```

## Outputs

- `compliance/atlas-migration-evidence/phase13b-atlas-do-index.csv`
  -- 253 rows, every Atlas DO with `in_phase13a_audit` flag.
- `compliance/atlas-migration-evidence/phase13b-ledger.csv`
  -- 253 ledger rows (1 per DO touched), idempotency journal.
- `compliance/atlas-migration-evidence/phase13b-review-queue.csv`
  -- 96 rows total:
  - 44 `ledger-but-no-paths` -- DOs with audit evidence but no file
    paths (the originating local YAML never declared
    `implementation.artifacts[].location` or
    `technical_details.file_structure`).
  - 52 `not-in-audit` -- DOs that exist in Atlas but have no record
    in any migration ledger; almost all are bare Phase 2 stubs that
    were created to satisfy DI traceability without listing files.

## What Phase 13c can now rely on

- For 157 DOs (78 % of the 201 migrated DOs, 62 % of all live DOs),
  the Atlas DO record now points at a concrete, sorted list of source
  files. Phase 13c can use these as the canonical owner-DO mapping
  when stamping headers into source files.
- For the 482 source files with at least one resolvable Atlas DI/DO
  in `phase13a-file-trace-audit.csv`, Phase 13c can compute the
  required header purely from the Phase 13a + 13b evidence -- no
  additional Atlas writes are required.
- The 95 DOs in the review queue should be deferred to a human
  triage pass; Phase 13c will not synthesise file paths for them.

## Risks / known limitations

1. **No write happens for the 44 + 52 DOs.** If a developer changes
   any of those DO areas later, they should set `source_reference`
   directly via `update_design_output` rather than waiting for another
   reconstruction pass.
2. **Some Phase 13b paths may be slightly stale.** The recovered
   paths are from the local YAMLs as of the pre-deletion SHA
   (`fd295e7054092dcc8e9258167beff3259c2cf487`). Files that were
   subsequently moved or renamed will resolve via Phase 13c's
   file-presence check; missing files will be flagged into a Phase
   13c-side queue.
3. **Bucketed DOs from Phase 8b** (where one DO covers many files)
   could produce very long `source_reference` strings. The script
   bounds the field to 4000 chars (sufficient for every current row;
   max observed is well under that).

## Gating decision for Phase 13c

Phase 13c (code-side mutation) is now ready to start:

- Authoritative DO -> file mapping: `phase13b-ledger.csv` (+ the
  audit CSV for the underlying paths).
- Authoritative file -> DI/DO mapping: `phase13a-file-trace-audit.csv`.
- Header convention: `phase13a-header-convention.md`.

Recommended Phase 13c order:

1. Stamp headers on the 482 files where Phase 13a already resolved a
   single owner DI/DO (the unambiguous case).
2. Triage the remaining 918 files into either `multiple-owners`,
   `class-A-skip`, or `add-to-13b-review-queue`.
3. Add a CI rule (and a `pre-commit` hook) that requires every
   Class B+ source file to either carry a valid `Atlas trace:`
   header or be in an explicit allow-list.
