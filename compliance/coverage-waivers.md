# Design Controls Coverage Waivers

This document records the known, accepted residuals after the Atlas
reconciliation cutover (Phases 0-9) and subsequent gap-remediation
passes (2026-04-19, 2026-04-20a, 2026-04-20b). Each waiver is
justified, scoped, and assigned an owner so it can be cleared in the
normal release loop rather than as a one-off remediation programme.

The authoritative source of truth for design controls is the Atlas
MCP server (product `PROD-LEO-CORE-AI-20260415-6AE8A23B`).

> **Pre-CSO note (2026-04-20)**: Every design control in this product
> is currently in `Draft` status. None have been through formal CSO
> review. The waivers below represent the state at which the product
> will be presented to the CSO; clearance dates assume CSO sign-off
> on the Phase-15 baseline.

## Snapshot at 2026-04-20 (post-remediation)

Source: `get_design_control_stats(PROD-LEO-CORE-AI-20260415-6AE8A23B)`
captured at 2026-04-20T16:46Z, after the SBAR provenance fix
(DI-740BE510 ACs 1-3 covered by VT-9A9DAA2C) and the orphan-DI
remediation pass.

| Surface | Count | Linked upstream | Linked downstream |
|---|---|---|---|
| User Needs        | 134 | n/a              | 134 -> DI (100%)   |
| Design Inputs     | 399 | 399 -> UN (100%) | 399 -> DO (100%) / 391 -> VT (98.0%) |
| Design Outputs    | 304 | 302 -> DI (99.3%; 3 newly-created stale in gap-tool cache) | 300 -> VT (98.7%) |
| Verification Tests| 407 | 398 -> DI (97.8%) | 270 -> DO (66.3%) |
| Validation Tests  |  24 |  22 -> UN (91.7%) | n/a               |
| Risks             | 273 | 160 -> UN (58.6%) | 211 -> DI (77.3%) |

VT execution: 161 passed, 246 not_executed, 0 failed.
Risks: 201 acceptable, 70 ALARP, 1 unacceptable (`R-21E608C8`,
in CSO queue -- see W-013).
Inconsistencies: 71 `diSafetyClassExceedsRisks`, 8
`doSafetyClassConflict`, 0 `diClassCNoBackingRisk`.

## Cleared since the cutover snapshot

The following waivers from the original cutover snapshot are now
fully cleared and removed from the open list:

- **W-002 (DI without DO)**: `linkedToDO: 399/399 = 100%`. The 9
  orphan DIs flagged on 2026-04-20 (3 training DIs, 6 LEO-widget
  DIs, the PPV umbrella `DI-58C55352`) all now have IMPLEMENTS
  edges. New DOs created: DO-48061888, DO-E06315C0, DO-69F60330,
  DO-18E985BB, DO-97855E28, DO-5176AD0A; the 4 PPV sub-DOs
  (DO-AE402D85, DO-2FA6DB4B, DO-8A25D759, DO-D4F4A538) were
  additionally linked to the umbrella DI.
- **W-004 (DOs without VT)**: dropped from 36 to 4 (304 - 300).
  The remaining 4 are the runtime/release/governance/PPV-link DOs
  whose VT shells are tracked on the new W-015.
- **W-011 (parallel DI without VT)**: superseded by W-015; the
  underlying DI `DI-E3689657` is now tracked in the Phase-15
  follow-up VT shells.

## Waivers

### W-001 -- 4 User Needs without a DI

- **Scope**: 4 of 134 UNs have no `HAS_DESIGN_INPUT` edge.
- **Status**: accepted, low risk.
- **Justification**: stakeholder-level umbrella needs satisfied by
  combinations of existing DIs already attached to peer UNs (e.g.
  "stakeholder confidence", "operational visibility"). Phase 8
  reverse-traceability sweep created catch-all parent UNs and at
  least one DI per uncovered code bucket; the residual UNs are
  non-implementable outcomes that map to the same physical
  implementation as a sibling UN.
- **Owner**: QA / RA Lead.
- **Clear by**: next quarterly design review (2026-07).

### W-003 -- 2 stale DOs without a DI (gap-tool cache)

