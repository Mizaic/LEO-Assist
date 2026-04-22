# Per-Site Episode Rulebook - Atlas Traceability

Created 2026-04-22 for the per-site rulebook architecture. These are the
Atlas dcIds that new source files under `libs/episode_detector/` and the
per-site default JSON rulebooks cite in their module-level traceability
headers. See the plan at `.cursor/plans/per-site_episode_rulebooks_*.plan.md`.

Product: `PROD-LEO-CORE-AI-20260415-6AE8A23B`

## Parent User Need

| dcId          | Title                                 |
|---------------|---------------------------------------|
| `UN-B0A58F43` | Portable per-site episode rulebooks   |

## Design Inputs

| dcId          | Title                                                  | Covers                                 |
|---------------|--------------------------------------------------------|----------------------------------------|
| `DI-951F26E0` | Episode rulebook schema and validator                  | SiteRulebook, validate_no_pii          |
| `DI-FA3CE229` | Episode rulebook runtime loader and bundle             | RulebookBundle, review-only fallback   |
| `DI-BF97CEAC` | Per-site episode rulebook registry                     | (:ModelVersion) per-site, PII refusal  |
| `DI-AC6838DD` | Gold-patient regression gate on rulebook promotion     | Per-site gate on promotion             |
| `DI-D983C6EE` | Per-site rulebook retrain from correction events       | pattern_miner, CANDIDATE-only output   |

Parent detector DI (pre-existing): `DI-8A5FCF4F` (12-component detector).

## Risks

| dcId          | Title                                                                     | Initial RPN | Residual RPN |
|---------------|---------------------------------------------------------------------------|-------------|--------------|
| `R-94D0D086`  | Rulebook drift silently regresses episode detection accuracy              | 27          | 12           |
| `R-192A2D18`  | Rulebook artefact leaks patient identifiers or clinical text              | 48          | 8            |
| `R-5FA0C950`  | Cross-site signal leakage pulls wrong-site encounters into an episode     | 24          | 8            |
| `R-098701D8`  | Customer-instance rulebook version skew against detector binary           | 24          | 4            |

## Verification Tests

Infrastructure (one per DI):

| dcId          | Title                                                 | Verifies      |
|---------------|-------------------------------------------------------|---------------|
| `VT-9D9DDA68` | Episode rulebook schema round-trip and no-PII validator | `DI-951F26E0` |
| `VT-FA062CE5` | Rulebook runtime loader and bundle parity             | `DI-FA3CE229` |
| `VT-D00D74AC` | Per-site rulebook registry writes and champion uniqueness | `DI-BF97CEAC` |
| `VT-4DB20182` | Rulebook promotion gate on gold-patient VT pass       | `DI-AC6838DD` |
| `VT-68463BA7` | Rulebook retrain pipeline produces CANDIDATE only     | `DI-D983C6EE` |

Gold regression gates (one per gold patient slice):

| dcId          | Title                                                   | Gold patient            |
|---------------|---------------------------------------------------------|-------------------------|
| `VT-7F9A700C` | Breast rulebook v1 gold regression on patient 4246897485 | 4246897485 (breast)     |
| `VT-426CF21F` | Prostate-urological rulebook v1 gold regression on 6282779235 | 6282779235 (prostate) |
| `VT-31B7A37B` | Upper GI rulebook v1 gold regression on 4920262426      | 4920262426 (upper_gi)   |
| `VT-04407859` | Lung rulebook v1 gold regression on 4920262426          | 4920262426 (lung)       |

All gold VTs VERIFY both `DI-AC6838DD` (the gate) and `DI-FA3CE229` (the
loader that executes the rulebook against real data).

## Traceability chain

