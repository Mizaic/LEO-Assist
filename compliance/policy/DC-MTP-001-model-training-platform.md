# Clinical NER Model Training and Inference Platform Specification

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Document ID      | DC-MTP-001                                                            |
| Version          | 1.0.0                                                                 |
| Status           | Draft                                                                 |
| Effective Date   | TBD (see §17 Revision History)                                        |
| Standards        | ISO 13485:2016 §7.3; IEC 62304:2006+A1:2015 §5; AAMI TIR34971:2023; EU AI Act Annex IV (Art. 11); MDCG 2019-11; FDA GMLP (Guiding Principles for Good Machine Learning Practice) |
| Classification   | QMS — Design Controls — Software Specification                        |
| Product          | PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4                  |
| Safety Class     | B (inherited from DI-37B3DC71)                                        |
| Owner            | QA/RA Lead, ML Engineering Lead                                       |
| Change Control   | CR-06F0668F (Waves 0-5 rollout)                                        |

---

## 1. Purpose

This document specifies the configuration, settings, and controlled behaviour of the clinical Named Entity Recognition (NER) model training and inference subsystem. It is the **authoritative specification** used to evidence that training and inference occur under planned arrangements for ISO 13485 §7.3.3 (Design Inputs) and §7.3.4 (Design Outputs).

It satisfies ML-specific evidence requirements under AAMI TIR34971 (risk management for ML medical devices), MDCG 2019-11 (qualification of software as a medical device), and EU AI Act Annex IV item 2(b) (description of design choices) and 2(c) (what the system is optimised for, trade-offs).

---

## 2. Scope

**In scope**

- spaCy `SpanCategorizer` training pipeline driven by `services/training_worker/`.
- Inference pipeline driven by `services/model_inference/`.
- Supporting library modules under `libs/training_ext/` (calibration, bundle manifest, drift monitor, review queue, LoRA adapter, pseudo-labelling, stratified split, feature flag registry).
- Pre-/post-processing that is baked into the model artifact bundle (orthographic variants, per-label thresholds, isotonic calibration curves, SHA-256 integrity manifest).

**Out of scope** (governed by separate controlled documents)

- LLM / episode engine path (`services/analysis_worker/app/episode_engine/`).
- Episode detector rulebook (`libs/episode_detector/`, `services/analysis_worker/app/episode_detector_v2/`).
- Terminology / coding resolver (`libs/terminology/`).
- De-identification pipeline upstream of training data export (DC-DPA-002, DPIA-LEO-AI-001).
- Front-end UI components (DC-UE-001).

---

## 3. Intended Use Context

The NER model extracts clinical entities (disorder, finding, procedure, medicinal product, observable, and 23 further labels) from primary-care free text. Extracted spans feed the Mission Control coded data views and downstream population-level audit analytics.

The intended-use statement is in `compliance/policy/intended-use.md`. Foreseeable mis-use pathways handled by this specification:

- **Indirect patient harm** from systematic mis-classification leading to misdirected population-level quality improvement → mitigated by per-label F1 gates (§7, §11) and post-market drift monitoring (§13).
- **Silent model drift** after deployment → mitigated by the drift sink and review queue (§13).
- **Unverified artefact substitution** between training and inference → mitigated by bundle manifest SHA-256 verification (§10).

---

## 4. Safety Classification and Risk Ties

- **Software Safety Class:** B, inherited from DI-37B3DC71 (Model improvement cycle with active learning, metrics, golden gate, and warm start).
- **Risks mitigated** (edges in Atlas):
  - R-036E176B — model performance regression on promotion.
  - R-7A94507D — mis-calibrated confidence leading to over-/under-extraction.
  - R-FFDB88BF — labelling error contaminating the trained model.
  - R-61F5F634 — post-deployment drift without detection.
  - R-575EB05E — warm-start artefact mismatch.

Every risk is referenced by at least one acceptance criterion in the relevant DI and verified by at least one VT (see §11).

---

## 5. Subsystem Architecture Baseline

