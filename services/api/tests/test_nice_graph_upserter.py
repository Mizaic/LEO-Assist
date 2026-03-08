"""Tests for NiceGraphUpserter -- VT-LEO-AI-063."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.nice_graph_upserter import (
    NiceGraphUpserter,
    _extract_code,
    _extract_urgency,
    _extract_strength,
)


def _make_session_mock(return_value=None):
    """Return a mock Neo4j session context manager."""
    session = MagicMock()
    result = MagicMock()
    result.single.return_value = {"id": return_value or "NG151"}
    session.run.return_value = result
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    return session, ctx


@pytest.fixture()
def upserter():
    return NiceGraphUpserter()


def test_upsert_guideline_is_idempotent(upserter):
    """Calling upsert_guideline twice uses MERGE -- only one node created."""
    guidance = {
        "GuidanceNumber": "NG151",
        "Title": "Bowel cancer: recognition, referral and review",
        "Type": "clinical-guideline",
        "PublicationDate": "2023-01-01",
    }
    session, ctx = _make_session_mock("NG151")

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        result1 = upserter.upsert_guideline(guidance)
        result2 = upserter.upsert_guideline(guidance)

    assert result1 == "NG151"
    assert result2 == "NG151"
    assert session.run.call_count == 2
    query_text = session.run.call_args_list[0][0][0]
    assert "MERGE" in query_text


def test_upsert_guideline_sets_source_field(upserter):
    """Guideline node is created with source = nice_syndication_api."""
    guidance = {"GuidanceNumber": "CG89", "Title": "Test", "Type": "cg"}
    session, ctx = _make_session_mock("CG89")

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv
        upserter.upsert_guideline(guidance)

    cypher = session.run.call_args[0][0]
    assert "nice_syndication_api" in cypher


def test_upsert_recommendation_links_to_guideline(upserter):
    """Recommendation node is MERGEd and linked to parent Guideline."""
    rec = {"Title": "Refer urgently", "Text": "Refer if rectal bleeding > 50."}
    session, ctx = _make_session_mock("NG151:R000")

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        result = upserter.upsert_recommendation("NG151", "NG151:R000", rec)

    assert result == "NG151:R000"
    cypher = session.run.call_args[0][0]
    assert "HAS_RECOMMENDATION" in cypher


def test_upsert_section_creates_section_node(upserter):
    """Section node is created and linked to parent Guideline."""
    section = {"Title": "Recommendations", "Href": "/ch1"}
    session, ctx = _make_session_mock("NG151:S000")
    session.run.return_value = MagicMock()

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        upserter.upsert_section("NG151", section, 0)

    cypher = session.run.call_args[0][0]
    assert "HAS_SECTION" in cypher


@pytest.mark.parametrize(
    "guidance_json,expected",
    [
        ({"GuidanceNumber": "NG151"}, "NG151"),
        ({"Code": "cg89"}, "CG89"),
        ({}, "UNKNOWN"),
    ],
)
def test_extract_code(guidance_json, expected):
    assert _extract_code(guidance_json) == expected


@pytest.mark.parametrize(
    "rec,expected",
    [
        ({"Title": "2-week referral for suspected bowel cancer"}, "urgent_2w"),
        ({"Title": "Immediate referral for bowel obstruction"}, "immediate"),
        ({"Title": "Consider routine investigation"}, "routine"),
    ],
)
def test_extract_urgency(rec, expected):
    assert _extract_urgency(rec) == expected


@pytest.mark.parametrize(
    "rec,expected",
    [
        ({"Title": "Refer patients with rectal bleeding"}, "refer"),
        ({"Title": "Consider colonoscopy"}, "consider"),
        ({"Title": "Offer support"}, "offer"),
    ],
)
def test_extract_strength(rec, expected):
    assert _extract_strength(rec) == expected
