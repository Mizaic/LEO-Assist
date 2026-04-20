# Atlas Baseline Snapshot - 2026-04-19

Read-only Atlas state captured at the start of the reconciliation cutover.
Source of truth: `PROD-LEO-CORE-AI-20260415-6AE8A23B`.

## Files

- `design-control-stats.json` -- output of `get_design_control_stats`
- `traceability-gaps.json` -- output of `get_traceability_gaps`
- `traceability-matrix.json` -- output of `get_traceability_matrix` (full nodes + coverage; ~2.2 MB)
- `cso-review-queue.json` -- output of `get_cso_review_queue` (top 50 by RPN, includes approved)

## Atlas vs local headline numbers

| Type | Atlas total | Local YAML count | Net gap |
|---|---|---|---|
| User Needs | 89 | 98 | -9 |
| Design Inputs | 262 | 259 | +3 (and 109 need AC merge per phase3-di-merge-gap.md) |
| Design Outputs | 156 | 234 | -78 (mostly the deferred-no-parent group) |
| Verification Tests | 179 | 242 | -63 |
| Validation Tests | 21 | 15 | +6 |
| Risks | 159 | 212 | -53 |

## Atlas link coverage today

| From | Linked | Total | Coverage |
|---|---|---|---|
| UN -> DI | 84 | 89 | 94% (5 UN orphans) |
| UN -> VAL | 58 | 89 | 65% |
| DI -> UN | 262 | 262 | 100% |
| DI -> DO | 258 | 262 | 98% (4 DI orphans listed below) |
| DI -> VT | 261 | 262 | 99% (1 DI without VT) |
| DI -> VAL | 0 | 262 | 0% (VAL->DI link is unused on this product) |
| DO -> DI | 156 | 156 | 100% |
| DO -> VT | 45 | 156 | 29% (large gap -- Phase 3 work) |
| VT -> DI | 179 | 179 | 100% |
| VT -> DO | 44 | 179 | 25% (large gap -- Phase 3 work) |
| VAL -> UN | 21 | 21 | 100% |
| VAL -> DI | 0 | 21 | 0% (matches DI side) |
| Risk -> UN | 159 | 159 | 100% |
| Risk -> DI | 159 | 159 | 100% |

## VT execution state (concerning)

- Total VTs: 179
- Passed: 3 (1.7%)
- Failed: 0
- Not executed: 176

**Implication:** Phase 3 must run `record_verification_run(result="pass")` for every local VT YAML whose `execution_history[-1].result == "pass"`. This is a major Phase 3 sub-task.

## Risk CSO state

All 50 risks sampled from the queue have `cso_status: null` and `queue_reason: "new"`.

**Implication:** Phase 4 risk migration will NOT need `unlock_risk_for_edit` calls because no risks are CSO-approved yet. This simplifies the migration script considerably.

## Orphan Design Inputs (4)

These DIs have no DO linked. Phase 3 will close these:

- `DI 17aa6900` - Consensus arbitrator third-verdict warning for anomaly detection
- `DI 7736f734` - Care Overview PageIntro and accessible summary card typography
- `DI ec96f102` - Lab-value guard prevents diagnostic inference from observable measurements
- `DI f93acedb` - Avoidable delay assessment with cause classification and impact calculation

## Orphan User Needs (5)

The matrix shows 5 UNs missing DIs (warning gap from `traceability-matrix.json`).
Will be enumerated during Phase 2 triage.

## Next phase entry criteria

Phase 1 is unblocked. The platform fix for `update_design_input(rationale=...)` is in place and the Atlas baseline is captured. Begin per-DI AC + rationale merge against the 109 rows in `phase3-di-merge-gap.md`.
