"""Open a real PipelineRun in Validation Lab without enqueue.

Atlas:
  DI: DI-562F2C9E
  DO: DO-4FD76836
"""

from __future__ import annotations

from typing import Any

from libs.cypher.validation_lab_finding_queries import (
    FIND_PIPELINE_RUNS_BY_IDENTIFIER,
    GET_PIPELINE_RUN_EXISTS,
    LIST_CLINICAL_PATIENTS,
    LIST_RECENT_PIPELINE_RUNS,
)


def compact_lookup(raw: str) -> str:
    """NHS numbers and UBRNs often arrive with spaces or hyphens."""
    return "".join(ch for ch in str(raw or "") if ch.isalnum()).upper()


def list_recent_pipeline_runs(
    client: Any,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows = client.run(LIST_RECENT_PIPELINE_RUNS, limit=int(limit))
    return [_run_row(row) for row in rows]


def find_pipeline_runs(
    client: Any,
    *,
    query: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    compact = compact_lookup(query)
    if not compact:
        return []
    rows = client.run(
        FIND_PIPELINE_RUNS_BY_IDENTIFIER,
        lookup=str(query or "").strip(),
        compact=compact,
        limit=int(limit),
    )
    return [_run_row(row) for row in rows]


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


def _run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row.get("run_id") or ""),
        "status": str(row.get("status") or ""),
        "created_at": str(row.get("created_at") or ""),
        "plan_id": str(row.get("plan_id") or ""),
        "patient_id": str(row.get("patient_id") or ""),
        "patient_name": str(row.get("patient_name") or ""),
        "nhs_number": str(row.get("nhs_number") or ""),
        "ubrn": str(row.get("ubrn") or ""),
    }


def _patient_row(row: dict[str, Any]) -> dict[str, Any]:
    out = _run_row(row)
    out["run_count"] = int(row.get("run_count") or 1)
    return out
