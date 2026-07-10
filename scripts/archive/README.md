# Archive -- retired ad-hoc scripts

Retired one-off debug / data-fix / trigger scripts that used to live at the
repo root. Zero references were found in `start_leo-ai-core.{sh,ps1}`, CI
workflows (`.github/workflows/`), docs, or any other supported code path as
of 2026-07.

**Not maintained.** Do not rely on anything in this directory. If you need
the capability one of these scripts used to provide, use instead:

- `pytest tests/` for the real test suite.
- The admin / Data Quality (DQ) toolkit endpoints (`/admin/dq/*`) or the
  `leo-dq` MCP server for ad-hoc data inspection and fixes.
- `scripts/` (outside this `archive/` folder) for supported operational
  scripts.

This follows the same precedent as
[`scripts/investigations/DEPRECATED.md`](../investigations/DEPRECATED.md),
which retired a similar generation of one-off investigation scripts in
favour of the DQ toolkit.

## What's here

| Group | Files | Original purpose |
|---|---|---|
| DB / gold data fixes | `fix_db.py`, `fix_db2.py`, `fix_db3.py`, `clean_gold.py`, `restore_gold.py`, `migrate_gold_schema.py`, `force_sync_neo4j.py` | Iterative one-off patches to `ExtractionScenario` expected-strings fixtures and Neo4j sync. |
| Run triggers / pollers | `trigger_run.py`, `trigger_run2.py`, `trigger_run3.py`, `trigger_run_mock.py`, `poll_run.py` | Ad-hoc kickers and pollers for extraction scenario runs, superseded by the pipeline API and admin UI. |
| Dev utilities | `check_coding.py`, `_gpu_test.py`, `run_auth_bypass.py` | Local terminology probes, GPU/CuPy preflight checks, and an incomplete auth-bypass stub. |
| Debug / investigation scripts | `test_cache_serialization.py`, `test_context_scope.py`, `test_db_expected.py`, `test_db_score.py`, `test_db_type.py`, `test_entities.py`, `test_extraction.py`, `test_ferritin.py`, `test_ferritin2.py`, `test_ferritin3.py`, `test_full_val.py`, `test_match.py`, `test_match2.py`, `test_neo4j_ferritin.py`, `test_queries.py`, `test_redis.py`, `test_routing.py`, `test_score.py`..`test_score6.py`, `test_term.py`, `test_term_client.py`, `test_terms.py`, `test_tokenizer_fix.py`, `test_why_mismatch.py`, `test_ui_error.sh` | One-off spaCy/ConText experiments, direct Neo4j probes, scoring/match inspectors against specific fixture cases. Not part of the real `pytest tests/` suite despite the `test_` prefix. |

## Retirement schedule

Following the `scripts/investigations/DEPRECATED.md` pattern:

- **Cycle 1 (current, 2026-07)**: Moved here from repo root.
- **Cycle 2**: Delete after confirming no team member has an active need for
  any of these as a reference.
