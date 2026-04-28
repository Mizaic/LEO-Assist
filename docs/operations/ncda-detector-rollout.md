# NCDA detector rollout and v2 sunset

Atlas trace:
- DI: NCDA-DI-MIG ("Cancer-suspect routing must be flag-controlled and reversible.")
- DO: NCDA-DO-MIG (`libs/feature_flags.py::NCDA_DETECTOR`,
  `tests/ncda/test_feature_flag_routing.py`).

## Routing decision

The NCDA detector replaces `episode_detector_v2` for cancer pathways only.
A patient is considered **cancer-suspect** when at least one encounter scores
`role_p >= 0.5` for FTR or Dx in the role classifier (Stage 4 output).

Routing is controlled by the `ncda_detector` flag:

| flag value | who runs the NCDA detector | publishing |
| --- | --- | --- |
| `off` (default) | nobody | n/a; v2 unchanged |
| `shadow` | every patient | NCDA writes to `NCDALabelAudit`/`NCDARunShadow` only; v2 still publishes |
| `on` | cancer-suspect patients only (FTR or Dx p >= 0.5) | NCDA publishes for cancer-suspects; v2 publishes for everyone else |

Per-tenant overrides:

```bash
export NCDA_DETECTOR=shadow                # default for all tenants
export NCDA_DETECTOR__TENANT_PILOT=on      # one pilot tenant only
```

## Sunset criteria for episode_detector_v2 (cancer paths)

Three gates must all hold across two consecutive nightly evaluations
(Stage 11 + Stage 12):

1. **Linked-pair recovery** on the tidied reviewed cohort >= the
   `episode_detector_v2` Jaccard baseline.
2. **Cohort-3 false-alarm rate** below the agreed threshold (initial
   target: <= 0.10 on the held-out evaluation set).
3. **Attached-SEEN** match-rate **and** **attached-TREATMENT** match-rate
   against tidied reviewed milestones each >= 0.90.

Sunset checklist:

- [ ] Two consecutive nightly evaluations meet the three gates.
- [ ] `nightly_run_log` shows zero drift alerts on `1a`, `1b`, `2`, `3`
      cohort precision (Stage 11 `detect_drift`).
- [ ] QA/RA lead signs off in `:NCDALabelAudit` admin tile.
- [ ] Flip flag default to `on` and remove cancer paths from
      `episode_detector_v2` (separate PR, kept reversible).

## Rollback

Set `NCDA_DETECTOR=off`. v2 resumes for cancer paths immediately.
No data loss: NCDA outputs are stored on dedicated nodes (`NCDAPathway`,
`NCDALabelAudit`, `NCDARunShadow`) so removing them is a Cypher delete on
those labels only.
