from __future__ import annotations

from libs.auth.org_scope import CallerScope
from libs.episodes.lifecycle import HERO_BUCKETS
from services.analytics_api.app.routers import audit


def test_audit_summary_guards_empty_temporal_strings(monkeypatch):
    """First query (rows) must include the trim-coalesce guards; later
    queries (canonical confirmed / via-2WW counts and the MECE hero
    buckets) use the shared cohort helper and run against the same
    client."""

    class _FakeClient:
        def __init__(self):
            self.call = 0
            self.queries: list[str] = []

        def run(self, query, **kwargs):
            self.call += 1
            self.queries.append(query)
            if "trim(coalesce(toString(ep.referral_date), '')) = ''" in query:
                assert "trim(coalesce(toString(ep.referral_date), '')) = ''" in query
                assert (
                    "trim(coalesce(toString(ep.first_presentation_date), '')) = ''"
                    in query
                )
                assert "referral_date_value IS NOT NULL" in query
                return [
                    {
                        "ep_status": "completed",
                        "fp_date": "2025-01-01",
                        "di_start_date": "2025-01-01",
                        "ref_date": "2025-01-05",
                        "sn": True,
                        "diag_date": "2025-01-20",
                        "diag_is_inferred": False,
                        "is_confirmed": True,
                        "consultation_count": 2,
                    }
                ]
            if "bucket" in query and "RETURN bucket" in query:
                return [
                    {"bucket": "active", "n": 7},
                    {"bucket": "in_review", "n": 3},
                    {"bucket": "cancer_excluded", "n": 5},
                    {"bucket": "confirmed_cancer", "n": 11},
                ]
            return [{"n": 1}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )

    result = audit.audit_summary(scope=scope, org_id="org-1")
    assert result["total_episodes"] == 1
    assert result["confirmed_cancers"] == 1
    assert result["confirmed_cancers_via_2ww"] == 1
    assert result["confirmed_cancers_via_2ww_pct"] == 100.0
    assert result["median_di_days"] == 19.0


def test_audit_summary_excludes_screening_from_fast_track_rate(monkeypatch):
    captured: list[str] = []

    class _FakeClient:
        def run(self, query, **kwargs):
            captured.append(query)
            if "RETURN count(DISTINCT ep) AS n" in query:
                if "AND NOT (toLower" in query and "CONTAINS 'screening'" in query:
                    return [{"n": 29}]
                if "CONTAINS 'screening'" in query:
                    return [{"n": 6}]
                if "milestone_type = 'referral'" in query:
                    return [{"n": 35}]
                if "diagnosis_confirmed" in query:
                    return [{"n": 40}]
                return [{"n": 50}]
            return []

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    assert result["confirmed_cancers"] == 40
    assert result["confirmed_cancers_screening_programme"] == 6
    assert result["confirmed_cancers_excluding_screening"] == 34
    assert result["confirmed_cancers_via_2ww"] == 35
    assert result["confirmed_cancers_via_2ww_excluding_screening"] == 29
    assert result["confirmed_cancers_via_2ww_excluding_screening_pct"] == 85.3

    exclusion_queries = [
        q for q in captured if "AND NOT (toLower" in q and "CONTAINS 'screening'" in q
    ]
    assert len(exclusion_queries) == 1
    assert "place_of_presentation" in exclusion_queries[0]
    assert "place_of_presetnation" in exclusion_queries[0]


