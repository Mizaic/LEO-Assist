"""VT-LEO-AI-403 -- Pattern N2 same-day referral collapse.

Verifies the ``collapse_same_day_referrals`` helper in
``services/analysis_worker/app/analyzers/episode_builder/_milestone_dedup.py``
correctly collapses multiple same-date referral anchors inside a
single episode's link-group list while leaving genuinely
distinct same-day milestones, single-anchor groups, non-referral
milestones, and dateless anchors unchanged.

DI-LEO-AI-403 / DO-LEO-AI-403 / R-LEO-AI-403 / VT-LEO-AI-403.
"""

from __future__ import annotations

from typing import Any

import pytest

from services.analysis_worker.app.analyzers.episode_builder._milestone_dedup import (
    REFERRAL_SUBTYPE_PRIORITY,
    _referral_subtype_rank,
    collapse_same_day_referrals,
)


def _ref(
    encounter_id: str,
    encounter_date: str,
    referral_subtype: str | None = None,
    created_at: str = "",
) -> dict[str, Any]:
    return {
        "encounter_id": encounter_id,
        "encounter_date": encounter_date,
        "referral_subtype": referral_subtype,
        "created_at": created_at,
    }


# -- _referral_subtype_rank ------------------------------------------------


class TestReferralSubtypeRank:
    """VT-403-TC-001 .. TC-005 helper unit tests."""

    def test_prism_is_top_priority(self) -> None:
        assert _referral_subtype_rank("prism") == 0

    def test_form_field_is_middle_priority(self) -> None:
        assert _referral_subtype_rank("form_field") == 1

    def test_text_generic_is_lowest_listed(self) -> None:
        assert _referral_subtype_rank("text_generic") == 2

    def test_unknown_subtype_falls_below_text_generic(self) -> None:
        assert _referral_subtype_rank("hospital_letter") == len(
            REFERRAL_SUBTYPE_PRIORITY
        )

    def test_none_or_empty_falls_below_text_generic(self) -> None:
        assert _referral_subtype_rank(None) == len(REFERRAL_SUBTYPE_PRIORITY)
        assert _referral_subtype_rank("") == len(REFERRAL_SUBTYPE_PRIORITY)


# -- collapse_same_day_referrals -------------------------------------------


