# Pilot SLOs and Error Budgets

## Scope

These SLOs apply to the Azure Container Apps pilot deployment for:

- `core-api`
- `pipeline-worker`
- Azure Service Bus queue `pipeline-jobs`

## SLO 1 - Queue Consumption Continuity

- **Objective:** no silent stop in job consumption.
- **SLI:** percentage of 5-minute windows where `pipeline-worker` consumer health is
  `healthy=true` from `GET /health/consumer`.
- **Target:** 99.9% monthly.
- **Error budget:** 43.2 minutes/month.
- **Page threshold:** 2 consecutive failed windows (10 minutes).

## SLO 2 - Job Completion Reliability

- **Objective:** jobs complete without operator intervention.
- **SLI:** `completed_jobs / (completed_jobs + failed_jobs)` for
  `pipeline-jobs` run IDs in the period.
- **Target:** 99.0% weekly.
- **Error budget:** 1 failure per 100 jobs.
- **Page threshold:** completion reliability < 98% over 1 hour.

## SLO 3 - Queue-to-Start Latency

- **Objective:** fast processing start after queue enqueue.
- **SLI:** P95 of `(worker_start_ts - queue_enqueue_ts)` per job.
- **Target:** P95 <= 60 seconds.
- **Error budget:** 5% of jobs may exceed 60 seconds.
- **Page threshold:** P95 > 120 seconds for 3 consecutive checks.

## Telemetry Requirements

The pilot must emit:

- Consumer health payload from `pipeline-worker` (`/health/consumer`).
- Queue depth and dead-letter depth from Service Bus metrics.
- Job state transitions (`queued`, `running`, `completed`, `failed`) with run ID.
- Consumer reconnect warnings from `libs.message_bus.azure`.

## Incident Policy For Pilot

- Error budget burn > 25% in 24 hours -> freeze non-critical releases.
- Error budget burn > 50% in 24 hours -> run incident review, require QA/RA sign-off.
- Error budget exhausted -> rollback to last known good image tags.
