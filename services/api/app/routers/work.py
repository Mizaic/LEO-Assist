"""Unified work queue endpoints.

Atlas trace:
  DI: DI-6BD7B681

Backs the /work route consumed by the staff role. Every row returned here
already carries a deep-link resolve_url, so this router is read-only and
never mutates the underlying task sources.

UncodedPhrase nodes live in the knowledge graph. This router opens a
KnowledgeGraphClient alongside the patient client and passes it to the
queue service as kg_session. When the knowledge graph is unreachable,
My work still returns the patient-graph tasks with phrase_publish count = 0.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db.neo4j_client import PatientGraphClient
from app.services.session_store import COOKIE_NAME, load_session, touch_session
from libs.neo4j_client.client import KnowledgeGraphClient
from libs.work.queue import (
    VALID_SOURCES,
    WorkTaskFilters,
    get_work_counts,
    get_work_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/work", tags=["work"])


def _require_authed_session(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="not_authenticated")
    data = load_session(session_id)
    if not data:
        raise HTTPException(status_code=401, detail="session_expired")
    idle = int(data.get("idle_timeout_minutes") or 0)
    refreshed = touch_session(session_id, idle_timeout_minutes=idle)
    if not refreshed:
        raise HTTPException(status_code=401, detail="session_expired")
    return refreshed


def _get_client() -> PatientGraphClient:
    return PatientGraphClient()


def _coerce_sources(
    raw_sources: list[str] | None,
) -> tuple[str, ...] | None:
    if not raw_sources:
        return None
    normalised: list[str] = []
    for value in raw_sources:
        for token in str(value or "").split(","):
            token = token.strip()
            if token and token in VALID_SOURCES:
                normalised.append(token)
    if not normalised:
        raise HTTPException(status_code=400, detail="invalid_source")
    seen: dict[str, None] = {}
    for item in normalised:
        seen.setdefault(item, None)
    return tuple(seen.keys())


def _open_kg_client() -> KnowledgeGraphClient | None:
    """Open a KnowledgeGraphClient; return None when credentials are absent."""
    try:
        return KnowledgeGraphClient()
    except RuntimeError:
        logger.warning("KnowledgeGraphClient unavailable; phrase_publish skipped")
        return None


@router.get("/tasks")
def list_tasks(
    request: Request,
    source: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    client: PatientGraphClient = Depends(_get_client),
) -> dict[str, Any]:
    """Return one page of unified work tasks plus counts-by-source."""
    _require_authed_session(request)
    sources = _coerce_sources(source)
    filters = WorkTaskFilters(sources=sources, limit=limit, offset=offset)
    kg = _open_kg_client()
    try:
        with client.session() as session:
            page = get_work_tasks(session, filters, kg_session=kg)
    finally:
        if kg:
            kg.close()
    return page.to_dict()


@router.get("/counts")
def get_counts(
    request: Request,
    client: PatientGraphClient = Depends(_get_client),
) -> dict[str, int]:
    """Return the counts-by-source strip used on the /work landing page."""
    _require_authed_session(request)
    kg = _open_kg_client()
    try:
        with client.session() as session:
            counts = get_work_counts(session, kg_session=kg)
    finally:
        if kg:
            kg.close()
    return counts
