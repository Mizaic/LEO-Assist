# Phase 3 -- DO + VT Migration Closeout

Completes the DO and VT chains in Atlas after Phase 2 finished UN and DI.
After this phase Atlas holds the canonical DO/VT inventory for
`PROD-LEO-CORE-AI-20260415-6AE8A23B`, every local DO/VT either remaps to
an existing Atlas dcId or has been created with full local content, and
the VT->DI / VT->DO / DO->DI relationships have been re-built. Every VT
whose local YAML records `status: passed` with a `result: pass` history
entry has had a `record_verification_run` call executed against Atlas.

## Atlas state at end of Phase 3

| Type | Atlas total | Linked to parent | Notes |
|---|---|---|---|
| User needs       |  92 | 88 -> DI | unchanged from Phase 2 |
| Design inputs    | 300 | 300 -> UN, 259 -> DO, 290 -> VT | unchanged from Phase 2 |
| Design outputs   | 173 | 170 -> DI, 169 -> VT | +17 created in Phase 3 |
| Verification tests | 311 | 302 -> DI, 164 -> DO | +132 created in Phase 3 |
| Validation tests |  21 | unchanged | Phase 5 closes the last gap |
| Risks            | 159 | unchanged | Phase 4 will migrate +212 local |
| VT runs recorded |  -  | 110 verification tests passed | +107 recorded in Phase 3 |

## Sub-phases

### Phase 3a -- Design Outputs (130 local)

Script: `scripts/atlas/phase3_do_vt_migrate.py --kind DO`
Ledger: `design-controls/phase9-do-migration.csv` and `.md`
State:  `scripts/atlas/.phase3_do_state.json`

| Decision | Count | What we did |
|---|---|---|
| `remap` (>=0.55 sim)   | 113 | record-only; mapping CSV updated |
| `create` (<0.40 sim)   |  17 | `create_design_output` + `link_design_controls IMPLEMENTS` to parent DI(s) |
| `review` (0.40-0.55)   |   0 | none in this band |
| Errors                 |   0 | clean run |

Of the 17 creates: 14 linked to one or more parent DIs; 3 (DO-LEO-AI-121,
145, 151) created without parent DI links because their declared parent
DIs (DI-LEO-AI-124, 149, 155) were marked `deferred-duplicate` in Phase 2
(parent UN deferred for human review). These are tracked as follow-ups
to be closed once the deferred UNs are resolved.

### Phase 3b -- Verification Tests (147 local)

Script: `scripts/atlas/phase3_do_vt_migrate.py --kind VT`
Ledger: `design-controls/phase9-vt-migration.csv` and `.md`
State:  `scripts/atlas/.phase3_vt_state.json`

| Decision | Count | What we did |
|---|---|---|
| `remap`        |  13 | record-only |
| `remap-manual` |   2 | VT-LEO-AI-022 + 116 manually promoted from review band |
| `create`       | 132 | `create_verification_test` + `link_design_controls VERIFIES` to parent DI(s) |
| `review`       |   0 | both candidates promoted to remap-manual |
| Errors         |   0 | clean run |

Of the 132 creates: 123 linked to at least one parent DI; 9 created
without parent DI links because their declared parent DIs were also
deferred or are stale local references.

The local YAML schema for VTs almost never declares
`traceability.design_outputs`; instead each local DO YAML declares
`traceability.verification_tests` (or the alternate-schema field
`verified_by`). So the VT->DO links were built in a separate pass:

Script: `scripts/atlas/phase3b_vt_do_link.py --live`
Ledger: `design-controls/phase9-vt-do-links.csv`
State:  `scripts/atlas/.phase3b_vt_do_state.json`

- Built the inverse DO->VT map from every local DO YAML (covers both
  schemas: `traceability.verification_tests` and `verified_by`).
- 214 (VT, [DO,...]) candidate pairs.
- 120 successfully linked via `link_design_controls TESTS`.
- 94 skipped because the VT side referenced a `VT-LEO-AI-*` ID that has
  no local YAML (stale references in old DO files); recorded in the
  ledger for the optional repo-cleanup pass.
- 0 errors.

### Phase 3c -- record_verification_run for passing VTs

Script: `scripts/atlas/phase3_do_vt_migrate.py --kind VT --record-runs --live`
Ledger: `design-controls/phase9-vt-runs.csv`
State:  `scripts/atlas/.phase3_vt_runs_state.json`

For every local VT whose YAML carries `status: passed` AND has at least
one `execution_history` entry with `result: pass`, the script records a
fresh `pass` run against the Atlas VT.

- 132 created VTs scanned (only the local-VT creates -- remapped VTs
  already had Atlas-side runs).
- 25 skipped (status pending/partial or no passing execution_history).
- 107 successfully recorded as `pass` (1 cached from a probe call,
  106 newly recorded).
- 0 errors.

## Bugs and fixes during Phase 3

1. **Heterogeneous local DO schema** -- The 130 local DO YAMLs use two
   incompatible shapes: the canonical `specification.title` /
   `traceability.design_inputs` shape, and an alternate flat shape with
   top-level `title` / `derived_from` / `satisfies` /
   `implementation_artefacts` / `deliverables` / `components`. The
   loader was patched to accept both, including pulling source paths
   from all four artefact-list field names. After the fix, 5 DOs that
   had previously matched at 0.06-0.18 still matched at 0.06-0.18
   because they really are absent from Atlas (DO-LEO-AI-034, 035, 067,
   068, 069 -- security batches and per-tenant billing).

2. **`record_verification_run` requires UUID, not `dcId`** -- exact same
   class of bug as Phase 1's `update_design_input` issue. The first
   live attempt produced 107 `record_error` rows with the API saying
   "Verification test not found". Probed the API directly:
   `record_verification_run` accepts the internal UUID
   (e.g. `bf1c6463-ceb0-467e-90a2-798ef9f03791`), not `VT-BF1C6463`.
   Patched the script with a `_resolve_vt_uuid` helper that fetches via
   `get_design_control` once per VT and caches the result in the runs
   state file, then re-ran successfully.

3. **VT-LEO-AI-001 probe duplicate** -- The UUID-resolution probe
   accidentally created one extra `pass` run on `VT-BF1C6463`. The runs
   state file is pre-seeded so subsequent runs skip that VT instead of
   double-recording it.

4. **Decision threshold tuning** -- Initial DO dry-run had 17 items in
   the soft `[0.40, 0.55)` band. After spot-checking, every one was a
   true positive (titles matched literally), so the soft band was
   tightened by lowering REMAP_HARD to 0.55. For VTs the same
   tightening produced just 2 review items, both of which were also
   true positives; they were promoted manually via
   `phase3_decisions.json`.

## Net new Atlas design controls created in Phase 3

- 17 design-outputs
- 132 verification-tests
- 107 verification runs

## Open follow-ups handed to later phases

- 3 DOs (DO-LEO-AI-121, 145, 151) and 9 VTs need parent links once the
  deferred Phase 2 UN/DI items are reviewed. Captured in their state
  files; rerunning the script will auto-link them after the deferred
  UNs are remapped/created.
- 94 stale `DO -> verification_tests` references with no matching local
  VT YAML are listed in `phase9-vt-do-links.csv` (`skip: VT not in
  mapping CSV`). Optional cleanup task for Phase 12.
- 25 VTs with `status: pending|partial` or empty execution history
  have no `record_verification_run` call yet. They will pick up runs
  once their owning teams record execution, via Phase 8 (reverse
  traceability) or normal Atlas usage.