- **Scope**: `get_design_control_stats` reports 2 of 304 DOs not
  linked to a DI. `get_traceability_gaps` reports 3 (the three new
  LEO-widget DOs created 2026-04-20). The IMPLEMENTS edges for all
  3 widget DOs were verified directly via `get_design_control(
  dc_type="design-output", dc_id=...)` and exist in the graph; the
  gap-tool delta is a known cache lag in the QMS Graph API.
- **Status**: accepted, transient (cache lag).
- **Justification**: direct reads on DO-18E985BB show 4 IMPLEMENTS
  edges (to DI-85C95E53, DI-A1206416, DI-85944331, DI-5F121122);
  the gap report has not refreshed.
- **Owner**: QA / RA Lead.
- **Clear by**: next gap-tool refresh (cache TTL ~24h).

### W-004 -- 4 DOs without a VT (`TESTS`)

- **Scope**: 4 of 304 DOs have no `TESTS` edge (down from 36 at
  cutover).
- **Status**: accepted, scheduled.
- **Justification**: the 4 remaining are the LEO-widget runtime
  (DO-18E985BB), release channel (DO-97855E28), governance pack
  (DO-5176AD0A), and the cross-DI PPV dashboard surface DO
  (DO-D4F4A538). None of the corresponding code is implemented yet
  (see W-015), so the test files and VT shells will be created in
  the same sprint that lands the implementation.
- **Owner**: Engineering Lead.
- **Clear by**: with the W-015 Phase-15 follow-up.

### W-005 -- 9 VTs without a DI (`VERIFIES`)

- **Scope**: 9 of 407 VTs have no `VERIFIES` edge to any DI.
- **Status**: accepted, transient.
- **Justification**: Atlas baseline VTs imported without a parent
  DI. None are safety-critical (verified manually). The Phase-11
  cursor rules block creation of new VTs without a `VERIFIES`
  edge to a DI, so the set will not grow.
- **Owner**: QA / RA Lead.
- **Clear by**: next quarterly design review (2026-07).

### W-006 -- 62 Risks without a DI (`MITIGATES`)

- **Scope**: 62 of 273 risks have no `MITIGATES` edge from any DI.
- **Status**: accepted, justified by category.
- **Justification**: the unlinked risks fall into three categories:
  1. **External / regulatory risks** (NHS England directive
     change, NICE guideline withdrawal, GMC fitness-to-practise
     concerns) -- mitigated by post-market monitoring and clinical
     governance, not by a code DI.
  2. **Organisational risks** (supplier insolvency, key-person
     dependency on a single CSO) -- mitigated by procedural
     controls captured in the QMS, not by a code DI.
  3. **Pending-classification risks** -- imported from FMEA before
     the Atlas DI taxonomy stabilised; will be re-bucketed against
     the Phase-8 reverse-traceability DIs in the next quarterly
     risk review.
- **Owner**: CSO + QA / RA Lead.
- **Clear by**: next quarterly risk review (2026-07). The 211 of
  273 risks that do have a code-level mitigation are the
  safety-critical set and are at 100% DI coverage.

### W-007 -- 246 VTs `not_executed`

- **Scope**: 246 of 407 VTs have no `record_verification_run`
  entry.
- **Status**: accepted, scheduled.
- **Justification**: 161 VTs (39.6%) are recorded as passed -- up
  from 110 at cutover. The remaining 246 include the Phase-8 (30),
  Phase-9b (9), Phase-15 (4) and 2026-04-20 widget VT shells (3)
  documented in W-004 and W-015, plus 200 baseline Atlas VTs whose
  runs were never imported from CI. The CI pipeline populates
  `record_verification_run` for every new VT execution from
  cutover onwards; the back-fill is in progress.
- **Owner**: Engineering Lead.
- **Clear by**: 90 days from cutover (back-fill of CI evidence).

### W-008 -- VAL `linkedToDI = 22 of 24`

- **Scope**: 22 of 24 validation tests link to UN level (canonical
  IEC 62304 validation pattern); only 2 link to DIs.
- **Status**: accepted, by design.
- **Justification**: validation tests should validate user needs,
  not design inputs (validation = user-needs satisfied;
  verification = design-inputs implemented). The stats report
  flags the absence as a gap but the IEC 62304 / ISO 13485 mapping
  is correct.