class TestCollapseSameDayReferrals:
    """VT-403-TC-006 .. TC-021 collapse helper behaviour."""

    def test_canonical_9990003001_three_referrals_collapse_to_prism(self) -> None:
        """The exact patient 9990003001 2025-03-26 case: prism +
        text_generic + text_generic -> keep the prism one."""
        link_groups = [
            (
                [
                    _ref("text_a", "2025-03-26", "text_generic"),
                    _ref("prism_b", "2025-03-26", "prism"),
                    _ref("text_c", "2025-03-26", "text_generic"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert len(result) == 1
        kept_anchors, milestone = result[0]
        assert milestone == "referral"
        assert len(kept_anchors) == 1
        assert kept_anchors[0]["encounter_id"] == "prism_b"

    def test_form_field_kept_over_text_generic(self) -> None:
        link_groups = [
            (
                [
                    _ref("t1", "2025-04-01", "text_generic"),
                    _ref("f1", "2025-04-01", "form_field"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert [a["encounter_id"] for a in result[0][0]] == ["f1"]

    def test_prism_kept_over_form_field(self) -> None:
        link_groups = [
            (
                [
                    _ref("f1", "2025-04-01", "form_field"),
                    _ref("p1", "2025-04-01", "prism"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert [a["encounter_id"] for a in result[0][0]] == ["p1"]

    def test_distinct_dates_both_kept(self) -> None:
        """Two genuinely distinct referrals on different dates within
        the same episode must BOTH survive."""
        link_groups = [
            (
                [
                    _ref("e1", "2025-03-26", "prism"),
                    _ref("e2", "2025-04-15", "text_generic"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        kept_ids = sorted(a["encounter_id"] for a in result[0][0])
        assert kept_ids == ["e1", "e2"]

    def test_single_anchor_passes_through_untouched(self) -> None:
        link_groups = [
            ([_ref("e1", "2025-03-26", "prism")], "referral"),
        ]
        result = collapse_same_day_referrals(link_groups)
        assert result == link_groups

    def test_empty_anchor_list_preserved(self) -> None:
        link_groups = [([], "referral")]
        result = collapse_same_day_referrals(link_groups)
        assert result == link_groups

    def test_empty_link_groups_returns_empty(self) -> None:
        assert collapse_same_day_referrals([]) == []

    def test_non_referral_milestone_unaffected(self) -> None:
        """diagnosis_confirmed, treatment_started, first_seen,
        first_presentation, care_obstruction must NOT be deduped by
        N2 (they have their own existing dedup semantics)."""
        link_groups = [
            (
                [
                    _ref("d1", "2025-05-19"),
                    _ref("d2", "2025-05-19"),
                ],
                "diagnosis_confirmed",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert len(result[0][0]) == 2

    def test_referral_and_non_referral_groups_processed_independently(self) -> None:
        link_groups = [
            (
                [
                    _ref("r1", "2025-03-26", "prism"),
                    _ref("r2", "2025-03-26", "text_generic"),
                ],
                "referral",
            ),
            (
                [
                    _ref("d1", "2025-05-19"),
                    _ref("d2", "2025-05-19"),
                ],
                "diagnosis_confirmed",
            ),
        ]
        result = collapse_same_day_referrals(link_groups)
        ref_kept = [a["encounter_id"] for a in result[0][0]]
        diag_kept = [a["encounter_id"] for a in result[1][0]]
        assert ref_kept == ["r1"]
        assert diag_kept == ["d1", "d2"]

    def test_dateless_anchor_passes_through(self) -> None:
        """An anchor with no encounter_date is never silently
        dropped -- pass it through for downstream visibility."""
        link_groups = [
            (
                [
                    _ref("e1", "", "text_generic"),
                    _ref("e2", "2025-03-26", "prism"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        kept_ids = sorted(a["encounter_id"] for a in result[0][0])
        assert kept_ids == ["e1", "e2"]

    def test_unknown_subtype_loses_to_listed_subtype(self) -> None:
        link_groups = [
            (
                [
                    _ref("u1", "2025-03-26", "hospital_letter"),
                    _ref("t1", "2025-03-26", "text_generic"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert [a["encounter_id"] for a in result[0][0]] == ["t1"]

    def test_two_unknown_subtypes_pick_first_in_input(self) -> None:
        link_groups = [
            (
                [
                    _ref("u1", "2025-03-26", "hospital_letter"),
                    _ref("u2", "2025-03-26", "self_referral"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert [a["encounter_id"] for a in result[0][0]] == ["u1"]

    def test_same_subtype_earlier_created_at_wins(self) -> None:
        link_groups = [
            (
                [
                    _ref("late", "2025-03-26", "prism", created_at="2025-03-26T15:00:00Z"),
                    _ref("early", "2025-03-26", "prism", created_at="2025-03-26T11:46:00Z"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        assert [a["encounter_id"] for a in result[0][0]] == ["early"]

    def test_input_list_not_mutated(self) -> None:
        anchors = [
            _ref("a", "2025-03-26", "text_generic"),
            _ref("b", "2025-03-26", "prism"),
        ]
        link_groups = [(anchors, "referral")]
        original_ids = [a["encounter_id"] for a in anchors]
        collapse_same_day_referrals(link_groups)
        assert [a["encounter_id"] for a in anchors] == original_ids

    def test_input_anchor_dicts_not_mutated(self) -> None:
        anchors = [_ref("a", "2025-03-26", "prism", "ts1")]
        link_groups = [(anchors, "referral")]
        result = collapse_same_day_referrals(link_groups)
        assert result[0][0][0] is anchors[0]
        assert anchors[0] == {
            "encounter_id": "a",
            "encounter_date": "2025-03-26",
            "referral_subtype": "prism",
            "created_at": "ts1",
        }

    def test_opt_in_milestone_types_widens_collapse_to_diagnosis(self) -> None:
        """The default collapses only referrals, but callers can opt
        diagnosis_confirmed in if they want -- this guards the
        public API surface."""
        link_groups = [
            (
                [
                    _ref("d1", "2025-05-19", "text_generic"),
                    _ref("d2", "2025-05-19", "prism"),
                ],
                "diagnosis_confirmed",
            )
        ]
        result_default = collapse_same_day_referrals(link_groups)
        assert len(result_default[0][0]) == 2

        result_opt_in = collapse_same_day_referrals(
            link_groups,
            milestone_types=("referral", "diagnosis_confirmed"),
        )
        assert [a["encounter_id"] for a in result_opt_in[0][0]] == ["d2"]

    def test_three_dates_each_with_duplicates_collapses_each_date(self) -> None:
        link_groups = [
            (
                [
                    _ref("a1", "2025-03-26", "prism"),
                    _ref("a2", "2025-03-26", "text_generic"),
                    _ref("b1", "2025-04-15", "text_generic"),
                    _ref("b2", "2025-04-15", "text_generic"),
                    _ref("c1", "2025-05-01", "form_field"),
                ],
                "referral",
            )
        ]
        result = collapse_same_day_referrals(link_groups)
        kept_ids = sorted(a["encounter_id"] for a in result[0][0])
        # First text_generic of 2025-04-15 wins on input order.
        assert kept_ids == ["a1", "b1", "c1"]


# -- integration safety net ------------------------------------------------


@pytest.mark.parametrize(
    "subtype",
    REFERRAL_SUBTYPE_PRIORITY,
)
def test_single_subtype_anchor_is_not_dropped(subtype: str) -> None:
    """No matter which subtype, a sole anchor always survives.
    Guards against regressions where the helper accidentally
    drops every anchor."""
    link_groups = [([_ref("e1", "2025-03-26", subtype)], "referral")]
    result = collapse_same_day_referrals(link_groups)
    assert len(result[0][0]) == 1
    assert result[0][0][0]["encounter_id"] == "e1"
