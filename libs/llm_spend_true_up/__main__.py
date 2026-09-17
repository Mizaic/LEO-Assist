"""CLI: python -m libs.llm_spend_true_up

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from libs.llm_spend_true_up.azure import fetch_azure_cost, fetch_azure_tokens
from libs.llm_spend_true_up.entitlement import check_quotas, current_uk_month
from libs.llm_spend_true_up.monthly import run_monthly_pack
from libs.llm_spend_true_up.run_job import UK, previous_uk_day, run_daily_true_up
from libs.neo4j_client.client import PatientGraphClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_spend_true_up")


def main() -> int:
    environment = os.getenv("LEO_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "prod"
    day = os.getenv("LLM_TRUE_UP_DAY") or previous_uk_day()
    gbp_usd = float(os.getenv("LLM_TRUE_UP_GBP_USD", "1.34"))
    token_warn = float(os.getenv("LLM_TRUE_UP_TOKEN_DRIFT", "0.15"))
    cost_warn = float(os.getenv("LLM_TRUE_UP_COST_DRIFT", "0.25"))
    client = PatientGraphClient()
    snap = run_daily_true_up(
        client,
        day=day,
        environment=environment,
        fetch_azure_tokens=fetch_azure_tokens,
        fetch_azure_cost=fetch_azure_cost,
        gbp_usd=gbp_usd,
        token_warn=token_warn,
        cost_warn=cost_warn,
    )
    logger.info("true-up %s status=%s", day, snap.get("status"))
    check_quotas(client, month=current_uk_month())
    pack = run_monthly_pack(
        client, today=datetime.now(UK).date(), environment=environment
    )
    logger.info("monthly pack %s", pack.get("reason") or pack.get("month"))
    return 0 if snap.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
