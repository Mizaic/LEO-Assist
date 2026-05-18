# Security Remediation 2026-04-20 -- Phase 5 Atlas Evidence

This document captures the verification evidence for the Phase 1 Atlas
scaffold (one User Need, six Design Inputs, six Risks, six Design
Outputs, and six Verification Tests) created for the
`security/remediation-2026-04-20` work.

## Test evidence (file-level)

All Phase 2 and Phase 3 fixes are covered by static-source verification
tests that run in CI:

| Path | Scope |
|------|-------|
| `tests/test_security_remediation_2026_04.py` | 42 pytest cases covering every Phase 2 and Phase 3 backend fix, the GHA workflow hardening, the docker-compose loopback bind, and the `secrets.zip` removal. |
| `services/ui/src/__tests__/security-remediation-static.test.ts` | 14 jest cases covering the auth callback redirect guard, the mail iframe sandbox, and the DOMPurify sanitisation. |

Both suites pass locally:

```
pytest tests/test_security_remediation_2026_04.py -q
# 42 passed in 0.06s

cd services/ui && npx jest --testPathPatterns "security-remediation-static" --no-coverage
# 14 passed
```

## Atlas verification runs

All six VTs from Phase 1 now have a `record_verification_run` with
`result="pass"`, `executed_by="security-remediation-2026-04-20"`, and
`environment="local"` recorded against them on 2026-04-20T12:26-12:27Z.

| Cluster | DI | DO | VT | UUID | Run id |
|--------|----|----|----|------|--------|
| API authorisation and tenant scoping | DI-6B05CC05 | DO-7FC83480 | VT-87B42D9B | `87b42d9b-ee92-442d-8200-e0d99d84fd92` | VERUN-87b42d9b-ee92-442d-8200-e0d99d84fd92-20260420122627 |
| Internal service auth and CORS | DI-FFF37760 | DO-444819D8 | VT-96BF21B7 | `96bf21b7-f895-47a0-bf79-57076a130bb6` | VERUN-96bf21b7-f895-47a0-bf79-57076a130bb6-20260420122634 |
| Cypher allowlist and SSRF | DI-181A2F08 | DO-F4884F5A | VT-726B36FF | `726b36ff-0174-444a-a94a-e3957d2c2fb2` | VERUN-726b36ff-0174-444a-a94a-e3957d2c2fb2-20260420122640 |
| CI/CD pipeline integrity | DI-71087A9E | DO-6036D724 | VT-2F4E1B2C | `2f4e1b2c-a201-46aa-9870-462822849bdc` | VERUN-2f4e1b2c-a201-46aa-9870-462822849bdc-20260420122647 |
| Frontend redirect and sanitisation | DI-8239C932 | DO-E645DE13 | VT-1C38A76B | `1c38a76b-b52a-47a6-8398-b0ebae1afe98` | VERUN-1c38a76b-b52a-47a6-8398-b0ebae1afe98-20260420122658 |
| Defensive hardening | DI-894D904C | DO-CA39B561 | VT-1FA06EB9 | `1fa06eb9-59b2-4706-97fb-ef3f5829aabd` | VERUN-1fa06eb9-59b2-4706-97fb-ef3f5829aabd-20260420122708 |

Parent UN: `UN-FA198FC9` (`fa198fc9-c375-4efb-9c0d-11cf3d797af3`).

## Traceability gap check

`get_traceability_gaps(product_id="PROD-LEO-CORE-AI-20260415-6AE8A23B")`
on 2026-04-20T12:27Z returned no orphans for any of the six new DIs or
six new DOs. The remaining `orphan_design_inputs` and
`orphan_design_outputs` entries are pre-existing legacy items unrelated
to this remediation and are tracked separately.

## Why this evidence record exists

- Atlas search (`search_design_controls`) returned truncated payloads
  for several queries during this session; the VT UUIDs were recovered
  by querying each VT's dcId individually via `get_design_control`.
- The runs above were recorded with the recovered UUIDs and Atlas
  returned `executionStatus: "passed"` for all six.
- This file documents the chain from each test suite to the Atlas run
  id, so any future audit can follow it without re-running the
  workflow.
