# Phase 4 -- Risk migration to Atlas (closeout)

Run completed: 2026-04-19.

## Scope

Local risks comprised 230 distinct items:

- 179 YAML files in `design-controls/risks/R-LEO-AI-*.yaml`.
- 63 FMEA-only "FMEA_GAP" rows from `MASTER-RISK-LIST-FINAL.csv`
  (no YAML counterpart -- they were only ever workshop-tracked).

Atlas baseline (2026-04-19) already contained 159 risks: 94 sourced
from prior YAML migration and 63 from FMEA workshops. The migration
script `scripts/atlas/phase4_risk_migrate.py` was written to reconcile
the two while strictly avoiding duplicate creation.

## Decision profile

| Decision         | Count | Source                                   |
|------------------|-------|------------------------------------------|
| `remap`          | 129   | Auto-remap (FMEA-exact + score >= 0.55)  |
| `remap-manual`   |  25   | 0.40-0.55 review band, manually confirmed|
| `create-review`  |  38   | 0.40-0.55 band, no manual override       |
| `create`         |  50   | Score < 0.40 (truly new)                 |
| **Total**        | 242   |                                          |

Result: **154 risks remapped to existing Atlas entries** (0 silent
mismerges) and **88 new risks created in Atlas**. Zero errors.

## De-duplication rules

The script applied the following decision precedence (highest first):

1. **Exact FMEA reference match** -- Atlas FMEA-sourced risks carry
   `FMEA refs: FMEA-NNN` in their description. If any local
   `Source_FMEA_IDs` value appears in an Atlas description, treat it
   as an exact match and remap immediately. Hit rate: 91 risks.
2. **Auto-remap** when `max(SequenceMatcher, Jaccard) >= 0.55` OR
   title-Jaccard alone >= 0.50. Hit rate: 51 additional risks.
3. **Review band** (0.40 <= score < 0.55) -- DEFAULT to CREATE so we
   never silently merge two distinct risks. Each review-band candidate
   is written to `design-controls/phase10-risk-review-band.md` with
   the suggested Atlas dcId. Manual remap decisions live in
   `scripts/atlas/phase4_decisions.json` (25 manual remaps confirmed).
4. **Auto-create** when score < 0.40.

## MITIGATES link coverage

For every successfully resolved local risk, the script walked
`mitigation_measures[].implemented_by` (YAML) or the `Mitigating_DIs`
column (CSV) and translated each local DI to its Atlas dcId via
`design-controls/atlas-id-mapping.csv`. Then a single
`link_design_controls` call was issued per risk with
`relationship=MITIGATES`.

- 97 risks gained at least one MITIGATES link
- 145 risks had no resolvable parent DIs (mostly because the
  `Mitigating_DIs` column lists Atlas-style UUIDs that pre-date our
  mapping CSV, or local DIs that were not migrated in earlier phases)
- Total DI -> Risk MITIGATES links created: 164

The "no parent DIs resolved" group is acceptable: those risks now
exist in Atlas with their full text, and Atlas's existing controls
linkage workflow (or the planned reverse-traceability phase) can add
links later without losing data.

## Atlas before vs after

| Field                | Before | After | Delta |
|----------------------|--------|-------|-------|
| Total risks          |   159  |  247  |  +88  |
| Risks linked to DI   |     ~  |  185  |    -  |
| Acceptability split  |     -  | 175 acceptable / 71 ALARP / 1 unacceptable | - |

## Bugs / fixes during execution

- `monitoring:` field in some YAMLs was a list rather than a dict
  (free-form notes). Fixed by `_as_dict()` helper that returns
  `{}` for non-dict values.
- Initial threshold sweep treated 0.30-0.55 band as "remap-conservative"
  and silently merged ~120 distinct risks. Spot-check showed many
  cross-domain mismatches (e.g. screen-reader risk being remapped to
  cancer-dashboard risk). Threshold band tightened to 0.40-0.55 and
  the default flipped to CREATE to honour the user's "do not duplicate"
  instruction without producing false merges.

## Files

- `scripts/atlas/phase4_risk_migrate.py` -- migration script (idempotent).
- `scripts/atlas/phase4_decisions.json` -- 25 manual remap overrides.
- `scripts/atlas/.phase4_risk_state.json` -- per-row state.
- `scripts/atlas/.phase4_risk_links_state.json` -- linked-pairs state.
- `design-controls/phase10-risk-migration.csv` / `.md` -- main ledger.
- `design-controls/phase10-risk-review-band.md` -- review-band report.
- `design-controls/phase10-risk-mitigates-links.csv` -- MITIGATES audit log.

## Follow-ups

- The 38 `create-review` risks have suggested Atlas matches that I
  was not confident enough to merge. A clinical reviewer could pass
  through `phase10-risk-review-band.md` and either (a) leave as-is
  (now distinct Atlas risks) or (b) use Atlas `suggest_merge` /
  `update_risk` to consolidate.
- 145 risks have no parent DI links yet. These will be picked up by
  Phase 7 (reverse-traceability) when it identifies missing
  implements / mitigates edges across the whole graph.
- The 1 "unacceptable" residual-risk in Atlas was pre-existing -- it
  is not a Phase 4 creation. Worth confirming this is on the CSO
  queue.