- **Owner**: QA / RA Lead.
- **Clear by**: never (not a defect; documented as "by design" in
  the Atlas dashboard).

### W-009 -- 10 Class-A DIs without a Risk (`MITIGATES`)

- **Scope**: 10 of 399 DIs have no `MITIGATES` edge from any Risk.
- **Status**: accepted, by classification, **with reclassification
  candidates flagged for CSO review**.
- **Justification**: per the IEC 62304 Class A / B / C
  proportionality rule, only Class B and Class C DIs require a
  MITIGATES edge from a Risk. The 10 DIs below are currently
  Class A and carry no patient-safety hazard.
- **CSO review candidates** (5 of the 10 may warrant Class B
  reclassification given new clinical surface):
  - `DI-21C63B6A` -- @leo/design-system workspace package
    (parent UNs `UN-FD9BE3CA`, `UN-852649B0`, `UN-109EEB10` are
    all Class B; the package now underpins the LEO-by-Mizaic
    branding contract for the portable widget DI-85944331).
  - `DI-39C53CDA` -- Centralised MUI theme factory
    (`createLeoTheme`); same branding-contract argument as above.
  - `DI-61CB27B2` -- DM Sans typography for clinical labels;
    legibility for older clinicians (`UN-109EEB10`) is an
    explicit Class B safety control.
  - `DI-BCDC245C` -- Similar-candidates batch dialog highlighter
    + match-rationale chips (clinical coding-review surface).
  - `DI-F0846E55` -- Role-first shell rollout cleanup (UI shell
    that gates clinical surfaces).
- **Confirmed Class A** (no clinical surface):
  - `DI-EB8642F4` -- legacy ID stub (DI-LEO-AI-096); needs human
    triage before reclassification or retirement.
  - `DI-37D1B7D7` -- in-memory message bus adapter (dev/test).
  - `DI-20104031` -- ODS sync worker entry point (infrastructure).
  - `DI-21996926` -- LLM usage cost configuration (billing/ops).
  - `DI-B884A243` -- Redis-backed checkpoint and rebuild status
    (infrastructure plumbing).
- **Owner**: QA / RA Lead + CSO (for the 5 reclassification
  candidates).
- **Clear by**: next quarterly design review (2026-07): CSO
  decides on each of the 5 candidates; the confirmed Class A set
  remains as a documented exception.

### W-010 -- DI-740BE510 ACs 4-5 not yet implementation-covered

- **Scope**: 2 of 5 ACs on `DI-740BE510` (SBAR source-encounter
  and coded-entity provenance) are accepted by Atlas but not yet
  implementation-covered:
  - **AC4**: source-record provenance preserved in every export
    pathway (FHIR Composition / DocumentReference, JSON export,
    downstream API consumers) with a contract test for the
    round-trip. The current implementation persists
    `background_parts` on the `:Assessment` node and exposes it
    on `GET /sbar/assessments/{id}`, but the FHIR export and any
    downstream JSON export pathways have not been audited and no
    round-trip contract test exists.
  - **AC5**: portable / embeddable SBAR renderer SDK trust
    boundary. The new portable-widget DIs (DI-85C95E53,
    DI-A1206416, DI-85944331, DI-5F121122, DI-3C06AFD0,
    DI-2FBDAC7D) and their DOs (DO-18E985BB, DO-97855E28,
    DO-5176AD0A) have been created; the implementation is
    tracked in W-015.
- **Status**: accepted, scheduled.
- **Justification**: ACs 1-3 (structured-data exposure end-to-end,
  per-section disclosure defaulting to collapsed, no inline
  source-ID HTML/markdown comments) are covered by `VT-9A9DAA2C`
  with three recorded passes (jest `sbar-final-view` +
  `sbar-playground-chrome`, pytest `tests/sbar/*`).
- **Owner**: Engineering Lead (renderer SDK + export contract).
- **Clear by**:
  - AC4: next sprint -- add a FHIR export contract test under
    `tests/contracts/` that asserts `background_parts` survives
    the round-trip and gate any new export adapter on it.
  - AC5: with the W-015 Phase-15 follow-up.

### W-013 -- 1 risk in CSO queue with corrected scoring math