```
+---------------------+       +------------------------+       +-----------------------+
| GoldLabel corpus    | --->  | training_worker        | --->  | Model artifact bundle |
| (Neo4j)             |       |   label_exporter       |       |  /model/              |
+---------------------+       |   trainer (spaCy v3)   |       |  /meta.json           |
                              |   calibrator            |       |  /calibration.json    |
+---------------------+       |   evaluator             |       |  /bundle_manifest.json|
| Golden set (frozen) | --->  |   job_runner (phases)   |       |  /orth_variants.json  |
+---------------------+       +------------------------+       |  /span_alignment.json |
                                                               +-----------+-----------+
                                                                           |
+---------------------+       +------------------------+                   v
| ACA inference       | <---  | model_inference         | <----------------+
| endpoint /extract   |       |   model_loader          |
+---------------------+       |   main (FastAPI)        |
                              |   inference_calibration |
                              |   drift_monitor         |
                              |   review_queue          |
                              +------------------------+
```

**Controlled configuration items (CIs)**

| CI | Path | Role |
|----|------|------|
| CI-TW-01 | `services/training_worker/app/trainer.py` | Config resolution, spaCy CLI invocation, multi-seed orchestration. |
| CI-TW-02 | `services/training_worker/app/config/base.cfg` | Baseline spaCy config (window, stride, accumulate_gradient, use_averages, reducer, LR schedule). |
| CI-TW-03 | `services/training_worker/app/calibrator.py` | Per-label threshold sweep + optional isotonic regression. |
| CI-TW-04 | `services/training_worker/app/evaluator.py` | Calibrated-threshold evaluation and F1 gates. |
| CI-TW-05 | `services/training_worker/app/job_runner.py` | Training job state machine (export → train → evaluate → calibrate → bundle → upload). |
| CI-TW-06 | `services/training_worker/app/label_exporter.py` | Stratified split + span alignment report. |
| CI-TE-01 | `libs/training_ext/bundle.py` | Bundle manifest assembly and integrity verification. |
| CI-TE-02 | `libs/training_ext/inference_calibration.py` | Runtime calibration loader. |
| CI-TE-03 | `libs/training_ext/drift_monitor.py` | Aggregated prediction statistics sink. |
| CI-TE-04 | `libs/training_ext/review_queue.py` | Active learning grey-zone queue. |
| CI-TE-05 | `libs/training_ext/precision_gates.py` | Neo4j-backed per-label F1 gate loader. |
| CI-TE-06 | `libs/training_ext/lora_adapter.py` | PEFT/LoRA fine-tuning adapter. |
| CI-TE-07 | `libs/training_ext/feature_flags.py` | **Normative** inventory of configuration flags (see §8). |
| CI-MI-01 | `services/model_inference/app/model_loader.py` | Bundle load, version pinning, calibration attachment. |
| CI-MI-02 | `services/model_inference/app/main.py` | FastAPI endpoint; applies per-label thresholds; emits drift & review records. |

Any change to a CI that alters externally observable behaviour requires a Change Request per §15.

---

## 6. Training Data Requirements

- **Source:** `GoldLabel` nodes in the primary Neo4j instance, produced by the Mission Control curation UI.
- **De-identification:** all training text has passed the de-identification pipeline referenced in DC-DPA-002 §3 and DPIA-LEO-AI-001. The training worker does **not** re-de-identify; it trusts upstream.
- **Inclusion criteria:**
  - `GoldLabel.approved_by_second_reviewer = true`, OR single-reviewer with a curator role tagged `qa-ra-lead`.
  - Assertion must not be in `TRAINING_EXCLUDE_ASSERTIONS` (default excludes negated, hypothetical, family_history, possible).
- **Exclusion criteria:**
  - `frozen_golden_set = true` records are held back for the golden evaluation pass (§11) and never appear in training or dev splits.
  - Records whose span offsets fail realignment are logged in `span_alignment_report.json` and excluded (they do **not** abort export).
