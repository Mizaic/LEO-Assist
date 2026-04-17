# Review-Readiness Summary

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Snapshot: 2026-04-17 after WP4 completion.

## Atlas coverage

| Artefact | Count | Linked up | Linked down |
|---|---|---|---|
| User Needs (UN) | 73 | n/a | 73 / 73 have at least one DI |
| Design Inputs (DI) | 221 | 221 / 221 have a UN | 84 / 221 have a DO (38%) |
| Design Outputs (DO) | 23 | 23 / 23 have at least one DI | 23 / 23 have a VT (100%) |
| Verification Tests (VT) | 23 | 84 DIs + 23 DOs linked | n/a |
| Validation Tests (VAL) | 1 | 1 UN linked | 0 DIs linked |
| Risks | 0 | n/a | n/a (out of scope - separate chat) |

## What is review-ready today

- Every UN has complete acceptance criteria and is linked to at least one DI.
- Every DI has complete acceptance criteria and is linked to a UN.
- Every DO created during the retrospective audit is linked to a VT.

## Gaps blocking "In Review" transition

1. **DI -> DO gap (137 orphan DIs).** Tracked in
   `wp2-orphan-di-execution-plan.md`, split into 14 thematic batches.
   Each batch requires per-DI code verification before an umbrella DO is
   created.
2. **DO-level structured acceptance criteria (23 DOs).** Atlas MCP cannot
   populate DO-level AC today (reconcile endpoint returns 404 for DOs;
   no `update_design_output` tool). Escalated as a platform backlog item.
   DO AC is currently implicit via the `IMPLEMENTS` chain to DIs.
3. **VT execution history.** All 23 VTs are `status: Draft` with no
   execution runs. A reviewer cannot approve a VT without a matching
   `record_verification_run` entry. Tests referenced in each VT must be
   run against real fixtures and the result written back.
4. **VAL coverage (72 / 73 UNs without VAL).** Clinical-outcome UNs
   (coding, episode classification, SBAR narrative, de-identification,
   provenance) require a VAL before Class C review can sign off.
5. **Risk register.** Zero risks in Atlas. ISO 14971 retrofit is being
   handled in a separate chat per user direction; the existing local
   payload-generation scripts
   (`design-controls/risks/generate_atlas_risk_payloads.py`,
   `fire_atlas_risks.py`) will back-fill this once unblocked.
6. **Status transitions.** Every artefact is `Draft`. Transition to
   `In Review` and `Approved` is a human QA action in the Atlas UI; no
   MCP tool exposes status change. QA/RA Lead must walk the board.

## Recommended review sequence

1. **Close the highest-risk DI gaps first.** Batches A (provenance) and
   B (SNOMED coding) in the WP2 execution plan are the clinical-safety
   hot spots.
2. **Execute the 23 VTs** against existing test fixtures and record
   runs via `record_verification_run`. Target at least one passing run
   per VT before formal review.
3. **Build VALs for the six Class C UNs** (UN-0374FE26, UN-FC99D533,
   UN-2C01CF40, UN-83D9A46D, UN-B2C85448, UN-C2F187E9). Each VAL should
   reference a validation scenario that a clinical reviewer can execute
   against staging.
4. **Commission the risk register in the separate chat.** Every Class B
   / C DI needs at least one linked risk with mitigation + residual
   risk recorded per ISO 14971.
5. **Formal design review** once Atlas gaps drop to 0 for UNs, 0 for
   DIs (DO linkage), and VT execution coverage is at or above 80%.

## Evidence for reviewers

- `DC-TM-002-traceability-matrix.csv` - authoritative Atlas-sourced
  matrix (225 rows).
- `DC-TM-001-traceability-matrix.md` - legacy codebase matrix using
  `DI-LEO-AI-*` IDs; to be reconciled against Atlas IDs.
- `design-controls/audits/batch-*` - per-phase audit reports covering
  implementation verdict per DI.
- `design-controls/audits/improvements-backlog.md` - every deferred
  "must-fix" or "must-build" with owner and status.
- `design-controls/audits/wp2-orphan-di-execution-plan.md` - batched
  plan for closing the 137-DI gap.
