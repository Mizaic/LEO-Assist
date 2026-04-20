# Review-Readiness Summary

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`
Snapshot: 2026-04-17 after WP1 + WP2 + WP4 + VT structural upgrade + full VAL programme.

## Atlas coverage

| Artefact | Count | Linked up | Linked down |
|---|---|---|---|
| User Needs (UN) | 73 | n/a | 73 / 73 have at least one DI |
| Design Inputs (DI) | 221 | 221 / 221 have a UN | 221 / 221 have a DO (100%) |
| Design Outputs (DO) | 39 | 39 / 39 have at least one DI | 39 / 39 have a VT (100%) |
| Verification Tests (VT) | 39 | 221 DIs + 39 DOs linked | n/a |
| Validation Tests (VAL) | 19 | 73 UNs linked via VALIDATES | n/a |
| Risks | 0 | n/a | n/a (out of scope - separate chat) |

## What is review-ready today

- Every UN has complete acceptance criteria and is linked to at least one DI.
- Every DI has complete acceptance criteria and is linked to a UN.
- Every DO created during the retrospective audit is linked to a VT.
- Every DO (39 / 39) carries structured `acceptance_criteria` populated via
  the new `update_design_output` MCP tool: per-DI implementation pledges,
  code-path coverage, gap-tracking, change-control provenance, and a
  no-regression hold against the linked VT (WP1).
- Every VT (39 / 39) carries structured `acceptance_criteria` plus an
  ordered `protocol_steps` array (env setup -> test load -> pytest
  invocation -> per-DI assertion check -> evidence capture ->
  `record_verification_run` -> CR or defect ticket) so a reviewer can
  execute the protocol verbatim.
- Full VAL programme created: 19 VALs covering all 73 UNs via
  `VALIDATES` links (13 bespoke Tier-1 VALs for Class C / clinical-outcome
  UNs, 5 themed Tier-2 umbrella VALs for safety-relevant UN groups, and
  1 Tier-3 umbrella VAL for developer/platform UNs). Every VAL has
  structured `acceptance_criteria`, ordered `protocol_steps`, and a
  `scenario` / `goal` grounded in the linked UN acceptance criteria.

## VAL register (Atlas IDs)

| ID | Title | UNs covered |
|---|---|---|
| VAL-94A75EF2 | SNOMED CT auto-coding accuracy and HITL gate | UN-0374FE26 |
| VAL-510CC69F | Episode grouping accuracy and review gate | UN-FC99D533 |
| VAL-3DD678D1 | Episode quality validation and reporting gate | UN-2C01CF40 |
| VAL-09F9CDCC | Clinical relation linking quality and ontology compliance | UN-83D9A46D |
| VAL-CEDF6D3F | Extraction provenance integrity and audit trail access control | UN-B2C85448 |
| VAL-4548AAE2 | Pre-LLM de-identification bypass prevention | UN-C2F187E9 |
| VAL-4C76712D | SBAR clinical summary generation, review gate and provenance | UN-AFFA1FB3 |
| VAL-4038043D | Plain-language interpretation readability, content safety and review gate | UN-575E8DCB |
| VAL-8ADF8394 | Guideline conformance accuracy, review gate and programme isolation | UN-FBBFD5CB |
| VAL-245DF9E9 | Safety netting worklist, severity classification and auto-suppression | UN-459367FA |
| VAL-1087D5A3 | Anti-automation-bias review UX - active engagement gate and metrics | UN-8659DD53 |
| VAL-6A796484 | Data completeness disclosure and coverage indicator | UN-A949A642 |
| VAL-4A43EE72 | Tamper-evident audit trail, retention enforcement and regulatory export | UN-F8E1F0D0 |
| VAL-6605AD24 | Change-control workflow - approval gating, impact assessment and RBAC | UN-785DFCDE, UN-ED00ED74, UN-F6A0C5BA, UN-17724530, UN-EA93F7B7, UN-7D740697 |
| VAL-0A1ECC1E | Knowledge base authoring - AI extraction, approval gate and currency tracking | UN-6D46C832, UN-319F33F0, UN-4AEB2F29, UN-407F090F, UN-A412610D, UN-16E151CB, UN-4BD56518, UN-87CB1498 |
| VAL-3EC79832 | Clinical intelligence - patient context, comparable outcomes and HITL gates | UN-06FD3F7D, UN-1A6F1E0E, UN-2266BDAE, UN-9206EFF0, UN-9396A2FA, UN-F3300833, UN-67663AAF |
| VAL-8B398B49 | Operations and admin - pipeline monitoring, DQ engine, drift detection | UN-7294050B, UN-AE5D7812, UN-9E66C163, UN-4DCD5891, UN-87632C9E, UN-BB817C74, UN-3376B57D, UN-6C8AEB83, UN-FB2DA651 |
| VAL-60B4AB9E | Model lifecycle - canary rollout, active learning, label auditing | UN-AE5B5691, UN-5236129E, UN-1AC15812, UN-70A35225, UN-8663A98C |
| VAL-0A11F56F | Developer and platform - API contract, sandbox, FHIR conformance, tenancy | UN-718B7AF3, UN-9A7C2AA3, UN-94833CA3, UN-395B630E, UN-A031A603, UN-412D1ECD, UN-F2372DE0, UN-07AB5B97, UN-21D88B69, UN-16116C5F |

## Gaps blocking "In Review" transition

1. **VT execution history.** All 39 VTs are `status: Draft` with no
   execution runs. A reviewer cannot approve a VT without a matching
   `record_verification_run` entry. Tests referenced in each VT must be
   run against real fixtures and the result written back.
2. **Code-gaps inside umbrella DOs.** Several DIs (DI-080A2454 7-year
   retention, DI-12015DBC F1 gate, DI-88C8BBCD threshold drift
   monitoring, DI-DD67ACFF and DI-9DCBC4BA research workspace UI,
   DI-44802DF3 and DI-ED3A89F5 SLA timers, DI-48C13EB6 ConText impact
   report, DI-693FFEEA function-length CI) have a DO + VT but the
   underlying code is partial. VT will fail until the code-gap is
   closed. Tracked in `improvements-backlog.md`.
3. **VAL coverage — COMPLETE.** 19 VALs now cover all 73 UNs via
   `VALIDATES` links (see VAL register table above). No further VAL
   creation is required before formal review.
4. **Risk register.** Zero risks in Atlas. ISO 14971 retrofit is being
   handled in a separate chat per user direction.
5. **Status transitions.** Every artefact is `Draft`. Transition to
   `In Review` and `Approved` is a human QA action in the Atlas UI; no
   MCP tool exposes status change. QA/RA Lead must walk the board.

## Recommended review sequence

1. **Execute the 39 VTs** against existing test fixtures and record
   runs via `record_verification_run`. Target at least one passing run
   per VT before formal review. Start with Class C VTs (provenance,
   NER+SNOMED, clinical intelligence, NLP training + FHIR).
2. **Close the highest-risk code-gaps** listed above before the
   corresponding VTs are executed (they will fail otherwise).
3. **Build VALs** - COMPLETE. 19 VALs created covering all 73 UNs.
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
