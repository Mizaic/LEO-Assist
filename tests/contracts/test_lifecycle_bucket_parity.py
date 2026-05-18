"""Lifecycle bucket parity contract.

Pins the invariant that the dashboard's MECE hero-card counts and the
Mission Control patient list filtered by ``lifecycle_bucket=X`` use the
exact same Cypher classifier (``libs.episodes.lifecycle.build_hero_bucket_case``).

If a clinician clicks "Confirmed Cancer 45" on the dashboard, the
patient list opened by that click must contain exactly 45 EpisodeOfCare
nodes -- never a different cohort. The audit / safety story breaks if
this drifts. See DI-105A4EC7 / R-24C3AAED.

The contract also pins the URL <-> API <-> filter chain (TypeScript
mirror at ``services/ui/src/lib/missionControlFilters.ts``) so the
serialised query parameter stays in lockstep with the FastAPI Query
validator.
"""

from __future__ import annotations

import re
from pathlib import Path

from libs.episodes.lifecycle import HERO_BUCKETS, build_hero_bucket_case
from services.analytics_api.app.routers import audit, mission_control
from services.analytics_api.app.routers.mission_control import (
    LIFECYCLE_BUCKET_PATTERN,
    NO_PATHWAY_BUCKET,
    _apply_lifecycle_bucket_filter,
    _no_pathway_scope_match,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_MIRROR = REPO_ROOT / "services" / "ui" / "src" / "lib" / "missionControlFilters.ts"


# ---------------------------------------------------------------------------
# 1. Producer / consumer Cypher parity.
# ---------------------------------------------------------------------------


def test_mission_control_filter_uses_same_case_as_dashboard_buckets():
    """The Cypher snippet appended by the Mission Control filter MUST be
    derivable from the same ``build_hero_bucket_case('ep')`` snippet used
    to compute the dashboard hero counts. Otherwise the two cohorts can
    drift and a click-through could return a different count from the
    headline number it was launched from.
    """
    canonical_case = build_hero_bucket_case("ep")
    base = "MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) WHERE true "
    for bucket in HERO_BUCKETS:
        appended, params = _apply_lifecycle_bucket_filter(base, {}, bucket)
        # The appended fragment must contain the canonical CASE
        # expression literally -- not a hand-rolled equivalent.
        assert canonical_case in appended, (
            f"lifecycle_bucket={bucket!r} did not append the canonical "
            "build_hero_bucket_case('ep'); the dashboard and the "
            "patient-list filter would drift."
        )
        assert params["lifecycle_bucket"] == bucket
        assert appended.endswith("= $lifecycle_bucket "), appended


def test_lifecycle_bucket_pattern_is_exhaustive_over_hero_buckets():
    """The endpoint Query() pattern must accept all four MECE buckets,
    the no_pathway bucket (for patients with no EpisodeOfCare yet,
    surfaced by DI-CA1B4C6E), and the wildcard, while rejecting
    everything else. The set of legal URL values is exactly the set
    of buckets the dashboard cohort summary can deep-link into.
    """
    rx = re.compile(LIFECYCLE_BUCKET_PATTERN)
    for bucket in HERO_BUCKETS:
        assert rx.match(bucket), bucket
    assert rx.match(NO_PATHWAY_BUCKET)
    assert rx.match("all")
    # Defensive: typosquatted values must not be accepted.
    for bad in (
        "Active",
        "in-review",
        "confirmed-cancer",
        "cancer_excluded ",
        "no-pathway",
        "noPathway",
    ):
        assert not rx.match(bad), bad


def test_no_pathway_scope_match_excludes_patients_with_episodes():
    """The no_pathway query path must select Patient nodes that have
    NO EpisodeOfCare relationship. If this drifts (e.g. someone
    refactors the predicate to ``EXISTS{...}``), the deep-link from
    the dashboard ``patients_without_pathway`` caption would silently
    return the WRONG cohort -- either every patient or no patients
    -- and the cohort denominator on the dashboard would no longer
    agree with what the click opens.
    """
    from libs.auth.org_scope import CallerScope

    admin_scope = CallerScope(email="contract-test@nhs.net", is_admin=True)
    base, params = _no_pathway_scope_match(None, admin_scope)
    assert "(:EpisodeOfCare)" in base
    assert "NOT EXISTS" in base
    assert "HAS_EPISODE_OF_CARE" in base
    # Admin + no org_id => no organisation parameter required.
    assert params == {}


# ---------------------------------------------------------------------------
# 2. Cohort summary card contract.
# ---------------------------------------------------------------------------


def test_audit_summary_exposes_cohort_totals_for_dashboard_card():
    """The /audit/summary contract must surface every total the
    dashboard "Cohort" card needs:
      * total_cohort_patients - all Patients in scope (parity with
        Mission Control's cohort denominator; was a real bug --
        previously this counted only patients with episodes, hiding
        10 patients-without-pathway from the dashboard).
      * total_cohort_patients_with_pathway - the subset with at least
        one EpisodeOfCare (drives the "97 of 107" display).
      * patients_without_pathway - the difference (drives the
        clickable caption + lifecycle_bucket=no_pathway deep-link).
      * total_cohort_episodes_all - every EpisodeOfCare including
        admin-only statuses (drives the admin-only footnote).
    """
    src = Path(audit.__file__).read_text(encoding="utf-8")
    assert '"total_cohort_patients"' in src
    assert '"total_cohort_patients_with_pathway"' in src
    assert '"patients_without_pathway"' in src
    assert '"total_cohort_episodes_all"' in src
    # The cohort patient denominator MUST come from _patient_base
    # (every Patient in scope), not from a query that joins through
    # HAS_EPISODE_OF_CARE -- otherwise patients_without_pathway is
    # always 0 and the dashboard silently disagrees with Mission
    # Control's denominator. See R-D32A2AC2.
    assert "_patient_base(" in src
    # The cohort episode totals must include admin-only episodes so
    # the four MECE buckets can sum to <= total and any discrepancy
    # is rendered as a footnote.
    assert "_episode_base_all_cohort" in src


# ---------------------------------------------------------------------------
# 3. TypeScript mirror parity.
# ---------------------------------------------------------------------------


def test_typescript_mirror_lists_every_hero_bucket():
    """The TS LifecycleBucket type must list every bucket the Python
    LIFECYCLE_BUCKET_PATTERN accepts: the four MECE buckets, the
    no_pathway bucket, and the wildcard. Otherwise the dashboard
    could send a URL param the API rejects (or the API could accept
    a value the TS deserialiser silently coerces to 'all').
    """
    src = TS_MIRROR.read_text(encoding="utf-8")
    for bucket in HERO_BUCKETS:
        assert f'"{bucket}"' in src, (
            f"missionControlFilters.ts is missing the {bucket!r} "
            "lifecycle bucket; the dashboard hero card click would "
            "produce a URL the TypeScript filter cannot deserialise."
        )
    assert f'"{NO_PATHWAY_BUCKET}"' in src, (
        "missionControlFilters.ts is missing the 'no_pathway' bucket; "
        "the dashboard cohort card 'X have no cancer pathway yet' "
        "caption would deep-link to a URL the TS deserialiser drops."
    )
    # The wildcard 'all' must be included so the cohort card can link
    # to the unfiltered patient list.
    assert '"all"' in src


def test_typescript_mirror_serialises_lifecycle_bucket_param():
    """The TS serialiser must emit ``lifecycle_bucket=...`` (the same
    URL param the FastAPI Query() validator listens for), and the API
    helper must always include it so the API can apply the filter.
    """
    src = TS_MIRROR.read_text(encoding="utf-8")
    assert 'p.set("lifecycle_bucket"' in src
    # Both sides of the contract: mission_control.py declares the same
    # query parameter name.
    py_src = Path(mission_control.__file__).read_text(encoding="utf-8")
    assert "lifecycle_bucket: str = Query(" in py_src
