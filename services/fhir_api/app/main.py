"""FHIR API service.

Atlas trace:
  DO: DO-B3397C94
  DI: DI-FC9A8824
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-B3397C94")

R4B-compliant endpoints for Measure, MeasureReport, Library, Device,
PlanDefinition. Evaluates Measures against Patient Graph using Library
Cypher queries stored in Knowledge Graph.

Ported from VRB fhir-api.
"""

# aca-image: fhir-api build/deploy verification (no runtime effect).

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from libs.utils.logging import configure_logging

from services.fhir_api.app.routers.audit_event import router as audit_event_router
from services.fhir_api.app.routers.benchmark import router as benchmark_router
from services.fhir_api.app.routers.measure import router as measure_router
from services.fhir_api.app.routers.measure_report import router as measure_report_router
from services.fhir_api.app.routers.library import router as library_router
from services.fhir_api.app.routers.device import router as device_router
from services.fhir_api.app.routers.plan_definition import (
    router as plan_definition_router,
)
from services.fhir_api.app.routers.activity_definition import (
    router as activity_definition_router,
)
from services.fhir_api.app.routers.schema import router as schema_router

configure_logging(service_name="fhir-api")
logger = logging.getLogger("fhir-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("FHIR API starting")
    # Lift the anyio threadpool ceiling so sync `def` endpoints (and sync I/O
    # called via `to_thread`) do not bottleneck on Starlette's default 40
    # tokens. See plan: backend-concurrency-overhaul Phase 0.
    try:
        import os as _os

        import anyio

        _limiter = anyio.to_thread.current_default_thread_limiter()
        _tokens = int(_os.getenv("ANYIO_THREADPOOL_TOKENS", "200"))
        _limiter.total_tokens = _tokens
        logger.info("anyio threadpool ceiling set to %d", _tokens)
    except Exception as exc:
        logger.warning("Failed to lift anyio threadpool ceiling: %s", exc)
    import threading

    def _seed_plan_definitions():
        try:
            from libs.neo4j_client.client import KnowledgeGraphClient
            from scripts.seed_plan_definitions import seed_with_client

            client = KnowledgeGraphClient()
            seed_with_client(client)
            client.close()
        except Exception as exc:
            logger.warning("PlanDefinition seed failed (non-fatal): %s", exc)

    t = threading.Thread(target=_seed_plan_definitions, daemon=True)
    t.start()
    yield
    logger.info("FHIR API shutting down")


app = FastAPI(
    title="FHIR API",
    description="FHIR R4B Measure evaluation, MeasureReport, Library, Device, PlanDefinition",
    version="0.1.0",
    lifespan=lifespan,
)

import os

_allowed_origins_raw = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
if not _allowed_origins_raw:
    logger.warning(
        "FHIR API: ALLOWED_ORIGINS is not set -- CORS will reject all cross-origin "
        "requests. Set ALLOWED_ORIGINS in the environment."
    )
_allowed_origins = _allowed_origins_raw
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-Request-ID",
        "X-Correlation-ID",
    ],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every FHIR API response."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    return response


from libs.observability import ServerTimingMiddleware  # noqa: E402

app.add_middleware(ServerTimingMiddleware)

app.include_router(audit_event_router, prefix="/fhir", tags=["AuditEvent"])
app.include_router(benchmark_router, prefix="/benchmarks", tags=["Benchmarks"])
app.include_router(measure_router, prefix="/fhir", tags=["Measure"])
app.include_router(measure_report_router, prefix="/fhir", tags=["MeasureReport"])
app.include_router(library_router, prefix="/fhir", tags=["Library"])
app.include_router(device_router, prefix="/fhir", tags=["Device"])
app.include_router(plan_definition_router, prefix="/fhir", tags=["PlanDefinition"])
app.include_router(
    activity_definition_router, prefix="/fhir", tags=["ActivityDefinition"]
)
app.include_router(schema_router, prefix="/fhir", tags=["Schema"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fhir-api"}
