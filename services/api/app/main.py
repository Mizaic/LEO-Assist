"""FastAPI app for HITL training creator MVP."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

# Operational logging: app at INFO, third-party noise suppressed
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("PyRuSH").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("neo4j").setLevel(logging.ERROR)  # Neo4j schema notifications (SurfaceForm, etc.)
logging.getLogger("neo4j.notifications").setLevel(logging.CRITICAL)

# PyRuSH uses loguru, not stdlib logging — disable its DEBUG spam
try:
    from loguru import logger as _loguru_logger
    _loguru_logger.disable("PyRuSH")
    _loguru_logger.disable("PyRuSH.PyRuSHSentencizer")
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from libs.auth.org_scope import get_caller_scope

from app import config  # noqa: F401 - loads secrets/.env
from app.deps import get_caller_scope_from_request
from app.routers.agent import router as agent_router
from app.routers.anchor_review import router as anchor_review_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.exports import router as exports_router
from app.routers.games import router as games_router
from app.routers.operations import router as operations_router
from app.routers.model_registry import router as model_registry_router
from app.routers.training import router as training_router
from app.routers.patients import router as patients_router
from app.routers.pipeline import router as pipeline_router
from app.routers.proxy import router as proxy_router
from app.routers.review import router as review_router
from app.routers.terminology import router as terminology_router


@asynccontextmanager
async def lifespan(app: object):
    import threading
    from app.services.pipeline_service import PipelineService

    def _preload():
        PipelineService.preload_embedder()

    t = threading.Thread(target=_preload, daemon=True)
    t.start()
    # Don't block startup — embedder loads in background; pipeline will wait if needed
    yield


app = FastAPI(
    title="Training Creator HITL API",
    version="0.2.0",
    description="Medical-grade candidate generation and review workflow API.",
    lifespan=lifespan,
)

# In this API service, allow org-scope identity to come from session cookie as
# a fallback for direct browser routes that do not inject X-User-Email.
app.dependency_overrides[get_caller_scope] = get_caller_scope_from_request

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(anchor_review_router)
app.include_router(auth_router)
app.include_router(proxy_router)
app.include_router(patients_router)
app.include_router(pipeline_router)
app.include_router(review_router)
app.include_router(audit_router)
app.include_router(exports_router)
app.include_router(terminology_router)
app.include_router(games_router)
app.include_router(operations_router)
app.include_router(model_registry_router)
app.include_router(training_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
