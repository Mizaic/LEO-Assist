"""Terminology API service.

Owns SNOMED search, hybrid coding resolution, terminology writeback,
ValueSet/ConceptMap CRUD, and Redis-cached terminology lookups,
all against the Knowledge Graph.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.terminology_api.app.routers import (
    search_router,
    writeback_router,
    valueset_router,
    conceptmap_router,
    resolve_router,
    concepts_router,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("terminology-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Terminology API starting")
    yield
    logger.info("Terminology API shutting down")


app = FastAPI(
    title="Terminology API",
    description="SNOMED terminology search, hybrid coding resolution, ValueSet/ConceptMap management",
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

app.include_router(search_router, prefix="/terminology", tags=["search"])
app.include_router(resolve_router, prefix="/terminology", tags=["resolve"])
app.include_router(writeback_router, prefix="/terminology", tags=["writeback"])
app.include_router(valueset_router, prefix="/terminology", tags=["valueset"])
app.include_router(conceptmap_router, prefix="/terminology", tags=["conceptmap"])
app.include_router(concepts_router, prefix="/terminology", tags=["concepts"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "terminology-api"}
