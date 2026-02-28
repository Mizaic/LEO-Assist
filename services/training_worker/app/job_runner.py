"""Training job runner — executes the full fine-tuning pipeline in a
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

import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from app.job_store import TrainingJob, TrainingJobStore

logger = logging.getLogger(__name__)

_MAX_CONCURRENT = int(os.getenv("TRAINING_MAX_CONCURRENT_JOBS", "1"))
_semaphore = threading.Semaphore(_MAX_CONCURRENT)


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
        store.update(job, status="failed", error="Another training job is already running. Try again later.")
        return

    store.update(job, status="running", started_at=time.time())

    with tempfile.TemporaryDirectory(prefix="training_job_") as tmp:
        work_dir = Path(tmp)
        try:
            _phase_export(job, store, work_dir)
            train_path = work_dir / "train.spacy"
            dev_path = work_dir / "dev.spacy"

            model_dir = _phase_train(job, store, work_dir, train_path, dev_path)
            metrics = _phase_evaluate(job, store, model_dir, dev_path)

            if not metrics["passed_gates"]:
                store.update(
                    job,
                    status="failed",
                    phase="evaluate",
                    error=(
                        f"Precision/recall below thresholds: "
                        f"P={metrics['precision']:.3f} R={metrics['recall']:.3f}"
                    ),
                    metrics=metrics,
                    finished_at=time.time(),
                )
                return

            artifact_uri, version = _phase_upload(job, store, model_dir)
            _phase_register(job, store, version, artifact_uri, metrics)

            store.update(
                job,
                status="done",
                phase="",
                artifact_uri=artifact_uri,
                model_version=version,
                metrics=metrics,
                finished_at=time.time(),
            )
            store.append_log(job, f"Training complete — version {version} registered and ready for promotion.")

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
    from app.label_exporter import export_labels

    store.update(job, phase="export")
    store.append_log(job, "Phase 1/5 — Exporting training labels from Neo4j…")

    result = export_labels(
        work_dir,
        log_fn=lambda line: store.append_log(job, line),
    )

    store.update(job, metrics={
        **job.metrics,
        "export": result,
    })
    store.append_log(
        job,
        f"Exported {result['total']} labels → "
        f"{result['train_count']} train / {result['dev_count']} dev"
    )


def _phase_train(
    job: TrainingJob,
    store: TrainingJobStore,
    work_dir: Path,
    train_path: Path,
    dev_path: Path,
) -> Path:
    from app.trainer import run_training

    store.update(job, phase="train")
    store.append_log(job, "Phase 2/5 — Running spaCy training (Bio_ClinicalBERT backbone)…")

    model_dir = run_training(
        work_dir,
        train_path=train_path,
        dev_path=dev_path,
        log_fn=lambda line: store.append_log(job, line),
    )
    return model_dir


def _phase_evaluate(
    job: TrainingJob,
    store: TrainingJobStore,
    model_dir: Path,
    dev_path: Path,
) -> dict:
    from app.evaluator import evaluate_model

    store.update(job, status="evaluating", phase="evaluate")
    store.append_log(job, "Phase 3/5 — Evaluating precision/recall on dev set…")

    metrics = evaluate_model(
        model_dir,
        dev_path,
        log_fn=lambda line: store.append_log(job, line),
    )
    store.update(job, metrics={**job.metrics, "ner": metrics})
    return metrics


def _phase_upload(
    job: TrainingJob,
    store: TrainingJobStore,
    model_dir: Path,
) -> tuple[str, str]:
    store.update(job, status="uploading", phase="upload")
    store.append_log(job, "Phase 4/5 — Uploading NER head artifact to Azure Blob…")

    import datetime
    version = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    try:
        from libs.model_store import ModelStore
        blob_store = ModelStore()
        artifact_uri = blob_store.upload(model_dir, version)
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
) -> None:
    store.update(job, phase="register")
    store.append_log(job, "Phase 5/5 — Registering version in ModelRegistry…")

    try:
        from libs.model_registry import ModelRegistry
        registry = ModelRegistry()
        registry.register(
            version=version,
            artifact_uri=artifact_uri,
            notes=job.notes,
        )
        registry.validate_offline(
            version=version,
            precision=metrics["precision"],
            recall=metrics["recall"],
        )
    except Exception as exc:
        raise RuntimeError(f"Registry registration failed: {exc}") from exc

    store.append_log(job, f"Version {version} registered — status: offline_validated")