```
UN-B0A58F43
  -- HAS_DESIGN_INPUT --> DI-951F26E0 (schema)          <- VT-9D9DDA68
  -- HAS_DESIGN_INPUT --> DI-FA3CE229 (loader)          <- VT-FA062CE5, VT-7F9A700C, VT-426CF21F, VT-31B7A37B, VT-04407859
  -- HAS_DESIGN_INPUT --> DI-BF97CEAC (registry)        <- VT-D00D74AC
  -- HAS_DESIGN_INPUT --> DI-AC6838DD (gate)            <- VT-4DB20182, VT-7F9A700C, VT-426CF21F, VT-31B7A37B, VT-04407859
  -- HAS_DESIGN_INPUT --> DI-D983C6EE (retrain)         <- VT-68463BA7

R-94D0D086  MITIGATED_BY  DI-AC6838DD, DI-D983C6EE
R-192A2D18  MITIGATED_BY  DI-951F26E0, DI-BF97CEAC
R-5FA0C950  MITIGATED_BY  DI-FA3CE229, DI-951F26E0
R-098701D8  MITIGATED_BY  DI-951F26E0, DI-FA3CE229
```

Design Outputs are created in their respective implementation phases
(P1-P5) and cited here when they land.

## Design Outputs landed

| dcId           | Title                                                   | Implements                  | Phase |
|----------------|---------------------------------------------------------|-----------------------------|-------|
| `DO-476EAF1D`  | Episode rulebook schema, loader and v0 defaults         | `DI-951F26E0`, `DI-FA3CE229`| P1    |
| `DO-4487051A`  | Per-site rulebook registry, promotion gate, and CLI     | `DI-BF97CEAC`, `DI-AC6838DD`| P6    |
| `DO-EC7B6251`  | Per-site rulebook pattern miner (CorrectionEvent retrainer) | `DI-D983C6EE`          | P7    |

## VT runs recorded

| dcId          | Result | Notes                                                                                                                                                   |
|---------------|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `VT-9D9DDA68` | pass   | 2026-04-22 local. 34 tests pass. Schema round-trip, PII validator, schema_version rejection, SNOMED-shape check.                                        |
| `VT-FA062CE5` | pass   | 2026-04-22 local. 34 tests pass. Loader defaults ship every canonical site; v0 parity byte-matches REFERRAL/CLINIC_SEEN/SUSPECTED_SITE SNOMED registries and ACTIVATION. |
| `VT-7F9A700C` | pass   | 2026-04-22 local. Breast v1 gold regression tests on 4246897485 pass: 2WW + ultrasound-normal anchors, benign closure with 90-day no-confirmed window, cross_site_guard strips urinary SNOMED. |
| `VT-426CF21F` | pass   | 2026-04-22 local. Prostate-urological v1 gold regression on 6282779235 pass: auto-eligible, 2WW + legacy urological anchors, PSA observation, GP letter completed closure with 180-day quiet window, cross_site_guard on other sites. |
| `VT-31B7A37B` | pass   | 2026-04-22 local. Upper GI v1 gold regression on 4920262426 pass: UGI 2WW + dysphagia anchors, PPI treatment signal, text patterns for dysphagia/indigestion, cross_site_guard blocks lung suspected. |
| `VT-04407859` | pass   | 2026-04-22 local. Lung v1 gold regression on 4920262426 pass: suspected lung cancer + smoker anchors, CXR normal benign closure, text patterns for cough/smoker, cross_site_guard blocks UGI. Reciprocal test with upper_gi.v1 proves multi-site split. |
| `VT-D00D74AC` | pass   | 2026-04-22 local. Registry PII-refusal on registration, duplicate guard, champion uniqueness, rollback_target_version recording, rollback restores prior champion (10 tests). |
| `VT-4DB20182` | pass   | 2026-04-22 local. Gold-gate blocks when no pass / stale pass / unknown version; promotes when pass is fresh; force-flag bypasses with [forced] audit tag. CLI emits PromotionDecision as JSON; compare_episode_lists_by_site scores per site. |
| `VT-68463BA7` | pass   | 2026-04-22 local. 13 pattern-miner tests pass: attach-/detach-mining over CorrectionEvent, per-site scope, code_kind routing into suspected/referral/confirmed buckets, cross_site_guard extension on detach, dedupe + baseline-order preservation, PII refusal, CANDIDATE-only contract (registry state REGISTERED, promotion blocked without fresh gold pass). |