def test_audit_summary_returns_mece_hero_bucket_counts(monkeypatch):
    """The audit_summary response surfaces the four MECE lifecycle
    bucket counts and they sum to total_cohort_episodes by construction
    (DI-105A4EC7)."""

    class _FakeClient:
        def __init__(self):
            self.call = 0
            self.queries: list[str] = []

        def run(self, query, **kwargs):
            self.call += 1
            self.queries.append(query)
            if self.call == 1:
                return []
            if "bucket" in query and "RETURN bucket" in query:
                return [
                    {"bucket": "active", "n": 60},
                    {"bucket": "in_review", "n": 20},
                    {"bucket": "cancer_excluded", "n": 12},
                    {"bucket": "confirmed_cancer", "n": 49},
                    # An out-of-vocabulary bucket name (defensive guard:
                    # if the Cypher CASE were to drift, the dashboard
                    # must NOT silently drop the count).
                    {"bucket": "garbage", "n": 999},
                ]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )

    result = audit.audit_summary(scope=scope, org_id="org-1")

    # The four MECE fields must be present and aligned with HERO_BUCKETS.
    assert set(HERO_BUCKETS) == {
        "active",
        "in_review",
        "cancer_excluded",
        "confirmed_cancer",
    }
    assert result["active_lifecycle_episodes"] == 60
    assert result["in_review_episodes"] == 20
    assert result["cancer_excluded_episodes"] == 12
    assert result["confirmed_cancer_episodes"] == 49

    # Sum of the four buckets MUST equal total_cohort_episodes (the
    # garbage bucket is intentionally dropped, not silently absorbed).
    assert result["total_cohort_episodes"] == 60 + 20 + 12 + 49


def test_audit_summary_returns_cohort_totals_for_dashboard_card(monkeypatch):
    """The dashboard 'Cohort' summary card needs FOUR fields:

      * total_cohort_patients - all Patients in scope (matches Mission
        Control's cohort denominator; was the original bug -- before
        this fix the dashboard counted only patients-with-episodes
        and silently disagreed with Mission Control).
      * total_cohort_patients_with_pathway - the subset with at least
        one EpisodeOfCare; drives the "97 of 107" display.
      * patients_without_pathway - the difference; drives the
        clickable caption + lifecycle_bucket=no_pathway deep-link.
      * total_cohort_episodes_all - includes admin-only EpisodeOfCare
        statuses so the four MECE bucket counts can sum to <= total
        and any discrepancy renders as a footnote.

    See DI-105A4EC7 / DI-CA1B4C6E / R-D32A2AC2.
    """

    captured: list[str] = []

    class _FakeClient:
        def __init__(self):
            self.call = 0

        def run(self, query, **kwargs):
            self.call += 1
            captured.append(query)
            if self.call == 1:
                return []
            if "RETURN bucket" in query:
                return [
                    {"bucket": "active", "n": 28},
                    {"bucket": "in_review", "n": 37},
                    {"bucket": "cancer_excluded", "n": 31},
                    {"bucket": "confirmed_cancer", "n": 45},
                ]
            if (
                "total_patients" in query
                and "patients_with_pathway" in query
            ):
                return [
                    {"total_patients": 107, "patients_with_pathway": 97}
                ]
            if "total_episodes_all" in query:
                return [{"total_episodes_all": 144}]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )

    result = audit.audit_summary(scope=scope, org_id="org-1")

    assert result["total_cohort_patients"] == 107
    assert result["total_cohort_patients_with_pathway"] == 97
    assert result["patients_without_pathway"] == 10
    assert result["total_cohort_episodes_all"] == 144
    assert result["total_cohort_episodes_all"] >= result["total_cohort_episodes"]

    # The patient denominator query MUST NOT join through
    # HAS_EPISODE_OF_CARE in its outer MATCH, otherwise patients with
    # no pathway are silently excluded and the dashboard disagrees
    # with Mission Control.
    patient_q = next(
        q for q in captured if "patients_with_pathway" in q
    )
    # The OUTER match is just MATCH (p:Patient)... the only
    # HAS_EPISODE_OF_CARE reference must be inside the EXISTS{} sub-
    # pattern that classifies which patients have a pathway.
    assert "(p:Patient)" in patient_q
    has_ep = patient_q.count("HAS_EPISODE_OF_CARE")
    assert has_ep == 1, (
        "Cohort patient denominator query must reference "
        "HAS_EPISODE_OF_CARE only inside the EXISTS{} classifier, "
        "not in the outer MATCH (otherwise patients-without-pathway "
        "are silently excluded)."
    )

    # Cohort episode totals query must NOT exclude admin-only
    # statuses -- we want admin-only episodes counted in the totals
    # card so any discrepancy with the four MECE buckets is rendered
    # as a footnote instead of hidden.
    episodes_q = next(
        q for q in captured if "total_episodes_all" in q
    )
    assert "merged" not in episodes_q
    assert "closed_phantom" not in episodes_q


