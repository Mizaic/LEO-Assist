"""Orchestrate one daily Azure spend check.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from libs.llm_spend_true_up.alerts import maybe_send_alert
from libs.llm_spend_true_up.compare import (
    azure_total_tokens,
    classify_status,
    drift_ratio,
    our_total_tokens,
)
from libs.llm_spend_true_up.queries import (
    LIST_AUDIT_EVENT_IDS,
    SUM_OUR_LLM_SPEND,
    UPSERT_TRUE_UP,
)

logger = logging.getLogger(__name__)

UK = ZoneInfo("Europe/London")


def day_bounds(day: str) -> tuple[str, str]:
    start = datetime.fromisoformat(day).replace(tzinfo=UK)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def run_daily_true_up(
    client: Any,
    *,
    day: str,
    environment: str,
    fetch_azure_tokens: Callable[..., dict[str, Any]],
    fetch_azure_cost: Callable[..., dict[str, Any]],
    gbp_usd: float = 1.34,
    send_mail: Callable[..., None] | None = None,
    token_warn: float = 0.15,
    cost_warn: float = 0.25,
) -> dict[str, Any]:
    from_iso, to_iso = day_bounds(day)
    client.run(LIST_AUDIT_EVENT_IDS, from_date=from_iso, to_date=to_iso)
    try:
        ours = _our_spend(client, from_iso, to_iso)
        azure_tokens = fetch_azure_tokens(day=day)
        azure_cost = fetch_azure_cost(day=day)
    except Exception:
        logger.warning("true-up: fetch failed for %s", day, exc_info=True)
        snap = _failed_snapshot(day, environment)
        _persist(client, snap)
        return snap
    return _finish_ok(
        client,
        day=day,
        environment=environment,
        ours=ours,
        azure_tokens=azure_tokens,
        azure_cost=azure_cost,
        gbp_usd=gbp_usd,
        send_mail=send_mail,
        token_warn=token_warn,
        cost_warn=cost_warn,
    )


def _our_spend(client: Any, from_iso: str, to_iso: str) -> dict[str, Any]:
    rows = list(client.run(SUM_OUR_LLM_SPEND, from_date=from_iso, to_date=to_iso) or [])
    row = rows[0] if rows else {}
    return {
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "cached_tokens": int(row.get("cached_tokens") or 0),
        "cost_usd": float(row.get("cost_usd") or 0.0),
    }


def _finish_ok(
    client: Any,
    *,
    day: str,
    environment: str,
    ours: dict[str, Any],
    azure_tokens: dict[str, Any],
    azure_cost: dict[str, Any],
    gbp_usd: float,
    send_mail: Callable[..., None] | None,
    token_warn: float,
    cost_warn: float,
) -> dict[str, Any]:
    our_tok = our_total_tokens(ours["input_tokens"], ours["output_tokens"])
    az_tok = azure_total_tokens(
        int(azure_tokens.get("prompt_tokens") or 0),
        int(azure_tokens.get("completion_tokens") or 0),
    )
    provisional = bool(azure_cost.get("provisional"))
    gbp = azure_cost.get("cost_gbp")
    azure_usd = None if gbp is None else float(gbp) * float(gbp_usd)
    token_d = drift_ratio(float(our_tok), float(az_tok))
    cost_d = (
        0.0
        if provisional or gbp is None
        else drift_ratio(ours["cost_usd"], azure_usd or 0.0)
    )
    status = classify_status(
        token_d,
        cost_d,
        provisional=provisional,
        failed=False,
        token_warn=token_warn,
        cost_warn=cost_warn,
    )
    snap = {
        "date": day,
        "environment": environment,
        "our_input_tokens": ours["input_tokens"],
        "our_output_tokens": ours["output_tokens"],
        "our_cached_tokens": ours["cached_tokens"],
        "our_cost_usd": ours["cost_usd"],
        "azure_prompt_tokens": int(azure_tokens.get("prompt_tokens") or 0),
        "azure_completion_tokens": int(azure_tokens.get("completion_tokens") or 0),
        "azure_cost_gbp": None if gbp is None else float(gbp),
        "azure_cost_usd": azure_usd,
        "token_drift": token_d,
        "cost_drift": None if provisional else cost_d,
        "cost_provisional": provisional,
        "status": status,
        "azure_scope": "account-wide",
    }
    _persist(client, snap)
    _maybe_alert(snap, token_warn, cost_warn, send_mail)
    return snap


def _failed_snapshot(day: str, environment: str) -> dict[str, Any]:
    return {
        "date": day,
        "environment": environment,
        "our_input_tokens": None,
        "our_output_tokens": None,
        "our_cached_tokens": None,
        "our_cost_usd": None,
        "azure_prompt_tokens": None,
        "azure_completion_tokens": None,
        "azure_cost_gbp": None,
        "azure_cost_usd": None,
        "token_drift": None,
        "cost_drift": None,
        "cost_provisional": True,
        "status": "failed",
        "azure_scope": "account-wide",
    }


_UPSERT_KEYS = (
    "date",
    "environment",
    "our_input_tokens",
    "our_output_tokens",
    "our_cached_tokens",
    "our_cost_usd",
    "azure_prompt_tokens",
    "azure_completion_tokens",
    "azure_cost_gbp",
    "azure_cost_usd",
    "token_drift",
    "cost_drift",
    "cost_provisional",
    "status",
)


def _persist(client: Any, snap: dict[str, Any]) -> None:
    client.run(UPSERT_TRUE_UP, **{k: snap.get(k) for k in _UPSERT_KEYS})


def _maybe_alert(
    snap: dict[str, Any],
    token_warn: float,
    cost_warn: float,
    send_mail: Callable[..., None] | None,
) -> None:
    if snap["status"] != "warn":
        return
    token_d = float(snap.get("token_drift") or 0.0)
    cost_d = float(snap.get("cost_drift") or 0.0)
    if token_d > token_warn:
        maybe_send_alert(
            "LEO AI tokens do not match Azure",
            _token_body(snap),
            send_mail=send_mail,
        )
        return
    if not snap.get("cost_provisional") and cost_d > cost_warn:
        maybe_send_alert(
            "LEO AI cost does not match Azure",
            _cost_body(snap),
            send_mail=send_mail,
        )


def _token_body(snap: dict[str, Any]) -> str:
    return (
        f"Date: {snap['date']}\n"
        f"Our tokens: {snap['our_input_tokens']}+{snap['our_output_tokens']}\n"
        f"Azure tokens (whole account): "
        f"{snap['azure_prompt_tokens']}+{snap['azure_completion_tokens']}\n"
        f"Gap: {float(snap['token_drift'] or 0):.0%}\n"
        "This may mean a fault in our tracker, or AI use we did not record."
    )


def _cost_body(snap: dict[str, Any]) -> str:
    return (
        f"Date: {snap['date']}\n"
        f"Our cost: ${snap['our_cost_usd']}\n"
        f"Azure bill (whole account): GBP {snap['azure_cost_gbp']}\n"
        f"Gap: {float(snap['cost_drift'] or 0):.0%}\n"
        "This may mean a price change, or that we used the wrong AI model."
    )


def uk_today() -> str:
    return datetime.now(UK).date().isoformat()


def previous_uk_day(today: date | None = None) -> str:
    current = today or datetime.now(UK).date()
    return (current - timedelta(days=1)).isoformat()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
