"""Persist ValidationFinding records against a lab or pipeline run.

Atlas:
  DI: DI-562F2C9E
  DO: DO-4FD76836
"""

from __future__ import annotations

import uuid
from typing import Any

from libs.cypher.validation_lab_finding_queries import (
    LIST_FINDINGS_FOR_RUN,
    LIST_OPEN_FINDINGS,
    UPSERT_VALIDATION_FINDING,
)
from libs.validation_lab.service import _json_safe

FINDING_CATEGORIES = frozenset(
    {"extraction", "context", "guard", "phrase_mapping", "guideline_rule"}
)
FINDING_STAGES = frozenset(
    {"extract", "post", "terminology", "persist", "compliance", "sbar"}
)
FINDING_STATUSES = frozenset({"open", "routed", "retested", "closed"})


class FindingError(ValueError):
    """Raised when a finding payload is not valid."""


def _plain(value: Any, *, max_len: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:max_len]


def validate_finding_fields(
    *,
    category: str,
    stage_id: str,
    status: str,
) -> None:
    if category not in FINDING_CATEGORIES:
        raise FindingError(f"Unknown finding category: {category}")
    if stage_id not in FINDING_STAGES:
        raise FindingError(f"Unknown finding stage: {stage_id}")
    if status not in FINDING_STATUSES:
        raise FindingError(f"Unknown finding status: {status}")


def create_finding(
    client: Any,
    *,
    run_id: str,
    stage_id: str,
    category: str,
    target: str,
    note: str,
    status: str = "open",
) -> dict[str, Any]:
    rid = str(run_id or "").strip()
    if not rid:
        raise FindingError("run_id is required")
    validate_finding_fields(category=category, stage_id=stage_id, status=status)
    rows = client.run(
        UPSERT_VALIDATION_FINDING,
        finding_id=str(uuid.uuid4()),
        run_id=rid,
        stage_id=stage_id,
        category=category,
        target=_plain(target, max_len=512),
        note=_plain(note, max_len=1000),
        status=status,
    )
    if not rows:
        raise FindingError("Finding was not saved")
    return _finding_row(rows[0]["finding"])


def list_findings_for_run(client: Any, run_id: str) -> list[dict[str, Any]]:
    rid = str(run_id or "").strip()
    if not rid:
        return []
    rows = client.run(LIST_FINDINGS_FOR_RUN, run_id=rid)
    return [_finding_row(row["finding"]) for row in rows if row.get("finding")]


def list_open_findings(client: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = client.run(
        LIST_OPEN_FINDINGS,
        statuses=["open", "routed"],
        limit=int(limit),
    )
    return [_finding_row(row["finding"]) for row in rows if row.get("finding")]


def _finding_row(finding: Any) -> dict[str, Any]:
    return _json_safe(dict(finding or {}))
