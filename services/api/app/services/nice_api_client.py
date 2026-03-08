"""NICE Syndication API client -- structured JSON fetch only, no LLM.

URL structure (from NICE Syndication API guide ECD10):
  Root guidance:   https://api.nice.org.uk/services/guidance
  Guidance index:  https://api.nice.org.uk/services/guidance/index.json[?q=keyword]
  Individual doc:  https://api.nice.org.uk/services/guidance/documents/{CODE}.json
  Chapter content: follow Href links from the document Resources array
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_NICE_BASE = "https://api.nice.org.uk/services/guidance/documents"
_NICE_INDEX = "https://api.nice.org.uk/services/guidance/index.json"
# Pattern that matches valid NICE guidance codes e.g. NG151, CG89, TA123, QS12
NICE_CODE_RE = re.compile(r"^(NG|CG|TA|QS|PH|SC|MG|DG|HST|IPG|MTG|CSG|MPG|SSG|COVID)\d+$", re.IGNORECASE)
_CATALOGUE_KEY = "nice:catalogue"
_CATALOGUE_TTL = 86400  # 24 hours
_TIMEOUT = 30.0
_MAX_RETRIES = 3


def _api_key() -> str:
    """Read NICE_API_KEY from environment."""
    key = os.getenv("NICE_API_KEY", "")
    if not key:
        logger.warning("NICE_API_KEY not set -- NICE API calls will fail auth")
    return key


def _headers() -> dict[str, str]:
    return {"API-Key": _api_key(), "Accept": "application/json"}


async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """GET with retry and exponential back-off."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.get(url, headers=_headers(), timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"NICE API request failed after {_MAX_RETRIES} attempts: {last_exc}")


