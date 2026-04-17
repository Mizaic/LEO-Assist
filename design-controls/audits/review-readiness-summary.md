# Review-Readiness Summary

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Snapshot: 2026-04-17 after WP2 + WP4 completion.

## Atlas coverage

| Artefact | Count | Linked up | Linked down |
|---|---|---|---|
| User Needs (UN) | 73 | n/a | 73 / 73 have at least one DI |
| Design Inputs (DI) | 221 | 221 / 221 have a UN | 221 / 221 have a DO (100%) |
| Design Outputs (DO) | 39 | 39 / 39 have at least one DI | 39 / 39 have a VT (100%) |
| Verification Tests (VT) | 39 | 221 DIs + 39 DOs linked | n/a |
| Validation Tests (VAL) | 1 | 1 UN linked | 0 DIs linked |
| Risks | 0 | n/a | n/a (out of scope - separate chat) |

## What is review-ready today

- Every UN has complete acceptance criteria and is linked to at least one DI.
- Every DI has complete acceptance criteria and is linked to a UN.
- Every DO created during the retrospective audit is linked to a VT.

## Gaps blocking "In Review" transition

1. **DO-level structured acceptance criteria (39 DOs).** Atlas MCP
   cannot populate DO-level AC today (reconcile endpoint returns 404
   for DOs; no `update_design_output` tool). Escalated as a platform
   backlog item. DO AC is currently implicit via the `IMPLEMENTS` chain
   to DIs.
2. **VT execution history.** All 39 VTs are `status: Draft` with no
   execution runs. A reviewer cannot approve a VT without a matching
   `record_verification_run` entry. Tests referenced in each VT must be
   run against real fixtures and the result written back.
3. **Code-gaps inside umbrella DOs.** Several DIs (DI-080A2454 7-year
   retention, DI-12015DBC F1 gate, DI-88C8BBCD threshold drift
   monitoring, DI-DD67ACFF and DI-9DCBC4BA research workspace UI,
   DI-44802DF3 and DI-ED3A89F5 SLA timers, DI-48C13EB6 ConText impact
   report, DI-693FFEEA function-length CI) have a DO + VT but the
   underlying code is partial. VT will fail until the code-gap is
   closed. Tracked in `improvements-backlog.md`.
4. **VAL coverage (72 / 73 UNs without VAL).** Clinical-outcome UNs
   (coding, episode classification, SBAR narrative, de-identification,
   provenance) require a VAL before Class C review can sign off.
5. **Risk register.** Zero risks in Atlas. ISO 14971 retrofit is being
   handled in a separate chat per user direction.
6. **Status transitions.** Every artefact is `Draft`. Transition to
   `In Review` and `Approved` is a human QA action in the Atlas UI; no
   MCP tool exposes status change. QA/RA Lead must walk the board.

## Recommended review sequence

1. **Execute the 39 VTs** against existing test fixtures and record
   runs via `record_verification_run`. Target at least one passing run
   per VT before formal review. Start with Class C VTs (provenance,
   NER+SNOMED, clinical intelligence, NLP training + FHIR).
2. **Close the highest-risk code-gaps** listed above before the
   corresponding VTs are executed (they will fail otherwise).
3. **Build VALs for the six Class C UNs** (UN-0374FE26, UN-FC99D533,
   UN-2C01CF40, UN-83D9A46D, UN-B2C85448, UN-C2F187E9). Each VAL should
   reference a validation scenario that a clinical reviewer can execute
   against staging.
4. **Commission the risk register in the separate chat.** Every Class B
   / C DI needs at least one linked risk with mitigation + residual
   risk recorded per ISO 14971.
5. **Formal design review** once VT execution coverage is at or above
   80% and the Class C VAL set is at or above 100%.

## Evidence for reviewers

- `DC-TM-002-traceability-matrix.csv` - authoritative Atlas-sourced
  matrix (225 rows, 100% DI->DO and DI->VT coverage).
- `DC-TM-001-traceability-matrix.md` - legacy codebase matrix using
  `DI-LEO-AI-*` IDs; to be reconciled against Atlas IDs.
- `design-controls/audits/batch-*` - per-phase audit reports covering
  implementation verdict per DI.
- `design-controls/audits/wp2-completion-report.md` - full WP2 closure
  evidence including the 16 umbrella DOs and 16 new VTs.
- `design-controls/audits/improvements-backlog.md` - every deferred
  "must-fix" or "must-build" with owner and status.
