"""Soft monthly encounter limits. Email only. Never block a referral.

Atlas trace:
  DI: DI-6D87C32F
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-6D87C32F")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from libs.llm_spend_true_up.alerts import maybe_send_alert
from libs.llm_spend_true_up.queries import (
    COUNT_ENCOUNTERS_BY_ORG,
    LIST_ENCOUNTER_QUOTAS,
    UPSERT_ENCOUNTER_QUOTA,
)
from libs.llm_spend_true_up.run_job import UK

logger = logging.getLogger(__name__)


def should_block_referral(used: int, limit: int) -> bool:
    """Soft limit: never pause the pipeline."""
    return False


def month_bounds(month: str) -> tuple[str, str]:
    start = datetime.fromisoformat(f"{month}-01").replace(tzinfo=UK)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.isoformat(), end.isoformat()


def upsert_quota(
    client: Any, org_id: str, monthly_limit: int, org_name: str = ""
) -> dict:
    rows = client.run(
        UPSERT_ENCOUNTER_QUOTA,
        org_id=org_id,
        monthly_limit=int(monthly_limit),
        org_name=org_name,
    )
    return rows[0] if rows else {"orgId": org_id, "monthlyLimit": monthly_limit}


def list_quotas(client: Any) -> list[dict[str, Any]]:
    return list(client.run(LIST_ENCOUNTER_QUOTAS) or [])


def check_quotas(
    client: Any,
    *,
    month: str,
    send_mail: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    quotas = {row["orgId"]: row for row in list_quotas(client)}
    if not quotas:
        return []
    from_iso, to_iso = month_bounds(month)
    counts = {
        row["orgId"]: row
        for row in list(
            client.run(COUNT_ENCOUNTERS_BY_ORG, from_date=from_iso, to_date=to_iso)
            or []
        )
    }
    alerts: list[dict[str, Any]] = []
    for org_id, quota in quotas.items():
        used = int((counts.get(org_id) or {}).get("encounters") or 0)
        limit = int(quota.get("monthlyLimit") or 0)
        if limit <= 0:
            continue
        over = used > limit
        row = {
            "orgId": org_id,
            "orgName": quota.get("orgName") or org_id,
            "used": used,
            "limit": limit,
            "overLimit": over,
        }
        alerts.append(row)
        if over:
            _email_over(row, month, send_mail)
    return alerts


def _email_over(
    row: dict[str, Any], month: str, send_mail: Callable[..., None] | None
) -> None:
    maybe_send_alert(
        f"LEO customer over encounter limit -- {row['orgName']}",
        (
            f"Month: {month}\n"
            f"Customer: {row['orgName']}\n"
            f"Processed: {row['used']}\n"
            f"Contract limit: {row['limit']}\n"
            "This is a business alert. Care is not stopped."
        ),
        send_mail=send_mail,
    )


def current_uk_month() -> str:
    now = datetime.now(UK)
    return f"{now.year:04d}-{now.month:02d}"
