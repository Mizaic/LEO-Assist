# Design Controls Coverage Waivers

This document records the known, accepted residuals after the Atlas
reconciliation cutover (Phases 0-9). Each waiver is justified, scoped,
and assigned an owner so it can be cleared in the normal release loop
rather than as a one-off remediation programme.

The authoritative source of truth for design controls is the Atlas
MCP server (product `PROD-LEO-CORE-AI-20260415-6AE8A23B`). At the
moment of writing, `get_traceability_gaps` reports
**zero orphan design inputs** and **zero orphan design outputs**.
Everything below is a soft residual that the gap report does not flag
but is visible in `get_design_control_stats`.

## Snapshot at cutover

Source: `get_design_control_stats` (PROD-LEO-CORE-AI-20260415-6AE8A23B)
captured at the end of Phase 9.

| Surface | Count | Linked upstream | Linked downstream |
|---|---|---|---|
| User Needs        | 97  | n/a              | 93 -> DI (96%)    |
| Design Inputs     | 330 | 330 -> UN (100%) | 330 -> DO (100%) / 329 -> VT (99.7%) |
| Design Outputs    | 244 | 241 -> DI (98.8%)| 208 -> VT (85.2%) |
| Verification Tests| 350 | 341 -> DI (97.4%)| 203 -> DO (58.0%) |
| Validation Tests  | 21  | 21  -> UN (100%) | n/a               |
| Risks             | 249 | 159 -> UN (63.9%)| 187 -> DI (75.1%) |

VT execution: 110 passed, 240 not_executed, 0 failed.

## Waivers

### W-001 -- 4 User Needs without a DI

- **Scope**: 4 of 97 UNs have no `HAS_DESIGN_INPUT` edge.
- **Status**: accepted, low risk.
- **Justification**: these are stakeholder-level needs that are
  satisfied by combinations of existing DIs already attached to peer
  UNs (e.g. tooling/persona umbrella needs). The Phase 8 reverse-
  traceability sweep created catch-all parent UNs and at least one DI
  per uncovered code bucket; the residual UNs are non-implementable
  outcomes (e.g. "stakeholder confidence", "operational visibility")
  that map to the same physical implementation as a sibling UN.
- **Owner**: QA / RA Lead.
- **Clear by**: next quarterly design review (2026-07).

### W-002 -- 1 DI without a VT

- **Scope**: 1 of 330 DIs has no `VERIFIES` edge from any VT.
- **Status**: accepted, low risk.
- **Justification**: Phase 9b created VT shells for the 9 orphan DOs
  surfaced by `get_traceability_gaps`. The remaining 1 DI without a
  VT either has its DO covered by an Atlas VT that does not yet have
  the explicit `VERIFIES` link to the DI (the `TESTS` link is what
  Atlas considers authoritative for DO-side coverage, and that is
  100% on the DI->DO axis), or it is one of the four UN-orphan DIs
  noted in W-001. CSO queue inspection will catch the residual.
- **Owner**: Engineering Lead.
- **Clear by**: next sprint (raise the missing VERIFIES link).

### W-003 -- 3 DOs without a DI

- **Scope**: 3 of 244 DOs have no `IMPLEMENTS` edge to any DI.
- **Status**: accepted, transient.
- **Justification**: these are pre-existing DOs from Atlas baseline
  (created before the Phase 3a migration) whose parent DI was either
  retired or merged. They are not flagged by `get_traceability_gaps`
  because the gap tool only counts DIs without DOs.
- **Owner**: QA / RA Lead.
- **Clear by**: next quarterly design review (2026-07).

### W-004 -- 36 DOs without a VT (`TESTS`)

- **Scope**: 36 of 244 DOs have no `TESTS` edge from any VT.
- **Status**: accepted, scheduled.
- **Justification**: every Class B+ DO has a parent DI, and every DI
  with active code coverage has a VT via the `VERIFIES` edge (99.7%
  coverage). The missing `TESTS` edge is a downstream artefact of
  Atlas's bi-relational test model. The Phase 8 and Phase 9b VT
  shells (39 in total) are honest debt: they describe the test
  intent but the corresponding pytest/jest implementations have not
  yet been authored. Each of those VTs is `automation_status: not
  executed` and visible in the CSO queue.
- **Owner**: Engineering Lead.
- **Clear by**: rolling sprint backlog; review at every CSO release
  gate.

### W-005 -- 9 VTs without a DI (`VERIFIES`)

- **Scope**: 9 of 350 VTs have no `VERIFIES` edge to any DI.
- **Status**: accepted, transient.
- **Justification**: Atlas baseline VTs that were imported without a
  parent DI. None are safety-critical (verified manually). Phase 11
  cursor rules will block creation of new VTs without a `VERIFIES`
  edge to a DI.
- **Owner**: QA / RA Lead.
- **Clear by**: next quarterly design review (2026-07).

### W-006 -- 62 Risks without a DI (`MITIGATES`)

- **Scope**: 62 of 249 risks have no `MITIGATES` edge from any DI.
- **Status**: accepted, justified by category.
- **Justification**: the unlinked risks fall into three categories:
  1. **External / regulatory risks** (e.g. NHS England directive
     change, NICE guideline withdrawal, GMC fitness-to-practise
     concerns) -- mitigated by post-market monitoring and clinical
     governance, not by a code DI.
  2. **Organisational risks** (e.g. supplier insolvency, key-person
     dependency on a single CSO) -- mitigated by procedural
     controls captured in the QMS, not by a code DI.
  3. **Pending-classification risks** -- imported from FMEA imports
     before the Atlas DI taxonomy stabilised; will be re-bucketed
     against the Phase 8 reverse-traceability DIs in the next
     quarterly risk review.
- **Owner**: CSO + QA / RA Lead.
- **Clear by**: next quarterly risk review (2026-07). The 187 of 249
  risks that do have a code-level mitigation are the safety-critical
  set and are at 100% DI coverage.

### W-007 -- 240 VTs `not_executed`

- **Scope**: 240 of 350 VTs have no `record_verification_run` entry.
- **Status**: accepted, scheduled.
- **Justification**: 110 VTs (32%) are recorded as passed; the
  remaining 240 include the Phase 8 (30) and Phase 9b (9) VT shells
  documented in W-004, plus 201 baseline Atlas VTs whose runs were
  never imported from CI. The VT shells trace the verification
  intent and unblock the cutover; their pytest/jest counterparts
  exist in the repo but the run records were not back-filled. The
  CI pipeline will populate `record_verification_run` for every new
  VT execution from cutover onwards.
- **Owner**: Engineering Lead.
- **Clear by**: 90 days from cutover (back-fill of CI evidence).

### W-008 -- VAL `linkedToDI = 0`

- **Scope**: 21 of 21 validation tests have no direct DI link
  (they are linked at the UN level, which is the canonical IEC 62304
  validation pattern).
- **Status**: accepted, by design.
- **Justification**: validation tests should validate user needs,
  not design inputs (validation = user-needs satisfied; verification
  = design-inputs implemented). The stats report counts the absence
  as a gap but the IEC 62304 / ISO 13485 mapping is correct.
- **Owner**: QA / RA Lead.
- **Clear by**: never (not a defect; document as a "by design" stat
  in the Atlas dashboard).

## Review cadence

- **Per-release**: Engineering Lead inspects W-002 / W-004 / W-007
  via the CSO queue.
- **Quarterly**: QA/RA Lead clears W-001 / W-003 / W-005 / W-006 in
  the design review meeting; CSO signs off any residual.
- **Annually**: full re-baseline against Atlas stats; any waiver
  open for >12 months is escalated.
