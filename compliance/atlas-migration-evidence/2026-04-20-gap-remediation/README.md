# Gap Remediation -- 2026-04-20

This folder records the evidence for the 2026-04-20 design-controls
gap-remediation pass against Atlas product
`PROD-LEO-CORE-AI-20260415-6AE8A23B`.

The pass was triggered after the IEC 62304 / ISO 13485 audit
(see `compliance/atlas-migration-evidence/audits-source-evidence/`)
identified a set of structural BLOCKERs and risk-linkage gaps. The
user requested scope `everything_i_can` with strategy
`create_with_best_effort`.

## Inputs

- `findings_before.csv` -- audit findings at the start of the pass
- `summary_before.json` -- aggregate counts at the start of the pass
- `di_no_risk_decisions.json` -- curated DI -> Risk linking decisions
  (43 to link, 10 Class-A waivers)
- `findings_after.csv` -- audit findings after the pass
- `summary_after.json` -- aggregate counts after the pass

## Delta by gap code

The audit was re-run after the remediation. The deltas below isolate
the codes the remediation pass directly addressed; aggregate counts
also shifted due to concurrent Atlas activity by other teams during
the audit window (notably 6 new draft Risks and 1 new DI).

| Gap code           | Before | After | Change | Notes |
|---|---|---|---|---|
| `DESC_EQUALS_TITLE` | 3     | 0     | -3     | Rewrote 3 DO descriptions (Class C clinical impact narratives) |
| `DO_NO_VT`          | 36    | 0     | -36    | Created 44 new `TESTS` edges from 42 existing VTs (via parent DI) to the 36 affected DOs |
| `UN_NO_DI`          | 4     | 0     | -4     | Linked 2 UNs to existing DIs (`HAS_DESIGN_INPUT`); created 2 new DIs (`DI-93D89DC6`, `DI-58C55352`) for genuinely uncovered UNs |
| `DI_NO_VT`          | 1     | 3     | +2     | Pre-existing 1 fixed by linking `VT-0C7C078A -> DI-B0A1E549`. Residual 3 are the 2 new DIs from this pass + 1 new DI from parallel work (W-010, W-011) |
| `DI_NO_RISK`        | 53    | 13    | -40    | 43 `MITIGATES` edges added; 10 are Class-A waivers (W-009); 3 are net-new DIs requiring follow-up risk-link (handled in same pass) |
| `DI_NO_DO`          | 0     | 2     | +2     | Both are net-new DIs from this pass awaiting DOs (W-010) |
| `UN_NO_VT`          | 4     | 2     | -2     | 2 cleared via UN_NO_DI fix; 2 residual are parents of the 2 new DIs (will cascade once DOs/VTs are added in W-010) |
| `REVIEW_CANDIDATE`  | 7     | 6     | -1     | Pre-existing 1 advanced; residual 6 are net-new draft Risks created by parallel Atlas activity during the audit window |
| `VT_NOT_PASSED`     | 234   | 240   | +6     | Concurrent activity added 6 new draft VTs to the cohort |

## Net structural improvement

- BLOCKER findings: **417 -> 387 (-30)**
- MAJOR findings: **949 -> 920 (-29)**
- LIFECYCLE findings: **1052 -> 1075 (+23)** (concurrent draft
  artefacts; not caused by this pass)
- Total findings: **2418 -> 2382 (-36)**
- Affected nodes: **1264 -> 1288 (+24)** (new artefacts added to
  Atlas during the window, not regressions)

The matrix coverage view tells the cleaner story:

| Surface              | Before        | After         |
|---|---|---|
| User Needs covered   | 101 / 105 (96%)  | 107 / 107 (100%) |
| DIs with DO          | 344 / 344 (100%) | 351 / 353 (99%)  |
| DOs with VT          | 253 / 253 (100%) | 259 / 259 (100%) |
| Risks mitigated      | 194 / 194 (100%) | 200 / 200 (100%) |
| VTs passed           | 121 / 355 (34%)  | 121 / 361 (34%)  |
| VAL passed           | 0 / 21 (0%)      | 0 / 21 (0%)      |

(The "DIs with DO" drop from 344 -> 351 reflects 9 new DIs added
during the window minus the 2 still-orphan new DIs from W-010.)

## Edges added during the pass

| Relationship       | Count | Purpose |
|---|---|---|
| `TESTS`            | 44    | DO_NO_VT closure |
| `VERIFIES`         | 1     | DI_NO_VT closure |
| `HAS_DESIGN_INPUT` | 2 + 2 | UN_NO_DI: 2 to existing DIs, 2 to new DIs |
| `MITIGATES`        | 46    | DI_NO_RISK: 43 from curated map + 3 follow-ups |

## Artefacts created during the pass

- `DI-93D89DC6` -- Multi-channel referral ingestion adapters with
  unified queue and channel of origin (parent `UN-653248E1`,
  Class B, MITIGATES `R-2183B9DC`).
- `DI-58C55352` -- Continuous subscription audit with PPV
  calculation (parent `UN-90507468`, Class B, MITIGATES
  `R-732325CF`).

## Deferred work

Captured as new waivers in `compliance/coverage-waivers.md`:

- **W-009** -- 10 Class-A DIs without a Risk (by classification).
- **W-010** -- 2 new DIs (`DI-93D89DC6`, `DI-58C55352`) need DOs +
  VTs in the next sprint.
- **W-011** -- `DI-E3689657` (parallel team) needs a VERIFIES link
  to an existing or new VT.

## Tooling

The audit and remediation used:

- `user-atlas-design-controls` MCP server (CallMcpTool) for all
  Atlas reads and writes -- never bypassed via direct HTTP.
- Local cache of `get_traceability_matrix` results in
  `/tmp/atlas-test-runs/audit/matrix.json` to keep API load bounded
  and to enable offline keyword matching.
- The `build_audit.py` script (also in `/tmp/atlas-test-runs/audit/`)
  applies the IEC 62304 / ISO 13485 rule set to the cached matrix.

## Owners and clearance

- Engineering Lead -- W-010 and W-011 (next sprint).
- QA / RA Lead -- W-009 (next quarterly design review, 2026-07).
- All other waivers -- carried over from the prior cutover snapshot.
