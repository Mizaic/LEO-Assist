"""First-of-month internal pack: our cost per tenant. No billable figures.

Atlas trace:
  DI: DI-5DE41177
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-5DE41177")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from libs.llm_spend_true_up.alerts import maybe_send_alert
from libs.llm_spend_true_up.entitlement import month_bounds
from libs.llm_spend_true_up.queries import (
    GET_MONTHLY_PACK,
    GET_TRUE_UP_FOR_MONTH,
    LIST_ENCOUNTER_QUOTAS,
    MARK_MONTHLY_PACK_SENT,
    ORG_RAW_SPEND,
    COUNT_ENCOUNTERS_BY_ORG,
)
from libs.llm_spend_true_up.run_job import UK

logger = logging.getLogger(__name__)


def previous_calendar_month(today: date | None = None) -> str:
    current = today or datetime.now(UK).date()
    if current.month == 1:
        return f"{current.year - 1:04d}-12"
    return f"{current.year:04d}-{current.month - 1:02d}"


def should_send_monthly_pack(today: date | None = None) -> bool:
    current = today or datetime.now(UK).date()
    return current.day == 1


def run_monthly_pack(
    client: Any,
    *,
    today: date,
    environment: str,
    send_mail: Callable[..., None] | None = None,
) -> dict[str, Any]:
    if not should_send_monthly_pack(today):
        return {"sent": False, "reason": "not-first-of-month"}
    month = previous_calendar_month(today)
    existing = list(
        client.run(GET_MONTHLY_PACK, month=month, environment=environment) or []
    )
    if existing and existing[0].get("sentAt"):
        return {"sent": False, "reason": "already-sent", "month": month}
    rows = _tenant_rows(client, month)
    azure_gbp = _azure_month_gbp(client, environment, month)
    body = render_pack(month, rows, azure_gbp)
    sent = maybe_send_alert(
        f"LEO AI our-cost pack -- {month}",
        body,
        send_mail=send_mail,
    )
    if sent:
        client.run(MARK_MONTHLY_PACK_SENT, month=month, environment=environment)
    return {"sent": sent, "month": month, "rows": rows, "body": body}


def _tenant_rows(client: Any, month: str) -> list[dict[str, Any]]:
    from_iso, to_iso = month_bounds(month)
    spend = {
        r["orgId"]: r
        for r in list(
            client.run(ORG_RAW_SPEND, from_date=from_iso, to_date=to_iso) or []
        )
    }
    encounters = {
        r["orgId"]: r
        for r in list(
            client.run(COUNT_ENCOUNTERS_BY_ORG, from_date=from_iso, to_date=to_iso)
            or []
        )
    }
    quotas = {r["orgId"]: r for r in list(client.run(LIST_ENCOUNTER_QUOTAS) or [])}
    org_ids = sorted(set(spend) | set(encounters) | set(quotas))
    rows = []
    for org_id in org_ids:
        s = spend.get(org_id) or {}
        e = encounters.get(org_id) or {}
        q = quotas.get(org_id) or {}
        rows.append(
            {
                "orgId": org_id,
                "orgName": s.get("orgName") or e.get("orgName") or org_id,
                "encounters": int(e.get("encounters") or 0),
                "tokens": int(s.get("inputTokens") or 0)
                + int(s.get("outputTokens") or 0),
                "ourCostUsd": float(s.get("ourCostUsd") or 0.0),
                "limit": int(q["monthlyLimit"]) if q.get("monthlyLimit") else None,
            }
        )
    return rows


def _azure_month_gbp(client: Any, environment: str, month: str) -> float | None:
    start = f"{month}-01"
    end_iso = month_bounds(month)[1]
    end = end_iso[:10]
    rows = list(
        client.run(
            GET_TRUE_UP_FOR_MONTH,
            environment=environment,
            month_start=start,
            month_end=end,
        )
        or []
    )
    if not rows:
        return None
    value = rows[0].get("azure_cost_gbp")
    return None if value is None else float(value)


def render_pack(month: str, rows: list[dict[str, Any]], azure_gbp: float | None) -> str:
    lines = [
        f"Our AI cost by customer for {month}.",
        "These are our costs only. Customer bill amounts are not included.",
        "",
        "Customer | Referrals | Tokens | Our cost (USD) | Limit",
    ]
    for row in rows:
        limit = row.get("limit")
        limit_txt = f"{row['encounters']}/{limit}" if limit else "not set"
        lines.append(
            f"{row['orgName']} | {row['encounters']} | {row['tokens']} | "
            f"${row['ourCostUsd']:.4f} | {limit_txt}"
        )
    lines.append("")
    if azure_gbp is not None:
        lines.append(
            f"Azure whole-account bill (not split by customer): GBP {azure_gbp:.2f}"
        )
    return "\n".join(lines)
