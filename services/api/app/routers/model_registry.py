"""Model Registry API — full lifecycle management for NER models.

All model lifecycle transitions (upload → validate → canary → promote → rollback)
are exposed here so the frontend can drive the complete user journey without
any CLI access.

Routes
------
GET  /model-registry/status                         Active model + inference health
GET  /model-registry/versions                       All registered versions
GET  /model-registry/versions/{version}             Single version detail + manifest
POST /model-registry/register                       Register a new version record
POST /model-registry/versions/{version}/upload      Upload model dir to blob store
POST /model-registry/versions/{version}/validate    Record offline eval metrics
POST /model-registry/versions/{version}/canary/start  Start canary phase
POST /model-registry/versions/{version}/canary/result Record canary KPI
POST /model-registry/versions/{version}/promote     Promote + trigger hot-reload
POST /model-registry/rollback                       Rollback active to prior version
GET  /model-registry/inference/health               Proxy to inference service /health
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from libs.model_registry.registry import ModelRecord, ModelRegistry, get_registry
from libs.model_store import ModelStore
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-registry", tags=["model-registry"])

_INFERENCE_ENDPOINT = os.getenv("CODING_MODEL_ENDPOINT", "http://localhost:8004")

_GOLD_MAX_CANDIDATES = int(os.getenv("MODEL_GOLD_MAX_CANDIDATES", "1500"))

_canary_jobs_lock = threading.Lock()
_canary_jobs: dict[str, dict[str, Any]] = {}


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class RegisterRequest(BaseModel):
    model_name: str = ""
    model_version: str
    model_path: str = ""
    training_dataset_version: str = ""
    schema_version: str = "1.0"
    deid_version: str = "1.0"
    notes: str = ""


class UploadRequest(BaseModel):
    model_dir: str
    schema_version: str = "1.0"
    deid_version: str = "1.0"
    label_mapping_version: str = "1.0"
    dataset_version: str = ""
    manifest_path: str = ""
    notes: str = ""


class ValidateRequest(BaseModel):
    precision: float
    recall: float
    notes: str = ""


class CanaryStartRequest(BaseModel):
    cohort: str = "canary_cohort"


class CanaryResultRequest(BaseModel):
    precision: float
    recall: float


class PromoteRequest(BaseModel):
    rollback_target_version: Optional[str] = None
    force: bool = False
    force_reason: str = ""


class RejectRequest(BaseModel):
    reason: str = ""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _record_to_dict(rec: ModelRecord) -> dict[str, Any]:
    return {
        "model_name": rec.model_name,
        "model_version": rec.model_version,
        "model_path": rec.model_path,
        "artifact_uri": rec.artifact_uri,
        "training_dataset_version": rec.training_dataset_version,
        "schema_version": rec.schema_version,
        "deid_version": rec.deid_version,
        "status": rec.status,
        "offline_precision": rec.offline_precision,
        "offline_recall": rec.offline_recall,
        "canary_precision": rec.canary_precision,
        "canary_recall": rec.canary_recall,
        "canary_cohort": rec.canary_cohort,
        "rollback_target_version": rec.rollback_target_version,
        "registered_at": rec.registered_at,
        "promoted_at": rec.promoted_at,
        "notes": rec.notes,
    }


def _f1(precision: Optional[float], recall: Optional[float]) -> Optional[float]:
    if precision is None or recall is None:
        return None
    denom = precision + recall
    if denom <= 0:
        return 0.0
    return (2.0 * precision * recall) / denom



def _compute_metrics(
    tp: dict[str, int],
    fp: dict[str, int],
    fn: dict[str, int],
) -> dict[str, Any]:
    labels = sorted(set(tp) | set(fp) | set(fn))
    per_label: list[dict[str, Any]] = []
    total_tp = total_fp = total_fn = 0
    for label in labels:
        l_tp = tp.get(label, 0)
        l_fp = fp.get(label, 0)
        l_fn = fn.get(label, 0)
        total_tp += l_tp
        total_fp += l_fp
        total_fn += l_fn
        precision = (l_tp / (l_tp + l_fp)) if (l_tp + l_fp) else 0.0
        recall = (l_tp / (l_tp + l_fn)) if (l_tp + l_fn) else 0.0
        f1 = _f1(precision, recall) or 0.0
        per_label.append(
            {
                "label": label,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "tp": l_tp,
                "fp": l_fp,
                "fn": l_fn,
            }
        )
    overall_precision = (total_tp / (total_tp + total_fp)) if (total_tp + total_fp) else 0.0
    overall_recall = (total_tp / (total_tp + total_fn)) if (total_tp + total_fn) else 0.0
    overall_f1 = _f1(overall_precision, overall_recall) or 0.0
    return {
        "overall": {
            "precision": overall_precision,
            "recall": overall_recall,
            "f1": overall_f1,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        "per_label": per_label,
    }


def _fetch_gold_labels(limit: int = _GOLD_MAX_CANDIDATES) -> list[dict[str, Any]]:
    """Fetch included TrainingLabel nodes as the gold evaluation corpus."""
    from libs.cypher.training_label_queries import GET_ALL_INCLUDED_LABELS_FOR_EXPORT
    client = PatientGraphClient()
    with client.session() as session:
        rows = session.run(GET_ALL_INCLUDED_LABELS_FOR_EXPORT).data()
    return rows[:limit]


def _set_canary_job(job_id: str, patch: dict[str, Any]) -> None:
    with _canary_jobs_lock:
        current = _canary_jobs.get(job_id, {})
        current.update(patch)
        _canary_jobs[job_id] = current


def _run_canary_gold_job(version: str, job_id: str) -> None:
    _set_canary_job(
        job_id,
        {
            "job_id": job_id,
            "version": version,
            "status": "running",
            "phase": "initializing",
            "message": "Preparing canary gold evaluation",
            "created_at": time.time(),
            "updated_at": time.time(),
        },
    )
    try:
        reg = get_registry()
        rec = reg.get(version)
        if not rec:
            raise RuntimeError(f"Version {version!r} not found")
        if rec.status not in {"offline_validated", "canary"}:
            raise RuntimeError(f"Version {version!r} must be offline_validated or canary")

        _set_canary_job(
            job_id,
            {"phase": "starting_canary", "message": "Marking version as canary", "updated_at": time.time()},
        )
        if rec.status == "offline_validated":
            reg.start_canary(version, cohort="gold_patients")

        _set_canary_job(
            job_id,
            {"phase": "downloading_model", "message": "Downloading artifact from model store", "updated_at": time.time()},
        )
        store = ModelStore()
        model_dir = store.download(version)
        import spacy  # noqa: PLC0415 — lazy to avoid CuPy CUDA probe at API startup
        nlp = spacy.load(str(model_dir))

        _set_canary_job(
            job_id,
            {"phase": "loading_gold_data", "message": "Fetching included TrainingLabel gold corpus", "updated_at": time.time()},
        )
        import json as _json
        rows = _fetch_gold_labels()
        if not rows:
            raise RuntimeError("No included TrainingLabel records found — add labels in the Training Data tab first")

        # Reuse the same label normalisation as the offline evaluator / exporter.
        _LABEL_MAP: dict[str, str] = {
            "disorder": "DISORDER", "finding": "FINDING", "procedure": "PROCEDURE",
            "observable_entity": "OBSERVABLE", "qualifier_value": "QUALIFIER",
            "substance": "SUBSTANCE", "medicinal_product": "MEDICINAL_PRODUCT",
            "clinical_drug": "CLINICAL_DRUG", "situation": "SITUATION",
            "event": "EVENT", "body_structure": "BODY_STRUCTURE",
            "tumor_staging": "TUMOR_STAGING",
            "X_TEMPORAL": "TEMPORAL",
            "X_DOSAGE": "DOSAGE", "X_FREQUENCY": "FREQUENCY", "X_ROUTE": "ROUTE",
        }

        def _norm(raw: str) -> str:
            return _LABEL_MAP.get(raw, raw.upper())

        tp: dict[str, int] = {}
        fp: dict[str, int] = {}
        fn: dict[str, int] = {}
        docs_scored = 0

        _set_canary_job(
            job_id,
            {"phase": "scoring", "message": "Running model over gold labels", "total_candidates": len(rows), "updated_at": time.time()},
        )
        for idx, row in enumerate(rows, start=1):
            if idx % 50 == 0:
                _set_canary_job(
                    job_id,
                    {"progress": idx / max(len(rows), 1), "processed_candidates": idx, "updated_at": time.time()},
                )
            text = str(row.get("text") or "")
            if not text.strip():
                continue
            try:
                entities = _json.loads(row.get("entities_json") or "[]")
            except Exception:
                continue

            gold: set[tuple[int, int, str]] = set()
            for ent in entities:
                try:
                    start = int(ent.get("start", 0))
                    end = int(ent.get("end", 0))
                    label = _norm(str(ent.get("label", "") or ""))
                    if end > start and label:
                        gold.add((start, end, label))
                except Exception:
                    continue

            pred_doc = nlp(text)
            pred = {(e.start_char, e.end_char, e.label_) for e in pred_doc.ents}

            for span in pred:
                lbl = span[2]
                if span in gold:
                    tp[lbl] = tp.get(lbl, 0) + 1
                else:
                    fp[lbl] = fp.get(lbl, 0) + 1
            for span in gold:
                lbl = span[2]
                if span not in pred:
                    fn[lbl] = fn.get(lbl, 0) + 1
            docs_scored += 1

        metrics = _compute_metrics(tp, fp, fn)
        overall = metrics["overall"]
        reg.record_canary_result(
            version,
            precision=float(overall["precision"]),
            recall=float(overall["recall"]),
        )
        _set_canary_job(
            job_id,
            {
                "status": "completed",
                "phase": "completed",
                "message": "Gold test completed",
                "updated_at": time.time(),
                "completed_at": time.time(),
                "metrics": metrics,
                "sentences_scored": docs_scored,
                "candidate_count": len(rows),
            },
        )
    except Exception as exc:
        logger.exception("Gold canary run failed for version %s", version)
        _set_canary_job(
            job_id,
            {
                "status": "failed",
                "phase": "failed",
                "message": str(exc),
                "updated_at": time.time(),
                "completed_at": time.time(),
            },
        )
    finally:
        pass


async def _inference_health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_INFERENCE_ENDPOINT}/health")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {"status": "unreachable", "loaded": False, "active_version": None}


# ------------------------------------------------------------------
# GET /model-registry/status
# ------------------------------------------------------------------

@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Return active model record and inference service health in one call."""
    reg = get_registry()
    active = reg.get_active()
    inference = await _inference_health()
    return {
        "active_model": _record_to_dict(active) if active else None,
        "inference_service": inference,
        "total_versions": len(reg.list_all()),
    }


