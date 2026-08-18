"""Gated LEO phone-home: escalate now, digest by threshold.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Atlas: DI-C7DEF132
"""

from __future__ import annotations

import os
from typing import Any, Callable

from libs.atlas_qms.ncr_client import create_product_ncr, list_product_ncrs
from libs.atlas_qms.phone_home_sig import (
    IssueSignal,
    find_open_ncr,
    ncr_description,
    ncr_title,
    signature_for,
)
from libs.cypher.phone_home_queries import (
    LIST_PHONE_HOME_CANDIDATES,
    LIST_PHONE_HOME_UNCODED,
)

_SOURCE_FAMILY = {
    "pipeline_hitl_ner": "hitl_ner",
    "pipeline_hitl_coding": "hitl_coding",
}

ListFn = Callable[..., list[dict[str, Any]]]
CreateFn = Callable[..., dict[str, Any]]
RunFn = Callable[..., list[dict[str, Any]]]


def phone_home_enabled() -> bool:
    raw = os.getenv("LEO_PHONE_HOME_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "off", "no"}


def phone_home_threshold() -> int:
    try:
        return max(1, int(os.getenv("LEO_PHONE_HOME_THRESHOLD", "20")))
    except ValueError:
        return 20


def collect_signals(
    uncoded: list[dict[str, Any]] | None,
    candidates: list[dict[str, Any]] | None,
    min_count: int,
) -> list[IssueSignal]:
    out: list[IssueSignal] = []
    for row in uncoded or []:
        signal = _uncoded_signal(row, min_count)
        if signal:
            out.append(signal)
    for row in candidates or []:
        signal = _candidate_signal(row, min_count)
        if signal:
            out.append(signal)
    return out


def submit_signal(
    signal: IssueSignal,
    *,
    list_fn: ListFn | None = None,
    create_fn: CreateFn | None = None,
) -> dict[str, Any]:
    if not phone_home_enabled():
        return {
            "action": "disabled",
            "signature": signature_for(signal.family, signal.key),
        }
    rows = (list_fn or list_product_ncrs)(
        query=signature_for(signal.family, signal.key), limit=50
    )
    sig = signature_for(signal.family, signal.key)
    open_row = find_open_ncr(rows, sig)
    if open_row:
        return {"action": "exists", "signature": sig, "ncr": open_row}
    created = (create_fn or create_product_ncr)(
        title=ncr_title(signal),
        description=ncr_description(signal),
        severity=signal.severity,
    )
    return {"action": "created", "signature": sig, "ncr": created}


def phone_home_escalated(*, task_type: str) -> dict[str, Any]:
    key = " ".join((task_type or "unknown").split()) or "unknown"
    return submit_signal(
        IssueSignal(family="hitl_escalated", key=key, count=1, gate="escalate", tag=key)
    )


def preview_phone_home(
    *,
    run: RunFn | None = None,
    min_count: int | None = None,
) -> dict[str, Any]:
    threshold = min_count if min_count is not None else phone_home_threshold()
    signals = _load_signals(run, threshold)
    return {
        "threshold": threshold,
        "items": [_preview_item(signal) for signal in signals],
    }


def digest_phone_home(
    *,
    run: RunFn | None = None,
    list_fn: ListFn | None = None,
    create_fn: CreateFn | None = None,
    min_count: int | None = None,
) -> dict[str, Any]:
    threshold = min_count if min_count is not None else phone_home_threshold()
    signals = _load_signals(run, threshold)
    results = [
        submit_signal(signal, list_fn=list_fn, create_fn=create_fn)
        for signal in signals
    ]
    return {"threshold": threshold, "results": results}


def _uncoded_signal(row: dict[str, Any], min_count: int) -> IssueSignal | None:
    count = int(row.get("count") or 0)
    key = str(row.get("key") or "").strip()
    if count < min_count or not key:
        return None
    return IssueSignal(
        family="uncoded_phrase",
        key=key,
        count=count,
        gate="threshold",
        tag=str(row.get("tag") or ""),
    )


def _candidate_signal(row: dict[str, Any], min_count: int) -> IssueSignal | None:
    count = int(row.get("count") or 0)
    family = _SOURCE_FAMILY.get(str(row.get("source") or ""), "")
    if count < min_count or not family:
        return None
    return IssueSignal(
        family=family,
        key=str(row.get("key") or "unknown"),
        count=count,
        gate="threshold",
    )


def _load_signals(run: RunFn | None, threshold: int) -> list[IssueSignal]:
    runner = run or _knowledge_run
    return collect_signals(
        runner(LIST_PHONE_HOME_UNCODED, threshold=threshold),
        runner(LIST_PHONE_HOME_CANDIDATES, threshold=threshold),
        threshold,
    )


def _preview_item(signal: IssueSignal) -> dict[str, Any]:
    return {
        "family": signal.family,
        "count": signal.count,
        "gate": signal.gate,
        "signature": signature_for(signal.family, signal.key),
        "title": ncr_title(signal),
        "description": ncr_description(signal),
    }


def _knowledge_run(query: str, **params: Any) -> list[dict[str, Any]]:
    from libs.neo4j_client.client import KnowledgeGraphClient

    client = KnowledgeGraphClient()
    try:
        return client.run(query, **params)
    finally:
        client.close()
