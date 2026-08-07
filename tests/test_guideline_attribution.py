"""Tests for guideline author/publisher attribution helpers."""

from __future__ import annotations

from libs.guidance.guideline_attribution import (
    format_guideline_attribution,
    resolve_guideline_author,
)


def test_resolve_guideline_author_from_explicit_publisher() -> None:
    assert resolve_guideline_author(guideline_publisher="NICE") == "NICE"


def test_resolve_guideline_author_from_nice_code() -> None:
    assert resolve_guideline_author(guideline_id="NG12") == "NICE"


def test_resolve_guideline_author_from_nice_source() -> None:
    assert resolve_guideline_author(
        guideline_id="CUSTOM-1",
        guideline_source="nice_syndication_api",
    ) == "NICE"


def test_resolve_guideline_author_local_source() -> None:
    assert resolve_guideline_author(
        guideline_id="SEL-MSK-01",
        guideline_source="local_guideline",
    ) == "Local"


def test_format_guideline_attribution_includes_nice_author() -> None:
    assert (
        format_guideline_attribution(
            guideline_id="NG12",
            guideline_title="Suspected cancer: recognition and referral",
        )
        == "**Guideline:** NICE Suspected cancer: recognition and referral (`NG12`)"
    )


def test_format_guideline_attribution_does_not_double_prefix() -> None:
    assert (
        format_guideline_attribution(
            guideline_id="NG12",
            guideline_title="NICE Suspected cancer: recognition and referral",
            guideline_publisher="NICE",
        )
        == "**Guideline:** NICE Suspected cancer: recognition and referral (`NG12`)"
    )