- **Split policy:** stratified multi-label split, default `train=0.7, val=0.1, dev=0.1, test=0.1` (`libs/training_ext/stratified_split.py`). Rare labels may land in only a subset of splits; the exporter warns when a label is absent from any split.
- **Label schema:** defined in `libs/ner/label_schema.py`; 28 span labels organised in four precision tiers. Schema changes are CRs.
- **Provenance:** every training job records the `GoldLabel` IDs consumed in the `job_runner` state and copies them into the bundle manifest as `dataset_hash`. This satisfies EU AI Act Annex IV 2(d).

---

## 7. Training Configuration Specification (controlled)

The table below is the **controlled baseline** for a Class B training run. Changes to defaults require a CR. Per-run overrides via environment variables are permitted and are logged to MLflow (when enabled) and to the job runner's `TrainingJob` record.

### 7.1 Transformer backbone

| Setting | Default | Permitted range | Rationale |
|---------|---------|-----------------|-----------|
| Base model | `emilyalsentzer/Bio_ClinicalBERT` | HuggingFace model path | Clinical-domain pretrained backbone. |
| Training mode | `frozen` | `frozen` \| `lora` \| `full` | Default preserves Wave 0 freeze fix; LoRA requires `peft` installed. |
| LoRA rank | 8 | 4-32 | Effective only when `TRAINING_MODE=lora`. |
| LoRA alpha | 16 | 8-64 | — |
| LoRA dropout | 0.05 | 0.0-0.2 | — |

### 7.2 Strided window / context

| Setting | Default | Permitted range | Rationale |
|---------|---------|-----------------|-----------|
| Window tokens | 256 (from `base.cfg`) | 128-512 | Wave 1 correction of F2. Overridable by `TRAINING_WINDOW_TOKENS`. |
| Stride tokens | 192 (from `base.cfg`) | 96-384 | 75% overlap; aggregated at inference via `libs/training_ext/strided_spans.py`. Overridable by `TRAINING_STRIDE_TOKENS`. |

### 7.3 Optimisation

| Setting | Default | Permitted range | Rationale |
|---------|---------|-----------------|-----------|
| `accumulate_gradient` | 4 | 1-16 | Wave 1 smoothing for small-sample batches. |
| `use_averages` | true | boolean | Polyak averaging for Class B stability. |
| `mixed_precision` | true on CUDA, false on MPS/CPU | auto | Wave 1. |
| `dropout` | 0.1 | 0.05-0.3 | — |
| Reducer `hidden_size` | 768 | 256-1536 | Wave 1 correction of F10. |
| `batch_by_words` start | 512 | 128-2048 | Wave 1 correction of F11. |
| LR schedule | `warmup_linear.v1` | `warmup_linear.v1` \| `warmup_cosine.v1` | Default is warmup_linear (spaCy 3.x / thinc 8.3.x). Cosine requires thinc ≥ 9.0 (spaCy 4.x); auto-detected at runtime via `TRAINING_LR_SCHEDULE=cosine`. |
| Warmup steps | 250 | 0-1000 | — |
| Max steps | 20 000 | 5000-100 000 | Early-stop governed by eval-frequency. |
| Eval frequency | 200 | 100-1000 | — |
| Seeds | 1 seed (empty `TRAINING_SEEDS`) | CSV of ints | Multi-seed multiplies runtime by N; opt-in per run. |

### 7.4 Data augmentation

| Setting | Default | Permitted range | Rationale |
|---------|---------|-----------------|-----------|
| Ngram suggester `max_size` | 12 (clinical ngram suggester) | 6-24 | Wave 2 correction of F7. |
| Orthographic variants | ON when `orth_variants_en_clinical.json` co-located | boolean | Wave 2. |
| Label smoothing | 0.0 | 0.0-0.1 | Reference `leo_training.smoothed_spans_sc_scorer.v1` in `base.cfg` to enable. |

### 7.5 Calibration

