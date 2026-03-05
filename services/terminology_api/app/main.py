"""Terminology API service.

Owns SNOMED search, hybrid coding resolution, terminology writeback,
ValueSet/ConceptMap CRUD, and Redis-cached terminology lookups,
all against the Knowledge Graph.
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from libs.utils.logging import configure_logging

from services.terminology_api.app.routers import (
    search_router,
    writeback_router,
    valueset_router,
    conceptmap_router,
    resolve_router,
    concepts_router,
    surface_forms_router,
)

configure_logging(service_name="terminology-api")
logger = logging.getLogger("terminology-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Terminology API starting")
    # Pre-load the embedding model in a thread so each worker is warm before
    # it accepts its first real request.  Without this, the first request to
    # each worker blocks for 20-60s while the SentenceTransformer loads on CPU,
    # causing connection resets for concurrent callers.
    import asyncio
    from services.terminology_api.app.routers.resolve import _embedder
    await asyncio.get_event_loop().run_in_executor(None, _embedder._ensure_model)
    logger.info("Terminology API ready (embedder pre-loaded)")
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
app.include_router(surface_forms_router, prefix="/terminology", tags=["surface-forms"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "terminology-api"}
