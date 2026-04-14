"""Pipeline Worker service — dual-mode: HTTP server + message bus consumer.

The HTTP server (FastAPI/uvicorn on PIPELINE_WORKER_PORT, default 8006)
exposes endpoints that require SSE streaming back to a browser:
  POST /test-run/batch  — interactive batch dry-run against TrainingCandidates

The message bus consumer runs as an asyncio background task and handles
production pipeline-job messages published by the Core API.

Why dual-mode instead of running batch on the Core API?
  Batch dry-runs invoke LLM calls, spaCy NLP, and Neo4j queries for every
  candidate — CPU/IO work that must not compete with Core API request serving.
  The pipeline worker is the right place for heavy pipeline execution.
"""

# aca-image: pipeline-worker build/deploy verification (no runtime effect).

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from libs.auth.service_auth import verify_service_token

# Pre-import few_shot_selector here (main thread) so the sentence-transformers
# package is loaded before background warm-up threads start. Deferring into a
# thread races with spacy-transformers initialising the transformers lazy module,
# which intermittently causes an EncoderDecoderConfig ImportError.
import libs.prompts.few_shot_selector  # noqa: F401

from libs.message_bus.factory import create_message_bus
from libs.message_bus.base import Message
from libs.utils.logging import configure_logging
from libs.workflow.engine import ActionDefinition, WorkflowEngine
from libs.workflow.events import ServiceBusEventHandler

configure_logging(service_name="pipeline-worker")

for _ns in (
    "azure.servicebus",
    "azure.servicebus._pyamqp",
    "azure.servicebus._pyamqp.aio",
    "azure.core.pipeline.policies.http_logging_policy",
    "uamqp",
    "httpx",
    "botocore",
    "botocore.credentials",
):
    logging.getLogger(_ns).setLevel(logging.WARNING)

logger = logging.getLogger("pipeline-worker")

QUEUE_NAME = os.getenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")
PORT = int(os.getenv("PIPELINE_WORKER_PORT", "8006"))
_guidance_generate_jobs: dict[str, dict[str, Any]] = {}

if QUEUE_NAME == "coding-jobs":
    raise RuntimeError(
        "Invalid PIPELINE_QUEUE_NAME=coding-jobs. "
        "Set PIPELINE_QUEUE_NAME=pipeline-jobs."
    )

