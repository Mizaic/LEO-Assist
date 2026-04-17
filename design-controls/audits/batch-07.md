# Batch 07 -- UN-AE5B5691 Canary model rollout

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 2 DIs covering canary traffic split with audit-trail tagging, and
automatic halt/rollback on per-entity F1 regression.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-A557AE91 | Configurable traffic split + audit-trail tagging of canary runs | partial | `libs/model_registry/registry.py` supports canary lifecycle (start_canary, record_canary_result, promote, rollback). No traffic-split mechanism found (greps for `traffic_split|traffic_percentage|canary_traffic` return zero hits). |
| DI-7D710C52 | Automatic halt and rollback on per-entity F1 regression | partial | Gate uses aggregate precision + recall (`_MIN_CANARY_PRECISION`, `_MIN_CANARY_RECALL`) but no per-entity F1 threshold check. `libs/pipeline/label_filter.py` evaluates entity F1 but is not wired into rollback. |

## Findings

### DI-A557AE91 (partial)

Canary state machine exists, cohort tagging exists (`canary_cohort`), but the
system does not split production traffic between active and candidate models
at runtime. Inference path always uses the single active version.

### DI-7D710C52 (partial)

`ModelRegistry._MIN_CANARY_PRECISION` and `_MIN_CANARY_RECALL` gate promotion
but not rollback. Rollback is triggered manually. No per-entity-type F1 check.

## Atlas actions

- DO placeholder documenting the current canary lifecycle in
  `libs/model_registry/registry.py`.
- Backlog entries for traffic-split and per-entity F1 rollback.

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 0 |
| partial | 2 |
