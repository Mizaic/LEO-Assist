# Batch 08 -- UN-B9FDC3CA Surface forms dictionary

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 2 DIs covering surface-form CRUD with duplicate rejection + match
frequency, and the staging/review/versioning/rollback change gate.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-30D95132 | Surface form CRUD with match frequency and duplicate rejection | implemented | `services/terminology_api/app/routers/surface_forms.py` + `services/ui/src/app/settings/surface-forms/page.tsx` expose list/grouped/upsert/delete + duplicate audit. `AUDIT_SURFACE_FORM_DUPLICATES`/`DEDUPLICATE_SURFACE_FORM_RELS` provide duplicate handling. |
| DI-9FD54AD6 | Staging, review approval, versioning, and rollback for surface-form changes | missing | No staging state, no version history, no rollback. Greps for `SurfaceFormSet`, `surface_form.*version`, `staging|approval|review_gate|rollback` on the surface-forms router all return zero hits. `scripts/writeback_surface_form_mappings.py` edits live mappings directly. |

## Finding

DI-30D95132 is well covered: CRUD exists; duplicate detection/dedup exists;
match frequency is visible via the grouped list endpoint and the admin
surface-forms UI page.

DI-9FD54AD6 is a real gap. All writes in the current implementation flow
directly into the active KG. There is no draft -> staging -> approval -> active
state machine for surface-form sets, and no immutable snapshot/version to
roll back to. Given the downstream safety impact (bad surface forms corrupt
SNOMED coding), this is a must-fix.

## Atlas actions

- DO documenting current surface-form CRUD + duplicate audit.
- Backlog entry for the staging/version/rollback gate.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 1 |
| missing | 1 |
