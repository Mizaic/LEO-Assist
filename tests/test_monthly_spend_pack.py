"""Monthly internal our-cost pack -- acceptance verification.

Atlas trace:
  DI: DI-5DE41177
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-5DE41177")
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from libs.llm_spend_true_up.monthly import render_pack, run_monthly_pack
from libs.llm_spend_true_up.queries import (
    COUNT_ENCOUNTERS_BY_ORG,
    GET_MONTHLY_PACK,
    GET_TRUE_UP_FOR_MONTH,
    LIST_ENCOUNTER_QUOTAS,
    MARK_MONTHLY_PACK_SENT,
    ORG_RAW_SPEND,
)


class FakeGraph:
    def __init__(self) -> None:
        self.sent_months: set[str] = set()
        self.spend = [
            {
                "orgId": "org-a",
                "orgName": "Trust A",
                "runCount": 3,
                "inputTokens": 1000,
                "outputTokens": 200,
                "ourCostUsd": 1.25,
            },
            {
                "orgId": "org-b",
                "orgName": "Trust B",
                "runCount": 1,
                "inputTokens": 400,
                "outputTokens": 50,
                "ourCostUsd": 0.40,
            },
        ]
        self.encounters = [
            {"orgId": "org-a", "orgName": "Trust A", "encounters": 12},
            {"orgId": "org-b", "orgName": "Trust B", "encounters": 4},
        ]
        self.quotas = [{"orgId": "org-a", "monthlyLimit": 10, "orgName": "Trust A"}]
        self.azure_gbp = 12.5

    def run(self, query: str, **params):
        if query == GET_MONTHLY_PACK:
            if params["month"] in self.sent_months:
                return [{"month": params["month"], "sentAt": "2026-10-01T07:00:00"}]
            return []
        if query == MARK_MONTHLY_PACK_SENT:
            self.sent_months.add(params["month"])
            return [{"month": params["month"]}]
        if query == ORG_RAW_SPEND:
            return list(self.spend)
        if query == COUNT_ENCOUNTERS_BY_ORG:
            return list(self.encounters)
        if query == LIST_ENCOUNTER_QUOTAS:
            return list(self.quotas)
        if query == GET_TRUE_UP_FOR_MONTH:
            return [{"azure_cost_gbp": self.azure_gbp}]
        return []


def test_first_of_month_sends_one_internal_email(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com")
    graph = FakeGraph()
    send = MagicMock()
    result = run_monthly_pack(
        graph, today=date(2026, 10, 1), environment="prod", send_mail=send
    )
    assert result["sent"] is True
    assert result["month"] == "2026-09"
    send.assert_called_once()
    assert send.call_args.kwargs["from_address"] == "leo.alerts@mizaic.com"
    assert send.call_args.kwargs["to_addresses"] == ["ops@mizaic.com"]


def test_pack_has_our_cost_only_no_patient_data():
    body = render_pack(
        "2026-09",
        [
            {
                "orgName": "Trust A",
                "encounters": 12,
                "tokens": 1200,
                "ourCostUsd": 1.25,
                "limit": 10,
            }
        ],
        azure_gbp=12.5,
    )
    assert "Trust A" in body
    assert "12" in body
    assert "1200" in body
    assert "$1.2500" in body
    assert "12/10" in body
    assert "billable" not in body.lower()
    assert "margin" not in body.lower()
    assert "discount" not in body.lower()
    assert "NHS" not in body
    assert "whole-account" in body
    assert "GBP 12.50" in body


def test_not_first_of_month_skips():
    graph = FakeGraph()
    send = MagicMock()
    result = run_monthly_pack(
        graph, today=date(2026, 10, 2), environment="prod", send_mail=send
    )
    assert result["sent"] is False
    send.assert_not_called()


def test_already_sent_is_idempotent(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com")
    graph = FakeGraph()
    graph.sent_months.add("2026-09")
    send = MagicMock()
    result = run_monthly_pack(
        graph, today=date(2026, 10, 1), environment="prod", send_mail=send
    )
    assert result["reason"] == "already-sent"
    send.assert_not_called()


def test_empty_to_env_sends_no_mail(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.delenv("MAIL_ALERTS_TO_ADDRESSES", raising=False)
    graph = FakeGraph()
    send = MagicMock()
    result = run_monthly_pack(
        graph, today=date(2026, 10, 1), environment="prod", send_mail=send
    )
    assert result["sent"] is False
    send.assert_not_called()
