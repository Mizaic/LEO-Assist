"""Integration-style test for run_variation_for_site with a fake client.

Atlas trace: VT-3B37176C -- verifies the end-to-end per-site orchestration
loop and the resulting write paths.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from libs.variation.attribution import AttributionResult
from services.analytics_api.app.services import variation_service


class _FakeClient:
    def __init__(self, rows: List[Dict[str, Any]]):
        self._rows = rows
        self.calls: List[str] = []

    def run(self, cypher: str, **params: Any) -> List[Dict[str, Any]]:
        self.calls.append(cypher)
        return list(self._rows)


def _row(episode_id: str, from_step: str, to_step: str, days: int):
    return {
        "patient_id": "pat-1",
        "episode_id": episode_id,
        "community_id": 42,
        "from_step": from_step,
        "to_step": to_step,
        "from_date": "2026-01-01",
        "interval_days": days,
    }


def test_run_variation_for_site_flags_and_attributes(monkeypatch: pytest.MonkeyPatch):
    rows = [
        _row("ep-slow", "referral", "first_seen", 60),
        _row("ep-slow", "first_seen", "biopsy", 70),
        _row("ep-fast", "referral", "first_seen", 3),
    ]
    fake_client = _FakeClient(rows)

    from libs.variation.cohort_percentiles import MilestonePercentile

    percentiles = [
        MilestonePercentile("referral", "first_seen", 5.0, 10.0, 20.0, 50),
        MilestonePercentile("first_seen", "biopsy", 10.0, 20.0, 40.0, 50),
    ]

    written_results: List[Any] = []
    written_attrib: List[Any] = []

    def fake_pct(client, community_id, scope, months):
        return percentiles

    def fake_write_variation(client, result):
        written_results.append(result)

    def fake_attribute(client, patient_id, first_divergence):
        return AttributionResult(
            node_type="GPPractice",
            node_id="gp-9",
            node_name="Acme Surgery",
            edge_weight=7.0,
        )

    def fake_write_attrib(client, episode_id, attribution):
        written_attrib.append((episode_id, attribution))
        return True

    with patch.object(variation_service, "get_milestone_percentiles", fake_pct), \
        patch.object(variation_service, "write_variation_result", fake_write_variation), \
        patch.object(variation_service, "attribute_root_cause", fake_attribute), \
        patch.object(variation_service, "write_attribution_result", fake_write_attrib):
        summary = variation_service.run_variation_for_site(
            client=fake_client,
            scope=None,
            months=24,
            min_sample_size=1,
        )

    assert summary.episodes_considered == 2
    assert summary.episodes_scored == 2
    assert summary.episodes_flagged == 1
    assert summary.episodes_attributed == 1

    flagged = [r for r in written_results if r.variation_flag]
    assert len(flagged) == 1
    assert flagged[0].episode_id == "ep-slow"
    assert written_attrib[0][0] == "ep-slow"


def test_run_variation_for_site_empty_returns_zero_summary():
    fake_client = _FakeClient([])

    summary = variation_service.run_variation_for_site(
        client=fake_client,
        scope=None,
        months=24,
    )

    assert summary.episodes_considered == 0
    assert summary.episodes_scored == 0
    assert summary.episodes_flagged == 0
    assert summary.episodes_attributed == 0