- **Scope**: `R-21E608C8` ("A clinical decision is made but no
  record of it is saved").
- **Status**: in CSO queue (`cso_status: pending`); awaiting
  CSO sign-off.
- **Justification**: the FMEA 1-10 -> ISO 14971 1-5 scale
  migration left the risk in an arithmetically inconsistent state
  (initial_risk_score 12 < residual_risk_score 36). On 2026-04-20
  the scores were re-stated to:
  - Initial: severity 3, probability 3, detectability 4 -> 36
    (unmitigated state: serious harm, occasional probability,
    very poor detectability because the absence of an entry is
    invisible by definition).
  - Residual: severity 3, probability 2, detectability 2 -> 12
    (ALARP) (target state: 7 mitigating DIs already linked --
    DI-0A5CC384, DI-B88F2A76, DI-4F67189B, DI-5ADEC3D1,
    DI-A557AE91, DI-09E26C1D -- but `verification_pass_count = 0`
    across all 7, so residual is target rather than measured).
  The CSO submission note (2026-04-20T16:42Z) records the
  caveat. The `unacceptable` count of 1 in the live stats refers
  to this risk's pre-update state and clears once the CSO
  approves the new scoring.
- **Owner**: CSO.
- **Clear by**: next CSO review of the queue.

### W-014 -- 79 inherited safety-class inconsistencies

- **Scope**:
  - 71 `diSafetyClassExceedsRisks`: the DI is marked Class B/C but
    its linked risks justify only Class A.
  - 8 `doSafetyClassConflict`: a DO's explicit safety class does
    not match what its parent DI(s) inherit.
- **Status**: accepted, scheduled (policy decision required).
- **Justification**: most likely an artefact of the initial Atlas
  seed where DIs were defaulted to Class B (safer) without
  explicit risk linking. Two valid resolutions per DI: (a) add a
  MITIGATES link from a justifying Risk, or (b) demote to Class A.
  The 78 -> 71 reduction during the 2026-04-20 pass came from the
  newly-created DOs inheriting cleanly. Policy on bulk
  resolution requires CSO sign-off.
- **Owner**: CSO + QA / RA Lead.
- **Clear by**: dedicated workshop in the next sprint to triage
  the 79 cases against the 8-quadrant policy matrix.

### W-015 -- Phase-15 follow-up: code + VTs for newly-created DOs

- **Scope**: 7 newly-created DOs cover requirements whose code is
  not yet written. Each DO has a clear `source_reference` and an
  acceptance-criteria block, but no implementation file exists yet
  in the repo.
  - **Training DIs (3 DOs)**:
    - `DO-48061888` (DE-ID leakage gate evaluator + person-name
      pass) -> `DI-280F5A0C`. VT exists: `VT-3FB93FAF`.
    - `DO-E06315C0` (Multi-corpus gold promotion) -> `DI-F7828E0C`.
      VT exists: `VT-BBEE8ACA`.
    - `DO-69F60330` (Learnable ConText assertion classifier) ->
      `DI-4DFAB32F`. VT exists: `VT-09A07BFF`.
  - **LEO portable widget (3 DOs)**:
    - `DO-18E985BB` (widget runtime: distribution, auth, branding,
      telemetry) -> `DI-85C95E53`, `DI-A1206416`, `DI-85944331`,
      `DI-5F121122`. VT shell to be created.
    - `DO-97855E28` (widget release channel + CSO rollback) ->
      `DI-3C06AFD0`. VT shell to be created.
    - `DO-5176AD0A` (host governance pack: SaaS Embedding
      Agreement, DPA, DCB0129, IFU) -> `DI-2FBDAC7D`. VT shell to
      be created.
  - **PPV dashboard cross-DO (1 link cluster)**:
    - `DO-D4F4A538` (PPV dashboard surface) covers `DI-9D080448`
      and `DI-10A581D2`; the umbrella `DI-58C55352` is now linked
      to the 4 sub-DOs (`DO-AE402D85`, `DO-2FA6DB4B`,
      `DO-8A25D759`, `DO-D4F4A538`) so the IMPLEMENTS chain is
      complete on paper. VT shells exist
      (`VT-F4B33EA4`, `VT-F79DC6AC`, `VT-89618F57`, `VT-22E4478D`)
      but have no `record_verification_run` entries.
  - **Parallel DI from W-011**:
    - `DI-E3689657` (deterministic cancer-site dictionary +
      text-path episode builder integration) -- has a DO but no
      VT yet; tracked here.
- **Status**: accepted, scheduled (real engineering work, not
  paperwork).
- **Justification**: each DO accurately reflects a planned or
  partially-built capability. None of them is fictional; each
  `source_reference` names the file path the code will live in
  when the sprint lands. The CSO can review the DI-DO contract
  before the sprint starts.
- **Owner**: Engineering Lead, by capability:
  - Training DIs: ML / training pipeline lead.
  - LEO portable widget: UI infrastructure lead.
  - PPV dashboard: analytics lead.
  - DI-E3689657: episode-engine lead.
- **Clear by**: per-capability sprint commitment; PPV and
  DE-ID-gate are highest priority because both gate downstream
  work.

### W-016 -- 10 MVP-scope VTs blocked by source-or-scope drift (2026-04-21)

- **Scope**: 10 of 270 distinct MVP-scope VTs in
  `scripts/vt_execution/mvp_vt_backlog.csv` cannot be executed
  against the current code revision and have been triaged out of
  the 30-day MVP execution window:
  - **3 obsolete-source pytest VTs** (`blocked_obsolete_source`)
    -- the implementation file named in the linked DO has been
    deleted or renamed in the live tree:
    - `VT-8FA86B8B` -- DO points at
      `libs/cypher/completeness_report_queries.py` (deleted).
    - `VT-C3250CA6` -- DO points at
      `tests/pipeline_graph/test_completeness_subgraph.py`
      (deleted; subgraph refactored into
      `libs/pipeline_graph/subgraphs/`).
    - `VT-CE4E3C57` -- DO points at
      `libs/pipeline_graph/edges/integration_fetch_edge.py`
      (replaced by
      `libs/pipeline_graph/subgraphs/rest_connector.py`).
  - **7 umbrella VTs** (`blocked_umbrella_decompose`) -- each VT
    has 4-11 linked DIs spanning multiple capabilities and a
    "verify ALL ACs of ALL linked DIs" pass criterion that is
    not addressable by a single test file:
    - `VT-51A869C2` -- 4 safety DIs: data-gap detection,
      small-cohort suppression, mandatory acknowledgement gate.
    - `VT-51320DA9` -- ServiceDataRequirement registry: schema,
      CRUD, RBAC, immutable history, seed records.
    - `VT-B764F925` -- 4 DIs: multi-mode encounter shortlisting
      (keyword + BM25 + vector fusion + recall measurement).
    - `VT-FFF3909C` -- 11 DIs across `libs/training`,
      `libs/audit_agent`, `services/fhir_api`, and
      `services/coding_worker`.
    - `VT-0010386B` -- reviewer workflow + change-control
      surface (multiple DIs).
    - `VT-E265DA74` -- knowledge base authoring + staging
      surface (multiple DIs).
    - `VT-1E5FC70A` -- authoritative source monitoring +
      release management (multiple DIs).
- **Status**: accepted, awaiting architectural decisions; both
  groups need an architect / QA-RA lead action before any new test
  code can land.
- **Justification**: writing tests against deleted source modules
  would create false-positive evidence; bundling 11 distinct DI
  surfaces into one VT pass criterion violates the project rule
  that "VT acceptance criteria match the linked DI ACs one-for-one"
  (see `code-quality.mdc`). The fix in both cases is the standard
  Atlas remediation flow: update the DO `source_reference` (or
  retire the DO) for the obsolete-source group, and decompose each
  umbrella VT into per-DI sub-VTs with their own ACs and test
  files for the umbrella group.
- **Net result**: 260 of 270 distinct MVP-scope VTs (96.3%) are
  now passed and recorded against `record_verification_run` in
  Atlas. The 10 blocked entries are tagged in the backlog CSV with
  `current_status` and `owner` columns so they appear in the next
  triage report instead of being lost.
- **Owner**:
  - Obsolete-source group: QA / RA Lead + responsible
    code-area architect to update or retire the DO.
  - Umbrella group: QA / RA Lead + Engineering Lead to
    decompose into per-DI VTs and link them in Atlas.
- **Clear by**: 30 days from this entry (target 2026-05-21);
  follow-up captured in the MVP backlog and the next per-release
  Engineering review.

---

## W-017 -- Gold-patient VT: Colorectal benign slot_recall (DI-2C015ADE)

- **Added**: 2026-04-24. **Updated**: 2026-04-24 (post-segmenter fix).
- **Scope**: `tests/episode_engine/test_gold_patient_vt.py`,
  patient `4246428337` (Colorectal closed_benign).
- **Gap**: type_recall is now 1.00 (all five gold types found, including
  `benign_closure`). However slot_recall is 0.25 < 0.30 floor because the gold
  fixture has multi-slot types (primary_care_investigations x3, related_gp_visit
  x2) and the engine emits only one occurrence per type, picking encounter IDs
  that differ from the gold curator's selections. type_precision is 0.50 (at
  floor) due to extra context types.
