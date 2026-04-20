"""Analytics API service.

Atlas trace:
  DO: DO-9F3CD7DE
  DI: DI-CF03E4EA, DO-F78C84A6
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-9F3CD7DE")

Dashboard endpoints, pre-computed aggregation reads, IMD data retrieval,
CCI scoring, benchmark queries.

Ported from auditor_2 (IMD, CCI, benchmarks) and VRB (dashboard queries).
"""

# aca-image: analytics-api build/deploy verification (no runtime effect).

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_keyvault_secrets()

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from libs.utils.logging import configure_logging

from services.analytics_api.app.routers.cohorts import (
    router as cohort_router,
    seed_nhs_cohorts,
)
from services.analytics_api.app.routers.dashboards import router as dashboard_router
from services.analytics_api.app.routers.domains import router as domain_router
from services.analytics_api.app.routers.imd import router as imd_router
from services.analytics_api.app.routers.cci import router as cci_router
from services.analytics_api.app.routers.benchmarks import router as benchmark_router
from services.analytics_api.app.routers.org_context import router as org_context_router
from services.analytics_api.app.routers.audit import (
    router as audit_router,
    _ensure_registry,
)
from services.analytics_api.app.routers.mission_control import (
    router as mission_control_router,
)
from services.analytics_api.app.routers.mission_control_encounters import (
    router as mission_control_encounters_router,
)
from services.analytics_api.app.routers.patient_finder import (
    router as patient_finder_router,
)
from services.analytics_api.app.routers.research import router as research_router

configure_logging(service_name="analytics-api")
logger = logging.getLogger("analytics-api")


def _check_service_auth_secret():
    """Warn loudly if SERVICE_AUTH_SECRET is unset in a non-local environment."""
    env = os.getenv("ENVIRONMENT", "local")
    secret = os.getenv("SERVICE_AUTH_SECRET", "")
    if env != "local" and not secret:
        logger.critical(
            "SECURITY: SERVICE_AUTH_SECRET is not set in %s environment. "
            "Inter-service auth is disabled -- all callers are implicitly trusted.",
            env,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Analytics API starting")
    _check_service_auth_secret()
    try:
        n = seed_nhs_cohorts()
        if n > 0:
            logger.info("NHS screening cohorts seeded: %d presets", n)
    except Exception as exc:
        logger.warning("NHS cohort seeding skipped (graph unavailable?): %s", exc)
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient

        kg = KnowledgeGraphClient()
        try:
            registry = _ensure_registry(kg)
            domain_count = len(registry.get_all_domains())
            logger.info("DomainRegistry loaded at startup: %d domains", domain_count)
        finally:
            kg.close()
    except Exception as exc:
        logger.error(
            "DomainRegistry startup load FAILED -- analytics endpoints requiring "
            "domain config will raise until KG is available: %s",
            exc,
        )
    yield
    logger.info("Analytics API shutting down")


app = FastAPI(
    title="Analytics API",
    description="Dashboards, benchmarks, IMD, CCI scoring, pre-computed analytics",
    version="0.1.0",
    lifespan=lifespan,
)

_allowed_origins = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:3001",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(org_context_router, prefix="/analytics", tags=["auth"])
app.include_router(dashboard_router, prefix="/analytics", tags=["dashboards"])
app.include_router(cohort_router, prefix="/analytics", tags=["cohorts"])
app.include_router(domain_router, prefix="/analytics", tags=["domains"])
app.include_router(imd_router, prefix="/analytics", tags=["imd"])
app.include_router(cci_router, prefix="/analytics", tags=["cci"])
app.include_router(benchmark_router, prefix="/analytics", tags=["benchmarks"])
app.include_router(audit_router, prefix="/analytics", tags=["audit"])
app.include_router(
    mission_control_router, prefix="/analytics", tags=["mission-control"]
)
app.include_router(
    mission_control_encounters_router, prefix="/analytics", tags=["mission-control"]
)
app.include_router(research_router, prefix="/analytics", tags=["pathway-explorer"])
app.include_router(
    patient_finder_router, prefix="/analytics", tags=["patient-finder"]
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics-api"}
