"""Per-site scope tests for shadow_run.compare_episode_lists_by_site."""

from __future__ import annotations

from libs.episode_learning.shadow_run import compare_episode_lists_by_site


def test_per_site_split_scores_independently() -> None:
    v1 = {"breast": ["ep-b1"], "lung": ["ep-l1", "ep-l2"]}
    v2 = {"breast": ["ep-b1"], "lung": ["ep-l1"]}
    result = compare_episode_lists_by_site(v1, v2)
    assert set(result.keys()) == {"breast", "lung"}
    assert result["breast"]["agreement"] == 1.0
    assert result["lung"]["agreement"] < 1.0
    assert result["lung"]["dropped_in_v2"] == ["ep-l2"]


def test_site_missing_on_one_side_treated_as_empty() -> None:
    v1 = {"breast": ["ep-b1"]}
    v2 = {"lung": ["ep-l1"]}
    result = compare_episode_lists_by_site(v1, v2)
    assert result["breast"]["dropped_in_v2"] == ["ep-b1"]
    assert result["lung"]["added_in_v2"] == ["ep-l1"]
