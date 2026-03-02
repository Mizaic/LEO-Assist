"""spaCy NER model inference service.

Responsibilities
----------------
1. At startup: download the active model version from Azure Blob Storage into
   a local cache directory, then load it into memory.  No model files live in
   the Docker image — only source code.

2. Serve /extract requests from the coding worker.

3. On /reload: atomically hot-swap to a new model version from blob without
   restarting the process.  The old model serves until the new one is ready.

4. On /health: report the active version so callers know which model is live.

Startup behaviour
-----------------
- CODING_MODEL_VERSION env var tells the service which blob version to load.
- If the blob is unreachable, the service starts degraded (nlp=None) and
  returns 503 until /reload succeeds.
- All download/load work happens before the server reports healthy.

Environment variables
---------------------
See .env.example [Model Inference Service] section.
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from libs.keyvault.loader import load_keyvault_secrets

_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / "secrets" / ".env.config", override=False)
load_dotenv(_ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

# Inference runs on CPU only. Disable GPU device visibility before any
# spaCy / thinc / CuPy import so the CUDA probe is skipped entirely.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from libs.utils.logging import configure_logging

from app.model_loader import ModelLoader

configure_logging(service_name="model-inference")
logger = logging.getLogger(__name__)

# Global model loader — shared across all requests.
# Hot-reload swaps the internal nlp object atomically under a RLock.
_loader = ModelLoader()


def _resolve_startup_version() -> str:
    """Return the currently promoted version from the ModelRegistry.

    Always reads the registry — never uses a hardcoded env var — so the
    inference service is always in sync with whatever version was last promoted
    via the Model Deployment workflow.
    """
    try:
        from libs.model_registry.registry import get_registry
        active = get_registry().get_active()
        if active:
            logger.info(
                "Inference service: active version from registry — v%s (status=%s)",
                active.model_version, active.status,
            )
            return active.model_version
        logger.warning(
            "Inference service: no promoted model in registry — "
            "promote a version via the Model Deployment tab to load a model"
        )
    except Exception as exc:
        logger.warning("Inference service: could not read registry: %s", exc)
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    version = _resolve_startup_version()
    if version:
        try:
            await asyncio.to_thread(_loader.load_version, version)
        except Exception:
            logger.warning(
                "Inference service: startup model load failed — serving degraded",
                exc_info=True,
            )
    yield


app = FastAPI(
    title="NER Model Inference Service",
    version="1.0.0",
    description=(
        "spaCy NER extraction endpoint for the coding worker.  "
        "Models are loaded from Azure Blob Storage — no model files in the image."
    ),
    lifespan=lifespan,
)


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class SentenceIn(BaseModel):
    sentence_id: str
    text: str
    start: int
    end: int


class ExtractRequest(BaseModel):
    text: str
    sentences: list[SentenceIn]


class EntityOut(BaseModel):
    sentence_id: str
    text: str
    label: str
    semantic_tag: str
    span_start: int
    span_end: int
    confidence: float
    normalized: str
    source_meta: dict[str, Any] = {}


class ExtractResponse(BaseModel):
    model_name: str
    model_version: str
    entity_count: int
    entities: list[EntityOut]


class ReloadRequest(BaseModel):
    version: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    """Return service health and active model version."""
    active = _loader.active_version
    return {
        "status": "ok" if active else "degraded",
        "model_name": _loader.model_name,
        "active_version": active or "none",
        "loaded": active is not None,
    }


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest) -> ExtractResponse:
    """Run NER extraction on a batch of sentences.

    The coding worker sends this request; the response is parsed by
    ``ModelExtractorProvider._parse_service_response()``.
    """
    nlp = _loader.nlp
    if nlp is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No model loaded. "
                "POST /reload with a version to load a model from blob storage."
            ),
        )

    from libs.deid import deidentify

    entities: list[EntityOut] = []

    for sent in req.sentences:
        deid = deidentify(sent.text)
        doc = nlp(deid.text)
        for ent in doc.ents:
            label = ent.label_
            confidence = float(getattr(ent, "kb_id_", 0.0) or 0.0)
            entities.append(EntityOut(
                sentence_id=sent.sentence_id,
                text=ent.text,
                label=label,
                semantic_tag=label.lower(),
                span_start=sent.start + ent.start_char,
                span_end=sent.start + ent.end_char,
                confidence=round(confidence, 4),
                normalized=ent.text,
                source_meta={"model_label": label},
            ))

    return ExtractResponse(
        model_name=_loader.model_name,
        model_version=_loader.active_version or "unknown",
        entity_count=len(entities),
        entities=entities,
    )


@app.post("/reload")
async def reload_model(req: ReloadRequest) -> dict[str, Any]:
    """Hot-swap to a new model version from blob storage.

    Downloads the requested version in a background thread while the current
    model continues serving.  Atomically swaps the in-memory reference when
    the new model is ready.

    Called automatically by ``ModelRegistry.promote()`` and
    ``ModelRegistry.rollback()`` via the registry integration hook.
    """
    if not req.version:
        raise HTTPException(status_code=422, detail="version must be non-empty")

    start = time.monotonic()
    try:
        await asyncio.to_thread(_loader.load_version, req.version)
    except Exception as exc:
        logger.error("Reload failed for v%s: %s", req.version, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload model v{req.version}: {exc}",
        )

    elapsed_ms = round((time.monotonic() - start) * 1000)
    logger.info("Reload complete: v%s in %dms", req.version, elapsed_ms)
    return {
        "active_version": _loader.active_version,
        "elapsed_ms": elapsed_ms,
    }


@app.get("/versions")
async def list_versions() -> dict[str, Any]:
    """List available model versions in the blob store."""
    from libs.model_store import ModelStore
    store = ModelStore()
    try:
        versions = await asyncio.to_thread(store.list_versions)
        return {
            "versions": [v.to_dict() for v in versions],
            "active_version": _loader.active_version,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