| Setting | Default | Permitted range | Rationale |
|---------|---------|-----------------|-----------|
| Fit isotonic | true | boolean | Falls back to threshold-only when support < `CALIBRATION_MIN_SUPPORT`. |
| `CALIBRATION_MIN_THRESHOLD` | 0.1 | 0.01-0.9 | Lower bound of sweep. |
| `CALIBRATION_MAX_THRESHOLD` | 0.9 | 0.1-0.99 | Upper bound of sweep. |
| `CALIBRATION_THRESHOLD_STEP` | 0.01 | 0.005-0.1 | Sweep granularity. |
| `CALIBRATION_FALLBACK_THRESHOLD` | 0.5 | 0.1-0.9 | Used when sweep produces no valid threshold. |
| `CALIBRATION_MIN_SUPPORT` | 10 | ≥ 5 | Positive support required for per-label threshold. |

### 7.6 Promotion gates

| Setting | Default | Permitted range | Rationale |
|---------|---------|-----------------|-----------|
| Overall min F1 | 0.75 | 0.70-0.95 | Class B floor. |
| Golden set min F1 | 0.80 | 0.75-0.95 | Blocks promotion when golden regresses. |
| Per-label F1 gates | `_LABEL_MIN_F1_DEFAULTS` in `evaluator.py` | 0.50-0.95 per label | Overridable via Neo4j `:PrecisionGate` nodes (Wave 5) or `LABEL_MIN_F1_JSON`. |

---

## 8. Feature Flag Inventory (normative)

The single source of truth is `libs/training_ext/feature_flags.py`. The inventory below is a frozen snapshot at this document version. A CR is required to change any **default**; per-run `env` overrides are informative (logged, not CR-gated).

| Wave | Flag | Default | Description |
|------|------|---------|-------------|
| 1 | `TRAINING_WINDOW_TOKENS` | `0` (= use base.cfg) | Strided transformer window size. |
| 1 | `TRAINING_STRIDE_TOKENS` | `0` (= use base.cfg) | Strided transformer stride size. |
| 1 | `TRAINING_LR_SCHEDULE` | `cosine` | LR schedule (cosine default; warmup_linear selectable). |
| 3 | `CALIBRATION_FIT_ISOTONIC` | `true` | Fit per-label isotonic regression (falls back at low support). |
| 3 | `CALIBRATION_MIN_SUPPORT` | `10` | Per-label positive support threshold. |
| 3 | `TRAINING_SEEDS` | (empty) | CSV of seeds for multi-seed training. |
| 3 | `TRAINING_SKIP_CALIBRATION` | `false` | Skip Wave 3 calibration phase. |
| 4 | `TRAINING_MODE` | `frozen` | Training mode: full \| frozen \| lora. |
| 4 | `LORA_RANK` | `8` | LoRA rank when TRAINING_MODE=lora. |
| 4 | `PSEUDO_LABEL_MIN_CONFIDENCE` | `0.85` | Minimum confidence for pseudo-label emission. |
| 5 | `PRECISION_GATES_FROM_NEO4J` | `true` | Read `(:PrecisionGate)` nodes for per-label F1 gates. |
| 5 | `DRIFT_SINK_ENABLED` | `true` | Emit per-inference drift records. |
| 5 | `DRIFT_SINK_DIR` | `/var/lib/leo/drift` | Persistent volume for drift JSONL files. |
| 5 | `REVIEW_QUEUE_DIR` | `/var/lib/leo/review_queue` | Persistent volume for review queue. |
| 5 | `MLFLOW_TRACKING_URI` | (empty) | MLflow tracking URI (empty = no-op logger). |

Regenerate the inventory with:

```python
from libs.training_ext.feature_flags import to_markdown
print(to_markdown())
```

---

## 9. Calibration Policy

`calibration.json` is written to the model directory after every successful training run. Schema (normative):