def test_audit_summary_patients_without_pathway_clamps_to_zero(monkeypatch):
    """If the underlying counts ever produce a negative difference
    (e.g. transient inconsistency between the two queries), the
    response field must clamp to 0 -- the dashboard renders the
    'X have no pathway yet' caption only when the value is positive,
    and a negative value would crash MUI / leak nonsense to the
    clinician. See DI-CA1B4C6E.
    """

    class _FakeClient:
        def __init__(self):
            self.call = 0

        def run(self, query, **kwargs):
            self.call += 1
            if "patients_with_pathway" in query:
                # Pathological: somehow more patients-with-pathway
                # than total patients (impossible in practice but the
                # response must still be sane).
                return [
                    {"total_patients": 100, "patients_with_pathway": 105}
                ]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)
    assert result["patients_without_pathway"] == 0


def test_audit_summary_queries_use_hero_bucket_case(monkeypatch):
    """The bucket query uses the canonical Cypher snippet from
    libs.episodes.lifecycle (no inline duplication of priority chain)."""

    captured: list[str] = []

    class _FakeClient:
        def __init__(self):
            self.call = 0

        def run(self, query, **kwargs):
            self.call += 1
            captured.append(query)
            if self.call == 1:
                return []
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(
        email="qa@example.com",
        is_admin=False,
        org_ids=["org-1"],
        scope_type="gp",
        primary_org_id="org-1",
    )

    audit.audit_summary(scope=scope, org_id="org-1")

    bucket_queries = [
        q for q in captured if "RETURN bucket" in q
    ]
    assert len(bucket_queries) == 1, captured
    bucket_query = bucket_queries[0]
    # All four bucket strings must appear once in the same Cypher CASE.
    for bucket in ("active", "in_review", "cancer_excluded", "confirmed_cancer"):
        assert f"'{bucket}'" in bucket_query, bucket
    # Letter-inferred-benign guard must be wired into the CASE so a
    # benign letter never gets classified as confirmed cancer.
    assert "letter_inferred_benign" in bucket_query