- **Root cause**: Multi-slot milestone types in the gold fixture create a
  theoretical maximum slot_recall of ~0.63 under single-emission behaviour.
  Getting 0.25 reflects ~40% encounter-ID accuracy, which is acceptable for
  Phase 1. A separate issue (extra context types from the milestone extractor)
  is covered by prompt rules 10/11 but LLM variance persists.
- **Risk**: Low. All milestone types are found; encounter-ID mismatches mean
  the curator sees the milestone on a slightly different encounter (e.g. a
  related blood test rather than the exact one the curator chose). The episode
  is in human-review tier so the curator can correct any misattribution.
- **Owner**: Engineering Lead.
- **Clear by**: 2026-06-30 -- implement multi-slot emission from vector hints
  (retrieve all matching encounters per type, not just top-1) and reduce
  extra context types by improving closed-window contamination filtering.

---

## W-018 -- Gold-patient VT: Multi-site Lung closed-window contamination (DI-2C015ADE)

- **Added**: 2026-04-24. **Updated**: 2026-04-24 (segmenter fix shipped).
- **Scope**: `tests/episode_engine/test_gold_patient_vt.py`,
  patient `4920262426` (Multi-site Breast/Lung/UpperGI),
  episode Lung/closed_benign.
- **Gap**: The segmenter now correctly creates 3 windows (Lung, Breast, Upper
  GI) and the engine produces 3 episodes. Upper GI now passes all three
  thresholds (type_recall 0.75, slot_recall 0.62, type_precision 0.86).
  However the Lung episode has type_precision 0.43 < 0.50 floor: the
  July-16 CXR result encounter contains text "referred for upper GI
  investigation" (forward context) and the LLM emits `referral`,
  `referral_sent`, and `first_seen` for the closed Lung window despite
  prompt rule 12 (closed-window scope). `benign_closure` is also missed.
