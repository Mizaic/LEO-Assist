# Batch 06 -- UN-1AC15812 Training-label audit

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Scope: 3 DIs covering the training-label audit agent: bounded auto-fix +
human review queues, resource bounds, and the SNOMED-defect safety gate.

## Inventory

| DI | Title (short) | Verdict | Evidence |
|----|---------------|---------|----------|
| DI-CFA65509 | Automated training-label audit with bounded auto-fix + review queues | missing | No implementation found. `services/training_worker/app/` has trainer / exporter / evaluator modules but no audit-agent module |
| DI-54D00E21 | Audit agent resource bounds (iteration + token/cost budgets) | missing | N/A; depends on DI-CFA65509 agent |
| DI-922114AE | Safety gate: SNOMED coding defects always routed to human review | missing | N/A; `libs/audit/kg_verified_writeback.py` enforces a separate writeback-quality gate but no training-label audit agent exists to route defects |

## Finding

None of the three DIs in this phase are implemented. The `services/training_worker/`
module contains only the ML training + label export paths; there is no agentic
audit module that walks through training labels, applies safe auto-fix rules,
and routes defects to a human queue.

This is a documentation/plan-only feature set; the DIs describe a subsystem
that has not been built yet. Given the safety-critical nature (SNOMED coding
defects must never be auto-corrected), it is correct that no partial
implementation exists that might silently auto-fix SNOMED codes.

## Atlas actions

- Mark all three DIs as not-yet-implemented via backlog entries.
- No DOs created (no code to document).
- Design-time artefact: the DIs stand as forward specifications; capture
  the architecture constraints:
  - SNOMED defects -> always review queue (`DI-922114AE`).
  - Resource budget enforcement per `run_id` (`DI-54D00E21`).
  - Safe-fix rule set must be explicitly allowlisted (`DI-CFA65509`).

## Verdict summary

| Verdict | Count |
|---------|-------|
| implemented | 0 |
| partial | 0 |
| missing | 3 |