```json
{
  "default_threshold": 0.5,
  "per_label": {
    "<LABEL>": {
      "threshold": 0.42,
      "support_positive": 127,
      "support_negative": 312,
      "f1_at_default": 0.78,
      "f1_at_threshold": 0.83,
      "precision_at_threshold": 0.88,
      "recall_at_threshold": 0.79,
      "isotonic_x": [0.0, 0.25, 0.5, 0.75, 1.0],
      "isotonic_y": [0.0, 0.12, 0.48, 0.82, 1.0]
    }
  },
  "macro_f1_before": 0.78,
  "macro_f1_after": 0.82,
  "fit_isotonic": true,
  "min_support": 10,
  "threshold_sweep": {"min": 0.1, "max": 0.9, "step": 0.01, "fallback": 0.5}
}
```

Per-label acceptance criteria (enforced by `calibrator.py`):

1. `threshold` MUST satisfy `min <= threshold <= max`.
2. `support_positive` MUST be >= `min_support` for the per-label threshold to replace the default; otherwise the default is kept.
3. `f1_at_threshold` MUST be >= `f1_at_default - 0.01` (no meaningful regression).
4. When `fit_isotonic = true`, `isotonic_x`/`isotonic_y` MUST be monotonic non-decreasing and span `[0.0, 1.0]`.

---

## 10. Artifact Bundle and Integrity

The bundle manifest (`bundle_manifest.json`) is written by `libs/training_ext/bundle.py` and is part of the promoted artifact. Contents (normative):

```json
{
  "bundle_version": "1.0",
  "model_version": "<YYYYMMDD-HHMMSS-hash>",
  "created_at": "<ISO-8601>",
  "dataset_hash": "<sha256 of GoldLabel IDs consumed>",
  "extras": {"git": "<sha>", "mlflow_run_id": "<id or null>"},
  "file_hashes": {
    "meta.json": "<sha256>",
    "calibration.json": "<sha256>",
    "orth_variants_en_clinical.json": "<sha256 or absent>",
    "span_alignment_report.json": "<sha256 or absent>"
  }
}
```

Inference-side verification (`services/model_inference/app/model_loader.py` →
`libs/training_ext/inference_calibration.load_calibration`):

1. On load, recompute SHA-256 for each file listed in `file_hashes`.
2. If any file is missing or hash mismatches, set `InferenceCalibration.is_verified = False` and fall back to default threshold 0.5 for all labels. Log a high-severity warning.
3. `calibration.json` is honoured **only** when `is_verified = True`.

This closes R-575EB05E (artefact mismatch) and is the integrity evidence for ISO 13485 §4.2.4 (records).

---

## 11. Verification Specification

Each controlled setting in §7, §8, §9, §10 is verified by a named VT in Atlas. Coverage summary:

| Control area | VT(s) | Source tests |
|--------------|-------|--------------|
| Freeze + per-label F1 gates | VT-F50F9689 | `services/training_worker/tests/test_trainer.py`, `test_evaluator.py` |
| Wave 1 config defaults | new VT (planned) | `services/training_worker/tests/test_trainer.py::test_wave1_defaults_are_written` |
| Cosine LR default | new VT (planned) | `test_trainer.py::test_cosine_schedule_is_default` |
| Calibration math | new VT (planned) | `services/training_worker/tests/test_calibrator.py` |
| Stratified split + K-fold | new VT (planned) | `tests/training_ext/test_stratified_split.py`, `test_kfold.py` |
| Bundle integrity | new VT (planned) | `tests/training_ext/test_bundle.py` |
| Inference calibration roundtrip | new VT (planned) | `tests/training_ext/test_inference_calibration.py`, `tests/training_ext/test_wave_regression.py` |
| Drift sink + review queue | new VT (planned) | `tests/training_ext/test_drift_and_queue.py` |
| Neo4j precision gates | new VT (planned) | `tests/training_ext/test_precision_gates.py` |
| LoRA config parsing | new VT (planned) | `tests/training_ext/test_lora_adapter.py` |
| Label smoothing | new VT (planned) | `tests/training_ext/test_label_smoothing.py` |
| Feature flag coverage | new VT (planned) | `tests/training_ext/test_feature_flags.py` |

