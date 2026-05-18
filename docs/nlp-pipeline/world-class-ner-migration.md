# World-Class Clinical NER — Migration Runbook

This runbook documents the rollout of Waves 0–5 of the World-Class Clinical
NER plan. It is the reference that QA/RA and operators should read when
promoting a model trained with the new pipeline, and it is the document
referenced by the Atlas design control traceability matrix.

All changes ship behind environment-variable feature flags so the live
service can roll back by redeploying with the previous env set.

## Wave inventory

| Wave | Title | Modules touched |
|------|-------|-----------------|
| 0 | Trainer hardening | `trainer.py`, `evaluator.py` |
| 1 | Config hygiene bundle | `config/base.cfg`, `trainer.py` |
| 2 | Data pipeline | `label_exporter.py`, `libs/training_ext/stratified_split.py`, `libs/training_ext/suggesters.py`, `libs/training_ext/orth_variants_en_clinical.json` |
| 3 | Calibration + multi-seed + K-fold | `app/calibrator.py`, `app/trainer.py`, `libs/training_ext/stratified_split.py` |
| 4 | Arch upgrades | `libs/training_ext/lora_adapter.py`, `libs/training_ext/pseudo_labeller.py`, `libs/training_ext/label_smoothing.py`, `scripts/mlm_pretrain.py`, `scripts/generate_pseudo_labels.py` |
| 5 | Inference + observability | `libs/training_ext/bundle.py`, `libs/training_ext/inference_calibration.py`, `libs/training_ext/drift_monitor.py`, `libs/training_ext/review_queue.py`, `libs/training_ext/strided_spans.py`, `libs/training_ext/precision_gates.py`, `libs/training_ext/mlflow_logger.py` |

## Default posture (what is ON without any env vars)

The Waves 0-5 capabilities are the default training and inference
behaviour — running the worker with no env overrides will:

- Use the strided-window / stride / accumulate-gradient / Polyak-average /
  mixed-precision (CUDA-only) / reducer-sizing settings from Wave 1.
- Stratified train/val/dev/test split with alignment report (Wave 2).
- Orthographic-variant augmenter when the JSON sidecar is present (Wave 2).
- Per-label threshold sweep plus isotonic recalibration (Wave 3).
- Cosine learning-rate schedule (Wave 1/3).
- Bundle manifest with SHA256 file hashes (Wave 5).
- Inference-side per-label thresholds with manifest verification (Wave 5).
- Drift sink writing to `/var/lib/leo/drift/` (Wave 5).
- Active-learning review queue writing to `/var/lib/leo/review_queue/`
  (Wave 5).
- Neo4j-backed precision gates with fallback to code defaults (Wave 5).

The capabilities that stay **off** by default (for good reason, not
timidity):

- `TRAINING_MODE=lora` — requires the `peft` package to be installed.
  Default stays `frozen`. Flip when you install peft and want the
  adapter path.
- `TRAINING_SEEDS=...` — multi-seed multiplies run time by N. Default
  is one seed; flip per-run when you want the robustness sweep.
- `MLFLOW_TRACKING_URI` — empty by default (logger is a no-op). Set
  per environment when your MLflow server exists.
- Pseudo-labelling and MLM pretraining — separate scripts, run on
  demand rather than every training job.

## Feature flag inventory

Feature flags are defined in `libs/training_ext/feature_flags.py` and can be
dumped at runtime via:

```python
from libs.training_ext.feature_flags import to_markdown
print(to_markdown())
```

## Promotion checklist (per-wave)

### Wave 0 — transparency fixes

1. Deploy the training worker with the trainer fix in place. No env changes
   required.
2. Re-run any job that previously silently unfroze the transformer; confirm
   the new run uses the configured frozen list.
3. Verify the evaluator fails fast on a corrupt spancat scorer by running
   the regression test `services/training_worker/tests/test_evaluator.py`.

### Wave 1 — config hygiene

1. Default window/stride are wired to `(256, 192)`. To keep the old values,
   set:

   ```bash
   export TRAINING_WINDOW_TOKENS=512
   export TRAINING_STRIDE_TOKENS=384
   ```

2. `mixed_precision` now flips on only when the resolved accelerator is
   CUDA. MPS jobs continue in FP32.
3. LR schedule default is `warmup_linear` (compatible with spaCy 3.x / thinc 8.3.x).
   `warmup_cosine.v1` requires thinc ≥ 9.0 (spaCy 4.x). The trainer detects
   availability at runtime: set `TRAINING_LR_SCHEDULE=cosine` and it will use
   cosine automatically once the training venv is upgraded to spaCy 4 + thinc 9,
   and fall back to `warmup_linear` with a warning on older venvs.

### Wave 2 — data pipeline

1. `label_exporter.py` now writes `train/val/dev/test.spacy` with stratified
   splits. The ratio default is `0.7/0.1/0.1/0.1`; override via
   `SplitRatios` in code or pass `train_ratio=...` for the legacy shim.
2. `orth_variants_en_clinical.json` is copied next to the corpora so the
   spaCy augmenter can find `${paths.orth_variants}`. If the file is
   missing, the augmenter block is stripped automatically — training still
   succeeds but without augmentation.
3. A `span_alignment_report.json` is written alongside the corpora listing
   every span whose char offsets were silently widened to token
   boundaries. QA should inspect this after any major annotation batch.

### Wave 3 — calibration and multi-seed

