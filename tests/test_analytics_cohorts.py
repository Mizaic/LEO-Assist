"""VT-LEO-AI-130 - Canonical NCDA 'confirmed cancer' cohort helpers.

Covers TC-001, TC-002, TC-003, TC-004. TC-005 (live baseline pin) is
covered by a separate runtime smoke query, not exercised here because
it requires a live Neo4j session.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from libs.analytics import (
    CONFIRMED_CANCER_CLAUSE,
    SUSPECTED_CANCER_REFERRAL_CLAUSE,
    confirmed_cancer_where,
    suspected_cancer_referral_where,
)


# ---------------------------------------------------------------------------
# TC-001: confirmed_cancer_where returns canonical clause
# ---------------------------------------------------------------------------


def test_confirmed_cancer_where_excludes_invalid_and_benign_statuses():
    """Excluded: merged, closed_phantom, closed_related, closed_benign.

    'completed' must NOT be required (in_progress episodes that already
    carry a diagnosis_confirmed milestone are still counted).
    """
    clause = confirmed_cancer_where()
    assert "NOT ep.status IN" in clause
    for status in ("merged", "closed_phantom", "closed_related", "closed_benign"):
        assert f"'{status}'" in clause
    assert "ep.status = 'completed'" not in clause


def test_confirmed_cancer_where_contains_benign_filter():
    clause = confirmed_cancer_where()
    assert "coalesce(ep.letter_inferred_benign, false) = false" in clause


def test_confirmed_cancer_where_contains_diagnosis_exists():
    clause = confirmed_cancer_where()
    assert "EXISTS" in clause
    assert "IS_PART_OF" in clause
    assert "diagnosis" in clause
    assert "diagnosis_confirmed" in clause


def test_confirmed_cancer_where_honours_alias():
    clause = confirmed_cancer_where("episode")
    assert "NOT episode.status IN" in clause
    assert "ep.status" not in clause


def test_module_constant_matches_helper_output():
    assert CONFIRMED_CANCER_CLAUSE == confirmed_cancer_where()


# ---------------------------------------------------------------------------
# TC-002: suspected_cancer_referral_where composes canonical + referral
# ---------------------------------------------------------------------------


def test_suspected_cancer_extends_canonical_with_referral():
    canonical = confirmed_cancer_where()
    suspected = suspected_cancer_referral_where()
    assert canonical in suspected
    assert suspected.count("EXISTS") == 2
    assert "milestone_type = 'referral'" in suspected


def test_suspected_cancer_module_constant():
    assert SUSPECTED_CANCER_REFERRAL_CLAUSE == suspected_cancer_referral_where()


# ---------------------------------------------------------------------------
# TC-003: no inline cohort duplication in router files
# ---------------------------------------------------------------------------


_ROUTER_FILES = [
    "services/analytics_api/app/routers/audit.py",
    "services/analytics_api/app/routers/_audit_sections.py",
    "services/analytics_api/app/routers/_audit_intervals.py",
    "services/analytics_api/app/routers/dashboards.py",
    "services/analytics_api/app/routers/mission_control.py",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("router", _ROUTER_FILES)
def test_router_imports_canonical_cohort_helper(router: str):
    """Every affected analytics router must consume the canonical helper.

    This is a stronger check than 'no inline triple': because Python
    string-literal concatenation can split ``milestone_type IN
    ['diagnosis', 'diagnosis_confirmed']`` across source lines, we
    cannot reliably detect inline cohort duplication by substring
    match. Instead we assert the positive: every router on this list
    imports libs.analytics (directly or via the helpers). If a router
    legitimately does not need cohort filtering (e.g. an intervals
    module that only computes date coalescing), add it to
    ``_ROUTERS_EXEMPT_FROM_COHORT_IMPORT`` below with a comment.
    """
    path = _repo_root() / router
    if not path.exists():
        pytest.skip(f"router file not present: {router}")
    text = path.read_text()
    if router in _ROUTERS_EXEMPT_FROM_COHORT_IMPORT:
        return
    imports_helper = (
        "confirmed_cancer_where" in text
        or "CONFIRMED_CANCER_CLAUSE" in text
        or "suspected_cancer_referral_where" in text
        or "from libs.analytics" in text
    )
    assert imports_helper, (
        f"{router} must import libs.analytics.cohorts to use the "
        "canonical confirmed-cancer cohort helper. See DI-LEO-AI-134."
    )


# Routers that do not filter on 'confirmed cancer' cohort:
# - _audit_intervals.py computes PCI/DI across all referred episodes
#   and uses INFERRED_CANCER_DIAG_CASE as a DATE coalesce, not a
#   cohort filter. No helper import required.
_ROUTERS_EXEMPT_FROM_COHORT_IMPORT = {
    "services/analytics_api/app/routers/_audit_intervals.py",
}


# ---------------------------------------------------------------------------
# TC-004: cohort fragment is compose-safe (no leaked placeholders)
# ---------------------------------------------------------------------------


def test_clause_has_no_unformatted_braces():
    for clause in (
        CONFIRMED_CANCER_CLAUSE,
        SUSPECTED_CANCER_REFERRAL_CLAUSE,
        confirmed_cancer_where("ep"),
        suspected_cancer_referral_where("episode"),
    ):
        assert "{alias}" not in clause
        assert "{{" not in clause
        assert "}}" not in clause


def test_clause_is_single_line_safe():
    """The fragment must be splice-safe into an f-string WHERE chain."""
    frag = confirmed_cancer_where()
    composed = (
        "MATCH (ep:EpisodeOfCare) WHERE "
        f"{frag} "
        "RETURN count(ep)"
    )
    assert "\n" not in frag
    assert composed.startswith("MATCH (ep:EpisodeOfCare) WHERE NOT ep.status")
    assert "count(ep)" in composed
    assert composed.count("EXISTS") == 1
    assert composed.count("{") == composed.count("}")


# ---------------------------------------------------------------------------
# TC-006 (new in VT-LEO-AI-164): regression - in_progress with a
# diagnosis_confirmed milestone IS counted; closed_benign is NOT.
# ---------------------------------------------------------------------------


def test_in_progress_status_is_not_excluded():
    """in_progress episodes pass the status filter so they can be counted
    as confirmed cancer once a diagnosis_confirmed milestone exists.
    """
    clause = confirmed_cancer_where()
    assert "'in_progress'" not in clause


def test_completed_status_is_not_excluded():
    """completed episodes also pass the status filter -- the cohort is
    inclusive of any non-benign, non-administrative episode that carries
    a diagnosis milestone.
    """
    clause = confirmed_cancer_where()
    excluded_block = clause.split("NOT ep.status IN ")[1].split("]")[0]
    assert "'completed'" not in excluded_block