class NiceApiClient:
    """Async client for the NICE Syndication API.

    Fetches guideline documents, chapters, and sections as structured JSON.
    Maintains a Redis-cached guideline catalogue for the admin search UI.
    No LLM is used anywhere in this class.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")

    async def get_guidance(self, code: str) -> dict[str, Any]:
        """Fetch top-level guidance document JSON for a NICE code.

        Args:
            code: NICE guidance code e.g. ``NG151`` or ``CG89``.

        Returns:
            Parsed JSON dict from the NICE Syndication API.
        """
        url = f"{_NICE_BASE}/{code.upper()}.json"
        async with httpx.AsyncClient() as client:
            return await _get(client, url)

    async def get_chapters(self, code: str) -> list[dict[str, Any]]:
        """Fetch chapter resources for a guidance document.

        The NICE Syndication API returns chapter links inside the ``Resources``
        array of the top-level guidance document. Each resource uses ``Uri``
        (not ``Href``) for the link URL and ``/linkrels/guidance/chapter`` as
        the ``Rel`` value.

        Args:
            code: NICE guidance code e.g. ``NG12``.

        Returns:
            List of chapter dicts normalised to always include ``Href`` and
            ``Title`` keys so callers do not need to know the raw field names.
        """
        doc = await self.get_guidance(code)
        resources = doc.get("Resources", [])
        chapters = []
        for r in resources:
            rel = r.get("Rel", "")
            title = r.get("Title", "")
            if rel.endswith("/chapter") or "recommend" in title.lower():
                # Normalise: NICE API uses 'Uri'; keep 'Href' as alias
                uri = r.get("Uri", r.get("Href", ""))
                chapters.append({**r, "Href": uri, "Uri": uri, "Title": title})
        return chapters

    async def get_sections(self, chapter_uri: str) -> list[dict[str, Any]]:
        """Fetch section resources from a chapter URI.

        Args:
            chapter_uri: Fully-qualified NICE API URI for a chapter.

        Returns:
            List of section dicts.
        """
        url = chapter_uri if chapter_uri.endswith(".json") else f"{chapter_uri}.json"
        async with httpx.AsyncClient() as client:
            chapter = await _get(client, url)
        return chapter.get("Resources", [])

    async def get_recommendations(self, code: str) -> list[dict[str, Any]]:
        """Fetch recommendation items by walking chapter links in the guidance doc.

        The NICE Syndication API does not have a single /recommendations endpoint.
        Recommendations live inside chapter resources. This method fetches each
        chapter whose title suggests it contains recommendations and collects all
        Items found.

        Args:
            code: NICE guidance code e.g. ``NG12``.

        Returns:
            List of recommendation dicts with at least ``Title`` and/or ``Text``.
        """
        chapters = await self.get_chapters(code)
        recommendations: list[dict[str, Any]] = []
        async with httpx.AsyncClient() as client:
            for chapter in chapters:
                href = chapter.get("Href", "")
                if not href:
                    continue
                url = href if href.endswith(".json") else f"{href}.json"
                try:
                    chapter_data = await _get(client, url)
                    # Recommendations appear as Items in the chapter JSON
                    items = chapter_data.get("Items", chapter_data.get("Resources", []))
                    for item in items:
                        if item.get("Title") or item.get("Text"):
                            recommendations.append(item)
                except RuntimeError:
                    logger.debug("Could not fetch chapter %s for %s", url, code)
                    continue
        return recommendations

    async def search_index(self, query: str) -> list[dict[str, str]]:
        """Search the NICE guidance index by keyword/condition name.

        Uses the NICE Syndication API guidance index endpoint which supports
        keyword filtering. Returns up to 20 results.

        Args:
            query: Free-text search term (condition name, topic, NICE code).

        Returns:
            List of ``{code, title, type}`` dicts.
        """
        url = f"{_NICE_INDEX}?q={query}"
        async with httpx.AsyncClient() as client:
            try:
                data = await _get(client, url)
            except RuntimeError:
                logger.warning("NICE index search failed for query: %s", query)
                return []

        # NICE guidance index returns results under 'IndexItems' key
        items = data.get("IndexItems", data.get("Items", data.get("Guidance", [])))
        results: list[dict[str, str]] = []
        for item in items:
            code = item.get("GuidanceNumber") or item.get("Code", "")
            title = item.get("Title", "")
            if code and title:
                results.append({
                    "code": code.upper(),
                    "title": title,
                    # NICE API uses GuidanceType at top level, Type in index items
                    "type": item.get("GuidanceType", item.get("Type", "")),
                })
        return results[:20]

    async def sync_catalogue_from_index(self) -> int:
        """Fetch the complete NICE guidance index and populate the Redis catalogue.

        Walks all pages of the NICE guidance index (following ``NextPageUri``
        links) and replaces the Redis catalogue with the full result. This lets
        the admin search autocomplete work from day one without requiring any
        guidelines to have been ingested first.

        The catalogue TTL is extended to 7 days for a full sync (versus 24 h
        for individual ``add_to_catalogue`` calls).

        Returns:
            Number of guidelines written to the catalogue.

        Raises:
            RuntimeError: If the first page fetch fails entirely.
        """
        all_items: list[dict[str, str]] = []
        next_url: str | None = _NICE_INDEX
        async with httpx.AsyncClient() as client:
            while next_url:
                try:
                    data = await _get(client, next_url)
                except RuntimeError:
                    logger.warning("NICE index page fetch failed: %s", next_url)
                    break

                for item in data.get("IndexItems", data.get("Items", [])):
                    code = (item.get("GuidanceNumber") or item.get("Code", "")).upper()
                    title = item.get("Title", "")
                    if code and title:
                        all_items.append({
                            "code": code,
                            "title": title,
                            "type": item.get("GuidanceType", item.get("Type", "")),
                        })

                # Follow pagination links if present
                raw_next = data.get("NextPageUri", data.get("Next", ""))
                if raw_next and raw_next != next_url:
                    next_url = raw_next if raw_next.endswith(".json") else f"{raw_next}.json"
                else:
                    next_url = None

        if all_items:
            redis = aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                await redis.setex(
                    _CATALOGUE_KEY,
                    _CATALOGUE_TTL * 7,  # 7-day TTL for full syncs
                    json.dumps(all_items),
                )
            except Exception as exc:
                logger.warning("Could not write synced catalogue to Redis: %s", exc)
            finally:
                await redis.aclose()

        logger.info("NICE catalogue sync complete: %d guidelines", len(all_items))
        return len(all_items)

    async def fetch_catalogue(self) -> list[dict[str, str]]:
        """Return guideline index from Redis cache or empty list on API failure.

        The catalogue is intentionally populated by successful ingests so it
        grows organically as guidelines are loaded. Direct code entry remains
        available as a fallback in the UI.

        Returns:
            List of ``{code, title, type}`` dicts.
        """
        redis = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            cached = await redis.get(_CATALOGUE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        finally:
            await redis.aclose()
        return []

    async def add_to_catalogue(self, code: str, title: str, guidance_type: str) -> None:
        """Add a successfully ingested guideline to the Redis catalogue.

        Args:
            code: NICE guidance code.
            title: Human-readable guideline title.
            guidance_type: Guidance type e.g. ``clinical-guideline``.
        """
        redis = aioredis.from_url(self._redis_url, decode_responses=True)
        try:
            cached = await redis.get(_CATALOGUE_KEY)
            entries: list[dict[str, str]] = json.loads(cached) if cached else []
            if not any(e["code"] == code for e in entries):
                entries.append({"code": code, "title": title, "type": guidance_type})
            await redis.setex(_CATALOGUE_KEY, _CATALOGUE_TTL, json.dumps(entries))
        except Exception as exc:
            logger.warning("Could not update NICE catalogue cache: %s", exc)
        finally:
            await redis.aclose()
