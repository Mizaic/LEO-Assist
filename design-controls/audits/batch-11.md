# Batch 11 -- UN-55011459 Review queue and RBAC

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 2 DIs covering a unified RBAC-scoped review queue across all AI
proposal types, and RBAC enforcement across review/finalise actions.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-890BE989 | Unified review queue grouped by proposal type with structured reviewer corrections | partial | `libs/cypher/coding_review_queries.py` (CodingReview), `libs/cypher/surface_form_task_queries.py` provide per-type queues; there is no single union endpoint that presents all AI proposal types in one role-filtered queue; reviewer corrections are stored as TrainingLabel/CodingReview edges for coding path, but not uniformly for all proposal types |
| DI-E83828A9 | RBAC enforcement for all AI output review/finalise actions | missing (enforcement gap) | `libs/auth/role_state.py` + `libs/cypher/role_queries.py` define canonical roles and RoleSwitch audit; `services/api/app/routers/guidance_rules.py` and `nice_guidance.py` carry docstring "require ai.admin" but no Depends() on an auth dependency enforces it. Grep for `Depends(.*auth|Depends(.*role` returns zero hits. |

## Finding

Role state is modelled and switchable. Role-based access is documented in
router docstrings but not enforced at the API layer. This is a significant
audit gap (reviewer and finaliser actions require enforced RBAC).

A unified review queue does not exist; each proposal type (coding review,
surface-form task, etc.) has its own data path. A reviewer cannot pull
"everything I am authorised to review" from a single endpoint.

## Atlas actions

- DO documenting per-type review-queue Cypher.
- Backlog entries: unified queue; RBAC dependency on write/finalise endpoints.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 0 |
| partial | 1 |
| missing | 1 |
