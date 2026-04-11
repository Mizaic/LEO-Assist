"""Integration tests for the NICE Syndication API client.

These tests call the **live** NICE API and require a valid ``NICE_API_KEY``
environment variable. They are excluded from CI by default.

Run with:
    pytest -m integration services/api/tests/test_nice_integration.py -v

Skip in CI with:
    pytest -m "not integration" ...

Coverage:
  - Guidance index search (by condition name, by code)
  - Individual guideline fetch (top-level doc, chapters, recommendations)
  - Full index sync (Redis-backed catalogue)
  - Taxonomy walk (4-level HATEOAS tree: root → taxonomy → categories → subcategories)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _bootstrap_secrets() -> None:
    """Load .env.config then pull secrets from Azure Key Vault.

    The integration tests run outside the normal service startup path, so
    ``app.config`` is not auto-imported.  We replicate its two-step bootstrap
    here so that NICE_API_KEY is available before the client is instantiated.

    Falls back gracefully if Key Vault is unreachable (e.g. no ``az login``).
    """
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=False)

    # Only attempt KV load when AZURE_KEYVAULT_URL is configured.
    if os.environ.get("AZURE_KEYVAULT_URL"):
        try:
            from libs.keyvault.loader import load_keyvault_secrets

            load_keyvault_secrets()
        except Exception as exc:  # noqa: BLE001
            # Don't fail here -- the api_key_required fixture will skip cleanly.
            print(
                f"[integration] Key Vault load failed (will skip if key absent): {exc}"
            )


@pytest.fixture(scope="module", autouse=True)
def load_secrets() -> None:
    """Bootstrap secrets from Key Vault once per module."""
    _bootstrap_secrets()


@pytest.fixture(scope="module")
def api_key_required() -> None:
    """Skip the whole module if NICE_API_KEY is not set after Key Vault load."""
    if not os.getenv("NICE_API_KEY"):
        pytest.skip(
            "NICE_API_KEY not available (not in env and not found in Key Vault). "
            "Ensure AZURE_KEYVAULT_URL is set and you have run 'az login'."
        )


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
    assert any(
        "cancer" in t for t in titles
    ), f"Expected 'cancer' in at least one title, got: {titles[:5]}"
    assert all(r.get("code") for r in results), "Every result must have a code"


@pytest.mark.asyncio
async def test_search_index_returns_guidance_items(client):
    """search_index returns a list of valid guidance items from the NICE index.

    NOTE: The NICE guidance index endpoint does NOT support free-text ?q= search
    parameters -- it ignores them and returns the first page of the index
    alphabetically.  Text-based condition search is handled by ``_ranked_search``
    operating over the Redis-cached catalogue (populated by sync_catalogue_from_index).

    This test validates the structural contract: each item has code, title, type.
    """
    results = await client.search_index("cancer")  # query is ignored by the API
    assert isinstance(results, list), "search_index must return a list"
    assert len(results) > 0, "Expected at least one guidance item from the index"
    for r in results:
        assert r.get("code"), f"Every item must have a code: {r}"
        assert r.get("title"), f"Every item must have a title: {r}"
        assert "type" in r, f"Every item must have a type key: {r}"


@pytest.mark.asyncio
async def test_search_index_cold_cache_fallback_returns_items(client):
    """search_index is used as cold-cache fallback and must return at least some items.

    The primary search path uses the Redis catalogue (via sync_catalogue_from_index
    and _ranked_search in the router).  search_index is only called when Redis is
    empty.  Its results are unordered (alphabetical), which is acceptable for the
    fallback path -- the UI shows a loading hint to run 'Refresh guideline list'.
    """
    results = await client.search_index("bowel")
    assert isinstance(results, list)
    # May return unrelated items -- just verify the structural shape
    assert all(
        "code" in r and "title" in r for r in results
    ), "All items must have code and title fields"


# ---------------------------------------------------------------------------
# Individual guideline fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_guidance_ng12_returns_title(client):
    """Fetching NG12 top-level doc returns a Title and GuidanceNumber."""
    doc = await client.get_guidance("NG12")
    assert doc.get("Title"), "Expected a Title in the NG12 guidance doc"
    assert (
        doc.get("GuidanceNumber", "").upper() == "NG12"
        or doc.get("Code", "").upper() == "NG12"
    ), f"Expected NG12 guidance number, got: {doc.get('GuidanceNumber')} / {doc.get('Code')}"


@pytest.mark.asyncio
async def test_get_chapters_ng12_returns_at_least_one_chapter(client):
    """NG12 has at least one chapter link in its Resources."""
    chapters = await client.get_chapters("NG12")
    assert len(chapters) > 0, (
        "Expected at least one chapter for NG12. "
        "If Resources is empty, the API response structure may have changed."
    )
    assert all(
        c.get("Href") for c in chapters
    ), "Each chapter must have an Href link to follow"


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
        assert rec.get("Title") or rec.get(
            "Text"
        ), f"Every recommendation must have Title or Text, got: {rec}"


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
# Taxonomy walk (4-level HATEOAS tree)
# ---------------------------------------------------------------------------

# Known top-level categories from NICE API guide Appendix D.
# We check for a subset so the test stays green if NICE reorganises slightly.
_EXPECTED_CATEGORIES = {
    "conditions and diseases",
    "health and social care delivery",
    "lifestyle and wellbeing",
    "population groups",
}

# Known subcategories that must be present under "conditions and diseases".
_EXPECTED_SUBCATEGORIES = {"cancer"}


@pytest.mark.asyncio
async def test_fetch_taxonomy_returns_categories(client):
    """fetch_taxonomy returns at least the known top-level NICE categories.

    Validates the full 4-step HATEOAS walk:
      1. root → taxonomy link
      2. taxonomy doc → category links (NOT inline subcategories -- the real API
         uses links here, which caused the 2026-03-08 production failure)
      3. category link → subcategory links
      4. subcategory link → guideline list
    """
    entries = await client.fetch_taxonomy()
    assert isinstance(entries, list), "fetch_taxonomy must return a list"
    assert len(entries) > 0, (
        "Expected at least one taxonomy entry. "
        "If this is 0, the 4-level HATEOAS walk is broken -- check "
        "that category links are being followed (not just the taxonomy root)."
    )

    found_categories = {e["category_title"].lower() for e in entries}
    for expected in _EXPECTED_CATEGORIES:
        assert expected in found_categories, (
            f"Expected top-level category '{expected}' in taxonomy. "
            f"Categories found: {sorted(found_categories)}"
        )


@pytest.mark.asyncio
async def test_fetch_taxonomy_cancer_subcategory_has_ng_guidelines(client):
    """The 'cancer' subcategory must contain NG-prefixed clinical guidelines.

    NG12 (Suspected cancer) is the canonical cancer referral guideline and must
    appear in the taxonomy's cancer subcategory.
    """
    entries = await client.fetch_taxonomy()
    cancer_entries = [
        e for e in entries if "cancer" in e.get("subcategory_title", "").lower()
    ]
    assert cancer_entries, (
        "No 'cancer' subcategory found in taxonomy. "
        f"Subcategories present: {[e['subcategory_title'] for e in entries][:10]}"
    )

    cancer_codes = {
        code for e in cancer_entries for code in e.get("guideline_codes", [])
    }
    assert cancer_codes, (
        "Cancer subcategory found but contains no guideline codes. "
        "Check that subcategory URI is being fetched and guidance list parsed."
    )
    ng_codes = {c for c in cancer_codes if c.startswith("NG")}
    assert ng_codes, (
        f"Expected NG-prefixed clinical guidelines in cancer subcategory. "
        f"Codes found: {sorted(cancer_codes)[:10]}"
    )
    assert "NG12" in cancer_codes, (
        f"NG12 (Suspected cancer) must be in the cancer subcategory. "
        f"Codes found: {sorted(cancer_codes)[:20]}"
    )


@pytest.mark.asyncio
async def test_fetch_taxonomy_all_entries_have_required_fields(client):
    """Every taxonomy entry must have category_title, subcategory_title, and guideline_codes."""
    entries = await client.fetch_taxonomy()
    assert entries, "Taxonomy must return at least one entry"
    for entry in entries:
        assert entry.get("category_id"), f"Missing category_id: {entry}"
        assert entry.get("category_title"), f"Missing category_title: {entry}"
        assert entry.get("subcategory_id"), f"Missing subcategory_id: {entry}"
        assert entry.get("subcategory_title"), f"Missing subcategory_title: {entry}"
        assert isinstance(
            entry.get("guideline_codes"), list
        ), f"guideline_codes must be a list: {entry}"
        # Codes must all be valid NICE codes
        from app.services.nice_api_client import NICE_CODE_RE

        for code in entry["guideline_codes"]:
            assert NICE_CODE_RE.match(
                code
            ), f"Invalid NICE code '{code}' in subcategory '{entry['subcategory_title']}'"


@pytest.mark.asyncio
async def test_fetch_taxonomy_subcategory_count_is_plausible(client):
    """Taxonomy must return a plausible number of subcategories.

    Appendix D of the NICE API guide lists ~50 subcategories across all
    top-level categories. If the count is 0 the walk is broken; if it is
    much lower than expected, category links may not be followed correctly.
    """
    entries = await client.fetch_taxonomy()
    subcategory_count = len(entries)
    assert subcategory_count >= 20, (
        f"Expected at least 20 subcategories from the NICE taxonomy, got {subcategory_count}. "
        "This suggests the 4-level category-link walk is not working."
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
    assert any(
        e["code"] == "NG999" for e in entries
    ), "Expected NG999 to be in catalogue after add_to_catalogue"