_batch_trace_runs: dict[str, dict[str, Any]] = {}
_batch_trace_lock = threading.Lock()
_BATCH_TRACE_TTL_SECONDS = max(300, int(os.getenv("BATCH_TRACE_TTL_SECONDS", "3600")))
_BATCH_TRACE_MAX_RUNS = max(10, int(os.getenv("BATCH_TRACE_MAX_RUNS", "200")))
_BATCH_TRACE_PASS_SAMPLE_RATE = float(os.getenv("BATCH_TRACE_PASS_SAMPLE_RATE", "0"))
_consumer_state: dict[str, Any] = {
    "queue": QUEUE_NAME,
    "running": False,
    "subscribed": False,
    "started_at": None,
    "last_heartbeat_at": None,
    "last_message_at": None,
    "last_error": None,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_batch_traces(now: float | None = None) -> None:
    ts = now or time.time()
    expired = [
        run_id
        for run_id, run in _batch_trace_runs.items()
        if float(run.get("expires_at", 0)) <= ts
    ]
    for run_id in expired:
        _batch_trace_runs.pop(run_id, None)

    if len(_batch_trace_runs) <= _BATCH_TRACE_MAX_RUNS:
        return
    # Keep newest runs when the in-memory cache grows too large.
    ordered = sorted(
        _batch_trace_runs.items(),
        key=lambda item: float(item[1].get("created_at", 0)),
    )
    overflow = len(_batch_trace_runs) - _BATCH_TRACE_MAX_RUNS
    for run_id, _ in ordered[:overflow]:
        _batch_trace_runs.pop(run_id, None)


def _store_batch_candidate_trace(
    batch_run_id: str, candidate_id: str, payload: dict[str, Any]
) -> None:
    now = time.time()
    with _batch_trace_lock:
        _cleanup_batch_traces(now)
        run = _batch_trace_runs.setdefault(
            batch_run_id,
            {
                "created_at": now,
                "expires_at": now + _BATCH_TRACE_TTL_SECONDS,
                "candidates": {},
            },
        )
        run["expires_at"] = max(
            float(run.get("expires_at", 0)), now + _BATCH_TRACE_TTL_SECONDS
        )
        candidates = run.setdefault("candidates", {})
        candidates[candidate_id] = payload


def _get_batch_candidate_trace(
    batch_run_id: str, candidate_id: str
) -> dict[str, Any] | None:
    now = time.time()
    with _batch_trace_lock:
        _cleanup_batch_traces(now)
        run = _batch_trace_runs.get(batch_run_id)
        if not run:
            return None
        payload = (run.get("candidates") or {}).get(candidate_id)
        if not payload:
            return None
        return dict(payload)


# ── Lifespan: start/stop message bus consumer in background ──────────────────


def _warm_up() -> None:
    """Pre-load all models and singletons used by the pipeline.

    Runs in a background thread during startup so uvicorn reports healthy
    immediately, but the first real request doesn't pay a cold-start penalty.

    Things warmed here must match every subgraph that runs on this worker:
      - Bio_ClinicalBERT sentence transformer  (few-shot prompt selection)
      - spaCy / medspacy ConText NLP pipeline  (extraction + post-processing)
    """
    import threading

    def _warm_embedder() -> None:
        try:
            from libs.prompts.few_shot_selector import warm_shared_embedder

            warm_shared_embedder()  # sentence_transformers already imported in main thread
        except Exception:
            logger.warning("Embedder warm-up failed (non-fatal)", exc_info=True)

    def _warm_nlp() -> None:
        try:
            # Importing triggers module-level spaCy/medspacy setup; calling
            # _get_nlp() builds the ConText pipeline and caches it globally.
            from libs.ner.context_engine import _get_nlp

            _get_nlp()
            logger.info("Pipeline Worker: ConText NLP pipeline ready")
        except Exception:
            logger.warning("ConText NLP warm-up failed (non-fatal)", exc_info=True)

    def _warm_registry() -> None:
        try:
            # Touch the subgraph registry so all subgraphs are imported and any
            # module-level globals (model configs, rule sets) are initialised.
            from libs.pipeline_graph.registry import get_registry

            reg = get_registry()
            count = len(reg.list_subgraphs())
            logger.info(
                "Pipeline Worker: subgraph registry ready (%d subgraphs)", count
            )
        except Exception:
            logger.warning("Registry warm-up failed (non-fatal)", exc_info=True)

    threads = [
        threading.Thread(target=_warm_embedder, daemon=True, name="warm-embedder"),
        threading.Thread(target=_warm_nlp, daemon=True, name="warm-nlp"),
        threading.Thread(target=_warm_registry, daemon=True, name="warm-registry"),
    ]
    for t in threads:
        t.start()
    logger.info("Pipeline Worker: model warm-up started in background")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Warm up models, then start the message bus consumer as a background task."""
    # Kick off model warm-up (non-blocking — runs in daemon threads)
    _warm_up()

    bus = create_message_bus()

    neo4j_driver = None
    patient_audit_driver = None
    try:
        from libs.neo4j_client.client import get_async_driver

        neo4j_driver = get_async_driver()
    except Exception:
        logger.warning(
            "Knowledge Graph driver not available — running without graph storage"
        )
    try:
        from libs.neo4j_client.client import get_async_patient_driver

        patient_audit_driver = get_async_patient_driver()
    except Exception:
        logger.warning(
            "Patient Graph driver not available — pipeline spend audit writes disabled"
        )

    engine = WorkflowEngine(
        neo4j_driver=neo4j_driver,
        audit_neo4j_driver=patient_audit_driver,
        message_bus=bus,
    )
    handler = ServiceBusEventHandler(engine)

    async def on_message(msg: Message) -> None:
        _consumer_state["last_message_at"] = _utc_now_iso()
        try:
            await handler.handle_message(msg)
        except Exception:
            # Emit a progress error event so UI subscribers do not appear idle
            # when a run fails before first workflow step.
            try:
                from services.coding_worker.app.services.progress_publisher import (
                    publish_progress,
                )

                run_id = str(msg.correlation_id or msg.message_id or "")
                if run_id:
                    publish_progress(
                        run_id,
                        {
                            "type": "pipeline_error",
                            "run_id": run_id,
                            "message": "Pipeline worker failed before execution. See worker logs for details.",
                        },
                    )
            except Exception:
                pass
            raise

    consumer_task = asyncio.create_task(_run_consumer(bus, on_message))
    logger.info("Pipeline Worker: message bus consumer started (queue=%s)", QUEUE_NAME)

    yield  # serve HTTP requests

    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await bus.close()
    if neo4j_driver is not None:
        await neo4j_driver.close()
    if patient_audit_driver is not None:
        await patient_audit_driver.close()
    logger.info("Pipeline Worker: shutdown complete")


async def _run_consumer(bus, on_message) -> None:
    _consumer_state["running"] = True
    _consumer_state["started_at"] = _utc_now_iso()
    _consumer_state["last_error"] = None
    _consumer_state["subscribed"] = False
    _consumer_state["last_heartbeat_at"] = _utc_now_iso()
    try:
        await bus.subscribe(QUEUE_NAME, on_message)
        _consumer_state["subscribed"] = True
        logger.info("Pipeline Worker subscribed. Waiting for messages...")
        while True:
            _consumer_state["last_heartbeat_at"] = _utc_now_iso()
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _consumer_state["last_error"] = str(exc)
        logger.exception("Pipeline Worker consumer loop failed")
        raise
    finally:
        _consumer_state["running"] = False


def _consumer_health_payload() -> dict[str, Any]:
    healthy = bool(
        _consumer_state.get("running")
        and _consumer_state.get("subscribed")
        and not _consumer_state.get("last_error")
    )
    return {"healthy": healthy, **_consumer_state}


app = FastAPI(title="Pipeline Worker", lifespan=lifespan)


# ── Shared request / response models ─────────────────────────────────────────
# Mirrors the models previously on the Core API — kept in one place now that all
# interactive pipeline execution lives here.


class TestRunAction(BaseModel):
    id: str
    subgraph_id: str
    label: str = ""
    node_type: str = "action"
    config: dict = {}


class TestRunEdge(BaseModel):
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None


class StepTrace(BaseModel):
    step_id: str
    subgraph_id: str
    label: str
    node_type: str
    input_state: dict
    output_state: dict
    duration_ms: int
    error: str | None
    status: str


class TestRunRequest(BaseModel):
    plan_id: str | None = None
    actions: list[TestRunAction]
    edges: list[TestRunEdge]
    input: dict  # {encounter_text?, patient_id?, encounter_id?}


class TestRunResponse(BaseModel):
    status: str
    steps: list[StepTrace]
    final_state: dict


class BatchTestRequest(BaseModel):
    actions: list[TestRunAction]
    edges: list[TestRunEdge]
    limit: int = 20  # max candidates to process (capped at 100)
    status_filter: str | None = "pending"
    concurrency: int = 3  # parallel candidates (1–10)


class LabelVerifyStartRequest(BaseModel):
    mode: str = "all"
    reset_pending: bool = False


class GuidanceGenerateRequest(BaseModel):
    guideline_id: str


# ── Single-record dry-run helpers ────────────────────────────────────────────


def _build_actions(
    body_actions: list[TestRunAction], body_edges: list[TestRunEdge]
) -> tuple[list[ActionDefinition], dict]:
    """Shared edge/action builder used by all three dry-run endpoints."""
    edges_by_target: dict[str, list[dict]] = {}
    for e in body_edges:
        edges_by_target.setdefault(e.target, []).append(
            {
                "actionId": e.source,
                "sourceHandle": e.source_handle,
                "targetHandle": e.target_handle,
            }
        )
    actions = [
        ActionDefinition(
            action_id=a.id,
            subgraph_id=a.subgraph_id,
            trigger_type=a.config.get("trigger_type", ""),
            trigger_name=a.config.get("trigger_name", ""),
            node_type=a.node_type,
            config={"label": a.label, **a.config},
            related_edges=edges_by_target.get(a.id, []),
            sequence=idx,
        )
        for idx, a in enumerate(body_actions)
    ]
    return actions, edges_by_target


@app.post(
    "/test-run",
    response_model=TestRunResponse,
    dependencies=[Depends(verify_service_token)],
)
async def test_run_pipeline(body: TestRunRequest) -> TestRunResponse:
    """Dry-run the draft pathway against a single provided input (non-streaming).

    Executes each step in DAG order, capturing pipeline_state snapshots before
    and after every step. No data is written to any database.
    """
    actions, _ = _build_actions(body.actions, body.edges)

    initial: dict = dict(body.input)
    initial.setdefault("patient_id", "test-patient")
    initial.setdefault("encounter_id", "test-encounter")
    initial.setdefault("run_id", str(uuid.uuid4()))

    engine = WorkflowEngine()
    result = await engine.trace_run(actions, initial)

    return TestRunResponse(
        status=result["status"],
        steps=[StepTrace(**s) for s in result["steps"]],
        final_state=result["final_state"],
    )


@app.post("/test-run/stream", dependencies=[Depends(verify_service_token)])
async def test_run_pipeline_stream(body: TestRunRequest) -> StreamingResponse:
    """SSE stream of a single-record pipeline dry-run — one event per step.

    Event format (text/event-stream):
        event: step_start   data: {"type":"step_start","step_id":"...","label":"...","subgraph_id":"..."}
        event: step_done    data: {"type":"step_done","step_trace":{...StepTrace...}}
        event: pipeline_done  data: {"type":"pipeline_done","status":"...","final_state":{...}}

    No data is written to any database (dry_run=True in pipeline state).
    Runs on the pipeline worker — not the Core API — so LLM/NLP work does not
    compete with live request serving.
    """
    actions, _ = _build_actions(body.actions, body.edges)

    initial: dict = dict(body.input)
    initial.setdefault("patient_id", "test-patient")
    initial.setdefault("encounter_id", "test-encounter")
    initial.setdefault("run_id", str(uuid.uuid4()))

    engine = WorkflowEngine()

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for event in engine.trace_run_stream(actions, initial):
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        except Exception as exc:
            err = {"type": "error", "message": str(exc)}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Batch dry-run endpoint ────────────────────────────────────────────────────


@app.post("/test-run/batch", dependencies=[Depends(verify_service_token)])
async def batch_test_run(body: BatchTestRequest) -> StreamingResponse:
    """Batch dry-run of the draft pathway against real TrainingCandidates.

    Fetches up to ``limit`` TrainingCandidates from the Knowledge Graph and
    runs each through the draft pipeline in dry_run mode (no writes).
    Results are streamed back as SSE, one event per candidate, with a
    final ``batch_done`` summary.

    This endpoint lives on the pipeline worker (not the Core API) so that
    heavy LLM/NLP work does not block Core API request serving.
    """
    from libs.cypher.training_candidate_queries import GET_TRAINING_CANDIDATES_PAGE
    from libs.neo4j_client.client import KnowledgeGraphClient

    limit = max(1, min(body.limit, 100))
    concurrency = max(1, min(body.concurrency, 10))

    # ── Fetch candidates from the Knowledge Graph ─────────────────────────────
    client = KnowledgeGraphClient()
    candidates: list[dict] = []
    try:
        with client.session() as session:
            rows = session.run(
                GET_TRAINING_CANDIDATES_PAGE,
                status=body.status_filter,
                source=None,
                search=None,
                skip=0,
                limit=limit,
            )
            candidates = [dict(r) for r in rows]
    finally:
        client.close()

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No TrainingCandidates found"
            + (f" with status='{body.status_filter}'" if body.status_filter else ""),
        )

    # ── Build ActionDefinitions (shared, immutable across all candidates) ─────
    actions, _ = _build_actions(body.actions, body.edges)

    total = len(candidates)
    batch_run_id = str(uuid.uuid4())

    async def event_stream() -> AsyncGenerator[str, None]:  # noqa: C901
        passed = 0
        halted = 0
        errored = 0
        by_step_stats: dict[str, dict] = {}

        q: asyncio.Queue[str | None] = asyncio.Queue()

        def put(event_name: str, payload: dict) -> None:
            q.put_nowait(f"event: {event_name}\ndata: {json.dumps(payload)}\n\n")

        async def run_candidate(idx: int, cand: dict, sem: asyncio.Semaphore) -> None:
            nonlocal passed, halted, errored
            async with sem:
                candidate_id = cand.get("candidate_id", f"cand-{idx}")
                text = cand.get("text") or ""
                text_preview = text[:120].replace("\n", " ") + (
                    "…" if len(text) > 120 else ""
                )

                put(
                    "candidate_start",
                    {
                        "type": "candidate_start",
                        "batch_run_id": batch_run_id,
                        "candidate_id": candidate_id,
                        "text_preview": text_preview,
                        "index": idx + 1,
                        "total": total,
                    },
                )

                initial: dict = {
                    "encounter_text": text,
                    "candidate_id": candidate_id,
                    "patient_id": "batch-dry-run",
                    "encounter_id": candidate_id,
                    "run_id": str(uuid.uuid4()),
                    "dry_run": True,
                }

                t0 = time.time()
                final_status = "completed"
                halted_at: str | None = None
                halted_at_subgraph: str | None = None
                halt_reason: str | None = None
                verification_is_accurate: bool | None = None
                verification_confidence: float | None = None
                verification_threshold: float | None = None
                verification_issues: list[str] | None = None
                error_msg: str | None = None
                step_traces: list[dict[str, Any]] = []

                try:
                    engine = WorkflowEngine()
                    async for ev in engine.trace_run_stream(actions, initial):
                        if ev["type"] == "step_done":
                            trace = ev.get("step_trace", {})
                            if isinstance(trace, dict):
                                step_traces.append(dict(trace))
                            sg = trace.get("subgraph_id") or "unknown"
                            lbl = trace.get("label") or sg
                            st = trace.get("status")

                            entry = by_step_stats.setdefault(
                                sg, {"label": lbl, "ran": 0, "halted": 0}
                            )
                            entry["ran"] += 1

                            if st == "halted":
                                final_status = "halted"
                                halted_at = lbl
                                halted_at_subgraph = sg
                                halt_reason = trace.get("halt_reason")
                                if sg == "verification":
                                    out_state = trace.get("output_state") or {}
                                    if isinstance(out_state, dict):
                                        verification_threshold_raw = out_state.get(
                                            "confidence_threshold"
                                        )
                                        try:
                                            verification_threshold = float(
                                                verification_threshold_raw
                                            )
                                        except Exception:
                                            verification_threshold = None
                                        verification = (
                                            out_state.get("verification_result") or {}
                                        )
                                        if isinstance(verification, dict):
                                            verification_is_accurate = bool(
                                                verification.get("is_accurate", False)
                                            )
                                            conf_raw = verification.get("confidence")
                                            try:
                                                verification_confidence = float(
                                                    conf_raw
                                                )
                                            except Exception:
                                                verification_confidence = None
                                            issues_raw = verification.get("issues")
                                            if isinstance(issues_raw, list):
                                                verification_issues = [
                                                    str(i)
                                                    for i in issues_raw
                                                    if str(i).strip()
                                                ]
                                            elif issues_raw is None:
                                                verification_issues = []
                                            else:
                                                verification_issues = [str(issues_raw)]
                                entry["halted"] += 1
                            elif st == "error" and final_status != "halted":
                                final_status = "error"
                                error_msg = trace.get("error") or "Unknown error"

                            put(
                                "step_progress",
                                {
                                    "type": "step_progress",
                                    "candidate_id": candidate_id,
                                    "subgraph_id": sg,
                                    "label": lbl,
                                    "status": st,
                                    "ran": entry["ran"],
                                    "halted": entry["halted"],
                                },
                            )

                        elif ev["type"] == "pipeline_done":
                            ps = ev.get("status", "completed")
                            if ps not in ("completed",) and final_status == "completed":
                                final_status = ps
                except Exception as exc:
                    final_status = "error"
                    error_msg = str(exc)

                duration_ms = int((time.time() - t0) * 1000)

                if final_status == "completed":
                    passed += 1
                elif final_status == "halted":
                    halted += 1
                else:
                    errored += 1

                confidence_below_threshold = (
                    isinstance(verification_confidence, float)
                    and isinstance(verification_threshold, float)
                    and verification_confidence < verification_threshold
                )
                should_save_trace = (
                    final_status in ("halted", "error")
                    or verification_is_accurate is False
                    or confidence_below_threshold
                )
                if (
                    not should_save_trace
                    and final_status == "completed"
                    and _BATCH_TRACE_PASS_SAMPLE_RATE > 0
                ):
                    should_save_trace = (
                        (idx + 1) % max(1, int(1 / _BATCH_TRACE_PASS_SAMPLE_RATE))
                    ) == 0

                if should_save_trace and step_traces:
                    _store_batch_candidate_trace(
                        batch_run_id,
                        candidate_id,
                        {
                            "batch_run_id": batch_run_id,
                            "candidate_id": candidate_id,
                            "status": final_status,
                            "text_preview": text_preview,
                            "duration_ms": duration_ms,
                            "halted_at": halted_at,
                            "halted_at_subgraph": halted_at_subgraph,
                            "halt_reason": halt_reason,
                            "verification_is_accurate": verification_is_accurate,
                            "verification_confidence": verification_confidence,
                            "verification_threshold": verification_threshold,
                            "verification_issues": verification_issues,
                            "error": error_msg,
                            "trace_saved": True,
                            "saved_at": datetime.now(timezone.utc).isoformat(),
                            "step_traces": step_traces,
                        },
                    )

                put(
                    "candidate_done",
                    {
                        "type": "candidate_done",
                        "batch_run_id": batch_run_id,
                        "candidate_id": candidate_id,
                        "text_preview": text_preview,
                        "encounter_text": text[:8000],
                        "status": final_status,
                        "halted_at": halted_at,
                        "halted_at_subgraph": halted_at_subgraph,
                        "halt_reason": halt_reason,
                        "verification_is_accurate": verification_is_accurate,
                        "verification_confidence": verification_confidence,
                        "verification_threshold": verification_threshold,
                        "verification_issues": verification_issues,
                        "error": error_msg,
                        "duration_ms": duration_ms,
                        "index": idx + 1,
                        "total": total,
                        "trace_saved": should_save_trace and bool(step_traces),
                    },
                )

        sem = asyncio.Semaphore(concurrency)
        tasks = [
            asyncio.create_task(run_candidate(i, cand, sem))
            for i, cand in enumerate(candidates)
        ]

        async def _wait_and_close() -> None:
            await asyncio.gather(*tasks, return_exceptions=True)
            q.put_nowait(None)

        asyncio.create_task(_wait_and_close())

        while True:
            msg = await q.get()
            if msg is None:
                break
            yield msg

        yield (
            "event: batch_done\ndata: "
            + json.dumps(
                {
                    "type": "batch_done",
                    "batch_run_id": batch_run_id,
                    "total": total,
                    "passed": passed,
                    "halted": halted,
                    "errored": errored,
                    "by_step_stats": by_step_stats,
                }
            )
            + "\n\n"
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/test-run/batch/trace", dependencies=[Depends(verify_service_token)])
async def get_batch_candidate_trace(
    batch_run_id: str, candidate_id: str
) -> dict[str, Any]:
    payload = _get_batch_candidate_trace(
        batch_run_id=batch_run_id, candidate_id=candidate_id
    )
    if not payload:
        raise HTTPException(
            status_code=404,
            detail="Trace not found for this candidate/run (it may not have been persisted or has expired).",
        )
    return payload


@app.post("/label-verify/start", dependencies=[Depends(verify_service_token)])
async def label_verify_start(
    body: LabelVerifyStartRequest | None = None,
) -> dict[str, Any]:
    from libs.cypher.label_verification_queries import (
        DELETE_ALL_VERIFICATION_REVIEWS_FOR_INCLUDED,
        RESET_TRAINING_LABEL_VERIFICATION_FIELDS,
    )
    from libs.neo4j_client.client import PatientGraphClient
    from services.pipeline_worker.app.services.label_verifier import (
        begin_job,
        begin_job_with_mode,
        run_verification,
    )

    if body is None:
        started = begin_job()
        mode = "all"
        reset_pending = False
    else:
        mode = (
            body.mode
            if body.mode in {"all", "hitl_only", "resume", "re_extract"}
            else "all"
        )
        reset_pending = bool(body.reset_pending)
        started = begin_job_with_mode(run_mode=mode, reset_pending=reset_pending)

    if not started:
        raise HTTPException(
            status_code=409, detail="A label verification job is already running"
        )

    if reset_pending:
        client = PatientGraphClient()
        try:
            with client.session() as session:
                session.run(RESET_TRAINING_LABEL_VERIFICATION_FIELDS)
                session.run(DELETE_ALL_VERIFICATION_REVIEWS_FOR_INCLUDED)
        finally:
            client.close()

    thread = threading.Thread(target=run_verification, daemon=True, name="label-verify")
    thread.start()
    return {
        "status": "started",
        "mode": mode,
        "reset_pending": reset_pending,
        "message": "Label verification started in background",
    }


@app.post("/label-verify/stop", dependencies=[Depends(verify_service_token)])
async def label_verify_stop() -> dict[str, Any]:
    from services.pipeline_worker.app.services.label_verifier import request_stop_job

    if not request_stop_job():
        raise HTTPException(
            status_code=409, detail="No running label verification job to cancel"
        )
    return {"status": "stopping", "message": "Cancellation requested"}


@app.get("/label-verify/status", dependencies=[Depends(verify_service_token)])
async def label_verify_status() -> dict[str, Any]:
    from libs.cypher.label_verification_queries import (
        COUNT_VERIFICATION_QUEUE_PENDING,
        GET_VERIFICATION_STATS,
    )
    from libs.neo4j_client.client import PatientGraphClient
    from services.pipeline_worker.app.services.label_verifier import get_job_state

    state = get_job_state()
    client = PatientGraphClient()
    try:
        with client.session() as session:
            stats_row = session.run(GET_VERIFICATION_STATS).single()
            pending_row = session.run(COUNT_VERIFICATION_QUEUE_PENDING).single()
        return {
            **state,
            "auto_resolved": int(state.get("auto_resolved", 0) or 0),
            "stats": (
                dict(stats_row)
                if stats_row
                else {
                    "total_labels": 0,
                    "verified_labels": 0,
                    "agreements": 0,
                    "disagreements": 0,
                    "pending": 0,
                }
            ),
            "pending_review": pending_row["pending"] if pending_row else 0,
        }
    finally:
        client.close()


def _run_guidance_generation(job_id: str, guideline_id: str) -> None:
    from libs.neo4j_client.client import KnowledgeGraphClient
    from services.pipeline_worker.app.services.guidance_rule_generator import (
        GuidanceRuleGenerator,
    )

    try:
        client = KnowledgeGraphClient()
        try:
            generator = GuidanceRuleGenerator(client._driver)
            rule_ids = generator.generate_rules_for_guideline(guideline_id)
        finally:
            client.close()
        _guidance_generate_jobs[job_id].update(
            {
                "status": "done",
                "rule_ids": rule_ids,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as exc:
        logger.exception("Guidance rule generation failed for %s", guideline_id)
        _guidance_generate_jobs[job_id].update(
            {
                "status": "error",
                "error": str(exc),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )


@app.post(
    "/guidance/generate",
    status_code=202,
    dependencies=[Depends(verify_service_token)],
)
async def guidance_generate(body: GuidanceGenerateRequest) -> dict[str, Any]:
    # Reject a second concurrent request for the same guideline to prevent
    # duplicate rule writes or conflicting Neo4j transactions.
    for job in _guidance_generate_jobs.values():
        if job["guideline_id"] == body.guideline_id and job["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Rule generation for '{body.guideline_id}' is already running "
                    f"(job {job['job_id']!r}). Wait for it to finish before re-generating."
                ),
            )

    job_id = str(uuid.uuid4())
    _guidance_generate_jobs[job_id] = {
        "job_id": job_id,
        "guideline_id": body.guideline_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "rule_ids": [],
        "error": None,
    }
    thread = threading.Thread(
        target=_run_guidance_generation,
        args=(job_id, body.guideline_id),
        daemon=True,
        name="guidance-generate",
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/guidance/generate/{job_id}", dependencies=[Depends(verify_service_token)])
async def guidance_generate_status(job_id: str) -> dict[str, Any]:
    """Poll the status of a rule generation job started by POST /guidance/generate."""
    job = _guidance_generate_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Generation job '{job_id}' not found. It may have been cleared after a worker restart.",
        )
    return job


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "pipeline-worker"}


@app.get("/health/consumer")
async def health_consumer() -> dict[str, Any]:
    payload = _consumer_health_payload()
    payload["service"] = "pipeline-worker"
    return payload


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.pipeline_worker.app.main:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
