"""Soft monthly encounter limit -- acceptance verification.

Atlas trace:
  DI: DI-6D87C32F
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-6D87C32F")
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.llm_spend_true_up.entitlement import (
    check_quotas,
    should_block_referral,
    upsert_quota,
)
from libs.llm_spend_true_up.queries import (
    COUNT_ENCOUNTERS_BY_ORG,
    LIST_ENCOUNTER_QUOTAS,
    UPSERT_ENCOUNTER_QUOTA,
)


class FakeGraph:
    def __init__(self) -> None:
        self.quotas: dict[str, dict] = {}
        self.counts: dict[str, dict] = {}

    def run(self, query: str, **params):
        if query == UPSERT_ENCOUNTER_QUOTA:
            row = {
                "orgId": params["org_id"],
                "monthlyLimit": params["monthly_limit"],
                "orgName": params.get("org_name") or params["org_id"],
            }
            self.quotas[params["org_id"]] = row
            return [row]
        if query == LIST_ENCOUNTER_QUOTAS:
            return [q for q in self.quotas.values() if q["monthlyLimit"] > 0]
        if query == COUNT_ENCOUNTERS_BY_ORG:
            return list(self.counts.values())
        return []


def test_admin_can_set_monthly_limit():
    graph = FakeGraph()
    row = upsert_quota(graph, "org-1", 100, org_name="Trust A")
    assert row["monthlyLimit"] == 100
    assert graph.quotas["org-1"]["monthlyLimit"] == 100


def test_over_limit_sends_email(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com")
    graph = FakeGraph()
    upsert_quota(graph, "org-1", 100, org_name="Trust A")
    graph.counts["org-1"] = {"orgId": "org-1", "orgName": "Trust A", "encounters": 101}
    send = MagicMock()
    rows = check_quotas(graph, month="2026-09", send_mail=send)
    assert rows[0]["overLimit"] is True
    send.assert_called_once()


def test_under_limit_sends_no_email(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com")
    graph = FakeGraph()
    upsert_quota(graph, "org-1", 100, org_name="Trust A")
    graph.counts["org-1"] = {"orgId": "org-1", "orgName": "Trust A", "encounters": 99}
    send = MagicMock()
    rows = check_quotas(graph, month="2026-09", send_mail=send)
    assert rows[0]["overLimit"] is False
    send.assert_not_called()


def test_no_limit_skips_customer():
    graph = FakeGraph()
    graph.counts["org-1"] = {"orgId": "org-1", "orgName": "Trust A", "encounters": 50}
    send = MagicMock()
    rows = check_quotas(graph, month="2026-09", send_mail=send)
    assert rows == []
    send.assert_not_called()


def test_over_limit_does_not_block_referral():
    assert should_block_referral(used=101, limit=100) is False
