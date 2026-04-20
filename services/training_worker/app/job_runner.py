"""Training job runner — executes the full fine-tuning pipeline in a

Atlas trace:
  DO: DO-236545C8
  DI: DI-2D9F5064, DI-37B3DC71
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-236545C8")

background thread so the FastAPI process stays responsive.

Pipeline phases per job
-----------------------
1. export   — fetch TrainingLabel nodes → spaCy DocBin
2. qa       — validate record count meets minimum gate
3. train    — run spacy train subprocess (Bio_ClinicalBERT backbone, NER head)
4. evaluate — precision/recall on dev set vs threshold gates
5. upload   — pack NER head only → upload to Azure Blob
6. register — create ModelRegistry entry + validate_offline()

Progress events are published to Redis ``training:{job_id}`` so the SSE
relay endpoint can stream them to the browser.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from app.job_store import TrainingJob, TrainingJobStore

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = int(os.getenv("TRAINING_MAX_CONCURRENT_JOBS", "1"))
_semaphore = threading.Semaphore(_MAX_CONCURRENT)

_export_labels_fn: Optional[Callable] = None
_export_relations_fn: Optional[Callable] = None
_run_training_fn: Optional[Callable] = None
_run_relation_training_fn: Optional[Callable] = None
_evaluate_model_fn: Optional[Callable] = None
_evaluate_relation_model_fn: Optional[Callable] = None
_model_store_cls = None
_model_registry_cls = None


def submit_job(job: TrainingJob, store: TrainingJobStore) -> None:
    """Submit a training job to run in a daemon thread."""
    t = threading.Thread(
        target=_run_job,
        args=(job, store),
        daemon=True,
        name=f"training-job-{job.job_id[:8]}",
    )
    t.start()


def _run_job(job: TrainingJob, store: TrainingJobStore) -> None:
    """Full training pipeline — runs in a background thread."""
    acquired = _semaphore.acquire(blocking=False)
    if not acquired:
        store.update(
            job,
            status="failed",
            error="Another training job is already running. Try again later.",
        )
        return

    job_started_at = time.time()
    store.update(job, status="running", started_at=job_started_at)

    with tempfile.TemporaryDirectory(prefix="training_job_") as tmp:
        work_dir = Path(tmp)
        started_t = time.perf_counter()
        try:
            store.append_log(job, "Phase 0/5 — Preparing training pipeline…")
            _phase_export(job, store, work_dir)
            export_meta = job.metrics.get("export", {})
            _phase_export_relations(job, store, work_dir)
            relation_export_meta = job.metrics.get("relation_export", {})
            store.append_log(
                job, f"Phase export complete in {time.perf_counter() - started_t:.1f}s"
            )
            train_path = work_dir / "train.spacy"
            dev_path = work_dir / "dev.spacy"

            train_t = time.perf_counter()
            model_dir = _phase_train(job, store, work_dir, train_path, dev_path)
            relation_model_path = _phase_train_relations(job, store, work_dir)
            store.append_log(
                job, f"Phase train complete in {time.perf_counter() - train_t:.1f}s"
            )
            eval_t = time.perf_counter()
            metrics = _phase_evaluate(job, store, model_dir, dev_path)
            relation_metrics = _phase_evaluate_relations(
                job, store, relation_model_path, work_dir
            )
            store.update(
                job,
                metrics={**job.metrics, "relation_model": relation_metrics},
            )
            store.append_log(
                job, f"Phase evaluate complete in {time.perf_counter() - eval_t:.1f}s"
            )
            relation_gate_passed = bool(
                relation_metrics.get("passed_gates", True)
            )
            if (not metrics["passed_gates"]) or (not relation_gate_passed):
                g_f = metrics.get("golden_f1")
                min_g = metrics.get("min_golden_f1")
                if not relation_gate_passed:
                    err = (
                        f"Relation model gate failed: F1={float(relation_metrics.get('f1') or 0.0):.3f} "
                        f"(min={float(relation_metrics.get('min_f1') or 0.6):.3f})."
                    )
                elif g_f is not None and g_f < (min_g or 0):
                    err = (
                        f"Golden set F1={g_f:.3f} below threshold {min_g}. "
                        "Model regressed on frozen benchmark."
                    )
                else:
                    err = (
                        f"Precision/recall below thresholds: "
                        f"P={metrics['precision']:.3f} R={metrics['recall']:.3f}"
                    )
                store.update(
                    job,
                    status="failed",
                    phase="evaluate",
                    error=err,
                    finished_at=time.time(),
                )
                return

            upload_t = time.perf_counter()
            artifact_uri, version = _phase_upload(job, store, model_dir, export_meta)
            store.append_log(
                job, f"Phase upload complete in {time.perf_counter() - upload_t:.1f}s"
            )
            register_t = time.perf_counter()
            _phase_register(
                job, store, version, artifact_uri, metrics, export_meta, job_started_at
            )
            store.append_log(
                job,
                f"Phase register complete in {time.perf_counter() - register_t:.1f}s",
            )

            store.update(
                job,
                status="done",
                phase="",
                artifact_uri=artifact_uri,
                model_version=version,
                finished_at=time.time(),
            )
            store.append_log(
                job,
                f"Training complete — version {version} registered and ready for promotion. "
                f"Total elapsed {time.perf_counter() - started_t:.1f}s.",
            )

        except Exception as exc:
            logger.exception("Training job %s failed: %s", job.job_id, exc)
            store.update(
                job,
                status="failed",
                error=str(exc),
                finished_at=time.time(),
            )
        finally:
            _semaphore.release()


# ------------------------------------------------------------------
# Phase implementations
# ------------------------------------------------------------------


def _phase_export(job: TrainingJob, store: TrainingJobStore, work_dir: Path) -> None:
    store.update(job, phase="export")
    store.append_log(job, "Phase 1/5 — Preparing exporter…")
    load_t = time.perf_counter()
    export_labels = _get_export_labels()
    store.append_log(
        job, f"Phase 1/5 — Exporter ready in {time.perf_counter() - load_t:.2f}s"
    )
    store.append_log(job, "Phase 1/5 — Exporting training labels from Neo4j…")

    result = export_labels(
        work_dir,
        log_fn=lambda line: store.append_log(job, line),
    )

    store.update(
        job,
        metrics={
            **job.metrics,
            "export": result,
        },
    )
    store.append_log(
        job,
        f"Exported {result['total']} labels → "
        f"{result['train_count']} train / {result['dev_count']} dev",
    )


def _phase_train(
    job: TrainingJob,
    store: TrainingJobStore,
    work_dir: Path,
    train_path: Path,
    dev_path: Path,
) -> Path:
    store.update(job, phase="train")
    store.append_log(job, "Phase 2/5 — Preparing trainer…")
    load_t = time.perf_counter()
    run_training = _get_run_training()
    store.append_log(
        job, f"Phase 2/5 — Trainer ready in {time.perf_counter() - load_t:.2f}s"
    )
    store.append_log(
        job, "Phase 2/5 — Running spaCy training (Bio_ClinicalBERT backbone)…"
    )

    model_dir, accel_meta = run_training(
        work_dir,
        train_path=train_path,
        dev_path=dev_path,
        log_fn=lambda line: store.append_log(job, line),
    )
    store.update(
        job,
        metrics={
            **job.metrics,
            "accelerator": accel_meta,
        },
    )
    store.append_log(
        job,
        "Accelerator telemetry "
        f"(requested={accel_meta.get('requested_accelerator')}, "
        f"resolved={accel_meta.get('resolved_accelerator')}, "
        f"fallback_applied={accel_meta.get('fallback_applied')}, "
        f"fallback_reason={accel_meta.get('fallback_reason') or 'none'})",
    )
    return model_dir


def _phase_export_relations(job: TrainingJob, store: TrainingJobStore, work_dir: Path) -> None:
    store.append_log(job, "Phase 1/5 — Exporting relation train/dev dataset…")
    export_relations = _get_export_relations()
    result = export_relations(
        work_dir,
        log_fn=lambda line: store.append_log(job, line),
    )
    store.update(
        job,
        metrics={
            **job.metrics,
            "relation_export": result,
        },
    )


def _phase_train_relations(
    job: TrainingJob, store: TrainingJobStore, work_dir: Path
) -> Path:
    store.append_log(job, "Phase 2/5 — Training relation model…")
    train_relations = _get_run_relation_training()
    relation_train = work_dir / "relation_train.jsonl"
    relation_model = work_dir / "relation_model.json"
    summary = train_relations(
        relation_train,
        relation_model,
        log_fn=lambda line: store.append_log(job, line),
    )
    store.update(job, metrics={**job.metrics, "relation_train": summary})
    return relation_model


def _phase_evaluate(
    job: TrainingJob,
    store: TrainingJobStore,
    model_dir: Path,
    dev_path: Path,
) -> dict:
    store.update(job, status="evaluating", phase="evaluate")
    store.append_log(job, "Phase 3/5 — Preparing evaluator…")
    load_t = time.perf_counter()
    evaluate_model = _get_evaluate_model()
    store.append_log(
        job, f"Phase 3/5 — Evaluator ready in {time.perf_counter() - load_t:.2f}s"
    )
    store.append_log(job, "Phase 3/5 — Evaluating precision/recall on dev set…")

    metrics = evaluate_model(
        model_dir,
        dev_path,
        log_fn=lambda line: store.append_log(job, line),
    )
    store.update(job, metrics={**job.metrics, "ner": metrics})
    return metrics


def _phase_evaluate_relations(
    job: TrainingJob,
    store: TrainingJobStore,
    relation_model_path: Path,
    work_dir: Path,
) -> dict:
    store.append_log(job, "Phase 3/5 — Evaluating relation model…")
    eval_relations = _get_evaluate_relation_model()
    relation_dev = work_dir / "relation_dev.jsonl"
    metrics = eval_relations(
        relation_model_path,
        relation_dev,
        log_fn=lambda line: store.append_log(job, line),
    )
    if not metrics.get("passed_gates", False):
        store.append_log(
            job,
            (
                f"Relation model gate failed: F1={metrics.get('f1', 0.0):.3f} "
                f"(min={metrics.get('min_f1', 0.6):.3f})"
            ),
        )
    return metrics


def _phase_upload(
    job: TrainingJob,
    store: TrainingJobStore,
    model_dir: Path,
    export_meta: dict,
) -> tuple[str, str]:
    store.update(job, status="uploading", phase="upload")
    store.append_log(job, "Phase 4/5 — Uploading NER head artifact to Azure Blob…")

    import datetime

    version = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    try:
        ModelStore = _get_model_store_cls()
        blob_store = ModelStore()
        artifact_uri = blob_store.upload(
            model_dir,
            version,
            schema_version=os.getenv("MODEL_REQUIRED_SCHEMA_VERSION", "1.0"),
            deid_version=os.getenv("MODEL_REQUIRED_DEID_VERSION", "1.0"),
            label_mapping_version=os.getenv("MODEL_REQUIRED_LABEL_VERSION", "1.0"),
            dataset_version=export_meta.get("exported_at", ""),
            notes=job.notes,
        )
    except Exception as exc:
        raise RuntimeError(f"Blob upload failed: {exc}") from exc

    store.append_log(job, f"Uploaded: {artifact_uri}")
    return artifact_uri, version


def _phase_register(
    job: TrainingJob,
    store: TrainingJobStore,
    version: str,
    artifact_uri: str,
    metrics: dict,
    export_meta: dict,
    started_at: float,
) -> None:
    store.update(job, phase="register")
    store.append_log(job, "Phase 5/5 — Registering version in ModelRegistry…")

    import datetime as _dt
    from libs.model_registry.registry import ModelRecord

    training_duration_s = round(time.time() - started_at, 1)
    accelerator_meta = (job.metrics or {}).get("accelerator", {})

    # Build the full V&V-traceable record.
    record = ModelRecord(
        model_name=os.getenv("MODEL_STORE_MODEL_NAME", "medspacy_clinical_ner"),
        model_version=version,
        model_path="",
        training_dataset_version=export_meta.get("exported_at", ""),
        schema_version=os.getenv("MODEL_REQUIRED_SCHEMA_VERSION", "1.0"),
        deid_version=os.getenv("MODEL_REQUIRED_DEID_VERSION", "1.0"),
        artifact_uri=artifact_uri,
        notes=json.dumps(
            {
                # Training provenance
                "triggered_by": job.triggered_by,
                "base_model": os.getenv(
                    "TRAINING_HF_BASE_MODEL", "emilyalsentzer/Bio_ClinicalBERT"
                ),
                "frozen_components": os.getenv(
                    "TRAINING_FROZEN_COMPONENTS", "transformer"
                ),
                "training_duration_s": training_duration_s,
                "requested_accelerator": accelerator_meta.get(
                    "requested_accelerator", "auto"
                ),
                "resolved_accelerator": accelerator_meta.get(
                    "resolved_accelerator", "cpu"
                ),
                "fallback_applied": bool(
                    accelerator_meta.get("fallback_applied", False)
                ),
                "fallback_reason": accelerator_meta.get("fallback_reason", ""),
                # Dataset statistics
                "train_count": export_meta.get("train_count", 0),
                "dev_count": export_meta.get("dev_count", 0),
                "total_labels": export_meta.get("total_records", 0),
                "holdback_count": len(export_meta.get("holdback_label_ids", [])),
                "label_set": export_meta.get("label_set", []),
                "exported_at": export_meta.get("exported_at", ""),
                "train_split_hash": export_meta.get("train_split_hash", ""),
                "dev_split_hash": export_meta.get("dev_split_hash", ""),
                "holdback_split_hash": export_meta.get("holdback_split_hash", ""),
                # Evaluation results (full detail for V&V report)
                "offline_f1": metrics.get("f1"),
                "offline_precision": metrics.get("precision"),
                "offline_recall": metrics.get("recall"),
                "per_label_metrics": metrics.get("per_label", {}),
                "dev_doc_count": metrics.get("dev_doc_count", 0),
                # Gate thresholds recorded at time of validation
                "gate_min_precision": metrics.get("min_precision"),
                "gate_min_recall": metrics.get("min_recall"),
                "gate_passed": metrics.get("passed_gates"),
                "relation_export_total": metrics.get("relation_export", {}).get("total", 0),
                "relation_f1": metrics.get("relation_model", {}).get("f1"),
                "relation_precision": metrics.get("relation_model", {}).get("precision"),
                "relation_recall": metrics.get("relation_model", {}).get("recall"),
                "relation_gate_passed": metrics.get("relation_model", {}).get("passed_gates"),
                # User notes
                "user_notes": job.notes,
            }
        ),
    )

    try:
        ModelRegistry = _get_model_registry_cls()
        registry = ModelRegistry()
        registry.register(record)
        registry.validate_offline(
            version=version,
            precision=metrics["precision"],
            recall=metrics["recall"],
        )
    except Exception as exc:
        raise RuntimeError(f"Registry registration failed: {exc}") from exc

    store.append_log(
        job,
        f"Version {version} registered — "
        f"P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f} "
        f"— status: offline_validated",
    )


def preload_training_modules(log_fn: Optional[Callable[[str], None]] = None) -> None:
    """Eagerly import heavy training modules to reduce first-job latency."""
    t0 = time.perf_counter()
    _get_export_labels()
    _get_export_relations()
    _get_run_training()
    _get_run_relation_training()
    _get_evaluate_model()
    _get_evaluate_relation_model()
    _get_model_store_cls()
    _get_model_registry_cls()
    msg = f"Training module preload complete in {time.perf_counter() - t0:.2f}s"
    logger.info(msg)
    if log_fn:
        log_fn(msg)


def _get_export_labels():
    global _export_labels_fn
    if _export_labels_fn is None:
        from app.label_exporter import export_labels

        _export_labels_fn = export_labels
    return _export_labels_fn


def _get_run_training():
    global _run_training_fn
    if _run_training_fn is None:
        from app.trainer import run_training

        _run_training_fn = run_training
    return _run_training_fn


def _get_export_relations():
    global _export_relations_fn
    if _export_relations_fn is None:
        from app.relation_exporter import export_relation_dataset

        _export_relations_fn = export_relation_dataset
    return _export_relations_fn


def _get_run_relation_training():
    global _run_relation_training_fn
    if _run_relation_training_fn is None:
        from app.relation_trainer import train_relation_model

        _run_relation_training_fn = train_relation_model
    return _run_relation_training_fn


def _get_evaluate_model():
    global _evaluate_model_fn
    if _evaluate_model_fn is None:
        from app.evaluator import evaluate_model

        _evaluate_model_fn = evaluate_model
    return _evaluate_model_fn


def _get_evaluate_relation_model():
    global _evaluate_relation_model_fn
    if _evaluate_relation_model_fn is None:
        from app.relation_evaluator import evaluate_relation_model

        _evaluate_relation_model_fn = evaluate_relation_model
    return _evaluate_relation_model_fn


def _get_model_store_cls():
    global _model_store_cls
    if _model_store_cls is None:
        from libs.model_store import ModelStore

        _model_store_cls = ModelStore
    return _model_store_cls


def _get_model_registry_cls():
    global _model_registry_cls
    if _model_registry_cls is None:
        if os.getenv("MODEL_REGISTRY_STORE", "").strip().lower() == "neo4j":
            from libs.model_registry.neo4j_registry import Neo4jModelRegistry

            _model_registry_cls = Neo4jModelRegistry
        else:
            from libs.model_registry import ModelRegistry

            _model_registry_cls = ModelRegistry
    return _model_registry_cls