QA/RA Lead creates the "new VT (planned)" rows in Atlas as part of closing CR-06F0668F.

---

## 12. Validation Specification

Validation is governed by existing VAL artefacts linked to UN-5236129E:

- VAL (existing) — Clinician acceptance of per-label thresholds on a clinician-reviewed sample.
- VAL (planned) — Population-level audit validation on a 30-day shadow-mode run against the prior promoted model. Triggers on first promotion post-Waves 0-5.

---

## 13. Post-Market Monitoring Plan

Per MDCG 2019-11 §5.2 and MDR Article 83, the following signals are collected continuously once the model is in routine use:

| Signal | Source | Collection | Threshold for escalation |
|--------|--------|-----------|--------------------------|
| Per-label mean confidence | `drift_monitor` sink | 1 JSONL record per `/extract` call | Daily mean confidence drop > 10% vs. 7-day baseline for any label. |
| Below-threshold rate | `drift_monitor` sink | Same | Daily below-threshold rate > 20% above 7-day baseline. |
| Span count per 1k tokens | `drift_monitor` sink | Same | 25% decrease or 50% increase vs. baseline. |
| Active-learning review queue volume | `review_queue` | Per grey-zone span | Queue growing faster than reviewed; escalate at > 500 un-reviewed items. |
| Clinician-reported false-positive/false-negative | CAPA intake (DC-CM-001) | Manual | Any Class B-relevant report → CAPA. |

**Retraining trigger:** any two consecutive weeks of sustained threshold breach, OR 5 clinician reports of systematic mis-classification for the same label, OR a CAPA requesting a model update.

**Rollback trigger:** a single breach of an overall or golden F1 gate in any weekly re-run against the frozen golden set, OR any Class B risk escalation.

---

## 14. Human Oversight (EU AI Act §14)

| Role | Responsibility | Recorded where |
|------|---------------|----------------|
| ML Engineering Lead | Authors training run; selects per-run overrides; reviews calibration and gates; recommends promotion. | MLflow run + Atlas CR. |
| QA/RA Lead | Reviews this specification; reviews CRs; approves promotion; authorises rollback. | Atlas approvals; corporate-document acknowledgements. |
| Clinical Lead | Reviews per-label thresholds when materially changed; reviews drift alerts of Class B relevance. | Design review minutes under `compliance/design-reviews/`. |
| Curator (clinician or clinical-safety officer) | Reviews active-learning queue; resolves grey-zone spans. | Curation audit trail in Neo4j. |

No single role can promote a model unilaterally: promotion requires ML Lead + QA/RA Lead approval in Atlas.

---

## 15. Change Control

Any change that alters:

- A default value listed in §7 or §8, OR
- The schema of `calibration.json` (§9) or `bundle_manifest.json` (§10), OR
- The post-market monitoring thresholds in §13, OR
- The promotion gate values in §7.6,

requires a Change Request raised via `create_change_request` on Atlas, linked to this document via `link_change_request_to_document`, and — for Class B impact — an entry in the §17 Revision History on approval.

Per-run `env` overrides that stay within the **Permitted range** columns in §7 do not require a CR but MUST be logged in the `TrainingJob` record and (when enabled) MLflow.

This document currently references CR-06F0668F (Waves 0-5 rollout).

---

## 16. Rollback and Fallback Matrix

| Situation | Immediate action | Env variable | Follow-up |
|-----------|------------------|--------------|-----------|
| Trainer crash on config resolution | Revert env overrides and redeploy. | Unset `TRAINING_*`. | Root-cause in CAPA. |
| Calibrated metrics regress vs. raw | Disable calibration phase. | `TRAINING_SKIP_CALIBRATION=true` | Review calibrator logs; re-run with larger val set. |
| Inference refusing to start on bundle mismatch | Re-upload a bundle with a fresh manifest. | — | Review Wave 5 release train. |
| Drift sink filling disk | Disable sink. | `DRIFT_SINK_ENABLED=false` | Rotate volume or move to Redis backend. |
| Neo4j precision gates mis-set | Fall back to code defaults. | `PRECISION_GATES_FROM_NEO4J=false` | Fix `:PrecisionGate` nodes, re-enable. |
| LoRA training diverging | Fall back to frozen training. | `TRAINING_MODE=frozen` | Tune LoRA rank/alpha in a dev run. |
| Post-market drift breach (see §13) | Promote previous model revision (ACA blue/green revision roll-back). | N/A (deployment-layer). | CAPA; retraining cycle. |

