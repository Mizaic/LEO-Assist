# Phase 13a - file <-> Atlas DO trace audit (read-only)

## Inputs

- 744 legacy ids resolved to Atlas dcIds
- Pre-deletion local YAMLs read from git SHA `fd295e7054092dcc8e9258167beff3259c2cf487`
- Migration ledgers in `compliance/atlas-migration-evidence/`

## Forward (file -> Atlas DO)

Class B+ source files scanned: **1400** (under `libs/` and `services/`, excluding tests)

| Header state | Files | Share |
|---|---:|---:|
| `atlas` (Atlas-format dcId in file) | 24 | 1.7% |
| `legacy` (only `*-LEO-AI-N` ids in file) | 387 | 27.6% |
| `none` (no design-control reference at all) | 989 | 70.6% |

Resolvable to at least one Atlas DI/DO via the migration ledgers: **482** files. Cannot resolve from any ledger: **918** files. (The unresolvable bucket is the population that needs new Atlas design controls or a per-file triage in Phase 13c.)

## Reverse (Atlas DO -> file)

Atlas DOs we have evidence for: **201** (out of 252 total in Atlas, per `get_design_control_stats`).

- DOs with recoverable file paths: 157
- DOs with no recoverable file paths in our ledgers: 44

**Atlas API gap:** `get_design_control` does not return `source_reference` even though `create_design_output` and `update_design_output` accept it. We cannot read back the values we wrote; the audit therefore reconstructs expected values from (a) pre-deletion local YAMLs, and (b) the Phase 8b bucket ledger. Phase 13b will rewrite `source_reference` from this CSV (using `update_design_output`) so the field is the canonical, current truth.

## Output files

- `phase13a-legacy-to-atlas.csv` - full legacy_id -> atlas_dcid table
- `phase13a-do-source-reference-audit.csv` - per-DO file evidence
- `phase13a-file-trace-audit.csv` - per-file trace state
