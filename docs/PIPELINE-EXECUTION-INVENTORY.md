# Pipeline execution inventory (G0.0)

Catalogue of production, validation, training and analysis pipeline paths.
Migration disposition: **migrate** (unified runtime), **retain** (shared capability
only), or **retire**.

| Workflow ID | Trigger | Executor today | Queue | Migration |
|-------------|---------|----------------|-------|-----------|
| pd-referral-assessment | referral-received | DurableStepRunner (flagged) | pipeline-jobs | migrate (reference) |
| pd-gp-encounter-coding | encounter-created | Coding Worker WorkflowEngine | coding-jobs | migrate (Gate 4 U4.2) |
| pd-episode-bundle-coding | episode_bundle | Coding Worker WorkflowEngine | coding-jobs | migrate (Gate 4 U4.6) |
| pd-gold-training-audit | gold-audit-request | WorkflowEngine / API | varies | migrate (Gate 4 U4.3) |
| pd-val-key-fact-extraction | validation trigger | WorkflowEngine | pipeline-jobs | migrate (Gate 4 U4.4) |
| pd-val-pathway-criteria | validation trigger | WorkflowEngine | pipeline-jobs | migrate (Gate 4 U4.4) |
| pd-val-triage-completeness | validation trigger | WorkflowEngine | pipeline-jobs | migrate (Gate 4 U4.4) |
| pd-val-terminology-mapping | validation trigger | WorkflowEngine | pipeline-jobs | migrate (Gate 4 U4.4) |
| pd-val-sbar-summary | validation trigger | WorkflowEngine | pipeline-jobs | migrate (Gate 4 U4.4) |
| pd-referral-triage-e2e | validation trigger | WorkflowEngine | pipeline-jobs | migrate (Gate 4 U4.4) |
| Analysis Worker jobs | API / bus | analysis_worker analyzers | analysis queue | deferred (W-022; post-release) |

## Gate 4 remainder status (2026-07-22)

- **Migrated to durable_pubsub (seed + tests):** pd-gold-training-audit,
  pd-episode-bundle-coding, six validation plans, pd-referral-triage-e2e.
  Evidence: `tests/test_gate4_remainder_migration.py` (VT-F210824D).
- **Production validation runs:** enqueue `validation-run-requested` on
  pipeline-jobs (`extraction_scenarios.py`); not the sync runner.
- **Deferred (W-022):** `validation_workflow_runner.py` dev/dry-run sync path;
  analysis_worker queue jobs.

Pre-deploy: run `python -m scripts.seed_plan_definitions` on target Knowledge
Graph (see script docstring).

## Shared runtime contract (target)

All migrated workflows use:

- Atomic admission (`admission_key`, `ADMIT_PIPELINE_RUN`)
- Pinned manifest (Gate 2 M2.1; Atlas DI-B1E43400 / DO-3F7F7B7D)
- Per-stage lease + fencing generation (implemented)
- Fenced completion (`lease_owner`, `lease_generation`)
- Service Bus settlement policy (see below)
- First-step single enqueue (`CLAIM_FIRST_STEP_ENQUEUE`)

## Service Bus settlement policy (G6)

Under at-least-once delivery with competing consumers on `pipeline-jobs`:

| Outcome | Neo4j stage state | Service Bus action |
|---------|-------------------|-------------------|
| Step completed | `completed` | **Complete** message |
| Idempotent replay | `already_completed` | **Complete** message |
| Stage poisoned (max attempts) | `poisoned` | **Complete** message (terminal) |
| Lease busy (another worker) | unchanged | **Abandon** (defer redelivery) |
| Stale lease on complete (not yet done) | unchanged | **Abandon** (defer redelivery) |
| Stale complete recovered | `already_completed` | **Complete** message |
| Handler exception | may be `failed` | **Abandon** (retry until poison) |

Implementation: `libs/message_bus/settlement.py`,
`libs/workflow/stage_lease.py` (`StageLeaseBusyError`, `StageLeaseStaleError`),
`services/pipeline_worker/app/services/durable_dispatcher.py`,
`libs/message_bus/azure_adapter.py`.

### Environment variables (production defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PIPELINE_STAGE_LEASE_SECONDS` | 3600 | Neo4j stage lease TTL |
| `PIPELINE_STAGE_HEARTBEAT_SECONDS` | 120 | Lease renewal interval during long LLM steps |
| `SB_MAX_LOCK_RENEWAL_SECONDS` | 14400 | Azure Service Bus lock auto-renewal cap |
| `SB_MAX_CONCURRENT_CALLS` | 8 | Concurrent handlers per worker replica |
| `PIPELINE_STAGE_MAX_ATTEMPTS` | (store default) | Poison threshold after repeated abandon/redelivery |

Startup warns when heartbeat >= lease, lock renewal < lease, or lease < 300s
(`validate_pipeline_lease_config()` in `libs/message_bus/settlement.py`).

## Legacy paths to delete on cutover

- `libs/workflow/engine.py` synchronous in-process loop (Coding Worker)
- `DURABLE_ENGINE_ENABLED` ambiguous routing (Gate 4 U4.8)
- Deleted module imports in `tests/test_referral_durable_pubsub.py` (Gate 5 G5.1)
- Live Neo4j concurrency: optional `@pytest.mark.integration` (Gate 5 G5.3;
  see `docs/GATE5-TEST-POLICY.md`)

## Human review gates

| Surface | Control |
|---------|---------|
| SBAR Assessment | Advisory only; host contract (Gate 5 G5.10) |
| Gold training audit | human_gate capability |
| Coding review / Ask LEO | Mandatory reviewer before writeback |

Last updated: 2026-07-22 (Gate 4 remainder seeded; analysis worker deferred W-022).