# ------------------------------------------------------------------
# GET /model-registry/versions
# ------------------------------------------------------------------

@router.get("/versions")
def list_versions() -> dict[str, Any]:
    """Return all registered model versions with their lifecycle status."""
    reg = get_registry()
    versions = [_record_to_dict(r) for r in reg.list_all()]
    # Sort: promoted first, then by registered_at descending
    _order = {
        "promoted": 0, "canary": 1, "offline_validated": 2,
        "registered": 3, "rollback": 4, "deprecated": 5,
    }
    versions.sort(key=lambda v: (_order.get(v["status"], 9), v["registered_at"]), reverse=False)
    return {"versions": versions, "count": len(versions)}


# ------------------------------------------------------------------
# GET /model-registry/versions/{version}
# ------------------------------------------------------------------

@router.get("/versions/{version}")
async def get_version(version: str) -> dict[str, Any]:
    """Return full detail for a single version including blob manifest."""
    reg = get_registry()
    rec = reg.get(version)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")

    manifest = None
    if rec.artifact_uri:
        try:
            from libs.model_store import ModelStore
            store = ModelStore()
            art = store.get_manifest(version)
            if art:
                manifest = art.to_dict()
        except Exception:
            pass

    return {
        "record": _record_to_dict(rec),
        "manifest": manifest,
    }