1. After training, `app/calibrator.py` runs a per-label threshold sweep
   against the validation split and writes `calibration.json` into the
   model directory. **Isotonic regression is default on**
   (`CALIBRATION_FIT_ISOTONIC=true`); it falls back to raw threshold-only
   calibration when per-label positive support is below
   `CALIBRATION_MIN_SUPPORT` (default 10). Set
   `TRAINING_SKIP_CALIBRATION=true` to bypass the whole phase.
2. Set `TRAINING_SEEDS=1,2,3` to run multi-seed training; the winner is
   chosen by dev F1 reported in spaCy's `meta.json`.
3. K-fold CV is available as a library helper
   (`libs.training_ext.stratified_split.kfold_multilabel_split`); the
   training job does not yet consume it — wire it into a scripted sweep.

### Wave 4 — architecture upgrades

1. LoRA: set `TRAINING_MODE=lora` (requires the `peft` package). The
   training_worker will wrap the HF backbone after spaCy initialisation.
2. Domain-adaptive pretraining: run `python -m scripts.mlm_pretrain --help`
   on a de-identified corpus, then point `TRAINING_HF_BASE_MODEL` at the
   output checkpoint.
3. Pseudo-labelling: run `python -m scripts.generate_pseudo_labels --help`
   after a model passes the gates; the JSONL can be ingested alongside
   gold labels in the next training cycle.
4. Label smoothing: the scorer is registered as
   `leo_training.smoothed_spans_sc_scorer.v1`; to turn it on, reference it
   from `components.spancat.scorer` in `base.cfg` with `label_smoothing =
   0.05`.

### Wave 5 — inference and observability

1. The training job now writes a `bundle_manifest.json` alongside the
   model. The inference service verifies this manifest at load time and
   refuses to honour `calibration.json` on a manifest mismatch.
2. Per-label thresholds come from `calibration.json`; defaults continue to
   be `0.5` when no calibration file is present.
3. Drift monitoring is on by default; set `DRIFT_SINK_ENABLED=false` to
   disable. Daily JSONL files appear under `DRIFT_SINK_DIR` (default
   `/var/lib/leo/drift`). **Mount a persistent volume at this path** —
   `/tmp/` is NOT a safe default for post-deployment monitoring.
4. Low-confidence spans are enqueued for review when in the band
   `[REVIEW_LOWER_BOUND, threshold)`; inspect
   `$REVIEW_QUEUE_DIR/review-YYYY-MM-DD.jsonl` (default
   `/var/lib/leo/review_queue`, same volume guidance applies).
5. Per-label precision gates can be overridden from Neo4j. Create
   `(:PrecisionGate)` nodes with `label`, `min_f1`, `active` properties.
   Disable the loader with `PRECISION_GATES_FROM_NEO4J=false`.

## Rollback plan

Rollbacks are cheap — the feature flags are the single source of truth.

| Situation | Rollback |
|-----------|----------|
| Trainer crash on config resolution | Unset any `TRAINING_*` overrides and redeploy. |
| Calibrated metrics regress vs. raw | `export TRAINING_SKIP_CALIBRATION=true`. |
| Inference refusing to start due to bundle mismatch | Re-upload a bundle with a fresh manifest, or disable manifest verification (rebuild the `inference_calibration.py` loader). |
| Drift sink filling disk | `export DRIFT_SINK_ENABLED=false`. |
| Neo4j precision gates mis-set | `export PRECISION_GATES_FROM_NEO4J=false` — the hardcoded defaults take over. |
| LoRA training diverging | `export TRAINING_MODE=frozen`. |

## Atlas design control touchpoints

Use the `user-atlas-design-controls` MCP to:

1. Update `DO-236545C8` (training orchestrator) with references to the new
   calibrator, bundle, and feature-flag registry modules.
2. Update `DO-A00CD165` (inference service) with the calibration loader,
   drift sink, and review queue.
3. Update `DI-37B3DC71` and `DI-3FDBB57B` with the Wave 5 observability
   outputs (drift, review queue) and the bundle manifest artefact.
4. Ensure new VTs cover: calibration.json produced, manifest verified,
   drift sink file present, review queue non-empty for low-confidence
   spans, Neo4j precision gate override honoured.

## Regression suite additions

The cross-wave regression contract lives in `tests/training_ext/` and the
per-service test suites. The new suite adds:

* `tests/training_ext/test_stratified_split.py` — stratified split and
  K-fold determinism.
* `tests/training_ext/test_suggesters.py` — clinical n-gram suggester.
* `tests/training_ext/test_kfold.py` — K-fold coverage invariants.
* `tests/training_ext/test_lora_adapter.py` — LoRA config parsing.
* `tests/training_ext/test_pseudo_labeller.py` — pseudo-label config.
* `tests/training_ext/test_label_smoothing.py` — smoothing arithmetic.
* `tests/training_ext/test_bundle.py` — bundle manifest integrity.
* `tests/training_ext/test_inference_calibration.py` — per-label
  thresholding and isotonic interpolation.
* `tests/training_ext/test_drift_and_queue.py` — drift sink and review
  queue semantics.
* `tests/training_ext/test_precision_gates.py` — Neo4j gate loader.
* `services/training_worker/tests/test_calibrator.py` — calibrator
  scoring math.
* `services/training_worker/tests/test_label_exporter_wave2.py` — Wave 2
  exporter helpers (ratio resolver + alignment report).

Run all of the above with:

```bash
source .venv/bin/activate
python -m pytest tests/training_ext/ -q
(cd services/training_worker && python -m pytest tests/ -q)
```