def test_audit_summary_safety_netting_uses_signal_hierarchy(monkeypatch):
    """Section 8 (safety-netting) headline percentage MUST be computed
    from the canonical confirmed-cancer cohort (denominator) and the
    signal hierarchy stamped onto each EpisodeOfCare by
    ``libs/oncology/safety_netting.detect_safety_netting`` (numerator).

    Strict default: 'recorded' = strong + medium (free-text safety-net
    OR Y281b code OR PRISM 'Advice if worsens' field).  The tooltip
    surfaces the strong-only number too.

    Pinned because the previous implementation divided
    ``ep.safety_netting_recorded`` (referral-gated subset) by
    ``total_episodes`` (full cohort including cohort 3), which mixed
    denominators and rendered as 0% on dashboards even when the EMIS
    template had been completed.
    """

    captured: list[str] = []

    class _FakeClient:
        def __init__(self):
            self.call = 0

        def run(self, query, **kwargs):
            self.call += 1
            captured.append(query)
            # Safety-netting breakdown query — return a realistic mix.
            if (
                "ep.safety_netting_signal" in query
                and "RETURN coalesce(ep.safety_netting_signal" in query
            ):
                return [
                    {"signal": "strong", "n": 13},
                    {"signal": "medium", "n": 7},
                    {"signal": "advice_only", "n": 3},
                    {"signal": "none", "n": 19},
                ]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    # Hierarchy is preserved end-to-end so the tooltip can render it.
    assert result["safety_netting_signal_counts"] == {
        "strong": 13,
        "medium": 7,
        "advice_only": 3,
        "none": 19,
    }
    assert result["safety_netting_denominator"] == 42

    # Headline (strong + medium) — 20 of 42.
    assert result["safety_netting_recorded_n"] == 20
    assert result["safety_netting_pct"] == 47.6

    # Strict (strong only) — 13 of 42.
    assert result["safety_netting_strong_n"] == 13
    assert result["safety_netting_strong_pct"] == 31.0

    # The breakdown query MUST scope to confirmed cancers, not the
    # full cohort, so the rate matches NCDA Section 8 semantics.
    sn_queries = [
        q for q in captured if "RETURN coalesce(ep.safety_netting_signal" in q
    ]
    assert len(sn_queries) == 1, captured
    assert "letter_inferred_benign" in sn_queries[0], (
        "safety-netting breakdown must use confirmed_cancer_where(), "
        "which contains the letter_inferred_benign guard."
    )
    assert "diagnosis_confirmed" in sn_queries[0], (
        "safety-netting breakdown must use confirmed_cancer_where(), "
        "which requires a diagnosis milestone."
    )


def test_audit_summary_care_obstruction_uses_signal_hierarchy(monkeypatch):
    """Care-obstruction headline rate MUST be computed from the canonical
    confirmed-cancer cohort (denominator) and the signal hierarchy
    stamped onto each EpisodeOfCare by
    ``libs/oncology/care_obstruction.detect_care_obstructions``
    (numerator).

    Strict default: 'recorded' = any non-none signal (rejection + dna
    + cancellation + access_barrier).  The 'severe' subset surfaces
    rejection + dna only — the events that hard-stop the workup.
    """

    captured: list[str] = []

    class _FakeClient:
        def run(self, query, **kwargs):
            captured.append(query)
            if (
                "ep.care_obstruction_signal" in query
                and "RETURN coalesce(ep.care_obstruction_signal" in query
            ):
                return [
                    {"signal": "rejection", "n": 5},
                    {"signal": "dna", "n": 8},
                    {"signal": "cancellation", "n": 1},
                    {"signal": "access_barrier", "n": 2},
                    {"signal": "none", "n": 26},
                ]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    # Hierarchy preserved end-to-end so the breakdown dialog can render it.
    assert result["care_obstruction_signal_counts"] == {
        "rejection": 5,
        "dna": 8,
        "cancellation": 1,
        "access_barrier": 2,
        "none": 26,
    }
    assert result["care_obstruction_denominator"] == 42

    # Headline (any obstruction recorded) — 16 of 42.
    assert result["care_obstruction_recorded_n"] == 16
    assert result["care_obstruction_pct"] == 38.1

    # Severe subset (rejection + dna) — 13 of 42.
    assert result["care_obstruction_severe_n"] == 13
    assert result["care_obstruction_severe_pct"] == 31.0

    # The breakdown query MUST scope to confirmed cancers so the rate
    # is comparable to safety-netting and the rest of NCDA Section 9.
    co_queries = [
        q for q in captured if "RETURN coalesce(ep.care_obstruction_signal" in q
    ]
    assert len(co_queries) == 1, captured
    assert "letter_inferred_benign" in co_queries[0], (
        "care-obstruction breakdown must use confirmed_cancer_where(), "
        "which contains the letter_inferred_benign guard."
    )


