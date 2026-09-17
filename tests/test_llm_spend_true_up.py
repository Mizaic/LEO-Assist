"""Daily Azure AI spend check -- acceptance verification.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.llm_spend_true_up.alerts import maybe_send_alert, parse_alert_recipients
from libs.llm_spend_true_up.compare import classify_status, drift_ratio
from libs.llm_spend_true_up.queries import (
    LIST_AUDIT_EVENT_IDS,
    SUM_OUR_LLM_SPEND,
    UPSERT_TRUE_UP,
)
from libs.llm_spend_true_up.run_job import run_daily_true_up


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.our_row = {
            "input_tokens": 2_000_000,
            "output_tokens": 100_000,
            "cached_tokens": 0,
            "cost_usd": 2.11,
        }
        self.audit_ids = [{"id": "ae-patient-1"}]
        self.raise_on: str | None = None

    def run(self, query: str, **params):
        self.calls.append((query, params))
        if self.raise_on and self.raise_on in query:
            raise RuntimeError("graph down")
        if query == SUM_OUR_LLM_SPEND:
            return [self.our_row]
        if query == LIST_AUDIT_EVENT_IDS:
            return list(self.audit_ids)
        return [{"ok": True}]


def _day_window():
    return "2026-09-16", "prod"


def test_stored_check_keeps_our_two_million_tokens():
    graph = FakeGraph()
    snap = run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 2_000_000,
            "completion_tokens": 100_000,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 2.11, "provisional": False},
        gbp_usd=1.0,
        send_mail=MagicMock(),
    )
    assert snap["our_input_tokens"] == 2_000_000
    upsert = [p for q, p in graph.calls if q == UPSERT_TRUE_UP]
    assert upsert[0]["our_input_tokens"] == 2_000_000


def test_token_drift_fifty_percent_is_warn():
    graph = FakeGraph()
    graph.our_row["output_tokens"] = 0
    snap = run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 3_000_000,
            "completion_tokens": 0,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 2.11, "provisional": False},
        gbp_usd=1.0,
        send_mail=MagicMock(),
        token_warn=0.15,
        cost_warn=0.25,
    )
    assert snap["token_drift"] == pytest.approx(0.5)
    assert snap["status"] == "warn"


def test_cost_figures_are_stored_and_drift_computed():
    graph = FakeGraph()
    snap = run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 2_000_000,
            "completion_tokens": 100_000,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 2.61, "provisional": False},
        gbp_usd=1.0,
        send_mail=MagicMock(),
    )
    assert snap["azure_cost_gbp"] == pytest.approx(2.61)
    assert snap["our_cost_usd"] == pytest.approx(2.11)
    assert snap["cost_drift"] == pytest.approx(abs(2.61 - 2.11) / 2.11)


def test_empty_azure_cost_is_provisional_not_zero():
    graph = FakeGraph()
    snap = run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 2_000_000,
            "completion_tokens": 0,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": None, "provisional": True},
        gbp_usd=1.0,
        send_mail=MagicMock(),
    )
    assert snap["cost_provisional"] is True
    assert snap["azure_cost_gbp"] is None
    assert snap["status"] != "failed"


def test_failed_azure_does_not_look_like_a_match():
    graph = FakeGraph()

    def boom(*_a, **_k):
        raise RuntimeError("azure down")

    snap = run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=boom,
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 0.0, "provisional": False},
        gbp_usd=1.0,
        send_mail=MagicMock(),
    )
    assert snap["status"] == "failed"
    assert snap.get("token_drift") is None


def test_patient_audit_event_is_not_updated():
    graph = FakeGraph()
    run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 1,
            "completion_tokens": 1,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 1.0, "provisional": False},
        gbp_usd=1.0,
        send_mail=MagicMock(),
    )
    assert LIST_AUDIT_EVENT_IDS in [q for q, _p in graph.calls]
    assert any(q == UPSERT_TRUE_UP for q, _p in graph.calls)
    assert all("SET ae." not in q for q, _p in graph.calls)


def test_ten_percent_token_drift_sends_no_email(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com")
    send = MagicMock()
    graph = FakeGraph()
    graph.our_row["input_tokens"] = 1000
    graph.our_row["output_tokens"] = 0
    run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 1100,
            "completion_tokens": 0,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 2.11, "provisional": False},
        gbp_usd=1.0,
        send_mail=send,
        token_warn=0.15,
        cost_warn=0.25,
    )
    send.assert_not_called()


def test_twenty_percent_token_drift_sends_email(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com,fin@mizaic.com")
    send = MagicMock()
    graph = FakeGraph()
    graph.our_row["input_tokens"] = 1000
    graph.our_row["output_tokens"] = 0
    run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 1200,
            "completion_tokens": 0,
        },
        fetch_azure_cost=lambda *_a, **_k: {"cost_gbp": 2.11, "provisional": False},
        gbp_usd=1.0,
        send_mail=send,
        token_warn=0.15,
        cost_warn=0.25,
    )
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["from_address"] == "leo.alerts@mizaic.com"
    assert kwargs["to_addresses"] == ["ops@mizaic.com", "fin@mizaic.com"]
    assert (
        "do not match" in kwargs["subject"].lower()
        or "token" in kwargs["subject"].lower()
    )


def test_empty_alert_env_sends_no_mail(monkeypatch):
    monkeypatch.delenv("MAIL_ALERTS_FROM_ADDRESS", raising=False)
    monkeypatch.delenv("MAIL_ALERTS_TO_ADDRESSES", raising=False)
    sent = maybe_send_alert("subj", "body", send_mail=MagicMock())
    assert sent is False


def test_cost_drift_over_limit_sends_email(monkeypatch):
    monkeypatch.setenv("MAIL_ALERTS_FROM_ADDRESS", "leo.alerts@mizaic.com")
    monkeypatch.setenv("MAIL_ALERTS_TO_ADDRESSES", "ops@mizaic.com")
    send = MagicMock()
    graph = FakeGraph()
    run_daily_true_up(
        graph,
        day="2026-09-16",
        environment="prod",
        fetch_azure_tokens=lambda *_a, **_k: {
            "prompt_tokens": 2_000_000,
            "completion_tokens": 100_000,
        },
        fetch_azure_cost=lambda *_a, **_k: {
            "cost_gbp": 2.11 * 1.30,
            "provisional": False,
        },
        gbp_usd=1.0,
        send_mail=send,
        token_warn=0.15,
        cost_warn=0.25,
    )
    send.assert_called_once()
    assert "cost" in send.call_args.kwargs["subject"].lower()


def test_drift_ratio_and_status_helpers():
    assert drift_ratio(100, 110) == pytest.approx(0.1)
    assert classify_status(0.1, 0.1, provisional=False, failed=False) == "ok"
    assert (
        classify_status(0.2, 0.0, provisional=False, failed=False, token_warn=0.15)
        == "warn"
    )
    assert classify_status(0.0, 0.0, provisional=False, failed=True) == "failed"


def test_parse_recipients():
    assert parse_alert_recipients(" a@x.com, b@y.com ") == ["a@x.com", "b@y.com"]
    assert parse_alert_recipients("") == []
