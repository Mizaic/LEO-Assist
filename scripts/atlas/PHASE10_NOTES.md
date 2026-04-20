# Phase 10 closeout - local design-controls cutover

Status: complete
Date: 2026-04-20
Atlas product: PROD-LEO-CORE-AI-20260415-6AE8A23B

## Goal

Atlas is now the single source of truth for design controls. Phase 10
moves every non-MCP-shaped governance / policy / evidence document out
of the local `design-controls/` tree, deletes every MCP-shaped local
YAML (UN, DI, DO, VT, VAL, Risk) now that Atlas holds the canonical
copy, and removes the `design-controls/` directory entirely.

## What was done

### 1. Created the new layout

- `compliance/` (top-level) is the new home for governance, policy,
  superseded architecture sources, design-review minutes, prompts,
  verification-report evidence, and the Atlas migration evidence.
- `data/training/` is the new home for runtime training fixtures
  (the SBAR golden set + the manual gold seed) which were never
  design controls but were colocated under `design-controls/`.

### 2. Migrated 9 in-flight YAMLs to Atlas

A concurrent dev workstream had authored 9 untracked YAMLs after the
main reconciliation completed (the episode-status vocabulary + NCDA
cancer-type + MECE lifecycle bug-fix programme). These were migrated
to Atlas via `scripts/atlas/phase10_inflight_migrate.py` before any
deletion.

| Local ID            | Atlas dcId   | Notes                                         |
|---------------------|--------------|-----------------------------------------------|
| UN-LEO-AI-099       | UN-8225F9E1  | Engine and dashboard agree on episode status  |
| UN-LEO-AI-100       | UN-B5BE2BD1  | Hero cards give a MECE lifecycle view         |
| UN-LEO-AI-101       | UN-A2F0AE7F  | Cancer types use the canonical NCDA vocabulary|
| DI-LEO-AI-529       | DI-D14B711F  | Canonical EpisodeOfCare status vocabulary     |
| DI-LEO-AI-530       | DI-5CAC6D73  | Canonical NCDA cancer-type vocabulary         |
| DI-LEO-AI-531       | DI-105A4EC7  | MECE lifecycle classifier for hero cards      |
| DO-LEO-AI-529       | DO-AC244024  | Canonical EpisodeOfCare status implementation |
| VT-LEO-AI-527       | VT-C45C6AC7  | 13-case contract test, run recorded as pass   |
| R-LEO-AI-515        | R-DD9B8F9B   | Episode-status vocabulary drift (mitigated)   |

DI-530 and DI-531 have no DO/VT/Risk yet in Atlas - they were
incomplete in the local YAMLs too. Captured in
`compliance/coverage-waivers.md` as a follow-up.

### 3. git mv of non-MCP-shaped files

Nothing was lost. Every local file was preserved under one of:

| New location                                             | Contents                                               |
|----------------------------------------------------------|--------------------------------------------------------|
| `compliance/policy/`                                     | 20 governance / regulatory / process docs (DPA, DPIA, DTAC, NDOO, SOUP, etc.) plus the original `intended-use.md` |
| `compliance/architecture-superseded/`                    | 7 source docs that were consolidated into the Atlas SAD in Phase 6 (kept for audit chain) |
| `compliance/design-reviews/`                             | 5 design-review minute YAMLs (DR-LEO-AI-001..005) |
| `compliance/prompts/`                                    | 3 LLM prompts used during the local design control authoring |
| `compliance/verification-reports/`                       | The single VTR-LEO-AI-046-EXEC-001 verification report |
| `compliance/atlas-migration-evidence/`                   | atlas-id-mapping.csv, all 26 phase*.csv/md ledgers, the read-only Atlas baseline snapshot from 2026-04-19, and the audits + risks workshop evidence |
| `data/training/sbar-golden-set/`                         | Runtime SBAR fixtures (was `design-controls/training-data/sbar-golden-set/`) |
| `data/training/manual-gold-seed-2026-04-17.yaml`         | Runtime gold seed (was `design-controls/training-data/`) |

### 4. Deletions

After preservation, the following were deleted via `git rm -rqf`:

- `design-controls/user-needs/`            (101 YAMLs)
- `design-controls/design-inputs/`         (262 YAMLs)
- `design-controls/design-outputs/`        (236 YAMLs)
- `design-controls/verification-tests/`    (244 YAMLs)
- `design-controls/validation-tests/`      (15 YAMLs)
- `design-controls/risks/`                 (179 YAMLs after the 9 in-flight YAMLs were migrated)
- `design-controls/templates/`             (10 YAML schemas - now obsolete)
- `design-controls/README.md`              (auto-generated artefact tables - replaced by Atlas)
- `design-controls/DC-TM-001-traceability-matrix.md`  (replaced by Atlas `get_traceability_matrix`)
- `design-controls/DC-TM-002-traceability-matrix.csv` (replaced by Atlas `get_traceability_matrix`)

Total deletions: 1,047 MCP-shaped YAMLs + 13 obsolete supporting files.

### 5. design-controls/ directory removed

The empty `design-controls/` directory was removed via `rmdir`.

## Reference paths going forward

| Old path                                       | New path / source of truth                                      |
|------------------------------------------------|-----------------------------------------------------------------|
| `design-controls/user-needs/UN-LEO-AI-*.yaml`  | Atlas `get_design_control` / `search_design_controls` (UN-*)    |
| `design-controls/design-inputs/DI-LEO-AI-*`    | Atlas (DI-*)                                                    |
| `design-controls/design-outputs/DO-LEO-AI-*`   | Atlas (DO-*)                                                    |
| `design-controls/verification-tests/VT-LEO-AI-*` | Atlas (VT-*)                                                  |
| `design-controls/validation-tests/VAL-LEO-AI-*`  | Atlas (VAL-*)                                                 |
| `design-controls/risks/R-LEO-AI-*`             | Atlas (R-*)                                                     |
| `design-controls/DC-TM-001-traceability-matrix.md` | Atlas `get_traceability_matrix`                              |
| `design-controls/DC-ARCH-001-system-architecture.md` | Atlas SAD `get_software_architecture_document` + preserved source under `compliance/architecture-superseded/` |
| `design-controls/training-data/`               | `data/training/`                                                |
| `design-controls/{audits,prompts,design-reviews,verification-reports}/` | `compliance/{atlas-migration-evidence/audits-source-evidence,prompts,design-reviews,verification-reports}/` |
| Any other `design-controls/*` policy doc       | `compliance/policy/`                                            |

## Known follow-ups (not blocking cutover)

1. Code references to `design-controls/` paths: 1,242 changed files
   in this commit are renames; production code in `libs/`, `services/`,
   `scripts/`, `tests/`, `docs/`, `.cursor/rules/` etc. still has
   string references to old paths. These get rewritten in Phase 12.
2. Cursor rules (`.cursor/rules/design-controls-first.mdc`,
   `vt-enforcement.mdc`, `design-controls-validation.mdc`) still
   point at the deleted local tree. These get rewritten in Phase 11.
3. DI-LEO-AI-530 and DI-LEO-AI-531 (NCDA cancer-type, MECE classifier)
   landed in Atlas without DO/VT/Risk; flagged on
   `compliance/coverage-waivers.md` for follow-up.

## Outputs

- `compliance/atlas-migration-evidence/phase10-inflight-ledger.csv`
  (idempotency ledger for the 9 in-flight YAMLs)
- `scripts/atlas/phase10_inflight_migrate.py` (the migration script;
  resumeable via the ledger)
- This file: `scripts/atlas/PHASE10_NOTES.md`
