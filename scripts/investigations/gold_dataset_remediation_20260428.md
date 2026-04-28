# Gold Dataset Remediation - 2026-04-28

## Baseline Snapshot

Scope: completed `TrainingCandidate` rows with non-empty `GoldLabel.entities_json`
and `frozen_golden_set = false`.

- GoldLabel rows: 2,858
- Entity rows: 8,968
- Average quality score: 0.822
- High-quality rows: 1,739
- Frozen golden set rows: 0
- Malformed entity payloads: 0
- Phrase-level payload conflicts: 11
- Label/semantic_tag mismatches: 58 entity rows
- Missing offsets: 112 entity rows; surface text is exact-substring repairable for all but 1 row
- PrecisionGate overrides: none found

## Label Support Before Remediation

| label | entities | distinct surfaces | missing offsets |
| --- | ---: | ---: | ---: |
| procedure | 3,885 | 426 | 31 |
| observable_entity | 3,312 | 1,811 | 1 |
| finding | 1,015 | 710 | 26 |
| disorder | 384 | 263 | 21 |
| body_structure | 128 | 89 | 17 |
| situation | 112 | 89 | 7 |
| medicinal_product | 84 | 74 | 5 |
| qualifier_value | 23 | 10 | 1 |
| morphologic_abnormality | 8 | 5 | 0 |
| regime_therapy | 7 | 7 | 0 |
| record_artifact | 6 | 6 | 2 |
| product | 2 | 2 | 0 |
| substance | 1 | 1 | 0 |
| tumor_staging | 1 | 1 | 1 |

## Source Skew

| source | records | entities |
| --- | ---: | ---: |
| lab_coder_v1 | 1,601 | 6,795 |
| manual_gold_editor | 1,115 | 1,771 |
| manual | 33 | 108 |
| synthetic | 28 | 105 |
| pipeline_gold | 31 | 86 |
| manual_gold_seed_2026_04_17 | 21 | 48 |
| manual_gold_draft | 15 | 19 |
| encounter_* | 14 | 37 |

## Initial Diagnosis

The failed labels are primarily failing because the current training corpus is
both imbalanced and under-supported for rare labels. `lab_coder_v1` dominates
the export with procedure and observable examples, while several gated labels
have fewer than 25 total examples. The baseline also shows a concrete schema
quality problem: entity `label` and `semantic_tag` disagree in 58 rows, which
directly pollutes the spaCy class used by the exporter.

## Remediation Log

Actions and post-remediation counts are appended below as this remediation run
progresses.

## Actions Applied

- Aligned 56 SNOMED-backed `label` / `semantic_tag` mismatches across 54
  GoldLabels, preserving `remediation_backup_entities_json_20260428`.
- Removed 2 exact duplicate entity rows from GoldLabel payloads.
- Persisted 50 unique surface-derived `start` / `end` offsets.
- Resolved 11 initial duplicate-phrase payload conflicts, then resolved 19
  additional conflicts surfaced by real-candidate promotion.
- Promoted 19 high-confidence `live_encounter_correction` candidates that
  already had validated entity payloads and rare-label coverage.
- Removed 19 duplicate auto-real GoldLabels after promotion because equivalent
  live-correction GoldLabels already existed for the same candidates.
- Seeded 74 validated synthetic records from
  `data/training/gold-remediation-synthetic-2026-04-28.yaml`.
- Implemented support-aware per-label F1 gates in
  `services/training_worker/app/evaluator.py`.

## Label Support After Remediation

| label | entities | distinct surfaces |
| --- | ---: | ---: |
| procedure | 3,896 | 431 |
| observable_entity | 3,308 | 1,808 |
| finding | 985 | 680 |
| disorder | 417 | 293 |
| body_structure | 142 | 102 |
| situation | 131 | 102 |
| medicinal_product | 101 | 87 |
| qualifier_value | 36 | 21 |
| morphologic_abnormality | 29 | 26 |
| record_artifact | 24 | 22 |
| regime_therapy | 20 | 19 |
| substance | 4 | 4 |
| tumor_staging | 1 | 1 |

## Post-Remediation DQ Checks

- Phrase-level payload conflicts: 0
- Malformed entity payloads: 0
- Remaining label/tag mismatches: 2 edge cases left unresolved because they are
  not high-confidence automatic fixes.
- GoldLabels with backup payloads: 80

## Export And Evaluation Check

Bounded smoke run:
`scripts/investigations/gold_dataset_remediation_smoke_result_20260428.json`.

- Exported records: 2,902
- Split counts: 2,026 train / 293 val / 291 dev / 292 test
- Skipped records: 0
- Span-misaligned drops: 0
- Stratification warnings: 0
- Support-aware skips were emitted for low-dev-support rare labels:
  `BODY_STRUCTURE`, `MEDICINAL_PRODUCT`, `MORPHOLOGIC_ABNORMALITY`,
  `QUALIFIER`, `RECORD_ARTIFACT`, `REGIME_THERAPY`, `SITUATION`, and
  `SUBSTANCE`.

The bounded model was intentionally not promotion-grade (`TRAINING_MAX_STEPS=1`)
and still failed aggregate gates. Its purpose was to verify the remediated
export and the new gate reporting path. A full promotion training run should be
started with the normal step budget after this remediation is reviewed.
