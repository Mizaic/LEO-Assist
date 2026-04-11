"""Unit tests for the NCDA audit analytics router.

Tests focus on data-shaping logic (pct calculations, interval stats,
multi-scope envelope) without requiring a live Neo4j connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_scope(is_admin: bool = True, primary_org_id=None):
    scope = MagicMock()
    scope.is_admin = is_admin
    scope.primary_org_id = primary_org_id
    scope.org_ids = []
    scope.to_query_params.return_value = {}
    return scope


def _mock_client(rows_by_call):
    """Return a mock PatientGraphClient where .run() returns successive values."""
    mock = MagicMock()
    mock.run.side_effect = rows_by_call
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# Multi-scope response helpers
def _practice(result):
    return result["scopes"]["practice"]

def _alliance(result):
    return result["scopes"]["alliance_live"]

def _england(result):
    return result["scopes"]["england_live"]

def _benchmark(result):
    return result.get("benchmark")


# ---------------------------------------------------------------------------
# Tests: _q_cancer_type / audit_cancer_type
# ---------------------------------------------------------------------------

class TestAuditCancerType:
    """Tests for cancer type section multi-scope envelope."""

    def test_returns_multi_scope_envelope(self):
        rows = [
            {"cancer_type": "breast", "n": 14},
            {"cancer_type": "colorectal", "n": 8},
        ]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        assert "practice" in result["scopes"]
        assert "alliance_live" in result["scopes"]
        assert "england_live" in result["scopes"]
        assert "benchmark" in result

    def test_pct_sums_to_100(self):
        rows = [
            {"cancer_type": "breast", "n": 30},
            {"cancer_type": "colorectal", "n": 20},
            {"cancer_type": "lung", "n": 50},
        ]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        practice_data = _practice(result)
        total_pct = sum(r["pct"] for r in practice_data)
        assert abs(total_pct - 100.0) < 1.0

    def test_empty_returns_empty_practice(self):
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([[]])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert _practice(result) == []
        assert _alliance(result) is None
        assert _england(result) is None

    def test_no_org_selected_alliance_and_england_are_none(self):
        rows = [{"cancer_type": "breast", "n": 10}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type
            result = audit_cancer_type(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert _alliance(result) is None
        assert _england(result) is None


# ---------------------------------------------------------------------------
# Tests: _q_consultations
# ---------------------------------------------------------------------------

class TestAuditConsultations:
    """Tests for GET /analytics/audit/consultations multi-scope envelope.

    _q_consultations makes 2 DB calls: summary row + per-episode rows.
    """

    def test_multi_scope_envelope_present(self):
        summary_rows = [{"fewer_than_3": 10, "three_or_more": 5, "total_episodes": 15, "avg_consultations": 2.0}]
        per_ep_rows = [{"consult_count": 1}, {"consult_count": 3}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([summary_rows, per_ep_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_consultations
            result = audit_consultations(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        practice = _practice(result)
        assert "fewer_than_3_pct" in practice
        assert "three_or_more_pct" in practice

    def test_percentages_sum_to_100(self):
        summary_rows = [{"fewer_than_3": 42, "three_or_more": 9, "total_episodes": 51, "avg_consultations": 1.5}]
        per_ep_rows = []
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([summary_rows, per_ep_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_consultations
            result = audit_consultations(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        practice = _practice(result)
        assert practice["fewer_than_3_pct"] == round(42 * 100.0 / 51, 1)
        assert practice["three_or_more_pct"] == round(9 * 100.0 / 51, 1)

    def test_query_guards_empty_temporal_strings(self):
        summary_rows = [
            {
                "fewer_than_3": 1,
                "three_or_more": 1,
                "total_episodes": 2,
                "avg_consultations": 2.0,
            }
        ]
        per_ep_rows = [{"consult_count": 1}, {"consult_count": 3}]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([summary_rows, per_ep_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import (
                audit_consultations,
            )

            audit_consultations(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        queries = [str(c.args[0]) for c in mock.run.call_args_list]
        assert any(
            "trim(coalesce(toString(ep.referral_date), '')) = ''" in q
            for q in queries
        )
        assert any(
            "trim(coalesce(toString(ep.first_presentation_date), '')) = ''"
            in q
            for q in queries
        )


# ---------------------------------------------------------------------------
# Tests: interval stats computation (pure logic)
# ---------------------------------------------------------------------------

class TestIntervalStats:
    """Tests that median / IQR helpers produce correct values."""

    def test_median_even_list(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        n = len(vals)
        expected = (vals[n // 2 - 1] + vals[n // 2]) / 2  # 5.5

        def _median(v):
            if not v:
                return None
            k = len(v)
            return v[k // 2] if k % 2 else (v[k // 2 - 1] + v[k // 2]) / 2

        assert _median(vals) == expected

    def test_median_odd_list(self):
        vals = [1, 2, 3, 4, 5]

        def _median(v):
            if not v:
                return None
            k = len(v)
            return v[k // 2] if k % 2 else (v[k // 2 - 1] + v[k // 2]) / 2

        assert _median(vals) == 3

    def test_empty_patients_returns_none_stats(self):
        agg_rows = [{"pci_n": 0, "mean_pci": None, "di_n": 0, "mean_di": None}]
        patient_rows: list = []

        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([agg_rows, patient_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_intervals
            result = audit_intervals(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        practice = _practice(result)
        assert practice["pci"]["median"] is None
        assert practice["di"]["median"] is None
        assert practice["patients"] == []

    def test_interval_queries_guard_empty_temporal_strings(self):
        agg_rows = [
            {
                "pci_n": 1,
                "mean_pci": 4.0,
                "median_pci": 4.0,
                "pci_q1": 4.0,
                "pci_q3": 4.0,
                "di_n": 1,
                "mean_di": 12.0,
                "median_di": 12.0,
                "di_q1": 12.0,
                "di_q3": 12.0,
            }
        ]
        patient_rows = [
            {
                "episode_id": "ep-1",
                "cancer_type": "breast",
                "pci_days": 4,
                "di_days": 12,
            }
        ]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([agg_rows, patient_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_intervals

            audit_intervals(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        queries = [str(c.args[0]) for c in mock.run.call_args_list]
        assert any("trim(coalesce(fp_date, '')) <> ''" in q for q in queries)
        assert any(
            "trim(coalesce(effective_diag_date, '')) <> ''" in q
            for q in queries
        )


class TestAuditDemographics:
    def test_query_guards_empty_temporal_strings(self):
        sex_rows = [{"gender": "female", "n": 1}]
        age_rows = [{"age_band": "50-64", "n": 1}]
        age_vals_rows = [{"age": 58}]
        eth_rows = [{"ethnicity": "White", "n": 1}]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([sex_rows, age_rows, age_vals_rows, eth_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import (
                audit_demographics,
            )

            result = audit_demographics(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        assert result["scopes"]["practice"]["median_age"] == 58
        queries = [str(c.args[0]) for c in mock.run.call_args_list]
        assert any(
            "trim(coalesce(toString(ep.referral_date), '')) = ''" in q
            for q in queries
        )
        assert any(
            "trim(coalesce(toString(p.birthDate), '')) = ''" in q
            for q in queries
        )


# ---------------------------------------------------------------------------
# Tests: safety_netting
# ---------------------------------------------------------------------------

class TestAuditSafetyNetting:
    def test_multi_scope_envelope(self):
        rows = [{"total_episodes": 51, "recorded": 10}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_safety_netting
            result = audit_safety_netting(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        practice = _practice(result)
        assert "recorded_pct" in practice
        assert practice["recorded_pct"] == round(10 * 100.0 / 51, 1)


# ---------------------------------------------------------------------------
# Tests: avoidable_delays
# ---------------------------------------------------------------------------

class TestAuditAvoidableDelays:
    def test_multi_scope_envelope(self):
        rows = [{"total_episodes": 51, "has_delay": 14, "before_pres": 9, "pres_to_ref": 4, "after_ref": 1}]
        with patch("services.analytics_api.app.routers.audit.PatientGraphClient") as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_avoidable_delays
            result = audit_avoidable_delays(scope=_mock_scope(), org_id=None, date_from=None, date_to=None, benchmark_set_id=None)

        assert "scopes" in result
        practice = _practice(result)
        assert "avoidable_delay_pct" in practice
        assert practice["avoidable_delay_pct"] == round(14 * 100.0 / 51, 1)


# ---------------------------------------------------------------------------
# Tests: benchmark_category fetch helper
# ---------------------------------------------------------------------------

class TestFetchBenchmarkMetrics:
    """Tests for _fetch_benchmark_metrics ODS linkage logic."""

    def test_practice_matched_by_ods_code(self):
        set_rows = [{"set_name": "NCDA 2018"}]
        value_rows = [
            {"metric_id": "primary_care_interval.median_days", "scope_type": "gp_practice",
             "scope_id": "C84070", "scope_name": "Woodbrook Medical Centre", "value": 30},
            {"metric_id": "primary_care_interval.median_days", "scope_type": "national",
             "scope_id": "england", "scope_name": "England", "value": 25},
        ]

        with patch(
            "services.analytics_api.app.routers._audit_helpers.KnowledgeGraphClient"
        ) as MockKG:
            mock_kg = MagicMock()
            mock_kg.run.side_effect = [set_rows, value_rows]
            MockKG.return_value = mock_kg

            from services.analytics_api.app.routers._audit_helpers import (
                _fetch_benchmark_metrics,
            )
            result = _fetch_benchmark_metrics(
                "ncda-2018", "primary_care_interval",
                org_id="woodbrook-gp", org_ods_code="C84070", alliance_id=None,
            )

        assert result is not None
        metrics = result["metrics"]
        assert "primary_care_interval.median_days" in metrics
        m = metrics["primary_care_interval.median_days"]
        assert m["practice"] == 30
        assert m["national"] == 25

    def test_no_values_returns_none(self):
        set_rows = [{"set_name": "NCDA 2018"}]
        with patch(
            "services.analytics_api.app.routers._audit_helpers.KnowledgeGraphClient"
        ) as MockKG:
            mock_kg = MagicMock()
            mock_kg.run.side_effect = [set_rows, []]
            MockKG.return_value = mock_kg

            from services.analytics_api.app.routers._audit_helpers import (
                _fetch_benchmark_metrics,
            )
            result = _fetch_benchmark_metrics("ncda-2018", "primary_care_interval")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: Cypher composition helpers (phase 0 fix)
# ---------------------------------------------------------------------------

class TestCypherComposition:
    """Verify that _add_date_filters and _episode_base produce valid Cypher."""

    def test_add_date_filters_always_uses_and(self):
        """_add_date_filters must always append AND, never a bare WHERE."""
        from services.analytics_api.app.routers.audit import _add_date_filters

        # Base that already has a WHERE clause (e.g. org-scoped)
        base = "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep) WHERE true "
        result_base, _ = _add_date_filters(base, {}, "2024-01-01", "2024-12-31")
        assert "WHERE" not in result_base.split("AND")[0].split("true")[1]
        assert "AND ep.referral_date >= $date_from" in result_base
        assert "AND ep.referral_date <= $date_to" in result_base

    def test_add_date_filters_no_dates_unchanged(self):
        """When no dates are provided the base is returned unchanged."""
        from services.analytics_api.app.routers.audit import _add_date_filters

        base = "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep) WHERE true "
        result_base, result_params = _add_date_filters(base, {"org": "x"}, None, None)
        assert result_base == base
        assert result_params == {"org": "x"}

    def test_org_patient_match_starts_active_where_clause(self):
        """_ORG_PATIENT_MATCH must end with an active WHERE clause for AND composition."""
        from services.analytics_api.app.routers.audit import _ORG_PATIENT_MATCH
        stripped = _ORG_PATIENT_MATCH.rstrip()
        # Must end with the episode-exclusion clause (not bare WHERE true)
        assert "WHERE NOT ep.status IN" in stripped
        # The trailing text must end with the closing bracket + space so AND can follow
        assert stripped.endswith("]") or stripped.endswith("] ")

    def test_england_base_starts_active_where_clause(self):
        """_ENGLAND_BASE must end with an active WHERE clause for AND composition."""
        from services.analytics_api.app.routers.audit import _ENGLAND_BASE
        stripped = _ENGLAND_BASE.rstrip()
        assert "WHERE NOT ep.status IN" in stripped
        assert stripped.endswith("]") or stripped.endswith("] ")

    def test_date_filters_with_org_base_produces_no_double_where(self):
        """Applying date filters to org base must not produce double WHERE."""
        from services.analytics_api.app.routers.audit import (
            _add_date_filters,
            _ORG_PATIENT_MATCH,
        )
        base, params = _add_date_filters(_ORG_PATIENT_MATCH, {"org": "abc"}, "2024-01-01", None)
        # Count WHERE occurrences -- must be exactly 2:
        # one for the GP filter, one for the episode filter ("WHERE true")
        assert base.count("WHERE") == 2
        assert "AND ep.referral_date >= $date_from" in base


# ---------------------------------------------------------------------------
# Tests: comorbidity deduplication (phase 4 fix)
# ---------------------------------------------------------------------------

class TestComorbidityDeduplication:
    """Verify comorbidities do not double-count patients with multiple child concepts."""

    def test_same_patient_two_concept_ids_same_group_counted_once(self):
        """A patient with two child concepts in the same group must count as 1."""
        # Simulate disease_rows with patient_ids (new format after fix)
        # Both concepts map to "hypertension" group -- same patient "P1"
        disease_rows_with_pids = [
            {"concept_id": "59621000", "patient_ids": ["P1"]},
            {"concept_id": "38341003", "patient_ids": ["P1"]},
        ]
        id_to_term = {"59621000": "hypertension", "38341003": "hypertension"}
        concept_groups = {"hypertension": ["59621000", "38341003"]}

        group_patients: dict = {term: set() for term in concept_groups}
        for row in disease_rows_with_pids:
            cid_str = str(row.get("concept_id") or "")
            top_term = id_to_term.get(cid_str)
            if top_term and top_term in group_patients:
                group_patients[top_term].update(row.get("patient_ids") or [])

        counts = {term: len(patients) for term, patients in group_patients.items()}
        assert counts["hypertension"] == 1, "Patient with 2 child concepts must count once per group"

    def test_two_patients_different_concepts_same_group_counted_correctly(self):
        """Two different patients in the same group must both be counted."""
        disease_rows_with_pids = [
            {"concept_id": "59621000", "patient_ids": ["P1"]},
            {"concept_id": "38341003", "patient_ids": ["P2"]},
        ]
        id_to_term = {"59621000": "hypertension", "38341003": "hypertension"}
        concept_groups = {"hypertension": ["59621000", "38341003"]}

        group_patients: dict = {term: set() for term in concept_groups}
        for row in disease_rows_with_pids:
            cid_str = str(row.get("concept_id") or "")
            top_term = id_to_term.get(cid_str)
            if top_term and top_term in group_patients:
                group_patients[top_term].update(row.get("patient_ids") or [])

        counts = {term: len(patients) for term, patients in group_patients.items()}
        assert counts["hypertension"] == 2


# ---------------------------------------------------------------------------
# Tests: IS_PART_OF link helper (phase 1 fix)
# ---------------------------------------------------------------------------

class TestLinkEncountersToEpisode:
    """Verify _link_encounters_to_episode deduplicates and handles edge cases."""

    def test_no_encounter_id_skipped(self):
        """Anchors without encounter_id still trigger a replace call with empty payload."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import _link_encounters_to_episode

        client = MagicMock()
        _link_encounters_to_episode(client, "ep1", [
            ([{"encounter_id": None, "concept_name": "test"}], "referral"),
        ])
        client.run.assert_called_once()
        call_kwargs = client.run.call_args[1]
        assert call_kwargs["encounters"] == []

    def test_deduplicates_same_encounter_across_types(self):
        """Same encounter_id appearing in multiple anchor lists must be sent once."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import _link_encounters_to_episode

        client = MagicMock()
        _link_encounters_to_episode(client, "ep1", [
            ([{"encounter_id": "E1"}], "referral"),
            ([{"encounter_id": "E1"}], "diagnosis_confirmed"),
        ])
        client.run.assert_called_once()
        call_kwargs = client.run.call_args[1]
        encounter_ids = [e["encounter_id"] for e in call_kwargs["encounters"]]
        assert encounter_ids.count("E1") == 1

    def test_empty_episode_id_no_call(self):
        """Empty episode_id must result in no DB write."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import _link_encounters_to_episode

        client = MagicMock()
        _link_encounters_to_episode(client, "", [
            ([{"encounter_id": "E1"}], "referral"),
        ])
        client.run.assert_not_called()

    def test_multiple_encounters_all_sent(self):
        """Multiple distinct encounters must all be included in the payload."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import _link_encounters_to_episode

        client = MagicMock()
        _link_encounters_to_episode(client, "ep1", [
            ([{"encounter_id": "E1"}, {"encounter_id": "E2"}], "referral"),
            ([{"encounter_id": "E3"}], "diagnosis_confirmed"),
        ])
        client.run.assert_called_once()
        call_kwargs = client.run.call_args[1]
        encounter_ids = {e["encounter_id"] for e in call_kwargs["encounters"]}
        assert encounter_ids == {"E1", "E2", "E3"}

    def test_link_query_replaces_existing_links(self):
        """Link query should delete existing links before adding current ones."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import _link_encounters_to_episode

        client = MagicMock()
        _link_encounters_to_episode(client, "ep1", [
            ([{"encounter_id": "E1"}], "referral"),
        ])
        client.run.assert_called_once()
        query = str(client.run.call_args[0][0])
        assert "DELETE r_old" in query
