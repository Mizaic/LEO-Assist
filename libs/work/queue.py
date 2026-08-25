"""Service layer that backs the /work task queue.

Atlas trace:
  DI: DI-6BD7B681

Wraps libs.cypher.work_queue_queries so the API router never has to
assemble parameters or normalise source names by hand.

UncodedPhrase nodes live in the knowledge graph, not the patient graph.
get_work_tasks therefore accepts an optional kg_session for those rows.
If kg_session is None the phrase_publish bucket is silently skipped so
My work never hard-fails when the knowledge graph is unreachable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from libs.cypher.work_queue_queries import (
    COUNT_PHRASE_PUBLISH_TASKS,
    COUNT_WORK_TASKS_BY_SOURCE,
    GET_PHRASE_PUBLISH_TASKS,
    GET_UNIFIED_WORK_TASKS,
)

logger = logging.getLogger(__name__)

VALID_SOURCES: tuple[str, ...] = (
    "coding_review",
    "safety_net_alert",
    "gold_label",
    "extraction_quality_pause",
    "surface_form_approval",
    "phrase_publish",
)


@dataclass(frozen=True)
class WorkTaskFilters:
    """Inputs accepted by the /work/tasks endpoint."""

    sources: tuple[str, ...] | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class WorkTaskRow:
    """Canonical shape for a unified task row."""

    task_id: str
    task_type: str
    severity: int
    summary: str
    age_days: int
    resolve_url: str
    patient_id: str | None
    episode_id: str | None
    created_at: str = ""
    failure_kind: str = ""
    draft_author: str = ""
    draft_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "severity": self.severity,
            "summary": self.summary,
            "age_days": self.age_days,
            "created_at": self.created_at,
            "resolve_url": self.resolve_url,
            "patient_id": self.patient_id,
            "episode_id": self.episode_id,
            "failure_kind": self.failure_kind,
            "draft_author": self.draft_author,
            "draft_action": self.draft_action,
        }


@dataclass(frozen=True)
class WorkTasksPage:
    """One page of unified tasks plus the counts-by-source strip."""

    tasks: list[WorkTaskRow]
    counts_by_source: dict[str, int]
    limit: int
    offset: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [row.to_dict() for row in self.tasks],
            "counts_by_source": self.counts_by_source,
            "limit": self.limit,
            "offset": self.offset,
        }


def _coerce_sources(sources: Iterable[str] | None) -> tuple[str, ...] | None:
    if sources is None:
        return None
    picked = tuple(s for s in sources if s in VALID_SOURCES)
    return picked or None


def _iso_timestamp(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value).strip()
    if not text or text in {"None", "null"}:
        return ""
    return text


def _row_from_record(record: dict[str, Any]) -> WorkTaskRow:
    return WorkTaskRow(
        task_id=str(record["task_id"]),
        task_type=str(record["task_type"]),
        severity=int(record.get("severity") or 0),
        summary=str(record.get("summary") or ""),
        age_days=int(record.get("age_days") or 0),
        created_at=_iso_timestamp(record.get("created_at")),
        resolve_url=str(record.get("resolve_url") or ""),
        patient_id=(
            str(record["patient_id"]) if record.get("patient_id") else None
        ),
        episode_id=(
            str(record["episode_id"]) if record.get("episode_id") else None
        ),
        failure_kind=str(record.get("failure_kind") or ""),
        draft_author=str(record.get("draft_author") or ""),
        draft_action=str(record.get("draft_action") or ""),
    )


def _sort_key(row: WorkTaskRow) -> tuple[int, int, str]:
    return (-row.severity, -row.age_days, row.task_id)


def get_work_tasks(
    session: Any,
    filters: WorkTaskFilters,
    *,
    kg_session: Any = None,
) -> WorkTasksPage:
    """Return one page of unified work tasks plus counts-by-source.

    kg_session is the knowledge-graph Neo4j session. When provided,
    phrase_publish rows from UncodedPhrase are merged in. When None
    those rows are silently omitted.
    """
    sources = _coerce_sources(filters.sources)
    limit = max(1, min(int(filters.limit), 200))
    offset = max(0, int(filters.offset))

    # Fetch patient-graph rows; use a ceiling so we can merge before slicing.
    fetch_limit = offset + limit
    patient_records = session.run(
        GET_UNIFIED_WORK_TASKS,
        sources=list(sources) if sources else None,
        limit=fetch_limit,
        offset=0,
    )
    rows: list[WorkTaskRow] = [_row_from_record(dict(r)) for r in patient_records]

    # Merge knowledge-graph phrase_publish rows when the bucket is requested.
    kg_rows = _fetch_phrase_publish_rows(kg_session, sources, fetch_limit)  # kg_session is a KG client
    rows.extend(kg_rows)

    rows.sort(key=_sort_key)
    rows = rows[offset : offset + limit]

    counts = get_work_counts(session, kg_session=kg_session)
    return WorkTasksPage(
        tasks=rows,
        counts_by_source=counts,
        limit=limit,
        offset=offset,
    )


def _fetch_phrase_publish_rows(
    kg_client: Any,
    sources: tuple[str, ...] | None,
    fetch_limit: int,
) -> list[WorkTaskRow]:
    """Return phrase_publish rows from the knowledge graph, or [] on error.

    kg_client must expose a .run(query, **params) method, as KnowledgeGraphClient does.
    """
    bucket_wanted = sources is None or "phrase_publish" in sources
    if not bucket_wanted or kg_client is None:
        return []
    try:
        records = kg_client.run(
            GET_PHRASE_PUBLISH_TASKS,
            offset=0,
            limit=fetch_limit,
        )
        return [_row_from_record(dict(r)) for r in records]
    except Exception:
        logger.warning("phrase_publish rows unavailable; knowledge graph unreachable")
        return []


def get_work_counts(
    session: Any,
    *,
    kg_session: Any = None,
) -> dict[str, int]:
    """Return the counts-by-source map for the queue header strip.

    kg_session may be a KnowledgeGraphClient instance exposing .run().
    """
    records = session.run(COUNT_WORK_TASKS_BY_SOURCE)
    counts: dict[str, int] = {src: 0 for src in VALID_SOURCES}
    for record in records:
        data = dict(record)
        name = str(data.get("task_type") or "")
        if name in counts:
            counts[name] = int(data.get("total") or 0)

    # Add phrase_publish count from knowledge graph.
    if kg_session is not None:
        try:
            result = kg_session.run(COUNT_PHRASE_PUBLISH_TASKS)
            rows = list(result)
            counts["phrase_publish"] = int(rows[0]["total"]) if rows else 0
        except Exception:
            logger.warning("phrase_publish count unavailable")

    return counts
