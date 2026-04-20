"""Service layer that backs the /work task queue (DI-LEO-AI-138).

Atlas trace:
  DO: DO-65BA6EA0
  DI: DI-C0AD09D2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-65BA6EA0")

Wraps libs.cypher.work_queue_queries so the API router never has to
assemble parameters or normalise source names by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from libs.cypher.work_queue_queries import (
    COUNT_WORK_TASKS_BY_SOURCE,
    GET_UNIFIED_WORK_TASKS,
)

VALID_SOURCES: tuple[str, ...] = (
    "coding_review",
    "safety_net_alert",
    "gold_label",
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "severity": self.severity,
            "summary": self.summary,
            "age_days": self.age_days,
            "resolve_url": self.resolve_url,
            "patient_id": self.patient_id,
            "episode_id": self.episode_id,
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


def _row_from_record(record: dict[str, Any]) -> WorkTaskRow:
    return WorkTaskRow(
        task_id=str(record["task_id"]),
        task_type=str(record["task_type"]),
        severity=int(record.get("severity") or 0),
        summary=str(record.get("summary") or ""),
        age_days=int(record.get("age_days") or 0),
        resolve_url=str(record.get("resolve_url") or ""),
        patient_id=(
            str(record["patient_id"]) if record.get("patient_id") else None
        ),
        episode_id=(
            str(record["episode_id"]) if record.get("episode_id") else None
        ),
    )


def get_work_tasks(
    session: Any,
    filters: WorkTaskFilters,
) -> WorkTasksPage:
    """Return one page of unified work tasks plus counts-by-source."""
    sources = _coerce_sources(filters.sources)
    limit = max(1, min(int(filters.limit), 200))
    offset = max(0, int(filters.offset))

    task_records = session.run(
        GET_UNIFIED_WORK_TASKS,
        sources=list(sources) if sources else None,
        limit=limit,
        offset=offset,
    )
    rows = [_row_from_record(dict(r)) for r in task_records]

    counts = get_work_counts(session)
    return WorkTasksPage(
        tasks=rows,
        counts_by_source=counts,
        limit=limit,
        offset=offset,
    )


def get_work_counts(session: Any) -> dict[str, int]:
    """Return the counts-by-source map for the queue header strip."""
    records = session.run(COUNT_WORK_TASKS_BY_SOURCE)
    counts: dict[str, int] = {src: 0 for src in VALID_SOURCES}
    for record in records:
        data = dict(record)
        name = str(data.get("task_type") or "")
        if name in counts:
            counts[name] = int(data.get("total") or 0)
    return counts
