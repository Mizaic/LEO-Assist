"""Tests for NiceGraphUpserter -- VT-LEO-AI-063.

Graph model asserted by these tests:

    (Guideline)-[:HAS_CHAPTER]->(Chapter)-[:HAS_RECOMMENDATION]->(Recommendation)
    (Guideline)-[:HAS_RECOMMENDATION]->(Recommendation)  # shortcut edge for bitmap compiler

Versioning contract:
    - upsert_guideline() returns (id, version) tuple.
    - Version is embedded in child node IDs: NG151:v1:CH000:R000.
    - clear_guideline_content() marks rules as 'superseded' and detaches
      shortcut edges — it never deletes AppropriatenessRule or audit nodes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from app.services.nice_graph_upserter import (
    NiceGraphUpserter,
    _extract_code,
    _extract_urgency,
    _extract_strength,
)


def _make_session_mock(return_value=None, version=1):
    """Return a mock Neo4j session context manager.

    The mock returns a record containing both ``id`` and ``version`` so that
    ``upsert_guideline()`` can unpack them as a tuple.
    """
    session = MagicMock()
    result = MagicMock()
    result.single.return_value = {"id": return_value or "NG151", "version": version}
    session.run.return_value = result
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    return session, ctx


@pytest.fixture()
def upserter():
    return NiceGraphUpserter()


def test_upsert_guideline_is_idempotent(upserter):
    """Calling upsert_guideline twice uses MERGE and returns (id, version) tuples."""
    guidance = {
        "GuidanceNumber": "NG151",
        "Title": "Bowel cancer: recognition, referral and review",
        "Type": "clinical-guideline",
        "PublicationDate": "2023-01-01",
    }
    session, ctx = _make_session_mock("NG151", version=1)

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        result1 = upserter.upsert_guideline(guidance)
        result2 = upserter.upsert_guideline(guidance)

    assert result1 == ("NG151", 1)
    assert result2 == ("NG151", 1)
    assert session.run.call_count == 2
    query_text = session.run.call_args_list[0][0][0]
    assert "MERGE" in query_text
    assert "ingestVersion" in query_text


def test_upsert_guideline_sets_source_field(upserter):
    """Guideline node is created with source = nice_syndication_api."""
    guidance = {"GuidanceNumber": "CG89", "Title": "Test", "Type": "cg"}
    session, ctx = _make_session_mock("CG89", version=1)

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv
        upserter.upsert_guideline(guidance)

    cypher = session.run.call_args[0][0]
    assert "nice_syndication_api" in cypher


def test_upsert_recommendation_links_to_guideline(upserter):
    """Recommendation node is MERGEd and linked to parent Guideline via version-scoped ID."""
    rec = {"Title": "1.1.1", "Text": "Refer if rectal bleeding > 50."}
    rec_id = "NG151:v1:CH000:R000"
    session, ctx = _make_session_mock(rec_id)

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        result = upserter.upsert_recommendation(
            "NG151", rec_id, rec, version_id="NG151:v1"
        )

    assert result == rec_id
    cypher = session.run.call_args[0][0]
    assert "HAS_RECOMMENDATION" in cypher


def test_upsert_recommendation_links_to_chapter_when_chapter_id_given(upserter):
    """When chapter_id is supplied, the Recommendation is also linked to its Chapter."""
    rec = {
        "Title": "1.1.1",
        "Text": "Offer urgent referral for suspected colorectal cancer.",
    }
    session, ctx = _make_session_mock("NG151:v1:CH000:R000")

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        upserter.upsert_recommendation(
            "NG151",
            "NG151:v1:CH000:R000",
            rec,
            chapter_id="NG151:v1:CH000",
            version_id="NG151:v1",
        )

    cypher = session.run.call_args[0][0]
    # FOREACH block in the Cypher creates the Chapter→Recommendation edge
    assert "FOREACH" in cypher
    kwargs = session.run.call_args[1]
    assert kwargs.get("chapter_id") == "NG151:v1:CH000"


def test_upsert_chapter_creates_chapter_node(upserter):
    """upsert_chapter creates a version-scoped Chapter node linked to the parent Guideline."""
    chapter_id = "NG151:v1:CH000"
    session, ctx = _make_session_mock(chapter_id)

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        result = upserter.upsert_chapter(
            "NG151", chapter_id, "Recommendations", 0, version_id="NG151:v1"
        )

    assert result == chapter_id
    cypher = session.run.call_args[0][0]
    assert "HAS_CHAPTER" in cypher
    assert "MERGE (ch:Chapter" in cypher
    kwargs = session.run.call_args[1]
    assert kwargs.get("version_id") == "NG151:v1"


def test_clear_guideline_content_supersedes_rules_not_deletes(upserter):
    """clear_guideline_content marks rules as 'superseded' without deleting nodes.

    Regulatory requirement: AppropriatenessRule nodes and their GuidanceAuditEvent
    children must never be deleted.  clear_guideline_content must:
    1. Run a query that sets rule.status = 'superseded'.
    2. Run a query that removes HAS_CHAPTER / HAS_RECOMMENDATION shortcut edges.
    It must NOT run DETACH DELETE on Chapter or Recommendation nodes.
    """
    # First call (supersede rules) returns a count; second call (detach links) returns None.
    supersede_result = MagicMock()
    supersede_result.single.return_value = {"superseded_count": 3}
    detach_result = MagicMock()
    detach_result.single.return_value = None

    session = MagicMock()
    session.run.side_effect = [supersede_result, detach_result]
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        superseded = upserter.clear_guideline_content("NG151")

    assert superseded == 3
    assert session.run.call_count == 2

    cyphers = [call[0][0] for call in session.run.call_args_list]
    # First query marks rules superseded (never deletes them)
    assert "superseded" in cyphers[0].lower()
    assert "DETACH DELETE" not in cyphers[0]
    # Second query removes the shortcut edges
    assert "DELETE hch" in cyphers[1] or "DELETE" in cyphers[1]
    assert "DETACH DELETE" not in cyphers[1]


def test_upsert_taxonomy_creates_category_subcategory_and_domain(upserter):
    """upsert_taxonomy creates TaxonomyCategory, TaxonomySubcategory, and AuditDomain nodes."""
    session = MagicMock()
    session.run.return_value = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)

    taxonomy_entries = [
        {
            "category_id": "conditions-and-diseases",
            "category_title": "Conditions and diseases",
            "subcategory_id": "conditions-and-diseases:cancer",
            "subcategory_title": "Cancer",
            "subcategory_uri": "https://api.nice.org.uk/services/guidance/taxonomy/cancer.json",
            "guideline_codes": ["NG12", "NG151"],
        }
    ]

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        counts = upserter.upsert_taxonomy(taxonomy_entries)

    assert counts["categories"] == 1
    assert counts["subcategories"] == 1
    assert counts["domains"] == 1

    cypher_calls = [call[0][0] for call in session.run.call_args_list]
    assert any(
        "TaxonomyCategory" in c for c in cypher_calls
    ), "Should upsert TaxonomyCategory"
    assert any(
        "TaxonomySubcategory" in c for c in cypher_calls
    ), "Should upsert TaxonomySubcategory"
    assert any(
        "AuditDomain" in c and "nice" in c for c in cypher_calls
    ), "Should upsert AuditDomain with source=nice"
    assert any(
        "CLASSIFIES_GUIDELINE" in c for c in cypher_calls
    ), "Should link guidelines to subcategory"


def test_upsert_taxonomy_handles_empty_list(upserter):
    """upsert_taxonomy returns zero counts for empty input without error."""
    session = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        counts = upserter.upsert_taxonomy([])

    assert counts == {"categories": 0, "subcategories": 0, "domains": 0}
    session.run.assert_not_called()


def test_upsert_taxonomy_deduplicates_categories(upserter):
    """upsert_taxonomy only creates a category node once even with multiple subcategories."""
    session = MagicMock()
    session.run.return_value = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)

    taxonomy_entries = [
        {
            "category_id": "conditions-and-diseases",
            "category_title": "Conditions and diseases",
            "subcategory_id": "conditions-and-diseases:cancer",
            "subcategory_title": "Cancer",
            "subcategory_uri": "",
            "guideline_codes": [],
        },
        {
            "category_id": "conditions-and-diseases",
            "category_title": "Conditions and diseases",
            "subcategory_id": "conditions-and-diseases:diabetes",
            "subcategory_title": "Diabetes",
            "subcategory_uri": "",
            "guideline_codes": [],
        },
    ]

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv

        counts = upserter.upsert_taxonomy(taxonomy_entries)

    assert counts["categories"] == 1, "Category should only be counted once"
    assert counts["subcategories"] == 2
    assert counts["domains"] == 2

    # Only the MERGE (c:TaxonomyCategory ...) upsert counts -- not subcategory
    # Cypher that references TaxonomyCategory in its MATCH clause.
    cat_calls = [
        c
        for c in [call[0][0] for call in session.run.call_args_list]
        if "MERGE (c:TaxonomyCategory" in c
    ]
    assert len(cat_calls) == 1, "TaxonomyCategory Cypher should run only once"


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


def test_upsert_taxonomy_stores_guideline_codes_on_subcategory(upserter):
    """upsert_taxonomy passes guideline_codes list to the TaxonomySubcategory Cypher.

    Ensures the taxonomy browser can read codes back from Neo4j without
    relying on CLASSIFIES_GUIDELINE relationships (which only exist for
    fully-imported guidelines).
    """
    session = MagicMock()
    session.run.return_value = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)

    taxonomy_entries = [
        {
            "category_id": "conditions",
            "category_title": "Conditions",
            "subcategory_id": "conditions:cancer",
            "subcategory_title": "Cancer",
            "subcategory_uri": "https://example.com/cancer.json",
            "guideline_codes": ["NG12", "NG151", "CG89"],
        }
    ]

    with patch("app.services.nice_graph_upserter._kg_driver") as mock_driver:
        mock_drv = MagicMock()
        mock_drv.session.return_value = ctx
        mock_drv.close = MagicMock()
        mock_driver.return_value = mock_drv
        upserter.upsert_taxonomy(taxonomy_entries)

    # Find the TaxonomySubcategory upsert call and verify guideline_codes was passed
    subcategory_calls = [
        call
        for call in session.run.call_args_list
        if "TaxonomySubcategory" in call[0][0]
    ]
    assert subcategory_calls, "No TaxonomySubcategory Cypher call found"
    kwargs = subcategory_calls[0][1]
    assert kwargs.get("guideline_codes") == ["NG12", "NG151", "CG89"]
