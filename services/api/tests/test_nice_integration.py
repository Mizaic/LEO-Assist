"""Integration tests for the NICE Syndication API client.

These tests call the **live** NICE API and require a valid ``NICE_API_KEY``
environment variable. They are excluded from CI by default.

Run with:
    pytest -m integration services/api/tests/test_nice_integration.py -v

Skip in CI with:
    pytest -m "not integration" ...
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api_key_required() -> None:
    """Skip the whole module if NICE_API_KEY is not set."""
    if not os.getenv("NICE_API_KEY"):
        pytest.skip("NICE_API_KEY not set -- skipping NICE integration tests")


@pytest.fixture(scope="module")
def client(api_key_required):  # noqa: ARG001  -- fixture ensures key is set
    from app.services.nice_api_client import NiceApiClient
    return NiceApiClient()


# ---------------------------------------------------------------------------
# Guidance index search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_index_by_condition_name_returns_results(client):
    """Searching 'cancer' via the NICE guidance index returns at least one result."""
    results = await client.search_index("cancer")
    assert isinstance(results, list), "Expected a list from search_index"
    assert len(results) > 0, (
        "Expected at least one NICE guideline matching 'cancer'. "
        "If the API is unreachable, check NICE_API_KEY and network."
    )
    codes = [r["code"] for r in results]
    titles = [r["title"].lower() for r in results]
    # At least one result should mention cancer in its title
    assert any("cancer" in t for t in titles), (
        f"Expected 'cancer' in at least one title, got: {titles[:5]}"
    )
    assert all(r.get("code") for r in results), "Every result must have a code"


@pytest.mark.asyncio
async def test_search_index_by_condition_name_bowel(client):
    """Searching 'bowel' finds NG151 (Bowel cancer: recognition, referral and early diagnosis)."""
    results = await client.search_index("bowel")
    assert len(results) > 0, "Expected results for 'bowel'"
    codes = {r["code"] for r in results}
    # NG151 is the canonical bowel cancer recognition guideline
    assert "NG151" in codes or any("bowel" in r["title"].lower() for r in results), (
        f"Expected NG151 or bowel-related guideline in results, got: {results[:3]}"
    )


@pytest.mark.asyncio
async def test_search_index_by_nice_code(client):
    """Searching by exact NICE code returns that guideline."""
    results = await client.search_index("NG12")
    assert len(results) > 0, "Expected NG12 to be found by code search"
    codes = {r["code"] for r in results}
    assert "NG12" in codes, f"Expected NG12 in results, got: {codes}"


# ---------------------------------------------------------------------------
# Individual guideline fetch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_guidance_ng12_returns_title(client):
    """Fetching NG12 top-level doc returns a Title and GuidanceNumber."""
    doc = await client.get_guidance("NG12")
    assert doc.get("Title"), "Expected a Title in the NG12 guidance doc"
    assert doc.get("GuidanceNumber", "").upper() == "NG12" or doc.get("Code", "").upper() == "NG12", (
        f"Expected NG12 guidance number, got: {doc.get('GuidanceNumber')} / {doc.get('Code')}"
    )


@pytest.mark.asyncio
async def test_get_chapters_ng12_returns_at_least_one_chapter(client):
    """NG12 has at least one chapter link in its Resources."""
    chapters = await client.get_chapters("NG12")
    assert len(chapters) > 0, (
        "Expected at least one chapter for NG12. "
        "If Resources is empty, the API response structure may have changed."
    )
    assert all(c.get("Href") for c in chapters), (
        "Each chapter must have an Href link to follow"
    )


@pytest.mark.asyncio
async def test_get_recommendations_ng12_returns_items(client):
    """NG12 has recommendations accessible by walking chapter Href links."""
    recs = await client.get_recommendations("NG12")
    assert isinstance(recs, list), "get_recommendations must return a list"
    assert len(recs) > 0, (
        "Expected at least one recommendation for NG12 (Colorectal cancer prevention). "
        "The old /recommendations.json endpoint was broken -- this test validates the "
        "new chapter-walking approach."
    )
    for rec in recs:
        assert rec.get("Title") or rec.get("Text"), (
            f"Every recommendation must have Title or Text, got: {rec}"
        )


# ---------------------------------------------------------------------------
# Full index sync
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_catalogue_from_index_returns_guidelines(client):
    """sync_catalogue_from_index fetches the real NICE index and returns > 0 guidelines.

    Skips if Redis is not available -- the count is still returned even without Redis.
    """
    count = await client.sync_catalogue_from_index()
    assert count > 0, (
        "Expected at least one guideline from the NICE guidance index. "
        f"Got {count}. Check NICE_API_KEY and network connectivity."
    )
    assert count > 100, (
        f"NICE has 1000+ guidelines. Getting only {count} suggests pagination "
        "may have stopped early or the index response structure changed."
    )


# ---------------------------------------------------------------------------
# Catalogue / Redis (smoke test -- Redis may not be available)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_to_catalogue_and_fetch(client):
    """add_to_catalogue persists a guideline that fetch_catalogue returns.

    Skips if Redis is not available on localhost.
    """
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url("redis://localhost:6379")
        await r.ping()
        await r.aclose()
    except Exception:
        pytest.skip("Redis not available on localhost:6379")

    await client.add_to_catalogue("NG999", "Test guideline", "test")
    entries = await client.fetch_catalogue()
    assert any(e["code"] == "NG999" for e in entries), (
        "Expected NG999 to be in catalogue after add_to_catalogue"
    )
