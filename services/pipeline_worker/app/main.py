"""Pipeline Worker service — dual-mode: HTTP server + message bus consumer.

Atlas trace:
  DO: DO-C2F6CA16
  DI: DI-06CB6881
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-C2F6CA16")

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
from typing import Any, AsyncGenerator, Optional

from libs.model_registry.registry import get_registry
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
from services.pipeline_worker.app.services.progress_callback import (
    build_progress_callback as _build_progress_callback,
)

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
    # Lift the anyio threadpool ceiling so sync `def` endpoints (and sync I/O
    # called via `to_thread`) do not bottleneck on Starlette's default 40
    # tokens. See plan: backend-concurrency-overhaul Phase 0.
    try:
        import anyio

        _limiter = anyio.to_thread.current_default_thread_limiter()
        _tokens = int(os.getenv("ANYIO_THREADPOOL_TOKENS", "200"))
        _limiter.total_tokens = _tokens
        logger.info("anyio threadpool ceiling set to %d", _tokens)
    except Exception as exc:
        logger.warning("Failed to lift anyio threadpool ceiling: %s", exc)
    # Kick off model warm-up (non-blocking - runs in daemon threads)
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
        # Inspect body cheaply for SBAR jobs and dispatch directly to the
        # SBAROrchestrator. Other event_types continue through the workflow
        # engine. See DI-LEO-AI-186.
        try:
            body = msg.body
            if isinstance(body, (str, bytes)):
                body = json.loads(body)
        except Exception:
            body = None
        if isinstance(body, dict) and body.get("event_type") == "sbar_requested":
            try:
                from services.pipeline_worker.app.services.sbar_orchestrator import (
                    handle_sbar_message,
                )

                await handle_sbar_message(body)
                return
            except Exception:
                logger.exception("SBAR job failed")
                try:
                    from services.coding_worker.app.services.progress_publisher import (
                        publish_progress,
                    )
                    run_id = str(msg.correlation_id or msg.message_id or body.get("run_id") or "")
                    if run_id:
                        publish_progress(
                            run_id,
                            {
                                "type": "sbar_failed",
                                "run_id": run_id,
                                "message": "SBAR orchestrator raised an exception. See worker logs.",
                            },
                        )
                except Exception:
                    pass
                raise

        # Wire a step_callback so WorkflowEngine emits step_completed and
        # run_completed events to Redis pub/sub for the SSE stream
        # /pipeline/progress/{run_id}. Without this, the patient-drawer
        # "Reset and recode" chip stays stuck at "Resetting..." because no
        # progress event ever reaches the browser even though the engine
        # finishes the work in Neo4j. Atlas: DI-705C806B / VT-297D9C18.
        run_id = str(msg.correlation_id or msg.message_id or "")
        if isinstance(body, dict) and not run_id:
            run_id = str(body.get("run_id") or "")
        patient_id = ""
        if isinstance(body, dict):
            patient_id = str(body.get("patient_id") or "")

        step_callback = None
        if run_id:
            step_callback = _build_progress_callback(
                run_id, patient_id=patient_id
            )

        try:
            await handler.handle_message(msg, step_callback=step_callback)
        except Exception:
            # Emit a progress error event so UI subscribers do not appear idle
            # when a run fails before first workflow step.
            try:
                from services.coding_worker.app.services.progress_publisher import (
                    publish_progress,
                )

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
    only_without_rules: bool = False


class WorkerTraceEncounter(BaseModel):
    encounter_id: str
    text: str
    patient_id: Optional[str] = None
    encounter_date: Optional[str] = None


class WorkerTraceRequest(BaseModel):
    version: str
    plan_definition_id: str = os.getenv(
        "MODEL_TRACE_PLAN_DEFINITION_ID", "pd-gp-encounter-coding"
    )
    encounters: list[WorkerTraceEncounter]


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


def _normalise_worker_entity(ent: dict[str, Any]) -> dict[str, Any]:
    out = dict(ent)
    out["label"] = str(out.get("label") or out.get("semantic_tag") or "").upper()
    if not out.get("semantic_tag"):
        out["semantic_tag"] = str(out["label"]).lower()
    if "text" not in out:
        out["text"] = str(out.get("term") or out.get("lookup_term") or "")
    return out


def _label_assertion(entity: dict[str, Any]) -> tuple[str, str]:
    label = str(entity.get("label") or entity.get("semantic_tag") or "").upper()
    assertion = str(entity.get("assertion") or "").strip().lower()
    return label, assertion


def _span_key(entity: dict[str, Any]) -> tuple[int, int]:
    return int(entity.get("start", 0)), int(entity.get("end", 0))


def _dedupe_signature(entity: dict[str, Any]) -> tuple[str, str, int, int, str]:
    label, assertion = _label_assertion(entity)
    start, end = _span_key(entity)
    text = str(entity.get("text") or "").strip().lower()
    return (label, assertion, start, end, text)


def _diff_provenance(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    before_by_span: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for ent in before:
        key = _span_key(ent)
        before_by_span.setdefault(key, []).append(ent)

    matched_ids: set[int] = set()
    final_entities: list[dict[str, Any]] = []

    for ent in after:
        span = _span_key(ent)
        ent_label, ent_assertion = _label_assertion(ent)
        candidates = before_by_span.get(span, [])
        picked: Optional[dict[str, Any]] = None
        for cand in candidates:
            if id(cand) in matched_ids:
                continue
            cand_label, cand_assertion = _label_assertion(cand)
            if cand_label == ent_label and cand_assertion == ent_assertion:
                picked = cand
                break
        if picked is None:
            for cand in candidates:
                if id(cand) not in matched_ids:
                    picked = cand
                    break

        out = dict(ent)
        if picked is None:
            out["_provenance_stage"] = "post_processing_added"
            out["_provenance_detail"] = None
        else:
            matched_ids.add(id(picked))
            prev_label, prev_assertion = _label_assertion(picked)
            details: list[str] = []
            if prev_label != ent_label:
                details.append(f"label: {prev_label} -> {ent_label}")
            if prev_assertion != ent_assertion:
                details.append(
                    f"assertion: {prev_assertion or 'none'} -> {ent_assertion or 'none'}"
                )
            if details:
                out["_provenance_stage"] = "post_processing_modified"
                out["_provenance_detail"] = "; ".join(details)
            else:
                out["_provenance_stage"] = "ner"
                out["_provenance_detail"] = None
        final_entities.append(out)

    final_signatures = {_dedupe_signature(ent) for ent in final_entities}
    suppressed: list[dict[str, Any]] = []
    deduplicated: list[dict[str, Any]] = []
    for ent in before:
        if id(ent) in matched_ids:
            continue
        out = dict(ent)
        if _dedupe_signature(ent) in final_signatures:
            out["_provenance_stage"] = "deduplicated"
            out["_provenance_detail"] = "Removed as duplicate entity"
            deduplicated.append(out)
        else:
            out["_provenance_stage"] = "suppressed"
            out["_provenance_detail"] = "Removed during post-processing"
            suppressed.append(out)

    return final_entities, suppressed, deduplicated


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
                terms=[],
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


@app.post("/model-registry/worker-trace", dependencies=[Depends(verify_service_token)])
async def model_registry_worker_trace(body: WorkerTraceRequest) -> dict[str, Any]:
    reg = get_registry()
    rec = reg.get(body.version)
    if not rec:
        raise HTTPException(
            status_code=404, detail=f"Version {body.version!r} not found"
        )

    encounters = body.encounters[:20]
    if not encounters:
        raise HTTPException(status_code=400, detail="Select at least one encounter")

    from libs.neo4j_client.client import get_async_driver, get_async_patient_driver

    kg_driver = get_async_driver()
    pg_driver = get_async_patient_driver()
    engine = WorkflowEngine(neo4j_driver=kg_driver, audit_neo4j_driver=pg_driver)
    try:
        actions = await engine._get_all_plan_actions(body.plan_definition_id)
        if not actions:
            raise HTTPException(
                status_code=404,
                detail=f"No actions found for plan_definition_id={body.plan_definition_id!r}",
            )

        results: list[dict[str, Any]] = []
        for enc in encounters:
            encounter_id = str(enc.encounter_id or "").strip()
            patient_id = str(enc.patient_id or "").strip()
            if not encounter_id or not patient_id:
                results.append(
                    {
                        "encounter_id": enc.encounter_id,
                        "patient_id": enc.patient_id,
                        "encounter_date": enc.encounter_date,
                        "text_length": len(str(enc.text or "")),
                        "ner_entities": [],
                        "final_entities": [],
                        "suppressed_entities": [],
                        "deduplicated_entities": [],
                        "layer_trace": [],
                        "status": "failed",
                        "error": "patient_id and encounter_id are required for worker trace",
                        "errors": [
                            "encounter_loader: patient_id and encounter_id are required"
                        ],
                        "failing_step": "encounter_loader",
                        "step_count": 0,
                        "entity_counts": {
                            "extraction": 0,
                            "final": 0,
                            "suppressed": 0,
                            "deduplicated": 0,
                        },
                        "extraction_model": {
                            "requested_version": body.version,
                            "actual_version": "",
                            "actual_name": "",
                            "version_mismatch": False,
                        },
                    }
                )
                continue

            initial_state = {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "run_id": str(uuid.uuid4()),
                "errors": [],
                "plan_definition_id": body.plan_definition_id,
                "mode": "extract_encounter",
                "dry_run": True,
                "trigger_analysis": False,
                "extraction_method": "ner",
                "requested_model_version": body.version,
                "strict_model_version": True,
            }
            trace = await engine.trace_run(actions, initial_state)
            steps = trace.get("steps", []) if isinstance(trace, dict) else []
            final_state = (
                trace.get("final_state", {}) if isinstance(trace, dict) else {}
            ) or {}
            trace_status = str(trace.get("status") or "completed")

            extraction_entities: list[dict[str, Any]] = []
            post_processing_trace: list[dict[str, Any]] = []
            step_errors: list[str] = []
            failing_step: str | None = None
            for step in steps:
                if not isinstance(step, dict):
                    continue
                subgraph_id = str(step.get("subgraph_id") or "")
                output_state = step.get("output_state") or {}
                if (
                    subgraph_id == "extraction"
                    and isinstance(output_state, dict)
                    and isinstance(output_state.get("entities"), list)
                ):
                    extraction_entities = [
                        _normalise_worker_entity(dict(e))
                        for e in output_state.get("entities", [])
                        if isinstance(e, dict)
                    ]
                if (
                    subgraph_id == "post_processing"
                    and isinstance(output_state, dict)
                    and isinstance(output_state.get("post_processing_trace"), list)
                ):
                    post_processing_trace = [
                        dict(r)
                        for r in output_state.get("post_processing_trace", [])
                        if isinstance(r, dict)
                    ]
                status = str(step.get("status") or "")
                err = str(step.get("error") or "").strip()
                if status in {"error", "halted"} or err:
                    label = str(step.get("label") or step.get("subgraph_id") or "step")
                    if err:
                        step_errors.append(f"{label}: {err}")
                    elif status == "halted":
                        step_errors.append(
                            f"{label}: {str(step.get('halt_reason') or 'halted')}"
                        )
                    if not failing_step:
                        failing_step = label

            final_entities_raw = final_state.get("entities")
            final_entities_clean = (
                [
                    _normalise_worker_entity(dict(e))
                    for e in final_entities_raw
                    if isinstance(e, dict)
                ]
                if isinstance(final_entities_raw, list)
                else []
            )
            final_entities, suppressed_entities, deduplicated_entities = _diff_provenance(
                extraction_entities, final_entities_clean
            )
            extraction_model_requested_version = str(
                final_state.get("extraction_model_requested_version")
                or final_state.get("requested_model_version")
                or body.version
            ).strip()
            extraction_model_actual_version = str(
                final_state.get("extraction_model_version") or ""
            ).strip()
            extraction_model_actual_name = str(
                final_state.get("extraction_model_name") or ""
            ).strip()
            extraction_model_version_mismatch = bool(
                final_state.get("extraction_model_version_mismatch", False)
            )

            # Return the actual de-identified text the workflow processed
            # so the curator UI renders entity offsets against the same
            # string they will be persisted against. Document.text in
            # Neo4j is already de-identified at write time; falling back
            # to the request text would re-introduce raw PHI.
            processed_text = ""
            for key in ("encounter_text", "document_text", "text", "raw_text"):
                value = final_state.get(key)
                if isinstance(value, str) and value.strip():
                    processed_text = value
                    break

            layer_trace = [
                {
                    "layer_id": str(step.get("layer_id") or ""),
                    "name": str(step.get("name") or ""),
                    "status": str(step.get("status") or "ok"),
                    "before_count": int(step.get("before_count") or 0),
                    "after_count": int(step.get("after_count") or 0),
                    "added_count": int(step.get("added_count") or 0),
                    "removed_count": int(step.get("removed_count") or 0),
                    "updated_count": int(step.get("updated_count") or 0),
                    "duration_ms": int(step.get("duration_ms") or 0),
                }
                for step in post_processing_trace
            ]

            results.append(
                {
                    "encounter_id": enc.encounter_id,
                    "patient_id": enc.patient_id,
                    "encounter_date": enc.encounter_date,
                    "text": processed_text,
                    "text_length": len(processed_text)
                    if processed_text
                    else len(str(enc.text or "")),
                    "ner_entities": extraction_entities,
                    "final_entities": final_entities,
                    "suppressed_entities": suppressed_entities,
                    "deduplicated_entities": deduplicated_entities,
                    "layer_trace": layer_trace,
                    "status": trace_status,
                    "errors": step_errors
                    + [
                        str(e)
                        for e in (final_state.get("errors") or [])
                        if str(e).strip()
                    ],
                    "error": (
                        step_errors[0]
                        if step_errors
                        else (
                            str((final_state.get("errors") or [""])[0]).strip()
                            if final_state.get("errors")
                            else None
                        )
                    ),
                    "failing_step": failing_step,
                    "step_count": len(steps),
                    "entity_counts": {
                        "extraction": len(extraction_entities),
                        "final": len(final_entities),
                        "suppressed": len(suppressed_entities),
                        "deduplicated": len(deduplicated_entities),
                    },
                    "extraction_model": {
                        "requested_version": extraction_model_requested_version,
                        "actual_version": extraction_model_actual_version,
                        "actual_name": extraction_model_actual_name,
                        "version_mismatch": extraction_model_version_mismatch,
                    },
                }
            )
    finally:
        await kg_driver.close()
        await pg_driver.close()

    return {
        "model_version": body.version,
        "plan_definition_id": body.plan_definition_id,
        "mode": "worker_trace",
        "encounters": results,
        "count": len(results),
    }


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


def _run_guidance_generation(
    job_id: str,
    guideline_id: str,
    *,
    only_without_rules: bool = False,
) -> None:
    from libs.neo4j_client.client import KnowledgeGraphClient
    from services.pipeline_worker.app.services.guidance_rule_generator import (
        GuidanceRuleGenerator,
    )

    try:
        client = KnowledgeGraphClient()
        try:
            generator = GuidanceRuleGenerator(client._driver)
            rule_ids = generator.generate_rules_for_guideline(
                guideline_id,
                only_without_rules=only_without_rules,
            )
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
        kwargs={"only_without_rules": body.only_without_rules},
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
