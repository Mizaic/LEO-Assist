"""Open a real PipelineRun in Validation Lab without enqueue.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas:
  DI: DI-562F2C9E
  DO: DO-4FD76836
"""

from __future__ import annotations

from typing import Any, Literal

from libs.cypher.validation_lab_finding_queries import (
    COUNT_RECENT_PIPELINE_RUNS,
    FIND_PIPELINE_RUNS_BY_IDENTIFIER,
    FIND_PIPELINE_RUNS_BY_LETTER,
    GET_PIPELINE_RUN_EXISTS,
    LIST_CLINICAL_PATIENTS,
    LIST_RECENT_PIPELINE_RUNS,
    LIST_RECENT_PIPELINE_RUNS_PAGE,
)

SearchMode = Literal["patient", "letters"]
LETTER_MIN_CHARS = 3


def compact_lookup(raw: str) -> str:
    """NHS numbers and UBRNs often arrive with spaces or hyphens."""
    return "".join(ch for ch in str(raw or "") if ch.isalnum()).upper()


def letter_snippet(text: str, needle: str, radius: int = 48) -> str:
    raw = " ".join(str(text or "").split())
    key = str(needle or "").strip()
    if not raw:
        return ""
    idx = raw.lower().find(key.lower())
    if idx < 0:
        return raw[:96]
    start = max(0, idx - radius)
    end = min(len(raw), idx + len(key) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(raw) else ""
    return prefix + raw[start:end] + suffix


def list_recent_pipeline_runs(
    client: Any,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows = client.run(LIST_RECENT_PIPELINE_RUNS, limit=int(limit))
    return [_run_row(row) for row in rows]


def page_pipeline_runs(
    client: Any,
    *,
    page: int = 0,
    per_page: int = 25,
) -> dict[str, Any]:
    """Paginated recent PipelineRuns with total count."""
    skip = max(0, page) * max(1, per_page)
    rows = client.run(
        LIST_RECENT_PIPELINE_RUNS_PAGE,
        skip=skip,
        per_page=int(per_page),
    )
    count_rows = client.run(COUNT_RECENT_PIPELINE_RUNS)
    total = int(count_rows[0].get("total", 0)) if count_rows else 0
    return {"rows": [_run_row(r) for r in rows], "total": total}


def find_pipeline_runs(
    client: Any,
    *,
    query: str,
    limit: int = 30,
    mode: SearchMode = "patient",
) -> list[dict[str, Any]]:
    lookup = str(query or "").strip()
    if str(mode) == "letters":
        return _find_by_letter(client, lookup=lookup, limit=limit)
    return _find_by_patient(client, lookup=lookup, limit=limit)


def list_clinical_patients(
    client: Any,
    *,
    query: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Patients with a pipeline run. Does not enqueue a new job."""
    lookup = str(query or "").strip()
    rows = client.run(
        LIST_CLINICAL_PATIENTS,
        lookup=lookup,
        compact=compact_lookup(lookup),
        limit=int(limit),
    )
    return [_patient_row(row) for row in rows]


def require_pipeline_run(client: Any, run_id: str) -> dict[str, Any]:
    rid = str(run_id or "").strip()
    rows = client.run(GET_PIPELINE_RUN_EXISTS, run_id=rid)
    if not rows:
        raise KeyError(f"PipelineRun not found: {rid}")
    return {
        "run_id": str(rows[0].get("run_id") or rid),
        "status": str(rows[0].get("status") or ""),
    }


def _find_by_patient(
    client: Any,
    *,
    lookup: str,
    limit: int,
) -> list[dict[str, Any]]:
    compact = compact_lookup(lookup)
    if not compact:
        return []
    rows = client.run(
        FIND_PIPELINE_RUNS_BY_IDENTIFIER,
        lookup=lookup,
        compact=compact,
        limit=int(limit),
    )
    return [
        _run_row(row, matched_on=_patient_match_reason(lookup, compact, row))
        for row in rows
    ]


def _find_by_letter(
    client: Any,
    *,
    lookup: str,
    limit: int,
) -> list[dict[str, Any]]:
    if len(lookup) < LETTER_MIN_CHARS:
        return []
    rows = client.run(
        FIND_PIPELINE_RUNS_BY_LETTER,
        needle=lookup,
        limit=int(limit),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _run_row(row, matched_on="letter")
        item["snippet"] = letter_snippet(str(row.get("hit_text") or ""), lookup)
        out.append(item)
    return out


def _patient_match_reason(
    lookup: str,
    compact: str,
    row: dict[str, Any],
) -> str:
    if compact and compact_lookup(row.get("nhs_number") or "") == compact:
        return "nhs"
    if compact and compact_lookup(row.get("ubrn") or "") == compact:
        return "ubrn"
    name = str(row.get("patient_name") or "").upper()
    if lookup.upper() and lookup.upper() in name:
        return "name"
    return "patient"


def _run_row(
    row: dict[str, Any],
    *,
    matched_on: str = "",
) -> dict[str, Any]:
    return {
        "run_id": str(row.get("run_id") or ""),
        "status": str(row.get("status") or ""),
        "created_at": str(row.get("created_at") or ""),
        "plan_id": str(row.get("plan_id") or ""),
        "patient_id": str(row.get("patient_id") or ""),
        "patient_name": str(row.get("patient_name") or ""),
        "nhs_number": str(row.get("nhs_number") or ""),
        "ubrn": str(row.get("ubrn") or ""),
        "matched_on": matched_on,
        "snippet": str(row.get("snippet") or ""),
    }


def _patient_row(row: dict[str, Any]) -> dict[str, Any]:
    out = _run_row(row)
    out["run_count"] = int(row.get("run_count") or 1)
    return out