---

## 17. Training and Competence

- This document is acknowledged annually by all ML Engineering, QA/RA, and Clinical Safety roles (Atlas `atlas_requires_acknowledgement = true`, period = 365 days).
- Initial training: read-and-sign via the Atlas corporate-document acknowledgement flow.
- Evidence of training is maintained in Atlas (`acknowledge_corporate_document`).

---

## 18. Traceability Matrix

| This document | Traces to |
|---------------|-----------|
| §3 Intended use | UN-5236129E; `intended-use.md` |
| §4 Safety / risks | DI-37B3DC71; R-036E176B; R-7A94507D; R-FFDB88BF; R-61F5F634; R-575EB05E |
| §5 Architecture | DO-A35D2D57; SAD (Software Architecture Document on product) |
| §6 Data requirements | DC-DPA-002; DPIA-LEO-AI-001 |
| §7 Training config | DO-A35D2D57; DI-37B3DC71; VT-F50F9689 + planned VTs in §11 |
| §8 Feature flags | CI-TE-07 (`libs/training_ext/feature_flags.py`) |
| §9 Calibration | Planned VT; `tests/training_ext/test_inference_calibration.py` |
| §10 Bundle integrity | Planned VT; `tests/training_ext/test_bundle.py` |
| §11 Verification | All VTs listed in §11 |
| §12 Validation | Existing VAL on UN-5236129E |
| §13 Post-market | MDCG 2019-11; DC-CM-001; DC-PR-001 |
| §15 Change control | DC-CM-001; CR-06F0668F |

A consolidated trace view is available via `get_traceability_matrix(product_id="PROD-LEO-CLINICAL-DECISION-SUPPORT-20260515-118182E4")` in Atlas.

---

## 19. References

### Source code (controlled CIs)

- `services/training_worker/app/` — trainer, evaluator, calibrator, job_runner, label_exporter, config/base.cfg
- `services/model_inference/app/` — main, model_loader
- `libs/training_ext/` — bundle, inference_calibration, drift_monitor, review_queue, precision_gates, lora_adapter, stratified_split, suggesters, pseudo_labeller, label_smoothing, strided_spans, mlflow_logger, feature_flags
- `scripts/mlm_pretrain.py`; `scripts/generate_pseudo_labels.py`
- `docs/nlp-pipeline/world-class-ner-migration.md` — engineering-facing migration runbook (informative, not controlled).

### Standards and guidance

- ISO 13485:2016 §7.3 (Design and development), §4.2.3 (Medical device file), §4.2.4 (Control of records).
- IEC 62304:2006+A1:2015 §5 (Software development process).
- AAMI TIR34971:2023 (Risk management for AI/ML-enabled medical devices).
- EU AI Act Annex IV (Technical documentation), Articles 9, 14.
- MDCG 2019-11 (Qualification and classification of software).
- MDR Article 83 (Post-market surveillance system).
- FDA/Health Canada/MHRA Guiding Principles for Good Machine Learning Practice (2021).

### Atlas design controls

- UN-5236129E; DI-37B3DC71; DO-A35D2D57; VT-F50F9689; CR-06F0668F; risks listed in §4.

---

## 20. Revision History

| Version | Date | Author | Summary |
|---------|------|--------|---------|
| 1.0.0 | 2026-04-24 | ML Engineering Lead | Initial issue covering Waves 0-5 of the world-class clinical NER plan. Linked to CR-06F0668F and to product PROD-LEO-CORE-AI-20260415-6AE8A23B via DMR. |
