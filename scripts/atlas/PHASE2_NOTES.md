# Phase 2 -- UN/DI Triage and Low-Confidence DI Cleanup

Completed: 2026-04-19

## Scope and outcome

| Sub-phase | Scope | Tool | Result |
|---|---|---|---|
| 2a | 22 unmatched UNs | `phase2_un_di_triage.py` | 19 remapped, 3 created |
| 2b | 42 unmatched DIs | `phase2_un_di_triage.py` | 37 remapped, 5 created |
| 2c | 39 low-confidence DIs | `phase2c_low_confidence_action.py` | 33 created, 4 remapped, 2 confirmed |

All Atlas mutations recorded in:

- `design-controls/phase8-un-di-triage.csv` / `.md` (Phases 2a + 2b)
- `design-controls/phase8c-low-confidence-action.csv` / `.md` (Phase 2c)
- Resume-safe state: `scripts/atlas/.phase2_un_di_state.json`,
  `scripts/atlas/.phase2c_low_confidence_state.json`
- Manual decision overrides: `scripts/atlas/phase2_decisions.json`

## Phase 2c rollback of Phase 1 contamination

`phase1_di_merge.py` had merged each local DI's acceptance_criteria into
its CSV-recorded Atlas counterpart for 109 pairs. After human review of
the 39 `low-confidence` rows, almost every Phase 1 target was found to
be semantically wrong. Phase 2c walked each of those 39 wrong targets,
removed every AC whose normalised key matched a local AC of the source
DI, and then either:

- created a new Atlas DI from the local YAML and linked it to the
  proper parent UN(s); or
- remapped the mapping CSV row to a better-fitting existing Atlas DI;
  or
- confirmed the existing match (DI-LEO-AI-021, DI-LEO-AI-038).

Total ACs rolled back: 203 across 37 distinct Atlas DIs (one DI was a
no-op because the original Phase 1 merge added zero ACs).

## Bugs and fixes during Phase 2

1. `parse_gap_section` regex over-captured across markdown sections
   (`## DI` swallowed the `## VT` block). Fixed with `[^\\n]*` and
   removal of `re.S` flag.
2. `create_user_need` enforces a strict `stakeholder_types` enum and a
   `priority` enum. Local roles like "Clinical Audit Team Member" had
   to be mapped to API enum values via overrides in
   `scripts/atlas/phase2_decisions.json`.
3. DIs created in Atlas could not resolve their parent UN when that UN
   was newly created or manually remapped. Fixed by injecting all
   manual UN remap decisions into `un_mapping` at startup, and
   widening the resume logic so DIs previously marked
   "created (no parent UN known)" are retried.
4. The cache used by `phase2_low_confidence_di_review.py` held stale
   `_error` entries from initial probe failures. Switched the script
   to a strict cache-only mode so the report renders quickly with
   whatever the cache contains, and fetches happen only via the
   focused action script.
5. Phase 2c originally keyed one decision under
   `DI-LEO-AI-005-context`; CSV id is `DI-LEO-AI-005`. Renamed the
   key.

## What is now in Atlas

- 22 + 42 + 39 = 103 local UN/DI rows reconciled with Atlas.
- 41 net-new Atlas design controls added (3 UN + 5 DI from Phase 2a/2b
  + 33 DI from Phase 2c).
- The mapping CSV is the single source of truth for local-to-Atlas
  identity; every prior `low-confidence` row has been recategorised as
  `remap-manual`, `created-in-atlas`, or kept as the explicit confirm
  (`fuzzy` -> remains).

## Open follow-ups handed to later phases

- DOs and VTs that referenced the wrongly-merged Atlas DIs need to be
  re-pointed at the new DIs created in Phase 2c. Handled by Phase 3.
- The 9 deferred-duplicate UNs (UN-LEO-AI-003, 005, 006, 008, 009 ...)
  remain on the Phase 3 docket; they need a CSO-style human merge call
  rather than an automated remap.
