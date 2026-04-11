"""Tests for NiceApiClient -- VT-LEO-AI-063."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nice_api_client import NICE_CODE_RE, NiceApiClient


@pytest.fixture()
def client():
    return NiceApiClient(redis_url="redis://localhost:6379")


@pytest.mark.asyncio
async def test_get_guidance_returns_parsed_json(client):
    """NiceApiClient.get_guidance returns structured JSON for a valid code."""
    payload = {
        "GuidanceNumber": "NG151",
        "Title": "Bowel cancer",
        "Type": "clinical-guideline",
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_http

        result = await client.get_guidance("ng151")

    assert result["GuidanceNumber"] == "NG151"
    assert result["Title"] == "Bowel cancer"


@pytest.mark.asyncio
async def test_get_guidance_retries_on_transient_error(client):
    """NiceApiClient retries 3 times on transient errors before raising."""
    import httpx

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=httpx.TransportError("timeout"))
        mock_cls.return_value = mock_http

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="3 attempts"):
                await client.get_guidance("NG999")

    assert mock_http.get.call_count == 3


@pytest.mark.asyncio
async def test_fetch_catalogue_returns_cached_value(client):
    """fetch_catalogue returns value from Redis cache."""
    cached = [{"code": "NG151", "title": "Bowel cancer", "type": "clinical-guideline"}]

    with patch("redis.asyncio.from_url") as mock_redis_cls:
        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=json.dumps(cached))
        mock_r.aclose = AsyncMock()
        mock_redis_cls.return_value = mock_r

        result = await client.fetch_catalogue()

    assert len(result) == 1
    assert result[0]["code"] == "NG151"


@pytest.mark.asyncio
async def test_fetch_catalogue_returns_empty_on_cache_miss(client):
    """fetch_catalogue returns empty list when Redis cache is empty."""
    with patch("redis.asyncio.from_url") as mock_redis_cls:
        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=None)
        mock_r.aclose = AsyncMock()
        mock_redis_cls.return_value = mock_r

        result = await client.fetch_catalogue()

    assert result == []


@pytest.mark.asyncio
async def test_add_to_catalogue_appends_new_entry(client):
    """add_to_catalogue adds a new entry to the Redis list."""
    with patch("redis.asyncio.from_url") as mock_redis_cls:
        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=None)
        mock_r.setex = AsyncMock()
        mock_r.aclose = AsyncMock()
        mock_redis_cls.return_value = mock_r

        await client.add_to_catalogue("NG151", "Bowel cancer", "clinical-guideline")

    written = mock_r.setex.call_args[0][2]
    entries = json.loads(written)
    assert any(e["code"] == "NG151" for e in entries)


@pytest.mark.asyncio
async def test_get_chapters_filters_chapter_resources(client):
    """get_chapters returns chapter resources and normalises Uri -> Href.

    The NICE Syndication API uses 'Uri' (not 'Href') and rel value
    '/linkrels/guidance/chapter'. get_chapters must normalise to 'Href'.
    """
    doc = {
        "GuidanceNumber": "NG151",
        "Resources": [
            {
                "Rel": "/linkrels/guidance/chapter",
                "Uri": "https://api.nice.org.uk/ch1",
                "Title": "Recommendations",
            },
            {"Rel": "self", "Uri": "https://api.nice.org.uk/self", "Title": "Self"},
        ],
    }
    with patch.object(client, "get_guidance", new_callable=AsyncMock, return_value=doc):
        chapters = await client.get_chapters("NG151")

    assert len(chapters) == 1
    assert chapters[0]["Href"] == "https://api.nice.org.uk/ch1"
    assert chapters[0]["Title"] == "Recommendations"


@pytest.mark.asyncio
async def test_get_recommendations_walks_chapter_hrefs(client):
    """get_recommendations fetches each chapter URL and collects Items."""
    chapters = [
        {"Href": "https://api.nice.org.uk/ch1", "Title": "Recommendations"},
    ]
    chapter_payload = {
        "Items": [
            {"Title": "Offer colonoscopy", "Text": "Offer colonoscopy to adults..."},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = chapter_payload

    with patch.object(
        client, "get_chapters", new_callable=AsyncMock, return_value=chapters
    ):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_http

            recs = await client.get_recommendations("NG12")

    assert len(recs) == 1
    assert recs[0]["Title"] == "Offer colonoscopy"


@pytest.mark.asyncio
async def test_get_recommendations_skips_failed_chapters(client):
    """get_recommendations skips chapters that raise RuntimeError and returns partial results.

    _MAX_RETRIES=3, so a failing chapter triggers 3 GET attempts before being
    skipped. The mock must supply enough side-effects for all retry attempts.
    """
    import httpx

    chapters = [
        {"Href": "https://api.nice.org.uk/ch1", "Title": "Recommendations"},
        {"Href": "https://api.nice.org.uk/ch2", "Title": "Appendix"},
    ]
    good_payload = {"Items": [{"Title": "Rec 1", "Text": "Do this"}]}
    good_resp = MagicMock()
    good_resp.raise_for_status = MagicMock()
    good_resp.json.return_value = good_payload

    # Chapter 1 fails all 3 retry attempts; chapter 2 succeeds on first try
    side_effects = [httpx.TransportError("fail")] * 3 + [good_resp]

    with patch.object(
        client, "get_chapters", new_callable=AsyncMock, return_value=chapters
    ):
        with patch("httpx.AsyncClient") as mock_cls:
            mock_http = AsyncMock()
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            mock_http.get = AsyncMock(side_effect=side_effects)
            mock_cls.return_value = mock_http
            with patch("asyncio.sleep", new_callable=AsyncMock):
                recs = await client.get_recommendations("NG12")

    assert len(recs) == 1
    assert recs[0]["Title"] == "Rec 1"


@pytest.mark.asyncio
async def test_search_index_returns_parsed_results(client):
    """search_index returns code/title/type dicts from NICE index response.

    The NICE Syndication API returns results under 'IndexItems' (confirmed
    against live API). The type field is in 'GuidanceType' at document level.
    """
    payload = {
        "IndexItems": [
            {
                "GuidanceNumber": "NG12",
                "Title": "Suspected cancer: recognition and referral",
                "GuidanceType": "clinical-guideline",
            },
            {
                "GuidanceNumber": "NG151",
                "Title": "Bowel cancer",
                "GuidanceType": "clinical-guideline",
            },
        ]
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_http

        results = await client.search_index("cancer")

    assert len(results) == 2
    assert results[0]["code"] == "NG12"
    assert results[0]["title"] == "Suspected cancer: recognition and referral"


@pytest.mark.asyncio
async def test_search_index_returns_empty_on_api_failure(client):
    """search_index returns empty list when the NICE API is unavailable."""
    import httpx

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=httpx.TransportError("unreachable"))
        mock_cls.return_value = mock_http

        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await client.search_index("cancer")

    assert results == []


@pytest.mark.asyncio
async def test_sync_catalogue_from_index_single_page(client):
    """sync_catalogue_from_index stores all IndexItems when there is one page."""
    payload = {
        "IndexItems": [
            {
                "GuidanceNumber": "NG12",
                "Title": "Suspected cancer",
                "GuidanceType": "clinical-guideline",
            },
            {
                "GuidanceNumber": "NG151",
                "Title": "Bowel cancer",
                "GuidanceType": "clinical-guideline",
            },
        ]
        # No NextPageUri → single page
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_http

        with patch("redis.asyncio.from_url") as mock_redis_cls:
            mock_r = AsyncMock()
            mock_r.setex = AsyncMock()
            mock_r.aclose = AsyncMock()
            mock_redis_cls.return_value = mock_r

            count = await client.sync_catalogue_from_index()

    assert count == 2
    written = mock_r.setex.call_args[0][2]
    entries = json.loads(written)
    assert {e["code"] for e in entries} == {"NG12", "NG151"}


@pytest.mark.asyncio
async def test_sync_catalogue_from_index_follows_pagination(client):
    """sync_catalogue_from_index follows NextPageUri to collect all guidelines."""
    page1 = {
        "IndexItems": [
            {"GuidanceNumber": "NG1", "Title": "Guideline 1", "GuidanceType": ""}
        ],
        "NextPageUri": "https://api.nice.org.uk/services/guidance/index?page=2",
    }
    page2 = {
        "IndexItems": [
            {"GuidanceNumber": "NG2", "Title": "Guideline 2", "GuidanceType": ""}
        ],
        # No NextPageUri on last page
    }
    resp1 = MagicMock()
    resp1.raise_for_status = MagicMock()
    resp1.json.return_value = page1
    resp2 = MagicMock()
    resp2.raise_for_status = MagicMock()
    resp2.json.return_value = page2

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=[resp1, resp2])
        mock_cls.return_value = mock_http

        with patch("redis.asyncio.from_url") as mock_redis_cls:
            mock_r = AsyncMock()
            mock_r.setex = AsyncMock()
            mock_r.aclose = AsyncMock()
            mock_redis_cls.return_value = mock_r

            count = await client.sync_catalogue_from_index()

    assert count == 2
    assert mock_http.get.call_count == 2


@pytest.mark.asyncio
async def test_sync_catalogue_from_index_tolerates_redis_failure(client):
    """sync_catalogue_from_index returns count even when Redis write fails."""
    payload = {
        "IndexItems": [
            {"GuidanceNumber": "NG12", "Title": "Suspected cancer", "GuidanceType": ""}
        ],
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = payload

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_http

        with patch("redis.asyncio.from_url") as mock_redis_cls:
            mock_r = AsyncMock()
            mock_r.setex = AsyncMock(side_effect=Exception("Redis down"))
            mock_r.aclose = AsyncMock()
            mock_redis_cls.return_value = mock_r

            count = await client.sync_catalogue_from_index()

    assert count == 1  # count returned despite Redis failure


def _make_resp(data: dict) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = data
    return m


# Shared fixtures for taxonomy tests
_API_ROOT_WITH_TAXONOMY_LINK = {
    "Resources": [
        {
            "Rel": "/linkrels/guidance/newtaxonomy",
            "Uri": "https://api.nice.org.uk/services/guidance/newtaxonomy",
            "Title": "Taxonomy",
        },
        {
            "Rel": "/linkrels/guidance/index",
            "Uri": "https://api.nice.org.uk/services/guidance/index.json",
            "Title": "Index",
        },
    ]
}

# Real structure confirmed by live API probe 2026-03-08:
# - field is "name" (not "title"/"Title")
# - nested categories use "categories" recursively
# - guidelines are in "paths" with relative Uri like /services/guidance/documents/NG12
# - NO follow-up HTTP calls -- fully self-contained
_TAXONOMY_DOC = {
    "categories": [
        {
            "name": "Conditions and diseases",
            "categories": [
                {
                    "name": "Cancer",
                    "categories": [
                        {
                            "name": "Colorectal cancer",
                            "categories": [],
                            "paths": [
                                {
                                    "Rel": "/linkrels/guidance",
                                    "Uri": "/services/guidance/documents/NG12",
                                    "Title": "Suspected cancer (NG12)",
                                },
                                {
                                    "Rel": "/linkrels/guidance",
                                    "Uri": "/services/guidance/documents/NG151",
                                    "Title": "Bowel cancer (NG151)",
                                },
                            ],
                        }
                    ],
                    "paths": [],
                }
            ],
            "paths": [],
        }
    ]
}


@pytest.mark.asyncio
async def test_fetch_taxonomy_returns_flat_entries(client):
    """fetch_taxonomy discovers taxonomy URL from root, walks inline tree, returns flat list.

    The real API returns a self-contained nested tree -- no follow-up HTTP calls
    for subcategories are made.  Guideline codes come from paths[].Uri.
    """
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(
            side_effect=[
                _make_resp(
                    _API_ROOT_WITH_TAXONOMY_LINK
                ),  # step 1: root → discover taxonomy link
                _make_resp(_TAXONOMY_DOC),  # step 2: self-contained taxonomy tree
            ]
        )
        mock_cls.return_value = mock_http

        result = await client.fetch_taxonomy()

    assert len(result) == 1
    entry = result[0]
    assert entry["category_title"] == "Conditions and diseases"
    assert entry["subcategory_title"] == "Cancer"
    # Codes extracted from paths[].Uri via /documents/ splitting
    assert "NG12" in entry["guideline_codes"]
    assert "NG151" in entry["guideline_codes"]
    # No sub-subcategory HTTP calls should have been made
    assert mock_http.get.call_count == 2, (
        "Only 2 HTTP calls expected (root + taxonomy doc). "
        "The taxonomy is self-contained -- no subcategory fetches needed."
    )


@pytest.mark.asyncio
async def test_fetch_taxonomy_returns_empty_when_no_taxonomy_link(client):
    """fetch_taxonomy returns [] and logs a warning when root has no taxonomy link."""
    root_without_taxonomy = {
        "Resources": [
            {
                "Rel": "/linkrels/guidance/index",
                "Uri": "https://api.nice.org.uk/services/guidance/index.json",
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_make_resp(root_without_taxonomy))
        mock_cls.return_value = mock_http

        import logging

        with patch.object(
            logging.getLogger("app.services.nice_api_client"), "warning"
        ) as mock_warn:
            result = await client.fetch_taxonomy()

    assert result == []
    # Warning must say what rels were available so the operator knows what to look for
    assert mock_warn.called
    warning_msg = str(mock_warn.call_args)
    assert "taxonomy" in warning_msg.lower()


@pytest.mark.asyncio
async def test_fetch_taxonomy_warns_when_category_has_no_subcategories(client):
    """fetch_taxonomy logs a WARNING when a top-level category has no sub-categories.

    The taxonomy tree is inline so there are no per-subcategory HTTP calls.
    A category with an empty ``categories`` list should be warned and skipped.
    """
    taxonomy_empty_cat = {
        "categories": [
            {
                "name": "Conditions and diseases",
                "categories": [],  # no subcategories -- should warn
                "paths": [],
            },
            {
                "name": "Lifestyle and wellbeing",
                "categories": [
                    {
                        "name": "Alcohol",
                        "categories": [],
                        "paths": [
                            {
                                "Uri": "/services/guidance/documents/NG115",
                                "Rel": "/linkrels/guidance",
                                "Title": "Alcohol-use disorders (NG115)",
                            },
                        ],
                    }
                ],
                "paths": [],
            },
        ]
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(
            side_effect=[
                _make_resp(_API_ROOT_WITH_TAXONOMY_LINK),
                _make_resp(taxonomy_empty_cat),
            ]
        )
        mock_cls.return_value = mock_http

        import logging

        with patch.object(
            logging.getLogger("app.services.nice_api_client"), "warning"
        ) as mock_warn:
            result = await client.fetch_taxonomy()

    # Only the Lifestyle category has subcategories and should produce an entry
    assert len(result) == 1
    assert result[0]["subcategory_title"] == "Alcohol"
    assert "NG115" in result[0]["guideline_codes"]

    all_warnings = " ".join(str(c) for c in mock_warn.call_args_list)
    assert "Conditions and diseases" in all_warnings, (
        "Should warn about empty category. Warnings: " + all_warnings
    )


@pytest.mark.asyncio
async def test_fetch_taxonomy_returns_empty_on_root_failure(client):
    """fetch_taxonomy returns [] and logs a warning when the API root is unreachable."""
    import httpx

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=httpx.TransportError("no route to host"))
        mock_cls.return_value = mock_http

        import logging

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(
                logging.getLogger("app.services.nice_api_client"), "warning"
            ) as mock_warn,
        ):
            result = await client.fetch_taxonomy()

    assert result == []
    assert mock_warn.called, "Root fetch failure must produce a WARNING log"


@pytest.mark.asyncio
async def test_fetch_taxonomy_collects_codes_from_nested_subcategories(client):
    """Codes from deeply-nested sub-subcategories are collected into the level-2 entry.

    The real API has 3 levels: category → subcategory → sub-subcategory → paths.
    All codes from the subtree must be collected, not just the top-level paths.
    """
    taxonomy_deep = {
        "categories": [
            {
                "name": "Conditions and diseases",
                "categories": [
                    {
                        "name": "Cancer",
                        "categories": [
                            {
                                "name": "Colorectal cancer",
                                "categories": [],
                                "paths": [
                                    {
                                        "Uri": "/services/guidance/documents/NG12",
                                        "Rel": "/linkrels/guidance",
                                        "Title": "",
                                    },
                                    {
                                        "Uri": "/services/guidance/documents/NG151",
                                        "Rel": "/linkrels/guidance",
                                        "Title": "",
                                    },
                                ],
                            },
                            {
                                "name": "Lung cancer",
                                "categories": [],
                                "paths": [
                                    {
                                        "Uri": "/services/guidance/documents/NG122",
                                        "Rel": "/linkrels/guidance",
                                        "Title": "",
                                    },
                                ],
                            },
                        ],
                        "paths": [],
                    }
                ],
                "paths": [],
            }
        ]
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(
            side_effect=[
                _make_resp(_API_ROOT_WITH_TAXONOMY_LINK),
                _make_resp(taxonomy_deep),
            ]
        )
        mock_cls.return_value = mock_http

        result = await client.fetch_taxonomy()

    assert len(result) == 1
    entry = result[0]
    assert entry["subcategory_title"] == "Cancer"
    # All codes from nested sub-subcategories must be in the result
    assert "NG12" in entry["guideline_codes"]
    assert "NG151" in entry["guideline_codes"]
    assert "NG122" in entry["guideline_codes"]
    # Only 2 HTTP calls: root + taxonomy doc
    assert mock_http.get.call_count == 2


@pytest.mark.parametrize(
    "code,valid",
    [
        ("NG151", True),
        ("CG89", True),
        ("TA123", True),
        ("QS12", True),
        ("PH46", True),
        ("NG12", True),
        ("CANCER", False),
        ("", False),
        ("12345", False),
        ("NICE151", False),
        ("ng151", True),  # case-insensitive
    ],
)
def test_nice_code_re_validation(code, valid):
    """NICE_CODE_RE correctly identifies valid and invalid guidance codes."""
    assert bool(NICE_CODE_RE.match(code)) == valid
