# Durable Pipeline Steps

Production clinical workflows should use durable pub/sub steps instead of
passing one in-memory state dict through a whole pipeline run.

Each durable step must:

- Receive only IDs, scope, and run metadata in the queue message.
- Load clinical inputs from Neo4j using those IDs.
- Persist a `PipelineStageRun` before publishing the next event.
- Persist typed outputs such as `DOCUMENTS`, `GuidelineResult`,
  `CompletenessResult`, or `Assessment`.
- Emit a completion or failure progress event with the same `run_id`.
- Use `run_id:step_id` as the idempotency key unless a stronger key is
  explicitly documented.

`pd-referral-assessment` is the first production workflow using this pattern.
It persists clinical facts before SBAR so `SBAROrchestrator` can reload
graph-backed evidence and guideline results.

New production workflows must not use the legacy `sbar` subgraph or rely on
`inputSource: previous_step` as their primary data contract.
