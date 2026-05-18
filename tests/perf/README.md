# Perf canaries (k6)

Canary load tests that smoke the production services after a deploy.
They exist to verify the Phase 0-6 backend concurrency overhaul keeps
holding under load -- not to drive the system to breaking point.

## Layout

| File | Target | What it asserts |
|---|---|---|
| `analytics_audit.js` | `/analytics/audit/*` | Dashboard endpoints stay <2s p95 with 25 VUs over 1 min |
| `core_health.js` | `/health` and `/api/proxy/...` | Core API + proxy stay healthy with 50 VUs over 1 min |
| `mission_control.js` | `/analytics/mission-control/*` | Mission Control list/KPI endpoints stay <2.5s p95 |

## Running locally

```bash
# Install k6 (Mac):
brew install k6

# Hit a local stack
BASE_URL=http://localhost:8000 \
SESSION_COOKIE='leo.session=...' \
k6 run tests/perf/core_health.js
```

## Running in CI

Wire into the post-deploy gate (after the smoke tests pass) so a
regression in p95 latency or error rate fails the rollout. Each script
exits non-zero when a `thresholds` block is breached, which CI picks up.

## Thresholds

The thresholds encode the targets agreed in
`design-controls/DC-PERF-001-backend-concurrency-overhaul.md` (when
written): see Phase 6 of the plan. Adjust per environment via env
vars (e.g. `P95_BUDGET_MS=3000`) rather than editing the scripts.
