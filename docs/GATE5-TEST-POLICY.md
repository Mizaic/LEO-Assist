# Gate 5 test policy (G5.3)

How pipeline durability and concurrency tests run in CI versus optional live
Neo4j checks.

## Canonical in-memory suite (CI blocking)

These tests use `tests/helpers/claim_race_client.InMemoryClaimClient` and do
not require a live Patient Graph:

| Test file | Gate item | What it proves |
|-----------|-----------|----------------|
| `tests/test_pipeline_stage_claim_concurrency.py` | G5.3 | Single-flight claim under threads |
| `tests/test_pipeline_worker_competing_consumers.py` | G5.3 | Duplicate delivery executes once |
| `tests/test_pipeline_stage_poison.py` | G5.6 | Reclaim attempts and poison terminal |
| `tests/test_gate5_lease_chaos.py` | G5.6 | Crash / lease-expiry chaos |
| `tests/test_gate5_durable_replay.py` | G5.2 | Deterministic replay + stage hashes |
| `tests/test_gate5_extraction_equivalence.py` | G5.5 | Window size 1 vs 10 merge parity |
| `tests/test_gate3_security_isolation.py` | G5.8 | Trigger chunk + recall isolation |
| `tests/test_platform_conformance.py` | U4.7 | Plan snapshot conformance |

Run the full Gate 5 slice:

```bash
pytest tests/test_pipeline_stage_claim_concurrency.py \
  tests/test_pipeline_worker_competing_consumers.py \
  tests/test_pipeline_stage_poison.py \
  tests/test_gate5_durable_replay.py \
  tests/test_gate5_extraction_equivalence.py \
  tests/test_gate5_lease_chaos.py \
  tests/test_gate3_security_isolation.py \
  tests/test_platform_conformance.py \
  tests/test_referral_durable_pubsub.py \
  tests/test_durable_runner_referral_parity.py \
  -v --no-cov -m "not integration"
```

## Optional live Neo4j integration

`test_live_neo4j_concurrent_claim_exactly_one` in
`tests/test_pipeline_stage_claim_concurrency.py` is marked
`@pytest.mark.integration`.

Skip policy:

1. Skip when `NEO4J_URI` / `NEO4J_PATIENT_URI` or password env vars are unset.
2. Skip when the Patient Graph is unreachable (connectivity probe).
3. Never fail CI when credentials are absent -- the in-memory suite is the
   release gate.

Run live integration explicitly when credentials exist:

```bash
pytest tests/test_pipeline_stage_claim_concurrency.py -v -m integration
```

## Out of scope for this policy

- G5.9 Playwright VAL with real backend (manual / staging only).
- G0.3 clinician gold cohort adjudication.
- Atlas VT recording (see release blockers in Gate 5 proof report).