# ------------------------------------------------------------------
# POST /model-registry/register
# ------------------------------------------------------------------

@router.post("/register")
def register_version(req: RegisterRequest) -> dict[str, Any]:
    """Register a new model version in the lifecycle registry.

    This is the first step.  Use /upload next to push the model artifact to blob.
    """
    reg = get_registry()
    if reg.get(req.model_version):
        raise HTTPException(
            status_code=409,
            detail=f"Version {req.model_version!r} already registered",
        )
    rec = ModelRecord(
        model_name=req.model_name or os.getenv("CODING_MODEL_NAME", "medspacy_clinical_ner"),
        model_version=req.model_version,
        model_path=req.model_path,
        training_dataset_version=req.training_dataset_version,
        schema_version=req.schema_version,
        deid_version=req.deid_version,
        notes=req.notes,
    )
    reg.register(rec)
    return {"registered": True, "record": _record_to_dict(rec)}


# ------------------------------------------------------------------
# POST /model-registry/versions/{version}/upload
# ------------------------------------------------------------------

def _do_upload(version: str, req: UploadRequest) -> None:
    """Background task: upload model dir to blob and run compat gate."""
    try:
        reg = get_registry()
        rec = reg.get(version)
        if not rec:
            logger.error("Upload background: version %s not found", version)
            return

        # Optional compatibility gate
        if req.manifest_path:
            from libs.model_registry.manifest_reader import CompatibilityGate
            gate = CompatibilityGate()
            result = gate.check(
                manifest_path=req.manifest_path,
                model_schema_version=req.schema_version,
                model_deid_version=req.deid_version,
                model_label_mapping_version=req.label_mapping_version,
                model_dataset_version=req.dataset_version,
            )
            if not result.passed:
                logger.error(
                    "Upload blocked by compatibility gate for v%s: %s",
                    version, result.failures,
                )
                rec.notes = f"UPLOAD BLOCKED: {'; '.join(result.failures)}"
                reg._save()
                return

        uri = reg.upload_artifact(
            version,
            req.model_dir,
            schema_version=req.schema_version,
            deid_version=req.deid_version,
            label_mapping_version=req.label_mapping_version,
            dataset_version=req.dataset_version,
            notes=req.notes,
        )
        logger.info("Upload complete for v%s: %s", version, uri)
    except Exception:
        logger.exception("Upload background task failed for v%s", version)


