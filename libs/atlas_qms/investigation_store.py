"""Persist NCR investigation cases locally. Log redacted notes to Atlas.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Atlas: DI-ED5A9AC3
"""

from __future__ import annotations

import json
from typing import Any, Callable

from libs.atlas_qms.ncr_client import (
    NcrClientError,
    NcrNotConfigured,
    add_product_ncr_comment,
)
from libs.atlas_qms.redact import redact_for_atlas
from libs.cypher.ncr_investigation_queries import (
    ADD_EVENT,
    LIST_EVENTS,
    LOAD_INVESTIGATION,
    SAVE_CASES,
)
from libs.neo4j_client.client import PatientGraphClient

RunFn = Callable[..., list[dict[str, Any]]]
CommentFn = Callable[[str, str], Any]
CASE_KEYS = (
    "run_id",
    "patient_id",
    "patient_name",
    "nhs_number",
    "ubrn",
    "status",
)


def load_investigation(nc_id: str, run: RunFn | None = None) -> dict[str, Any]:
    key = nc_id.strip()
    rows = _run(run)(LOAD_INVESTIGATION, nc_id=key)
    events = _run(run)(LIST_EVENTS, nc_id=key)
    if not rows:
        return {"nc_id": key, "title": "", "cases": [], "events": events}
    row = rows[0]
    return {
        "nc_id": key,
        "title": str(row.get("title") or ""),
        "cases": _parse_cases(row.get("cases_json")),
        "events": events,
    }


def save_cases(
    nc_id: str,
    cases: list[dict[str, Any]],
    title: str = "",
    run: RunFn | None = None,
) -> dict[str, Any]:
    key = nc_id.strip()
    local = [_case_row(item) for item in cases]
    _run(run)(
        SAVE_CASES,
        nc_id=key,
        title=title,
        cases_json=json.dumps(local),
    )
    return {"nc_id": key, "cases": local}


def log_event(
    nc_id: str,
    kind: str,
    local_text: str,
    run: RunFn | None = None,
    comment: CommentFn | None = None,
) -> dict[str, Any]:
    key = nc_id.strip()
    atlas_text = redact_for_atlas(local_text)
    atlas_ok = _post_comment(comment or add_product_ncr_comment, key, atlas_text)
    rows = _run(run)(
        ADD_EVENT,
        nc_id=key,
        kind=kind,
        local_text=local_text,
        atlas_text=atlas_text,
        atlas_ok=atlas_ok,
    )
    row = rows[0] if rows else {}
    return {
        "event_id": str(row.get("event_id") or ""),
        "atlas_ok": bool(row.get("atlas_ok", atlas_ok)),
        "atlas_text": str(row.get("atlas_text") or atlas_text),
    }


def _post_comment(comment: CommentFn, nc_id: str, atlas_text: str) -> bool:
    try:
        comment(nc_id, atlas_text)
        return True
    except (NcrClientError, NcrNotConfigured):
        return False


def _run(run: RunFn | None) -> RunFn:
    return run or PatientGraphClient().run


def _parse_cases(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, list):
        return [_case_row(item) for item in raw if isinstance(item, dict)]
    if not isinstance(raw, str) or not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [_case_row(item) for item in parsed if isinstance(item, dict)]


def _case_row(item: dict[str, Any]) -> dict[str, str]:
    return {key: str(item.get(key) or "") for key in CASE_KEYS}