- **Root cause**: The July-16 encounter text documents the CXR result AND
  plans the next steps (upper GI referral) in a single record. The LLM
  treats the mention of the planned referral as an emittable milestone
  rather than forward context. This is a closed-window contamination issue:
  the milestone extractor cannot distinguish "event completed in this window"
  from "event mentioned but happening later".
- **Risk**: Low. The Lung episode correctly surfaces as a separate card with
  a benign investigation pathway. The extra milestone types (`referral`) are
  false positives that a curator reviewing the Lung episode would quickly
  dismiss; `confidence_tier=review` is set so no automatic acceptance occurs.
- **Owner**: Engineering Lead.
- **Clear by**: 2026-06-30 -- add deterministic post-filtering in `writer.py`
  that strips milestones whose encounter dates fall outside the episode window
  date range, and enforce `benign_closure` emission for windows that the
  classifier marks as benign.

---

## Review cadence

- **Per-release**: Engineering Lead inspects W-004 / W-007 /
  W-013 / W-015 / W-016 / W-017 / W-018 via the CSO queue.
- **Quarterly**: QA/RA Lead clears W-001 / W-003 / W-005 / W-006 /
  W-009 / W-014 in the design review meeting; CSO signs off any
  residual.
- **Annually**: full re-baseline against Atlas stats; any waiver
  open for >12 months is escalated.
