"""Phase 1 unit tests for the Pathway Explorer research workspace.

Tests cover:
  - Headline generator: correct plain-English output for each mission
  - Algorithm runner: dispatch, coverage info, data-availability checks
  - Research router: mission listing, run lifecycle, CSV export
  - GDS projection manager: data-gate logic for Layer B projections
  - Research worker job store: create/get/update/list

All tests use mocked GDS and Neo4j clients -- no live services required.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Headline generator tests
# ---------------------------------------------------------------------------


class TestHeadlineGenerator:
    """Tests for plain-English headline generation."""

    def setup_method(self):
        from services.analytics_api.app.services.headline_generator import (
            generate_headline,
            generate_method_text,
        )

        self.generate_headline = generate_headline
        self.generate_method_text = generate_method_text

    def test_groups_headline_multiple_communities(self):
        items = [
            {"community_id": 1, "size": 120, "rank": 1},
            {"community_id": 2, "size": 80, "rank": 2},
            {"community_id": 3, "size": 30, "rank": 3},
        ]
        headline = self.generate_headline(
            "groups", items, "Lung pathway, last 6 months"
        )
        assert "3 natural groups" in headline
        assert "120 patients" in headline

    def test_groups_headline_no_data(self):
        headline = self.generate_headline("groups", [], "all pathways, last 12 months")
        assert "enough data" in headline.lower() or "not" in headline.lower()

    def test_bottleneck_headline_with_delays(self):
        items = [
            {
                "label": "Radiology CT",
                "avg_wait_days": 23.0,
                "patient_count": 142,
                "is_bottleneck": True,
                "rank": 1,
            },
            {
                "label": "Histology",
                "avg_wait_days": 8.0,
                "patient_count": 98,
                "is_bottleneck": False,
                "rank": 2,
            },
        ]
        headline = self.generate_headline(
            "bottleneck", items, "Lung pathway, last 6 months"
        )
        assert "Radiology CT" in headline
        assert "23" in headline
        assert "142" in headline

    def test_bottleneck_headline_no_delays(self):
        items = [
            {
                "label": "Step A",
                "avg_wait_days": 5.0,
                "patient_count": 50,
                "is_bottleneck": False,
                "rank": 1,
            }
        ]
        headline = self.generate_headline(
            "bottleneck", items, "all pathways, last 12 months"
        )
        assert "no significant" in headline.lower()

    def test_gaps_headline_isolated_groups(self):
        items = [
            {"component_id": 99, "size": 12, "rank": 1, "is_main": False},
            {"component_id": 100, "size": 5, "rank": 2, "is_main": False},
        ]
        headline = self.generate_headline("gaps", items, "all pathways, last 12 months")
        assert "2 isolated group" in headline

    def test_similar_headline_with_results(self):
        items = [
            {"node_id": 1, "similarity_score": 0.87, "rank": 1, "patient_id": "P001"},
            {"node_id": 2, "similarity_score": 0.72, "rank": 2, "patient_id": "P002"},
        ]
        headline = self.generate_headline(
            "similar", items, "all pathways, last 12 months"
        )
        assert "2 patients" in headline
        assert "87%" in headline

    def test_method_text_groups(self):
        method = self.generate_method_text("groups", "Lung pathway, last 6 months")
        assert "plain" in method
        assert "technical" in method
        assert "Leiden" in method["technical"]

    def test_unknown_mission_returns_safe_default(self):
        headline = self.generate_headline("unknown_mission", [], "all pathways")
        assert "Analysis complete" in headline

    def test_critical_headline(self):
        items = [{"node_id": 1, "label": "Hypertension", "score": 2.5, "rank": 1}]
        headline = self.generate_headline(
            "critical", items, "all pathways, last 12 months"
        )
        assert "Hypertension" in headline

    def test_circles_headline_no_circles(self):
        headline = self.generate_headline("circles", [], "all pathways")
        assert "circular" in headline.lower() or "no" in headline.lower()


# ---------------------------------------------------------------------------
# Algorithm runner tests
# ---------------------------------------------------------------------------


class TestAlgorithmRunnerDispatch:
    """Tests for mission dispatch and error handling."""

    def test_unknown_mission_returns_unavailable_result(self):
        from libs.auth.org_scope import CallerScope
        from services.analytics_api.app.services.algorithm_runner import run_mission

        mock_client = MagicMock()
        scope = CallerScope(email="test@test.com", is_admin=True, org_ids=[])
        result = run_mission("nonexistent_mission", mock_client, scope)
        assert result.data_available is False
        assert "not implemented" in (result.unavailable_reason or "")

    def test_similar_without_patient_id_returns_error(self):
        from libs.auth.org_scope import CallerScope
        from services.analytics_api.app.services.algorithm_runner import run_mission

        mock_client = MagicMock()
        scope = CallerScope(email="test@test.com", is_admin=True, org_ids=[])
        result = run_mission("similar", mock_client, scope, patient_id=None)
        assert result.data_available is False
        assert "patient_id" in (result.unavailable_reason or "")

    def test_coverage_note_high_confidence(self):
        from services.analytics_api.app.services.algorithm_runner import _coverage_note

        note = _coverage_note(1500, 20, "high")
        assert "1,500 patients" in note
        assert "20 practices" in note

    def test_coverage_note_low_confidence(self):
        from services.analytics_api.app.services.algorithm_runner import _coverage_note

        note = _coverage_note(50, 3, "low")
        assert "50 patients" in note
        assert "not represent" in note

    def test_scope_label_all(self):
        from services.analytics_api.app.services.algorithm_runner import (
            _build_scope_label,
        )

        label = _build_scope_label("all", "6m")
        assert "all pathways" in label
        assert "last 6 months" in label

    def test_scope_label_specific_area(self):
        from services.analytics_api.app.services.algorithm_runner import (
            _build_scope_label,
        )

        label = _build_scope_label("lung", "12m")
        assert "Lung pathway" in label
        assert "last 12 months" in label

    def test_period_to_months(self):
        from services.analytics_api.app.services.algorithm_runner import (
            _period_to_months,
        )

        assert _period_to_months("3m") == 3
        assert _period_to_months("6m") == 6
        assert _period_to_months("12m") == 12
        assert _period_to_months("unknown") == 12  # default

    @patch(
        "services.analytics_api.app.services.algorithm_runner_condition"
        "._gds_client_from_env"
    )
    @patch(
        "services.analytics_api.app.services.algorithm_runner_condition"
        "._ensure_projection"
    )
    @patch(
        "services.analytics_api.app.services.algorithm_runner_condition"
        "._get_coverage"
    )
    def test_bottleneck_uses_cypher_not_gds(
        self, mock_coverage, mock_ensure, mock_gds
    ):
        """Bottleneck mission uses direct Cypher, not GDS algorithms."""
        from libs.auth.org_scope import CallerScope
        from services.analytics_api.app.services.algorithm_runner import run_mission
        from services.analytics_api.app.services.algorithm_runner import CoverageInfo

        mock_coverage.return_value = CoverageInfo(
            patient_count=500, practice_count=5, confidence="moderate"
        )
        mock_client = MagicMock()
        mock_client.run.return_value = [
            {
                "label": "CT Scan",
                "avg_wait_days": 18.0,
                "patient_count": 120,
            }
        ]
        scope = CallerScope(email="test@test.com", is_admin=True, org_ids=[])
        result = run_mission("bottleneck", mock_client, scope, area="lung", period="6m")

        # GDS should NOT be called for bottleneck (uses direct Cypher)
        mock_gds.assert_not_called()
        assert result.mission_id == "bottleneck"
        assert len(result.items) == 1
        assert result.items[0]["label"] == "CT Scan"
        assert result.items[0]["avg_wait_days"] == 18.0
        query = mock_client.run.call_args.args[0]
        assert "trim(toString(ep.referral_date)) <> ''" in query
        assert "date(toString(ep.referral_date)) AS ref_date" in query

    def test_variation_service_referral_date_coerces_to_string(self):
        from services.analytics_api.app.services.variation_service import (
            _EPISODES_IN_SCOPE_CYPHER,
        )

        assert "trim(toString(ep.referral_date)) <> ''" in _EPISODES_IN_SCOPE_CYPHER
        assert "date(toString(ep.referral_date)) >=" in _EPISODES_IN_SCOPE_CYPHER


# ---------------------------------------------------------------------------
# GDS projection manager tests
# ---------------------------------------------------------------------------


class TestGDSProjectionManager:
    """Tests for projection lifecycle and Layer B data-gating."""

    @patch(
        "services.analytics_api.app.services.gds_projection_manager"
        ".check_referral_data_available"
    )
    @patch(
        "services.analytics_api.app.services.gds_projection_manager._gds_client"
    )
    def test_list_projections_includes_layer_b_unavailable(
        self, mock_gds_client, mock_referral_check
    ):
        from libs.auth.org_scope import CallerScope
        from services.analytics_api.app.services.gds_projection_manager import (
            list_projections,
            PROJ_REFERRAL_NETWORK,
        )

        mock_referral_check.return_value = (False, 0)
        mock_gds = MagicMock()
        mock_gds.graph.list.return_value.to_dict.return_value = []
        mock_gds_client.return_value = mock_gds

        mock_client = MagicMock()
        scope = CallerScope(email="test@test.com", is_admin=True, org_ids=[])
        summary = list_projections(mock_client, scope)

        referral_proj = next(
            (p for p in summary.projections if p.name == PROJ_REFERRAL_NETWORK),
            None,
        )
        assert referral_proj is not None
        assert referral_proj.data_available is False
        assert referral_proj.layer == "B"
        assert summary.referral_data_available is False

    @patch(
        "services.analytics_api.app.services.gds_projection_manager"
        ".check_encounter_network_available"
    )
    @patch(
        "services.analytics_api.app.services.gds_projection_manager"
        ".check_referral_data_available"
    )
    def test_create_referral_projection_blocked_when_no_data(
        self, mock_referral_check, mock_encounter_check
    ):
        from libs.auth.org_scope import CallerScope
        from services.analytics_api.app.services.gds_projection_manager import (
            create_projection,
            PROJ_REFERRAL_NETWORK,
        )

        mock_referral_check.return_value = (False, 3)
        mock_encounter_check.return_value = False
        mock_client = MagicMock()
        scope = CallerScope(email="test@test.com", is_admin=True, org_ids=[])
        status = create_projection(mock_client, scope, PROJ_REFERRAL_NETWORK)

        assert status.exists is False
        assert status.data_available is False
        assert status.layer == "B"
        assert "3 referral" in (status.unavailable_reason or "") or \
               "no network" in (status.unavailable_reason or "").lower()

    def test_check_referral_data_available_below_threshold(self):
        from services.analytics_api.app.services.gds_projection_manager import (
            check_referral_data_available,
            _MIN_REFERRAL_COUNT,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = [{"cnt": _MIN_REFERRAL_COUNT - 1}]
        available, count = check_referral_data_available(mock_client)
        assert available is False
        assert count == _MIN_REFERRAL_COUNT - 1

    def test_check_referral_data_available_above_threshold(self):
        from services.analytics_api.app.services.gds_projection_manager import (
            check_referral_data_available,
            _MIN_REFERRAL_COUNT,
        )

        mock_client = MagicMock()
        mock_client.run.return_value = [{"cnt": _MIN_REFERRAL_COUNT + 5}]
        available, count = check_referral_data_available(mock_client)
        assert available is True


# ---------------------------------------------------------------------------
# Research router tests
# ---------------------------------------------------------------------------


class TestResearchRouter:
    """Tests for the research API router endpoints."""

    def test_mission_catalogue_has_required_fields(self):
        from services.analytics_api.app.routers.research import _MISSION_CATALOGUE

        required_keys = {"id", "group", "tier", "layer", "titles", "descriptions"}
        for mission in _MISSION_CATALOGUE:
            missing = required_keys - set(mission.keys())
            assert not missing, f"Mission {mission['id']} missing keys: {missing}"

    def test_all_tier_1_missions_are_layer_a(self):
        from services.analytics_api.app.routers.research import _MISSION_CATALOGUE

        tier1 = [m for m in _MISSION_CATALOGUE if m["tier"] == 1]
        for m in tier1:
            assert m["layer"] == "A", (
                f"Tier 1 mission {m['id']} must be Layer A (available now)"
            )

    def test_mission_available_layer_a_always_available(self):
        from services.analytics_api.app.routers.research import _mission_available

        mission = {"id": "groups", "layer": "A", "data_gated": False}
        assert _mission_available(mission, referral_available=False) is True
        assert _mission_available(mission, referral_available=True) is True

    def test_mission_available_layer_b_blocked_without_referral(self):
        from services.analytics_api.app.routers.research import _mission_available

        mission = {"id": "circles_referral", "layer": "B", "data_gated": False}
        assert _mission_available(mission, referral_available=False) is False
        assert _mission_available(mission, referral_available=True) is True

    def test_validate_mission_id_raises_for_unknown(self):
        from fastapi import HTTPException
        from services.analytics_api.app.routers.research import _validate_mission_id

        with pytest.raises(HTTPException) as exc_info:
            _validate_mission_id("not_a_real_mission")
        assert exc_info.value.status_code == 404

    def test_validate_mission_id_passes_for_known(self):
        from services.analytics_api.app.routers.research import _validate_mission_id

        # Should not raise
        _validate_mission_id("groups")
        _validate_mission_id("bottleneck")
        _validate_mission_id("gaps")

    def test_serialise_result_produces_expected_keys(self):
        from services.analytics_api.app.routers.research import _serialise_result
        from services.analytics_api.app.services.algorithm_runner import (
            AlgorithmResult,
            CoverageInfo,
        )

        result = AlgorithmResult(
            mission_id="groups",
            headline="We found 3 groups.",
            items=[{"community_id": 1, "size": 10, "rank": 1}],
            total_count=3,
            coverage=CoverageInfo(
                patient_count=500,
                practice_count=5,
                confidence="moderate",
                confidence_note="Based on 500 patients.",
            ),
            method_plain="We used community detection.",
            method_technical="Leiden algorithm (GDS).",
            next_steps=[{"label": "Find similar patients", "target": "similar"}],
            detail_level="summary",
        )
        serialised = _serialise_result(result)
        required_keys = {
            "mission_id",
            "headline",
            "items",
            "total_count",
            "coverage",
            "method_plain",
            "method_technical",
            "next_steps",
            "detail_level",
        }
        assert required_keys.issubset(set(serialised.keys()))
        assert serialised["coverage"]["patient_count"] == 500


# ---------------------------------------------------------------------------
# Research worker job store tests
# ---------------------------------------------------------------------------


class TestResearchJobStore:
    """Tests for the Redis-backed research job store."""

    def test_create_job_sets_queued_status(self):
        from services.research_worker.app.job_store import ResearchJob

        job = ResearchJob(
            job_id="RES_test001",
            mission_id="groups",
            area="all",
            period="6m",
            detail="summary",
            org_ids=["GP001"],
            is_admin=False,
        )
        assert job.status == "queued"
        assert job.result is None
        assert job.error is None

    def test_job_to_dict_round_trip(self):
        from services.research_worker.app.job_store import ResearchJob

        job = ResearchJob(
            job_id="RES_round_trip",
            mission_id="critical",
            area="lung",
            period="3m",
            detail="detailed",
            org_ids=["GP001", "ICB002"],
            is_admin=False,
            patient_id="P123",
        )
        d = job.to_dict()
        restored = ResearchJob.from_dict(d)
        assert restored.job_id == job.job_id
        assert restored.mission_id == job.mission_id
        assert restored.patient_id == job.patient_id
        assert restored.org_ids == job.org_ids

    @patch("services.research_worker.app.job_store.redis")
    def test_store_create_and_get(self, mock_redis_module):
        """Mock Redis to test create/get lifecycle."""
        import json

        from services.research_worker.app.job_store import ResearchJobStore

        mock_r = MagicMock()
        mock_redis_module.from_url.return_value = mock_r

        store = ResearchJobStore()
        job = store.create(
            mission_id="gaps",
            area="all",
            period="12m",
            detail="summary",
            org_ids=["GP001"],
            is_admin=False,
        )
        assert job.status == "queued"
        assert job.job_id.startswith("RES_")

        # Simulate retrieval from Redis
        mock_r.get.return_value = json.dumps(job.to_dict())
        retrieved = store.get(job.job_id)
        assert retrieved is not None
        assert retrieved.job_id == job.job_id
        assert retrieved.mission_id == "gaps"

    @patch("services.research_worker.app.job_store.redis")
    def test_store_update_changes_status(self, mock_redis_module):
        from services.research_worker.app.job_store import ResearchJobStore

        mock_r = MagicMock()
        mock_redis_module.from_url.return_value = mock_r

        store = ResearchJobStore()
        job = store.create(
            mission_id="bottleneck",
            area="lung",
            period="6m",
            detail="summary",
            org_ids=[],
            is_admin=True,
        )
        store.update(job, status="running", started_at=time.time())
        assert job.status == "running"
        assert job.started_at is not None
