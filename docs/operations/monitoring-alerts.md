# Monitoring and Alert Baseline (Pilot)

## Alert Set

## 1) Pipeline consumer unhealthy

- **Signal:** `GET /health/consumer` returns `healthy=false`.
- **Scope:** `pipeline-worker`.
- **Severity:** P1 after 10 minutes continuous failure.
- **Action:** trigger runbook `incident-runbook-pipeline-jobs.md`.

## 2) Service Bus socket timeout/reconnect loop

- **Signal:** log match on `libs.message_bus.azure`:
  - `Service Bus connection lost`
  - `amqp:socket-error`
- **Severity:** P2, escalate to P1 if repeated over 15 minutes.
- **Action:** inspect identity token health, queue depth, and worker revisions.

## 3) Dead-letter queue growth

- **Signal:** `pipeline-jobs/$DeadLetterQueue` message count increasing.
- **Severity:** P1 if growth is monotonic for 30 minutes.
- **Action:** inspect failed run IDs and unblock poison message cause.

## 4) Queue backlog and latency

- **Signal:** queue active message count and P95 queue-to-start latency.
- **Severity:** P2 when SLO threshold exceeded.
- **Action:** scale worker replicas, inspect downstream dependencies.

## 5) Container restart/readiness failures

- **Signal:** ACA restart count and failed readiness probes.
- **Severity:** P2, escalate P1 if `core-api` or `pipeline-worker` unavailable.
- **Action:** check latest revision image, env vars, and Key Vault access.

## KQL Starter Queries (Log Analytics)

```kql
ContainerAppConsoleLogs_CL
| where Log_s contains "Service Bus connection lost"
   or Log_s contains "amqp:socket-error"
| project TimeGenerated, ContainerAppName_s, Log_s
| order by TimeGenerated desc
```

```kql
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "pipeline-worker"
| where Log_s contains "Pipeline Worker consumer loop failed"
| project TimeGenerated, Log_s
| order by TimeGenerated desc
```

```kql
ContainerAppSystemLogs_CL
| where ContainerAppName_s in ("pipeline-worker", "core-api")
| where Log_s contains "readiness" or Log_s contains "restart"
| project TimeGenerated, ContainerAppName_s, Log_s
| order by TimeGenerated desc
```
