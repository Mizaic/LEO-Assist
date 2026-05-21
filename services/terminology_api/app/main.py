"""Terminology API service.

Atlas trace (local clinical language mappings):
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9

Owns SNOMED search, hybrid coding resolution, terminology writeback,
ValueSet/ConceptMap CRUD, and Redis-cached terminology lookups,
all against the Knowledge Graph.
"""

# aca-image: terminology-api build/deploy verification (no runtime effect).

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

from services.terminology_api.app.routers import (
    search_router,
    writeback_router,
    valueset_router,
    conceptmap_router,
    resolve_router,
    concepts_router,
    surface_forms_router,
    guidelines_router,
)

configure_logging(service_name="terminology-api")
logger = logging.getLogger("terminology-api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Terminology API starting")
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
    logger.info("Terminology API ready")
    yield
    logger.info("Terminology API shutting down")


app = FastAPI(
    title="Terminology API",
    description="SNOMED terminology search, hybrid coding resolution, ValueSet/ConceptMap management",
    version="0.1.0",
    lifespan=lifespan,
)

_DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000"
)
_cors_raw = os.getenv("TERMINOLOGY_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
if "*" in _cors_origins:
    raise RuntimeError(
        "TERMINOLOGY_CORS_ORIGINS must not contain '*'; the API uses "
        "credentialed cookies and a wildcard origin would let any site "
        "drive the API as the logged-in user."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Service-Token"],
)

from libs.observability import ServerTimingMiddleware  # noqa: E402

app.add_middleware(ServerTimingMiddleware)

app.include_router(search_router, prefix="/terminology", tags=["search"])
app.include_router(resolve_router, prefix="/terminology", tags=["resolve"])
app.include_router(writeback_router, prefix="/terminology", tags=["writeback"])
app.include_router(valueset_router, prefix="/terminology", tags=["valueset"])
app.include_router(conceptmap_router, prefix="/terminology", tags=["conceptmap"])
app.include_router(concepts_router, prefix="/terminology", tags=["concepts"])
app.include_router(surface_forms_router, prefix="/terminology", tags=["surface-forms"])
app.include_router(guidelines_router, prefix="/terminology", tags=["guidelines"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "terminology-api"}
