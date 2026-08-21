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
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type

            result = audit_cancer_type(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

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
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type

            result = audit_cancer_type(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        practice_data = _practice(result)
        total_pct = sum(r["pct"] for r in practice_data)
        assert abs(total_pct - 100.0) < 1.0

    def test_empty_returns_empty_practice(self):
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([[]])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type

            result = audit_cancer_type(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        assert _practice(result) == []
        assert _alliance(result) is None
        assert _england(result) is None

    def test_no_org_selected_alliance_and_england_are_none(self):
        rows = [{"cancer_type": "breast", "n": 10}]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_cancer_type

            result = audit_cancer_type(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        assert _alliance(result) is None
        assert _england(result) is None


# ---------------------------------------------------------------------------
# Tests: _q_consultations  (Haiku-enriched, NCDA-native polarity)
# ---------------------------------------------------------------------------


def _consult_agg_row(
    total: int = 20,
    three_or_more: int = 8,
    fewer_than_3: int = 12,
    enriched: int = 18,
    bucket_zero: int = 2,
    bucket_one: int = 10,
    bucket_two: int = 3,
    bucket_three_four: int = 4,
    bucket_five_seven: int = 2,
    bucket_eight_plus: int = 1,
    total_consultations: int = 60,
    f2f_total: int = 20,
    phone_total: int = 15,
    nurse_total: int = 5,
    email_total: int = 0,
    specialist_clinic_total: int = 10,
    home_visit_total: int = 0,
    phlebotomy_total: int = 8,
    result_review_total: int = 2,
    unrelated_filtered_total: int = 5,
    llm_cost_usd: float = 0.4200,
    llm_input_tokens: int = 200000,
    llm_output_tokens: int = 30000,
    llm_calls: int = 18,
    episodes_raw: list | None = None,
) -> list[dict]:
    """Build the aggregate row returned by the rewritten _q_consultations."""
    if episodes_raw is None:
        episodes_raw = [
            {"n": 0, "factors": [], "cancer_type": "Breast", "episode_id": "ep-a"},
            {"n": 1, "factors": [], "cancer_type": "Breast", "episode_id": "ep-b"},
            {"n": 2, "factors": ["different_initial_diagnosis"], "cancer_type": "Colorectal", "episode_id": "ep-c"},
            {"n": 3, "factors": ["reassurance_from_negative_investigation"], "cancer_type": "Melanoma", "episode_id": "ep-d"},
            {"n": 5, "factors": ["different_initial_diagnosis", "co_morbidity_blurring"], "cancer_type": "Colorectal", "episode_id": "ep-e"},
            {"n": 8, "factors": ["different_initial_diagnosis"], "cancer_type": "Prostate", "episode_id": "ep-f"},
        ]
    return [
        {
            "total_episodes": total,
            "three_or_more": three_or_more,
            "fewer_than_3": fewer_than_3,
            "enriched_n": enriched,
            "bucket_zero": bucket_zero,
            "bucket_one": bucket_one,
            "bucket_two": bucket_two,
            "bucket_three_four": bucket_three_four,
            "bucket_five_seven": bucket_five_seven,
            "bucket_eight_plus": bucket_eight_plus,
            "total_consultations": total_consultations,
            "f2f_total": f2f_total,
            "phone_total": phone_total,
            "nurse_total": nurse_total,
            "email_total": email_total,
            "specialist_clinic_total": specialist_clinic_total,
            "home_visit_total": home_visit_total,
            "phlebotomy_total": phlebotomy_total,
            "result_review_total": result_review_total,
            "unrelated_filtered_total": unrelated_filtered_total,
            "llm_cost_usd": llm_cost_usd,
            "llm_input_tokens": llm_input_tokens,
            "llm_output_tokens": llm_output_tokens,
            "llm_calls": llm_calls,
            "episodes_raw": episodes_raw,
        }
    ]


_CT_ROWS = [
    {"cancer_type": "Breast",     "n_total": 10, "n_three_or_more": 3, "n_enriched": 9, "mean_n": 2.1},
    {"cancer_type": "Colorectal", "n_total": 8,  "n_three_or_more": 4, "n_enriched": 8, "mean_n": 3.2},
]


def _consult_mock(agg_row=None, ct_rows=None):
    """_q_consultations now issues 2 Cypher queries: aggregate + per-CT."""
    return _mock_client([agg_row or _consult_agg_row(), ct_rows if ct_rows is not None else _CT_ROWS])


class TestAuditConsultations:
    """Tests for GET /analytics/audit/consultations multi-scope envelope.

    _q_consultations issues 2 Cypher queries:
      1. Aggregate row (+ inline episodes_raw).
      2. Per-cancer-type breakdown (by_cancer_type_live).
    """

    def test_multi_scope_envelope_present(self):
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _consult_mock()
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_consultations

            result = audit_consultations(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        assert "scopes" in result
        practice = _practice(result)
        assert "three_or_more_pct" in practice
        assert "fewer_than_3_pct" in practice
        assert "buckets" in practice
        assert "top_factors" in practice
        assert "factors_by_cancer_type" in practice
        assert "episode_evidence" in practice

    def test_ncda_native_polarity(self):
        """three_or_more_pct is the primary metric; fewer_than_3_pct is kept."""
        row = _consult_agg_row(total=20, three_or_more=8, fewer_than_3=12)
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            MockClient.return_value = _consult_mock(row)
            from services.analytics_api.app.routers.audit import audit_consultations

            result = audit_consultations(
                scope=_mock_scope(), org_id=None,
                date_from=None, date_to=None, benchmark_set_id=None,
            )

        practice = _practice(result)
        assert practice["three_or_more_pct"] == round(8 * 100.0 / 20, 1)
        assert practice["fewer_than_3_pct"] == round(12 * 100.0 / 20, 1)

    def test_distribution_buckets_present(self):
        row = _consult_agg_row(
            bucket_zero=2, bucket_one=5, bucket_two=4,
            bucket_three_four=6, bucket_five_seven=4, bucket_eight_plus=3,
            total=24,
        )
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            MockClient.return_value = _consult_mock(row)
            from services.analytics_api.app.routers.audit import audit_consultations

            result = audit_consultations(
                scope=_mock_scope(), org_id=None,
                date_from=None, date_to=None, benchmark_set_id=None,
            )

        practice = _practice(result)
        buckets = practice["buckets"]
        assert buckets["0"] == 2
        assert buckets["2"] == 4
        assert buckets["3-4"] == 6
        assert buckets["8+"] == 3

    def test_top_factors_ranked_by_frequency(self):
        """Factor codes from episodes_raw are ranked by frequency."""
        episodes_raw = [
            {"n": 3, "factors": ["different_initial_diagnosis", "co_morbidity_blurring"],
             "cancer_type": "Breast", "episode_id": "ep-1"},
            {"n": 5, "factors": ["different_initial_diagnosis"],
             "cancer_type": "Colorectal", "episode_id": "ep-2"},
            {"n": 4, "factors": ["different_initial_diagnosis"],
             "cancer_type": "Prostate", "episode_id": "ep-3"},
            {"n": 2, "factors": ["co_morbidity_blurring"],
             "cancer_type": "Melanoma", "episode_id": "ep-4"},
        ]
        row = _consult_agg_row(total=4, three_or_more=4, enriched=4,
                               episodes_raw=episodes_raw)
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            MockClient.return_value = _consult_mock(row)
            from services.analytics_api.app.routers.audit import audit_consultations

            result = audit_consultations(
                scope=_mock_scope(), org_id=None,
                date_from=None, date_to=None, benchmark_set_id=None,
            )

        practice = _practice(result)
        top = practice["top_factors"]
        # different_initial_diagnosis appears in 3 episodes; co_morbidity_blurring in 2.
        assert top[0]["factor"] == "different_initial_diagnosis"
        assert top[0]["n"] == 3
        assert any(f["factor"] == "co_morbidity_blurring" for f in top)

    def test_factors_by_cancer_type_structure(self):
        episodes_raw = [
            {"n": 3, "factors": ["different_initial_diagnosis"],
             "cancer_type": "Breast", "episode_id": "ep-1"},
            {"n": 5, "factors": ["different_initial_diagnosis", "co_morbidity_blurring"],
             "cancer_type": "Breast", "episode_id": "ep-2"},
        ]
        row = _consult_agg_row(total=2, episodes_raw=episodes_raw)
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            MockClient.return_value = _consult_mock(row)
            from services.analytics_api.app.routers.audit import audit_consultations

            result = audit_consultations(
                scope=_mock_scope(), org_id=None,
                date_from=None, date_to=None, benchmark_set_id=None,
            )

        practice = _practice(result)
        fct = practice["factors_by_cancer_type"]
        assert "Breast" in fct
        assert fct["Breast"]["different_initial_diagnosis"] == 2
        assert fct["Breast"]["co_morbidity_blurring"] == 1

    def test_median_iqr_computed_from_inline_episodes(self):
        """Median and IQR are derived from the episodes_raw n values."""
        episodes_raw = [
            {"n": 1, "factors": [], "cancer_type": "Breast", "episode_id": "ep-a"},
            {"n": 2, "factors": [], "cancer_type": "Breast", "episode_id": "ep-b"},
            {"n": 3, "factors": [], "cancer_type": "Colorectal", "episode_id": "ep-c"},
            {"n": 7, "factors": [], "cancer_type": "Melanoma", "episode_id": "ep-d"},
        ]
        row = _consult_agg_row(total=4, episodes_raw=episodes_raw)
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            MockClient.return_value = _consult_mock(row)
            from services.analytics_api.app.routers.audit import audit_consultations

            result = audit_consultations(
                scope=_mock_scope(), org_id=None,
                date_from=None, date_to=None, benchmark_set_id=None,
            )

        practice = _practice(result)
        # sorted [1,2,3,7] (n=4)
        # median = (counts[1] + counts[2]) / 2 = (2+3)/2 = 2.5
        # iqr_low  = counts[n//4]   = counts[1] = 2
        # iqr_high = counts[3*n//4] = counts[3] = 7
        assert practice["median_consultations"] == 2.5
        assert practice["iqr_low"] == 2.0
        assert practice["iqr_high"] == 7.0


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

        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([agg_rows, patient_rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_intervals

            result = audit_intervals(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

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
            "trim(coalesce(effective_diag_date, '')) <> ''" in q for q in queries
        )

    def test_pci_does_not_count_missing_first_presentation_as_zero_days(self):
        from services.analytics_api.app.routers._audit_intervals import (
            DI_START_DATE_EXPR,
            FP_DATE_EXPR,
        )

        assert "ep.first_presentation_date" in FP_DATE_EXPR
        assert "THEN toString(ep.referral_date)" not in FP_DATE_EXPR
        assert "THEN toString(ep.referral_date)" in DI_START_DATE_EXPR


class TestAuditDemographics:
    def test_query_guards_empty_temporal_strings(self):
        sex_rows = [{"gender": "female", "n": 1}]
        age_rows = [{"age_band": "50-64", "n": 1}]
        age_vals_rows = [{"age": 58}]
        eth_rows = [{"ethnicity": "White", "n": 1}]
        age_band_by_sex_rows = [{"gender": "female", "age_band": "50-64", "n": 1}]
        eth_snomed_agg = [{"snomed": "976631000000101", "n": 1}]
        eth_cover_row = [{"n": 1}]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client(
                [
                    sex_rows,
                    age_rows,
                    age_vals_rows,
                    eth_rows,
                    age_band_by_sex_rows,
                    eth_snomed_agg,
                    eth_cover_row,
                ]
            )
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
        pdemo = result["scopes"]["practice"]
        assert pdemo["demographics_cohort_n"] == 1
        assert pdemo["patients_with_ethnicity_snomed_n"] == 1
        assert pdemo["ethnicity_snomed_coverage_pct"] == 100.0
        queries = [str(c.args[0]) for c in mock.run.call_args_list]
        assert any(
            "trim(coalesce(toString(ep.referral_date), '')) = ''" in q for q in queries
        )
        assert any(
            "trim(coalesce(toString(p.birthDate), '')) = ''" in q for q in queries
        )

    def test_age_band_by_sex_cross_tab_returned(self):
        """DI-87D92943: /analytics/audit/demographics SHALL return an
        age_band_by_sex array of {gender, age_band, n, pct} entries."""
        sex_rows = [{"gender": "female", "n": 2}, {"gender": "male", "n": 1}]
        age_rows = [
            {"age_band": "50-64", "n": 2},
            {"age_band": "65-74", "n": 1},
        ]
        age_vals_rows = [{"age": 58}, {"age": 60}, {"age": 70}]
        eth_rows = [{"ethnicity": "White", "n": 3}]
        age_band_by_sex_rows = [
            {"gender": "female", "age_band": "50-64", "n": 2},
            {"gender": "male", "age_band": "65-74", "n": 1},
        ]
        eth_snomed_agg = [{"snomed": "976631000000101", "n": 2}]
        eth_cover_row = [{"n": 2}]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client(
                [
                    sex_rows,
                    age_rows,
                    age_vals_rows,
                    eth_rows,
                    age_band_by_sex_rows,
                    eth_snomed_agg,
                    eth_cover_row,
                ]
            )
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_demographics

            result = audit_demographics(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        practice = result["scopes"]["practice"]
        assert "age_band_by_sex" in practice
        rows = practice["age_band_by_sex"]
        assert len(rows) == 2
        keys = {"gender", "age_band", "n", "pct"}
        for row in rows:
            assert keys.issubset(row.keys())
        female_5064 = next(
            r for r in rows if r["gender"] == "female" and r["age_band"] == "50-64"
        )
        assert female_5064["n"] == 2
        # 2 / (2 + 1) = 66.7%
        assert female_5064["pct"] == 66.7

        eb = practice["ethnicity_by_snomed"]
        assert isinstance(eb, list) and len(eb) >= 1
        white_brit = next(
            (r for r in eb if r.get("snomed") == "976631000000101"),
            None,
        )
        assert white_brit is not None
        assert white_brit["n"] == 2
        # 2 / 3 sex-row patients = 66.7%
        assert white_brit["pct"] == 66.7
        assert "benchmark_key" in white_brit and "preferred_term" in white_brit
        assert practice["demographics_cohort_n"] == 3
        assert practice["patients_with_ethnicity_snomed_n"] == 2
        assert practice["ethnicity_snomed_coverage_pct"] == 66.7

        # Cross-tab Cypher must filter on gender and use age_at_referral case.
        queries = [str(c.args[0]) for c in mock.run.call_args_list]
        assert any(
            "p.gender IS NOT NULL" in q and "age_band" in q and "gender, age_band" in q
            for q in queries
        )
        assert any(
            "coalesce(d.domain, '') = 'ethnicity'" in q
            and "eth_snomed_ids" in q
            and "WITH DISTINCT p" in q
            for q in queries
        )
        assert any("RETURN count(DISTINCT p) AS n" in q for q in queries)


# ---------------------------------------------------------------------------
# Tests: safety_netting
# ---------------------------------------------------------------------------


class TestAuditSafetyNetting:
    def test_multi_scope_envelope(self):
        rows = [
            {
                "total_episodes": 51,
                "recorded": 10,
                "strong_n": 7,
                "medium_n": 3,
                "advice_only_n": 5,
                "none_n": 36,
            }
        ]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_safety_netting

            result = audit_safety_netting(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        assert "scopes" in result
        practice = _practice(result)
        assert "recorded_pct" in practice
        assert practice["recorded_pct"] == round(10 * 100.0 / 51, 1)

    def test_returns_signal_strength_breakdown(self):
        """The Safety Netting 'Open detail' dialog (per-year drill)
        reads ``signal_counts`` / ``signal_pct`` directly off the
        per-year response. Pin the contract here so a backend refactor
        cannot silently strip the breakdown.
        """
        rows = [
            {
                "total_episodes": 42,
                "recorded": 20,
                "strong_n": 13,
                "medium_n": 7,
                "advice_only_n": 3,
                "none_n": 19,
            }
        ]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_safety_netting

            result = audit_safety_netting(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        practice = _practice(result)
        assert practice["signal_counts"] == {
            "strong": 13,
            "medium": 7,
            "advice_only": 3,
            "none": 19,
        }
        # signal_pct must sum to ~100 (modulo rounding drift on each row).
        signal_pct = practice["signal_pct"]
        assert signal_pct["strong"] == 31.0  # 13/42
        assert signal_pct["medium"] == 16.7  # 7/42
        assert signal_pct["advice_only"] == 7.1  # 3/42
        assert signal_pct["none"] == 45.2  # 19/42

        # The strict 'strong only' subset is surfaced for the dialog
        # header ("strict (free-text or Y281b only)" tile).
        assert practice["strong_n"] == 13
        assert practice["strong_pct"] == 31.0

        # Recorded headline still equals strong + medium so the year
        # card and the dialog headline tile agree by construction.
        assert practice["recorded_n"] == 20
        assert practice["recorded_pct"] == round(20 * 100.0 / 42, 1)

    def test_handles_zero_episodes_without_division_error(self):
        """When the year window has no confirmed cancers yet, every
        rate must clamp safely (no ZeroDivisionError on the helper)."""
        rows = [
            {
                "total_episodes": 0,
                "recorded": 0,
                "strong_n": 0,
                "medium_n": 0,
                "advice_only_n": 0,
                "none_n": 0,
            }
        ]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_safety_netting

            result = audit_safety_netting(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

        practice = _practice(result)
        assert practice["total_episodes"] == 0
        assert practice["recorded_pct"] == 0.0
        assert practice["signal_counts"] == {
            "strong": 0,
            "medium": 0,
            "advice_only": 0,
            "none": 0,
        }
        assert practice["signal_pct"]["strong"] == 0.0
        assert practice["strong_pct"] == 0.0


# ---------------------------------------------------------------------------
# Tests: avoidable_delays
# ---------------------------------------------------------------------------


class TestAuditAvoidableDelays:
    def test_multi_scope_envelope(self):
        rows = [
            {
                "total_episodes": 51,
                "has_delay": 14,
                "before_pres": 9,
                "pres_to_ref": 4,
                "after_ref": 1,
            }
        ]
        with patch(
            "services.analytics_api.app.routers.audit.PatientGraphClient"
        ) as MockClient:
            mock = _mock_client([rows])
            MockClient.return_value = mock

            from services.analytics_api.app.routers.audit import audit_avoidable_delays

            result = audit_avoidable_delays(
                scope=_mock_scope(),
                org_id=None,
                date_from=None,
                date_to=None,
                benchmark_set_id=None,
            )

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
            {
                "metric_id": "primary_care_interval.median_days",
                "scope_type": "gp_practice",
                "scope_id": "C84070",
                "scope_name": "Woodbrook Medical Centre",
                "value": 30,
            },
            {
                "metric_id": "primary_care_interval.median_days",
                "scope_type": "national",
                "scope_id": "england",
                "scope_name": "England",
                "value": 25,
            },
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
                "ncda-2018",
                "primary_care_interval",
                org_id="woodbrook-gp",
                org_ods_code="C84070",
                alliance_id=None,
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
        # New anchor: outcome_date (year of diagnosis or benign closure),
        # bound by _OUTCOME_DATE_BIND in the per-section base.
        assert "AND outcome_date >= $date_from" in result_base
        assert "AND outcome_date <= $date_to" in result_base

    def test_add_date_filters_no_dates_unchanged(self):
        """When no dates are provided the base is returned unchanged."""
        from services.analytics_api.app.routers.audit import _add_date_filters

        base = "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep) WHERE true "
        result_base, result_params = _add_date_filters(base, {"org": "x"}, None, None)
        assert result_base == base
        assert result_params == {"org": "x"}

    def test_org_patient_match_binds_outcome_date(self):
        """_ORG_PATIENT_MATCH must bind outcome_date and end with WHERE true."""
        from services.analytics_api.app.routers.audit import _ORG_PATIENT_MATCH

        stripped = _ORG_PATIENT_MATCH.rstrip()
        # Episode-exclusion clause must still be present (now followed by
        # the outcome_date OPTIONAL MATCH + WITH chain).
        assert "WHERE NOT ep.status IN" in stripped
        # Outcome anchor must be bound so _add_date_filters can filter on it.
        assert "AS outcome_date" in stripped
        # The chain must terminate in an active WHERE clause so callers
        # can append predicates with AND.
        assert stripped.endswith("WHERE true")

    def test_england_base_binds_outcome_date(self):
        """_ENGLAND_BASE must bind outcome_date and end with WHERE true."""
        from services.analytics_api.app.routers.audit import _ENGLAND_BASE

        stripped = _ENGLAND_BASE.rstrip()
        assert "WHERE NOT ep.status IN" in stripped
        assert "AS outcome_date" in stripped
        assert stripped.endswith("WHERE true")

    def test_date_filters_with_org_base_produces_no_bare_where(self):
        """Applying date filters to org base must not produce a bare WHERE."""
        from services.analytics_api.app.routers.audit import (
            _add_date_filters,
            _ORG_PATIENT_MATCH,
        )

        base, params = _add_date_filters(
            _ORG_PATIENT_MATCH, {"org": "abc"}, "2024-01-01", None
        )
        # Count WHERE occurrences -- must be exactly 5:
        # patient org scope, nested GP EXISTS filter, episode filter,
        # optional-match milestone filter, and the trailing WHERE true
        # (now extended with the date filter).
        assert base.count("WHERE") == 5
        assert "AND outcome_date >= $date_from" in base


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
        assert (
            counts["hypertension"] == 1
        ), "Patient with 2 child concepts must count once per group"

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
# Tests: comorbidity referral-outcome labels (drilldown)
# ---------------------------------------------------------------------------


class TestComorbidityDrilldownOutcome:
    def test_outcome_label_confirmed_uses_canonical_cancer_type(self):
        from services.analytics_api.app.routers._audit_comorbidities import (
            _outcome_label,
        )

        assert _outcome_label(True, "breast", True) == "Breast"

    def test_outcome_label_prefers_snomed_cancer_type_bucket(self):
        from services.analytics_api.app.routers._audit_comorbidities import (
            _outcome_label,
        )

        assert (
            _outcome_label(True, "breast", True, ["SNOMED breast cancer"])
            == "SNOMED breast cancer"
        )

    def test_outcome_label_referral_no_cancer(self):
        from services.analytics_api.app.routers._audit_comorbidities import (
            _outcome_label,
        )

        assert (
            _outcome_label(False, None, True) == "Referral without cancer diagnosis"
        )

    def test_outcome_label_other(self):
        from services.analytics_api.app.routers._audit_comorbidities import (
            _outcome_label,
        )

        assert _outcome_label(False, None, False) == "Other"




class TestLinkEncountersToEpisode:
    """Verify _link_encounters_to_episode deduplicates and handles edge cases."""

    def test_no_encounter_id_skipped(self):
        """Anchors without encounter_id still trigger a replace call with empty payload."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import (
            _link_encounters_to_episode,
        )

        client = MagicMock()
        _link_encounters_to_episode(
            client,
            "ep1",
            [
                ([{"encounter_id": None, "concept_name": "test"}], "referral"),
            ],
        )
        client.run.assert_called_once()
        call_kwargs = client.run.call_args[1]
        assert call_kwargs["encounters"] == []

    def test_deduplicates_same_encounter_across_types(self):
        """Same encounter_id appearing in multiple anchor lists must be sent once."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import (
            _link_encounters_to_episode,
        )

        client = MagicMock()
        _link_encounters_to_episode(
            client,
            "ep1",
            [
                ([{"encounter_id": "E1"}], "referral"),
                ([{"encounter_id": "E1"}], "diagnosis_confirmed"),
            ],
        )
        client.run.assert_called_once()
        call_kwargs = client.run.call_args[1]
        encounter_ids = [e["encounter_id"] for e in call_kwargs["encounters"]]
        assert encounter_ids.count("E1") == 1

    def test_empty_episode_id_no_call(self):
        """Empty episode_id must result in no DB write."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import (
            _link_encounters_to_episode,
        )

        client = MagicMock()
        _link_encounters_to_episode(
            client,
            "",
            [
                ([{"encounter_id": "E1"}], "referral"),
            ],
        )
        client.run.assert_not_called()

    def test_multiple_encounters_all_sent(self):
        """Multiple distinct encounters must all be included in the payload."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import (
            _link_encounters_to_episode,
        )

        client = MagicMock()
        _link_encounters_to_episode(
            client,
            "ep1",
            [
                ([{"encounter_id": "E1"}, {"encounter_id": "E2"}], "referral"),
                ([{"encounter_id": "E3"}], "diagnosis_confirmed"),
            ],
        )
        client.run.assert_called_once()
        call_kwargs = client.run.call_args[1]
        encounter_ids = {e["encounter_id"] for e in call_kwargs["encounters"]}
        assert encounter_ids == {"E1", "E2", "E3"}

    def test_link_query_replaces_existing_links(self):
        """Link query should delete existing links before adding current ones."""
        from unittest.mock import MagicMock
        from services.analysis_worker.app.analyzers.episode_builder import (
            _link_encounters_to_episode,
        )

        client = MagicMock()
        _link_encounters_to_episode(
            client,
            "ep1",
            [
                ([{"encounter_id": "E1"}], "referral"),
            ],
        )
        client.run.assert_called_once()
        query = str(client.run.call_args[0][0])
        assert "DELETE r_old" in query
