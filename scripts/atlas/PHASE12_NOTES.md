# Phase 12 - Repo cleanup of `design-controls/` references

Status: COMPLETE

## Goal

Sweep the repo for residual `design-controls/` references left over from
the Atlas migration (Phases 0-11) and rewrite them so production code,
docs and CI no longer point at the deleted local YAML tree.

## Scope

`design-controls/` was deleted in Phase 10. Anything still pointing at
it was either:

- **Production code or docs** with stale paths (must be rewritten).
- **Cursor rules** with stale checklists (rewritten in Phase 11; final
  trim-up here).
- **Migration / investigation scripts** that read the now-deleted tree
  (moved to `compliance/atlas-migration-evidence/scripts/` or deleted).
- **Frozen historical evidence** (left untouched on purpose).

## Triage results

### Updated: production code paths

| File | Change |
|---|---|
| `scripts/seed_sbar_test_patients.py` | `SBAR_DIR` and docstring/fixture_path -> `data/training/sbar-golden-set/` |
| `scripts/run_sbar_golden_set.py` | `DEFAULT_FIXTURES_DIR` and `--fixtures-dir` help text -> `data/training/sbar-golden-set` |
| `scripts/seed_manual_gold_records.py` | Docstring + usage examples -> `data/training/manual-gold-seed-2026-04-17.yaml` |
| `libs/cypher/test_patient_queries.py` | Comment -> `data/training/sbar-golden-set/` |

### Updated: production code references to artefacts

| File | Change |
|---|---|
| `libs/analytics/cohorts.py` | Pointer -> `compliance/atlas-migration-evidence/audits-source-evidence/improvements-backlog.md` (historical reference; canonical risk lives in Atlas) |
| `libs/clinical_scoping/specialty_markers.py` | Audit-snapshot pointer -> `compliance/atlas-migration-evidence/audits-source-evidence/snapshots/...`; clarified DI-LEO-AI-138 is a legacy id and the canonical entry is in Atlas |
| `tests/episode_engine/test_audit_relevance_filter.py` | Module docstring now points at the Atlas VT (legacy id VT-LEO-AI-522) and `atlas-id-mapping.csv` |
| `tests/episode_engine/test_window_partitioner.py` | Same as above for VT-LEO-AI-523 |

### Updated: docs

| File | Change |
|---|---|
| `services/api/README.md` | Traceability paragraph rewritten to point at Atlas MCP + `get_traceability_matrix` |
| `docs/usability/README.md` | Reference list -> `compliance/policy/intended-use.md` and the Atlas SAD |
| `docs/usability/USABILITY-ENGINEERING-PROMPT.md` | Same |
| `docs/nlp-pipeline/VERIFICATION-REPORT.md` | Pointer rewritten to Atlas MCP product id |
| `docs/DATA-ACCESS-AUDIT-EVIDENCE.md` | All evidence-table rows rewritten: policy docs -> `compliance/policy/`, threat models -> `compliance/architecture-superseded/`, UN/DI/Risk/VT/VAL rows -> `get_design_control(...)` calls |

### Updated: Cursor rules (final trim)

| File | Change |
|---|---|
| `.cursor/rules/code-quality.mdc` | Definition of done rewritten - now references Atlas VT lookups (`get_design_control`, `record_verification_run`, `get_traceability_gaps`) instead of local VT YAMLs and TM CSVs |
| `.cursor/rules/ui-testing.mdc` | Same treatment for the UI definition of done |

### Updated: build / CI

| File | Change |
|---|---|
| `.dockerignore` | `design-controls/` -> `compliance/` |

### Moved: historical migration / investigation scripts

| From | To |
|---|---|
| `scripts/build_atlas_id_mapping.py` | `compliance/atlas-migration-evidence/scripts/build_atlas_id_mapping.py` |
| `scripts/audits/_build_inventory.py` | `compliance/atlas-migration-evidence/scripts/audits_build_inventory.py` |
| `scripts/audits/_assign_batches.py` | `compliance/atlas-migration-evidence/scripts/audits_assign_batches.py` |

`scripts/audits/` directory removed.

### Deleted: throwaway investigation scripts

These scripts read YAMLs in the now-deleted `design-controls/` tree and
have no live consumer; the same data is now obtainable via Atlas MCP.

- `scripts/investigations/_check_dis.py`
- `scripts/investigations/_find_di_for_extraction.py`

### Left untouched (intentional)

- `scripts/atlas/**` and `scripts/atlas/PHASE*_NOTES.md` - the migration
  scripts and closeout notes. They are evidence of the migration; their
  references to `design-controls/` reflect the world they ran against.
- `compliance/atlas-migration-evidence/**` - frozen evidence bundle for
  the migration (CSVs, MD ledgers, snapshot caches).
- `evidence-bundles/LEO-AI/verification/VT-LEO-AI-189/live-run-20260418/README.md`
  - frozen verification evidence.
- `.cursor/plans/close_security_gaps_a290bc3c.plan.md` - past plan.
- `.cursor/rules/atlas-design-controls-first.mdc`,
  `atlas-design-controls-validation.mdc` - new rules; the
  `design-controls/` references are the deliberate
  old-path -> Atlas-tool mapping table.
- `.cursor/rules/design-controls-first.mdc`,
  `vt-enforcement.mdc`,
  `design-controls-validation.mdc` - intentional redirect stubs.

## Verification

```
$ rg -l "design-controls/" \
    --glob '!compliance/**' \
    --glob '!scripts/atlas/**' \
    --glob '!evidence-bundles/**' \
    --glob '!.cursor/plans/**' \
    --glob '!.cursor/rules/**'
# (no output)

$ rg -l "design-controls" Makefile *.toml .github/ 2>/dev/null
# (no output)
```

All remaining hits are in frozen evidence, intentional Cursor-rule
mapping tables, or migration scripts. Production code, docs, tests
and `.dockerignore` no longer point at the deleted tree.

## Outcome

Phase 12 closes the design-controls migration. Every live consumer of
the old `design-controls/` directory now points at either:

- the Atlas MCP server (`user-atlas-design-controls`, product
  `PROD-LEO-CORE-AI-20260415-6AE8A23B`), via `get_design_control`,
  `get_traceability_matrix`, `get_traceability_gaps`,
  `record_verification_run` and friends; or
- the post-migration local homes - `compliance/policy/`,
  `compliance/architecture-superseded/`,
  `compliance/atlas-migration-evidence/`, or `data/training/`.

The 13-phase Atlas reconciliation programme is complete.
