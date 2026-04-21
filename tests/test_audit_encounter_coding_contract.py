"""Contract tests for the Loop 1 automated audit script.

These tests pin the CLI surface, deterministic run-id scheme, default
cost cap, encounter-text admin classifier, date-window computation,
AuditRun/DriftMetric Cypher contracts, and the immutability guard
behaviour described in DI-769B453A. They run in <2s and never invoke
Neo4j or Bedrock.

Atlas trace:
  VT: VT-D4BFB2F4 (Loop 1 Automated Audit Execution Verification)
  DI: DI-769B453A
  DOs: DO-1313E92D, DO-E3885491
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

import scripts.investigations.audit_encounter_coding as audit


def _build_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "preflight_only": False,
        "yes": True,
        "tier": "big",
        "cancer_only": False,
        "patient": None,
        "workers": 5,
        "skip_discovery": False,
        "report_only": False,
        "since_days": 7,
        "since": None,
        "until": None,
        "triggered_by": "schedule",
        "skip_neo4j_write": False,
        "cost_cap": 100.0,
        "limit": None,
        "output": "/tmp/audit_test",
        "kg_writeback": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestCliArgumentSurface:
    """AC-1: --since-days flag, AC-7: --cost-cap default $100, etc."""

    def _parse(self, argv: list[str]) -> argparse.Namespace:
        import sys

        old_argv = sys.argv
        sys.argv = ["audit_encounter_coding.py", *argv]
        try:
            return audit._parse_args()
        finally:
            sys.argv = old_argv

    def test_since_days_default_is_seven(self):
        args = self._parse([])
        assert args.since_days == 7

    def test_since_days_overridable(self):
        args = self._parse(["--since-days", "14"])
        assert args.since_days == 14

    def test_explicit_since_overrides_window(self):
        args = self._parse(["--since", "2026-01-01"])
        assert args.since == "2026-01-01"

    def test_cost_cap_default_is_one_hundred_usd(self):
        args = self._parse([])
        assert args.cost_cap == 100.0

    def test_triggered_by_supports_schedule_manual_validation(self):
        for v in ("schedule", "manual", "validation"):
            args = self._parse(["--triggered-by", v])
            assert args.triggered_by == v

    def test_triggered_by_default_is_manual(self):
        args = self._parse([])
        assert args.triggered_by == "manual"

    def test_workers_default_is_five(self):
        args = self._parse([])
        assert args.workers == 5

    def test_yes_skip_discovery_report_only_kg_writeback_are_flags(self):
        args = self._parse([
            "--yes",
            "--skip-discovery",
            "--report-only",
            "--kg-writeback",
            "--skip-neo4j-write",
        ])
        assert args.yes is True
        assert args.skip_discovery is True
        assert args.report_only is True
        assert args.kg_writeback is True
        assert args.skip_neo4j_write is True


class TestDateWindowComputation:
    """--since-days N maps to today - N days; --since/--until override."""

    def test_since_days_yields_today_minus_n(self):
        args = _build_args(since_days=7)
        since, until = audit._compute_date_window(args)
        expected = (date.today() - timedelta(days=7)).isoformat()
        assert since == expected
        assert until == date.today().isoformat()

    def test_explicit_since_overrides_since_days(self):
        args = _build_args(since_days=999, since="2026-01-01")
        since, _ = audit._compute_date_window(args)
        assert since == "2026-01-01"

    def test_explicit_until_used_when_provided(self):
        args = _build_args(until="2026-03-15")
        _, until = audit._compute_date_window(args)
        assert until == "2026-03-15"


class TestDeterministicRunId:
    """AC-2: deterministic run_id for scheduled, UUID for manual."""

    def test_scheduled_run_id_matches_iso_year_week(self):
        run_id = audit.make_run_id("schedule", "2026-04-13")
        iso_year, iso_week, _ = date(2026, 4, 13).isocalendar()
        assert run_id == f"audit-{iso_year}-W{iso_week:02d}"

    def test_scheduled_run_id_is_deterministic(self):
        a = audit.make_run_id("schedule", "2026-04-13")
        b = audit.make_run_id("schedule", "2026-04-13")
        assert a == b

    def test_manual_run_id_is_unique(self):
        a = audit.make_run_id("manual", "2026-04-13")
        b = audit.make_run_id("manual", "2026-04-13")
        assert a != b
        assert a.startswith("audit-manual-")
        assert b.startswith("audit-manual-")


class TestImmutabilityGuard:
    """AC-3: completed AuditRun cannot be overwritten."""

    def _client(self, responses: list[list[dict]]) -> MagicMock:
        client = MagicMock()
        client.run = MagicMock(side_effect=responses)
        return client

    def test_returns_run_id_when_no_existing_node(self):
        client = self._client([[]])
        out = audit._resolve_run_id(client, "audit-2026-W15")
        assert out == "audit-2026-W15"

    def test_returns_run_id_when_existing_node_is_running(self):
        client = self._client([[{"status": "running"}]])
        out = audit._resolve_run_id(client, "audit-2026-W15")
        assert out == "audit-2026-W15"

    def test_returns_run_id_when_existing_node_is_failed(self):
        client = self._client([[{"status": "failed"}]])
        out = audit._resolve_run_id(client, "audit-2026-W15")
        assert out == "audit-2026-W15"

    def test_completed_run_id_gets_retry_suffix(self):
        client = self._client([
            [{"status": "complete"}],
            [],
        ])
        out = audit._resolve_run_id(client, "audit-2026-W15")
        assert out == "audit-2026-W15-retry-1"

    def test_completed_retry_chain_finds_next_available(self):
        client = self._client([
            [{"status": "complete"}],
            [{"status": "complete"}],
            [{"status": "complete"}],
            [],
        ])
        out = audit._resolve_run_id(client, "audit-2026-W15")
        assert out == "audit-2026-W15-retry-3"


class TestAdminOnlyClassifier:
    """The script skips LLM calls on clearly non-clinical text."""

    def test_short_admin_pattern_text_is_skipped(self):
        text = "Receptionist note: appointment confirmation for Monday."
        assert audit._is_admin_only(text) is True

    def test_short_text_with_no_clinical_keyword_is_skipped(self):
        assert audit._is_admin_only("Hi.") is True

    def test_clinical_text_is_not_skipped(self):
        text = (
            "Patient presents with cough and fever. Examination of chest "
            "revealed crackles. Plan: review in one week, antibiotics if "
            "no improvement."
        )
        assert audit._is_admin_only(text) is False

    def test_long_admin_pattern_text_is_not_blanket_skipped(self):
        text = "Receptionist note. " + ("Some content. " * 200)
        assert audit._is_admin_only(text) is False


class TestAuditRunCypherContract:
    """AC-4: AuditRun records expose the eight required fields."""

    def test_audit_run_query_uses_required_parameters(self):
        q = audit._Q_CREATE_AUDIT_RUN
        for field in (
            "run_id",
            "triggered_by",
            "since_date",
            "until_date",
            "encounter_count",
            "pct_clean",
            "critical_count",
            "auditor_model_version",
            "cost_usd",
        ):
            assert f"${field}" in q, f"missing parameter ${field}"

    def test_audit_run_query_records_status(self):
        assert "status" in audit._Q_CREATE_AUDIT_RUN

    def test_check_audit_run_query_uses_run_id(self):
        assert "$run_id" in audit._Q_CHECK_AUDIT_RUN


class TestDriftMetricCypherContract:
    """AC-5: DriftMetric exposes pct_clean, per-domain JSON, counts."""

    def test_drift_metric_query_uses_required_parameters(self):
        q = audit._Q_CREATE_DRIFT_METRIC
        for field in (
            "metric_id",
            "run_id",
            "week_start",
            "pct_clean",
            "pct_clean_by_domain",
            "critical_count",
            "high_count",
            "overcoded_count",
            "auditor_model_version",
            "model_version_changed",
        ):
            assert f"${field}" in q, f"missing parameter ${field}"

    def test_drift_metric_query_records_metric_type_audit(self):
        assert "audit" in audit._Q_CREATE_DRIFT_METRIC.lower()


class TestKgWritebackGuard:
    """The --kg-writeback path is gated by an environment toggle."""

    def test_coding_agent_enabled_constant_exists(self):
        assert isinstance(audit._CODING_AGENT_ENABLED, bool)


class TestModuleSurface:
    """The module exposes the public functions referenced by DO-1313E92D."""

    @pytest.mark.parametrize(
        "name",
        [
            "main",
            "make_run_id",
            "_resolve_run_id",
            "_compute_date_window",
            "run_preflight",
            "run_discovery",
            "run_coding_audit",
            "run_llm_gap_resolution",
            "generate_reports",
            "_write_audit_results_to_neo4j",
        ],
    )
    def test_public_function_exists(self, name: str):
        assert callable(getattr(audit, name)), f"{name} missing or not callable"
