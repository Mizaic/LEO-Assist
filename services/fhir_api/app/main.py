"""FHIR API service.

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

from fastapi import FastAPI
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

_allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
