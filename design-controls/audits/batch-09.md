# Batch 09 -- UN-4AEB2F29 SNOMED release management

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 2 DIs covering the active SNOMED CT version endpoint and the
release-diff + blocking resolution workflow.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-553F50A2 | Active SNOMED CT version endpoint | missing | No `/snomed/version` or equivalent endpoint in `services/terminology_api/app/routers/`. `effective_time` is loaded per concept (`snomed_concept.py`) but not exposed as an active release version. |
| DI-B193C816 | Release diff with blocking resolution workflow | missing | Loader scripts in `services/terminology/scripts/loaders/` import releases directly into the active graph. No diff computation, no disposition records, no blocking gate. |

## Finding

SNOMED release management as specified is not implemented. The system supports
per-concept `effective_time` and can load a release, but no versioned release
entity is stored, no delta is computed against the prior active release, and
there is no blocking workflow that forces disposition of each diff row before
activation.

## Atlas actions

- No DOs created (no implementing code).
- Backlog entries for both DIs.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 0 |
| missing | 2 |
