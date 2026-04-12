from __future__ import annotations

from services.analytics_api.app.services.encounter_query_understanding import (
    understand_query,
)


def test_understand_query_applies_typo_normalization():
    result = understand_query("breat lump and wight loss")
    assert "breast" in result.normalized_query
    assert "weight" in result.normalized_query
    assert "lump" in result.normalized_query
    assert result.fulltext_query
    assert result.expanded_terms


def test_understand_query_without_llm_is_fail_open():
    result = understand_query("neck lump 2ww referral")
    assert result.original_query == "neck lump 2ww referral"
    assert result.rewrite_source in {"deterministic", "haiku"}
    assert isinstance(result.rewrite_applied, bool)
