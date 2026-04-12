# Pilot Go/No-Go Checklist

## Reliability Gate

- [ ] `pipeline-worker` `/health/consumer` remains healthy for 24h burn-in.
- [ ] No unresolved P1 incidents in the previous 72 hours.
- [ ] Queue dead-letter growth is stable and understood.

## Deployment Gate

- [ ] Target release uses immutable `sha-*` image tags.
- [ ] CD smoke checks pass after deployment in target environment.
- [ ] Rollback runbook tested using previous known-good tag.

## Observability Gate

- [ ] Alerts configured for consumer health, queue backlog, dead-letter, and restarts.
- [ ] On-call rota is assigned for pilot hours.
- [ ] Runbook owners confirmed for pipeline and auth incidents.

## Security and Compliance Gate

- [ ] Pilot traceability check passes for in-scope DIs.
- [ ] Any waivers are documented with owner and expiry date.
- [ ] Key Vault, managed identity, and TLS controls validated in target environment.

## Product and Ops Gate

- [ ] Pilot cohort (orgs/users) approved and documented.
- [ ] Support channels and escalation contacts shared with pilot users.
- [ ] Hypercare cadence (daily review) scheduled for first 7-14 days.

## Decision

- **Go** only when all mandatory gates are complete.
- If any mandatory gate is open, record **No-Go**, owner, and target completion date.
