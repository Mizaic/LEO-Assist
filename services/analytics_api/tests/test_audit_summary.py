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
            if self.call == 1:
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