def test_audit_summary_care_obstruction_handles_zero_confirmed(monkeypatch):
    """When the cohort has no confirmed cancers, the care-obstruction
    rates must be ``None`` (renders as em-dash on the tile) rather
    than crashing on a zero-division.
    """

    class _FakeClient:
        def run(self, query, **kwargs):
            if "RETURN coalesce(ep.care_obstruction_signal" in query:
                return []
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    assert result["care_obstruction_pct"] is None
    assert result["care_obstruction_severe_pct"] is None
    assert result["care_obstruction_recorded_n"] == 0
    assert result["care_obstruction_severe_n"] == 0
    assert result["care_obstruction_denominator"] == 0


def test_audit_summary_prior_consultations_uses_haiku_enrichment(monkeypatch):
    """Section 7 (NCDA "multiple consultations") headline rate must
    come from the ``ep.prior_consultations_n`` count stamped on each
    EpisodeOfCare by the Haiku enrichment pass.  Multi >= 2.  Same
    denominator (confirmed cancer cohort) as care-obstruction +
    safety-netting so the three NCDA-equivalent tiles are directly
    comparable."""

    captured: list[str] = []

    class _FakeClient:
        def run(self, query, **kwargs):
            captured.append(query)
            if "AS multi_n" in query and "prior_consultations_n" in query:
                return [
                    {
                        "denom": 30,
                        "enriched": 28,
                        "multi_n": 18,
                        "total_consultations": 64,
                        "llm_cost_usd": 0.7321,
                    }
                ]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    assert result["prior_consultations_denominator"] == 30
    assert result["prior_consultations_enriched_n"] == 28
    assert result["prior_consultations_n"] == 18
    # 18 / 30 -> 60.0%
    assert result["prior_consultations_pct"] == 60.0
    # Mean per ENRICHED episode (not denominator): 64 / 28 -> 2.29
    assert result["prior_consultations_mean_per_episode"] == 2.29
    assert result["prior_consultations_total_consultations"] == 64
    assert result["prior_consultations_llm_cost_usd"] == 0.7321

    # The summary query MUST scope to confirmed cancers so the rate is
    # comparable to safety-netting and care-obstructions.
    pc_queries = [q for q in captured if "prior_consultations_n" in q]
    assert len(pc_queries) == 1, captured
    assert "letter_inferred_benign" in pc_queries[0], (
        "prior-consultations summary must use confirmed_cancer_where(), "
        "which contains the letter_inferred_benign guard."
    )


def test_audit_summary_prior_consultations_handles_zero_confirmed(monkeypatch):
    """When no episodes have been enriched, the prior-consultations
    rates must be ``None`` (renders as em-dash) rather than crashing
    on a zero-division."""

    class _FakeClient:
        def run(self, query, **kwargs):
            if "AS multi_n" in query and "prior_consultations_n" in query:
                return [{"denom": 0, "enriched": 0, "multi_n": 0,
                         "total_consultations": 0, "llm_cost_usd": 0.0}]
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    assert result["prior_consultations_pct"] is None
    assert result["prior_consultations_mean_per_episode"] is None
    assert result["prior_consultations_n"] == 0
    assert result["prior_consultations_denominator"] == 0
    assert result["prior_consultations_llm_cost_usd"] == 0.0


def test_audit_summary_safety_netting_handles_zero_confirmed(monkeypatch):
    """When the cohort has no confirmed cancers, the safety-netting
    rates must be ``None`` (renders as em-dash on the tile) rather
    than crashing on a zero-division.
    """

    class _FakeClient:
        def run(self, query, **kwargs):
            if "RETURN coalesce(ep.safety_netting_signal" in query:
                return []
            return [{"n": 0}]

        def close(self):
            return None

    monkeypatch.setattr(audit, "PatientGraphClient", _FakeClient)
    scope = CallerScope(email="qa@example.com", is_admin=True)

    result = audit.audit_summary(scope=scope)

    assert result["safety_netting_pct"] is None
    assert result["safety_netting_strong_pct"] is None
    assert result["safety_netting_recorded_n"] == 0
    assert result["safety_netting_strong_n"] == 0
    assert result["safety_netting_denominator"] == 0
