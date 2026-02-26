"""FHIR API service.

R4B-compliant endpoints for Measure, MeasureReport, Library, Device,
PlanDefinition. Evaluates Measures against Patient Graph using Library
Cypher queries stored in Knowledge Graph.

Ported from VRB fhir-api.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.fhir_api.app.routers.measure import router as measure_router
from services.fhir_api.app.routers.measure_report import router as measure_report_router
from services.fhir_api.app.routers.library import router as library_router
from services.fhir_api.app.routers.device import router as device_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("fhir-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("FHIR API starting")
    yield
    logger.info("FHIR API shutting down")


app = FastAPI(
    title="FHIR API",
    description="FHIR R4B Measure evaluation, MeasureReport, Library, Device, PlanDefinition",
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

app.include_router(measure_router, prefix="/fhir", tags=["Measure"])
app.include_router(measure_report_router, prefix="/fhir", tags=["MeasureReport"])
app.include_router(library_router, prefix="/fhir", tags=["Library"])
app.include_router(device_router, prefix="/fhir", tags=["Device"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fhir-api"}
