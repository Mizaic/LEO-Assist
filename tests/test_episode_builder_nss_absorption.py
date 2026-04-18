"""Regression tests for the NSS-into-typed-group absorption pattern.

DI-LEO-AI-196: when an open referral cluster contains both a typed
(e.g. lung) referral anchor and an unsited / non_site_specific
referral anchor within SAME_EPISODE_DAYS, the unsited referral must
be absorbed into the typed group at create time -- preventing
phantom NSS EpisodeOfCare nodes that the duplicate resolver
immediately merges away. Pattern level: applies to ANY 2WW pathway
with mixed typed + unsited referral text in the same week.
"""

from __future__ import annotations

import pytest


def _ref(date: str, site_key: str, encounter_id: str) -> dict:
    return {
        "encounter_id": encounter_id,
        "encounter_date": date,
        "site_key": site_key,
        "site_hits": [site_key] if site_key not in ("", "non_site_specific") else [],
        "milestone_type": "referral",
        "confidence": 0.8,
    }


class TestNssAbsorption:

    def test_nss_same_day_as_typed_is_absorbed(self):
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            _ref("2024-04-09", "non_site_specific", "E2"),
        ]
        groups = _group_open_referrals(unclaimed)

        assert len(groups) == 1
        site_key, group = groups[0]
        assert site_key == "lung"
        assert {a["encounter_id"] for a in group} == {"E1", "E2"}

    def test_nss_within_same_episode_window_is_absorbed(self):
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            _ref("2024-04-15", "non_site_specific", "E2"),
        ]
        groups = _group_open_referrals(unclaimed)

        assert len(groups) == 1
        site_key, group = groups[0]
        assert site_key == "lung"
        assert {a["encounter_id"] for a in group} == {"E1", "E2"}

    def test_nss_far_outside_window_is_kept_separate(self):
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            _ref("2025-04-09", "non_site_specific", "E2"),
        ]
        groups = _group_open_referrals(unclaimed)

        assert len(groups) == 2
        keys = sorted(k for k, _ in groups)
        assert keys == ["lung", "non_site_specific"]

    def test_nss_absorbed_into_closest_typed_group(self):
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            _ref("2024-10-31", "breast", "E2"),
            _ref("2024-11-02", "non_site_specific", "E3"),
        ]
        groups = _group_open_referrals(unclaimed)

        assert len(groups) == 2
        breast_group = [g for k, g in groups if k == "breast"][0]
        lung_group = [g for k, g in groups if k == "lung"][0]
        assert {a["encounter_id"] for a in breast_group} == {"E2", "E3"}
        assert {a["encounter_id"] for a in lung_group} == {"E1"}

    def test_only_typed_groups_unchanged(self):
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            _ref("2024-10-31", "breast", "E2"),
        ]
        groups = _group_open_referrals(unclaimed)

        keys = sorted(k for k, _ in groups)
        assert keys == ["breast", "lung"]

    def test_only_nss_groups_unchanged(self):
        """When there is no typed group at all, NSS groups stand alone."""
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "non_site_specific", "E1"),
            _ref("2024-04-10", "non_site_specific", "E2"),
        ]
        groups = _group_open_referrals(unclaimed)

        assert len(groups) == 1
        site_key, group = groups[0]
        assert site_key == "non_site_specific"
        assert {a["encounter_id"] for a in group} == {"E1", "E2"}

    def test_unknown_key_treated_like_nss(self):
        """An anchor whose site_key extracts to 'unknown' must also be
        absorbed into a temporally-overlapping typed group."""
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            _ref("2024-04-10", "unknown", "E2"),
        ]
        groups = _group_open_referrals(unclaimed)

        assert len(groups) == 1
        site_key, group = groups[0]
        assert site_key == "lung"
        assert {a["encounter_id"] for a in group} == {"E1", "E2"}

    def test_anchor_without_date_does_not_crash(self):
        from services.analysis_worker.app.analyzers.episode_builder._grouping import (
            _group_open_referrals,
        )

        unclaimed = [
            _ref("2024-04-09", "lung", "E1"),
            {**_ref("", "non_site_specific", "E2"), "encounter_date": ""},
        ]
        groups = _group_open_referrals(unclaimed)

        assert any(k == "lung" for k, _ in groups)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
