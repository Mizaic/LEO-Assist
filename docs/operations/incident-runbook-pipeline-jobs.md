# Incident Runbook - Pipeline Jobs

## Trigger Conditions

- `pipeline-worker` consumer health endpoint reports `healthy=false`.
- Repeated `amqp:socket-error` / `Service Bus connection lost` logs.
- `pipeline-jobs` backlog or dead-letter queue growth.

## Step 1 - Confirm Blast Radius

1. Check `core-api` health endpoint.
2. Check `pipeline-worker` endpoints:
   - `/health`
   - `/health/consumer`
3. Confirm whether new run IDs are still progressing.

## Step 2 - Validate Queue State

1. Inspect active message count for `pipeline-jobs`.
2. Inspect dead-letter count for `pipeline-jobs/$DeadLetterQueue`.
3. If dead-letter count is increasing, capture top run IDs and error reasons.

## Step 3 - Validate Worker Runtime

1. Check latest worker revision status in Azure Container Apps.
2. Check restart counts and readiness probe failures.
3. Review logs for:
   - `Service Bus connection lost`
   - `Azure credential token expired`
   - `Pipeline Worker consumer loop failed`

## Step 4 - Triage Paths

## A) Connection instability

- Keep current revision if reconnect warnings are self-healing.
- Escalate if reconnect loop persists > 15 minutes.

## B) Credential/auth issue

- Validate managed identity assignment on `pipeline-worker`.
- Validate Key Vault and Service Bus role access.
- Recycle revision only after identity fix is confirmed.

## C) Poison messages/dead-letter growth

- Identify repeated failing message shape.
- Apply code/config mitigation in `dev` and `val`.
- Replay only messages confirmed safe to reprocess.

## Step 5 - Rollback Criteria

Rollback to previous image tag if any condition holds:

- Consumer unhealthy for > 30 minutes.
- Error budget exhausted for SLO 1 in the last 24 hours.
- New revision increases failure rate versus previous baseline.

## Step 6 - Post-Incident Evidence

- Incident start/end UTC timestamps.
- Impacted queue depth and failed runs.
- Root cause category: runtime, dependency, config, or data.
- Mitigation and follow-up ticket links.
- QA/RA note if safety-relevant processing was delayed.