@router.post("/versions/{version}/upload")
def upload_version(
    version: str,
    req: UploadRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Upload a trained model directory to Azure Blob Storage.

    Runs as a background task — returns immediately.
    Poll GET /versions/{version} to track when artifact_uri is populated.

    The model directory must be accessible on the API server's filesystem.
    For remote uploads, use the CLI: ``python scripts/upload_model.py``.
    """
    reg = get_registry()
    if not reg.get(version):
        raise HTTPException(
            status_code=404,
            detail=f"Version {version!r} not registered. POST /register first.",
        )
    background_tasks.add_task(_do_upload, version, req)
    return {
        "accepted": True,
        "message": (
            f"Upload of v{version} started in background. "
            "Poll GET /model-registry/versions/{version} for artifact_uri."
        ),
    }


# ------------------------------------------------------------------
# POST /model-registry/versions/{version}/validate
# ------------------------------------------------------------------

@router.post("/versions/{version}/validate")
def validate_version(version: str, req: ValidateRequest) -> dict[str, Any]:
    """Record offline eval precision/recall for a registered version.

    The registry compares against MODEL_MIN_PRECISION / MODEL_MIN_RECALL
    thresholds and advances to offline_validated or deprecated accordingly.
    """
    reg = get_registry()
    if not reg.get(version):
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")
    try:
        rec = reg.validate_offline(
            version,
            precision=req.precision,
            recall=req.recall,
            notes=req.notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "record": _record_to_dict(rec),
        "passed": rec.status == "offline_validated",
    }


# ------------------------------------------------------------------
# POST /model-registry/versions/{version}/canary/start
# ------------------------------------------------------------------

@router.post("/versions/{version}/canary/start")
def start_canary(version: str, req: CanaryStartRequest) -> dict[str, Any]:
    """Advance an offline-validated version to canary deployment."""
    reg = get_registry()
    if not reg.get(version):
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")
    try:
        rec = reg.start_canary(version, cohort=req.cohort)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"record": _record_to_dict(rec)}


# ------------------------------------------------------------------
# POST /model-registry/versions/{version}/canary/result
# ------------------------------------------------------------------

@router.post("/versions/{version}/canary/result")
def record_canary_result(version: str, req: CanaryResultRequest) -> dict[str, Any]:
    """Record canary cohort KPI precision/recall for a version in canary state."""
    reg = get_registry()
    if not reg.get(version):
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")
    try:
        rec = reg.record_canary_result(version, precision=req.precision, recall=req.recall)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "record": _record_to_dict(rec),
        "ready_to_promote": (
            rec.canary_precision is not None
            and rec.canary_recall is not None
        ),
    }


# ------------------------------------------------------------------
# POST /model-registry/versions/{version}/canary/run-gold
# ------------------------------------------------------------------

@router.post("/versions/{version}/canary/run-gold")
def run_canary_gold(version: str) -> dict[str, Any]:
    """Run automated gold-patient canary evaluation in a background thread."""
    reg = get_registry()
    rec = reg.get(version)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")
    if rec.status not in {"offline_validated", "canary"}:
        raise HTTPException(
            status_code=400,
            detail=f"Version {version!r} must be offline_validated or canary",
        )
    job_id = str(uuid.uuid4())
    _set_canary_job(
        job_id,
        {
            "job_id": job_id,
            "version": version,
            "status": "accepted",
            "phase": "queued",
            "message": "Canary gold run queued",
            "created_at": time.time(),
            "updated_at": time.time(),
        },
    )
    thread = threading.Thread(target=_run_canary_gold_job, args=(version, job_id), daemon=True)
    thread.start()
    return {"accepted": True, "job_id": job_id, "version": version}


@router.get("/canary-jobs/{job_id}")
def get_canary_gold_job(job_id: str) -> dict[str, Any]:
    with _canary_jobs_lock:
        job = _canary_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


# ------------------------------------------------------------------
# POST /model-registry/versions/{version}/promote
# ------------------------------------------------------------------

@router.post("/versions/{version}/promote")
def promote_version(version: str, req: PromoteRequest) -> dict[str, Any]:
    """Promote a canary version to production active.

    Validates canary KPI thresholds, promotes, and automatically signals
    the inference service to hot-reload the new version via POST /reload.
    """
    reg = get_registry()
    if not reg.get(version):
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")
    try:
        rec = reg.promote(
            version,
            rollback_target_version=req.rollback_target_version,
            force=req.force,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "promoted": True,
        "forced": req.force,
        "force_reason": req.force_reason,
        "record": _record_to_dict(rec),
        "inference_reload_triggered": True,
    }


@router.post("/versions/{version}/reject")
def reject_version(version: str, req: RejectRequest) -> dict[str, Any]:
    """Mark a version as deprecated after failed human review/canary decision."""
    reg = get_registry()
    rec = reg.get(version)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Version {version!r} not found")
    rec.status = "deprecated"
    note = (req.reason or "Rejected in model deployment workflow").strip()
    rec.notes = f"{rec.notes}\n{note}".strip()
    reg._save()  # keep backward compatibility without changing registry API surface
    return {"rejected": True, "record": _record_to_dict(rec)}


# ------------------------------------------------------------------
# POST /model-registry/rollback
# ------------------------------------------------------------------

@router.post("/rollback")
def rollback() -> dict[str, Any]:
    """Rollback the active model to its registered rollback target.

    Automatically signals the inference service to hot-reload the prior version.
    """
    reg = get_registry()
    try:
        rec = reg.rollback()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "rolled_back_to": rec.model_version,
        "record": _record_to_dict(rec),
        "inference_reload_triggered": True,
    }


# ------------------------------------------------------------------
# GET /model-registry/inference/health
# ------------------------------------------------------------------

@router.get("/inference/health")
async def inference_health() -> dict[str, Any]:
    """Proxy the inference service /health endpoint.

    Returns the active version currently loaded in memory and whether the
    service is healthy.  Used by the frontend status card.
    """
    result = await _inference_health()

    # Also fetch available versions from blob store if inference healthy
    available: list[dict] = []
    if result.get("status") == "ok":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{_INFERENCE_ENDPOINT}/versions")
                if resp.status_code == 200:
                    available = resp.json().get("versions", [])
        except Exception:
            pass

    return {**result, "available_versions": available}
