"""Analytics API service.

Dashboard endpoints, pre-computed aggregation reads, IMD data retrieval,
CCI scoring, benchmark queries.

Ported from auditor_2 (IMD, CCI, benchmarks) and VRB (dashboard queries).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.analytics_api.app.routers.cohorts import router as cohort_router
from services.analytics_api.app.routers.dashboards import router as dashboard_router
from services.analytics_api.app.routers.domains import router as domain_router
from services.analytics_api.app.routers.imd import router as imd_router
from services.analytics_api.app.routers.cci import router as cci_router
from services.analytics_api.app.routers.benchmarks import router as benchmark_router
from services.analytics_api.app.routers.org_context import router as org_context_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("analytics-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Analytics API starting")
    yield
    logger.info("Analytics API shutting down")


app = FastAPI(
    title="Analytics API",
    description="Dashboards, benchmarks, IMD, CCI scoring, pre-computed analytics",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics-api"}
