"""Read Azure Monitor tokens and Cost Management pounds.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")


def fetch_azure_tokens(day: str) -> dict[str, Any]:
    resource_id = os.getenv("AZURE_OPENAI_RESOURCE_ID", "").strip()
    if not resource_id:
        raise RuntimeError("AZURE_OPENAI_RESOURCE_ID is not set")
    start, end = _utc_window(day)
    data = _get_json(
        f"https://management.azure.com{resource_id}/providers/"
        "microsoft.insights/metrics"
        f"?metricnames=ProcessedPromptTokens,GeneratedTokens"
        f"&timespan={start}/{end}&aggregation=Total&api-version=2024-02-01"
    )
    prompt = _metric_total(data, "ProcessedPromptTokens")
    completion = _metric_total(data, "GeneratedTokens")
    return {"prompt_tokens": prompt, "completion_tokens": completion}


def fetch_azure_cost(day: str) -> dict[str, Any]:
    """Cost Management lags. Try the day, then the day before. Empty is provisional."""
    subscription = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip()
    resource_id = os.getenv("AZURE_OPENAI_RESOURCE_ID", "").strip()
    if not subscription or not resource_id:
        raise RuntimeError(
            "AZURE_SUBSCRIPTION_ID or AZURE_OPENAI_RESOURCE_ID is not set"
        )
    gbp = _query_cost(subscription, resource_id, day)
    if gbp is not None:
        return {"cost_gbp": gbp, "provisional": False}
    prev = (datetime.fromisoformat(day) - timedelta(days=1)).date().isoformat()
    gbp = _query_cost(subscription, resource_id, prev)
    if gbp is not None:
        return {"cost_gbp": gbp, "provisional": False}
    return {"cost_gbp": None, "provisional": True}


def _utc_window(day: str) -> tuple[str, str]:
    start = datetime.fromisoformat(day).replace(tzinfo=UK)
    end = start + timedelta(days=1)
    return (
        start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        end.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _metric_total(payload: dict[str, Any], name: str) -> int:
    for item in payload.get("value") or []:
        if item.get("name", {}).get("value") != name:
            continue
        total = 0.0
        for ts in item.get("timeseries") or []:
            for point in ts.get("data") or []:
                total += float(point.get("total") or 0.0)
        return int(total)
    return 0


def _query_cost(subscription: str, resource_id: str, day: str) -> float | None:
    nxt = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": f"{day}T00:00:00Z", "to": f"{nxt}T00:00:00Z"},
        "dataset": {
            "granularity": "None",
            "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
            "filter": {
                "dimensions": {
                    "name": "ResourceId",
                    "operator": "In",
                    "values": [resource_id],
                }
            },
        },
    }
    data = _post_json(
        f"https://management.azure.com/subscriptions/{subscription}"
        f"/providers/Microsoft.CostManagement/query?api-version=2023-11-01",
        body,
    )
    rows = (data.get("properties") or {}).get("rows") or []
    if not rows:
        return None
    return float(rows[0][0])


def _token() -> str:
    from azure.identity import DefaultAzureCredential

    cred = DefaultAzureCredential()
    return cred.get_token("https://management.azure.com/.default").token


def _get_json(url: str) -> dict[str, Any]:
    import httpx

    resp = httpx.get(url, headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    import httpx

    resp = httpx.post(
        url,
        json=body,
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
