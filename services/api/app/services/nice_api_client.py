"""NICE Syndication API client -- structured JSON fetch only, no LLM.

Atlas trace:
  DO: DO-24AA8840
  DI: DI-693FFEEA
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-24AA8840")

URL structure (from NICE Syndication API guide ECD10):
  Root guidance:   https://api.nice.org.uk/services/guidance.json
  Guidance index:  https://api.nice.org.uk/services/guidance/index.json[?q=keyword]
  Individual doc:  https://api.nice.org.uk/services/guidance/documents/{CODE}.json
  Chapter content: follow Uri links from the document Resources array
  Taxonomy:        discovered at runtime from root Resources (rel contains "taxonomy")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_NICE_BASE = "https://api.nice.org.uk/services/guidance/documents"
_NICE_INDEX = "https://api.nice.org.uk/services/guidance/index.json"
_NICE_ROOT = "https://api.nice.org.uk/services/guidance"
# Pattern that matches valid NICE guidance codes e.g. NG151, CG89, TA123, QS12
NICE_CODE_RE = re.compile(
    r"^(NG|CG|TA|QS|PH|SC|MG|DG|HST|IPG|MTG|CSG|MPG|SSG|COVID)\d+$", re.IGNORECASE
)
_CATALOGUE_KEY = "nice:catalogue"
_CATALOGUE_TTL = 86400  # 24 hours
_TIMEOUT = 30.0
_MAX_RETRIES = 3

# Matches Microsoft-style JSON dates: /Date(milliseconds+offset)/
_MS_DATE_RE = re.compile(r"/Date\((-?\d+)")


def parse_nice_ms_date(value: str) -> str:
    """Convert a NICE API date string to a plain ISO-8601 date (YYYY-MM-DD).

    The NICE Syndication API encodes dates as Microsoft-style JSON dates,
    e.g. ``/Date(1776237435079+0100)/``.  The numeric part is milliseconds
    since the Unix epoch; the ``+0100`` offset is irrelevant for our
    purposes because we normalise to UTC and then format as a date-only
    string.

    Falls back to returning the original value unchanged if it does not
    match the pattern (e.g. a plain ``"2023-01-01"`` string).

    Args:
        value: Raw date string from the NICE API.

    Returns:
        ISO-8601 date string ``"YYYY-MM-DD"``, or the original value if
        parsing fails, or ``""`` if *value* is falsy.
    """
    if not value:
        return ""
    m = _MS_DATE_RE.match(value)
    if m:
        ms = int(m.group(1))
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    return value


def _collect_codes(node: dict[str, Any]) -> list[str]:
    """Recursively collect NICE guideline codes from a taxonomy tree node.

    Each node may have:
    - ``paths``: list of guidance links with ``Uri`` like
      ``/services/guidance/documents/NG12``
    - ``categories``: nested child nodes (recursed into)

    Returns a deduplicated list preserving first-seen order.
    """
    seen: set[str] = set()
    codes: list[str] = []

    def _walk(n: dict[str, Any]) -> None:
        for path in n.get("paths", []):
            uri = path.get("Uri", "")
            if "/documents/" in uri:
                raw = uri.rsplit("/documents/", 1)[-1].strip().upper()
                if raw and NICE_CODE_RE.match(raw) and raw not in seen:
                    seen.add(raw)
                    codes.append(raw)
        for child in n.get("categories", []):
            _walk(child)

    _walk(node)
    return codes


def _slug(text: str) -> str:
    """Convert a free-text label to a stable lowercase slug for use as a Neo4j ID."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _find_link(doc: dict[str, Any], rel_fragment: str) -> str | None:
    """Return the first resource URI whose Rel contains *rel_fragment* (case-insensitive).

    The NICE API uses HATEOAS-style Resources arrays to advertise entry points.
    This helper lets callers discover URLs without hardcoding paths.

    Args:
        doc: Parsed NICE API JSON document that may contain a ``Resources`` list.
        rel_fragment: Substring to match against the ``Rel`` field (e.g. ``"taxonomy"``).

    Returns:
        The ``Uri`` (or ``Href``) of the matching resource, or ``None`` if not found.
    """
    for resource in doc.get("Resources", []):
        rel = resource.get("Rel", "").lower()
        if rel_fragment.lower() in rel:
            return resource.get("Uri") or resource.get("Href") or None
    return None


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
                await asyncio.sleep(2**attempt)
    raise RuntimeError(
        f"NICE API request failed after {_MAX_RETRIES} attempts: {last_exc}"
    )


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

        All resources whose ``Rel`` field contains ``"chapter"`` (case-insensitive)
        are returned. This captures the full guideline structure -- recommendations,
        context, glossary, evidence reviews, etc. -- as first-class Chapter nodes.

        Args:
            code: NICE guidance code e.g. ``NG12``.

        Returns:
            List of chapter dicts normalised to always include ``Href``, ``Uri``,
            and ``Title`` keys so callers do not need to know the raw field names.
        """
        doc = await self.get_guidance(code)
        resources = doc.get("Resources", [])
        chapters = []
        for r in resources:
            rel = r.get("Rel", "").lower()
            if "chapter" in rel:
                uri = r.get("Uri", r.get("Href", ""))
                title = r.get("Title", "")
                chapters.append({**r, "Href": uri, "Uri": uri, "Title": title})
        return chapters

    async def get_chapter_content(self, chapter_uri: str) -> dict[str, Any]:
        """Fetch the raw JSON for a single chapter resource.

        The chapter JSON contains a ``Resources`` array of section links whose
        ``Rel`` value is ``/linkrels/guidance/section``.  To get the actual
        recommendation text, callers must then fetch each section URI and parse
        the ``Content`` XHTML field — see :meth:`get_section_uris` and
        :meth:`get_section_content`.

        Args:
            chapter_uri: Fully-qualified NICE API URI for a chapter.

        Returns:
            Parsed JSON dict for the chapter resource.

        Raises:
            RuntimeError: If the fetch fails after all retries.
        """
        url = chapter_uri if chapter_uri.endswith(".json") else f"{chapter_uri}.json"
        async with httpx.AsyncClient() as client:
            return await _get(client, url)

    def get_section_uris(self, chapter_json: dict[str, Any]) -> list[str]:
        """Extract section URIs from a chapter's Resources array.

        The NICE Syndication API advertises intra-chapter sections via
        ``Resources`` entries whose ``Rel`` field is
        ``/linkrels/guidance/section``.  Each section contains the actual
        recommendation text in its ``Content`` field as XHTML.

        Args:
            chapter_json: Parsed JSON dict for a chapter (from
                :meth:`get_chapter_content`).

        Returns:
            Ordered list of section URIs.  Empty if the chapter has no
            section links (e.g. appendix-only chapters).
        """
        uris: list[str] = []
        for res in chapter_json.get("Resources", []):
            if (res or {}).get("Rel") == "/linkrels/guidance/section":
                uri = (res or {}).get("Uri") or (res or {}).get("Href")
                if uri:
                    uris.append(uri)
        return uris

    async def get_section_content(self, section_uri: str) -> dict[str, Any]:
        """Fetch a single section JSON, which contains the actual recommendation HTML.

        Each section returned by the NICE Syndication API has a ``Content``
        field containing XHTML.  That HTML contains
        ``<article class="numbered-paragraph">`` elements — one per
        recommendation — with the full clinical text.

        Args:
            section_uri: Fully-qualified NICE API URI for a section.

        Returns:
            Parsed JSON dict including ``Content`` (XHTML string), ``Title``,
            and ``SectionId``.

        Raises:
            RuntimeError: If the fetch fails after all retries.
        """
        url = section_uri if section_uri.endswith(".json") else f"{section_uri}.json"
        async with httpx.AsyncClient() as client:
            return await _get(client, url)

    async def get_recommendations(self, code: str) -> list[dict[str, Any]]:
        """Flat list of all recommendation items across all chapters.

        .. deprecated::
            The ingest pipeline now uses :meth:`get_chapters` + :meth:`get_chapter_content`
            to preserve the chapter hierarchy in Neo4j. This method returns a
            flat list for backwards compatibility (e.g. integration tests).

        Args:
            code: NICE guidance code e.g. ``NG12``.

        Returns:
            Flat list of recommendation dicts with at least ``Title`` and/or ``Text``.
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
                results.append(
                    {
                        "code": code.upper(),
                        "title": title,
                        # NICE API uses GuidanceType at top level, Type in index items
                        "type": item.get("GuidanceType", item.get("Type", "")),
                    }
                )
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
                        all_items.append(
                            {
                                "code": code,
                                "title": title,
                                "type": item.get("GuidanceType", item.get("Type", "")),
                            }
                        )

                # Follow pagination links if present
                raw_next = data.get("NextPageUri", data.get("Next", ""))
                if raw_next and raw_next != next_url:
                    next_url = (
                        raw_next if raw_next.endswith(".json") else f"{raw_next}.json"
                    )
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
            logger.debug("Redis catalogue cache read failed", exc_info=True)
        finally:
            await redis.aclose()
        return []

    async def fetch_taxonomy(self) -> list[dict[str, Any]]:
        """Walk the NICE taxonomy hierarchy and return a flat list of entries.

        The real NICE ``newtaxonomy.json`` endpoint returns a **self-contained**
        nested tree — no follow-up HTTP calls are needed for categories or
        subcategories.  The structure (confirmed by live API probe 2026-03-08):

          1. GET ``/services/guidance.json``      → find rel=newtaxonomy link
          2. GET taxonomy doc (newtaxonomy.json)  → inline nested tree:

             .. code-block:: text

                categories[].name                      # "Conditions and diseases"
                categories[].categories[].name         # "Blood and immune system conditions"
                categories[].categories[].categories[].name   # "Allergies and anaphylaxis"
                categories[].categories[].categories[].paths[].Uri  # "/services/guidance/documents/NG12"

        Guideline codes are extracted from the relative ``Uri`` in each ``paths``
        entry by splitting on ``/documents/``.  Codes are collected recursively
        from the entire subcategory subtree so that deeply-nested entries are
        not missed.

        Returns:
            Flat list of dicts keyed by category (level 1) and subcategory
            (level 2), with ``guideline_codes`` = all codes from the full
            subtree of that subcategory::

                {
                    "category_id": str,
                    "category_title": str,
                    "subcategory_id": str,
                    "subcategory_title": str,
                    "subcategory_uri": "",   # always empty -- data is inline
                    "guideline_codes": list[str],
                }

        All failures are logged at WARNING level with diagnostic detail.
        No silent fallbacks.
        """
        result: list[dict[str, Any]] = []
        async with httpx.AsyncClient() as client:

            # ── Step 1: discover taxonomy URL from the API root ────────────
            root_url = f"{_NICE_ROOT}.json"
            try:
                root_doc = await _get(client, root_url)
            except RuntimeError as exc:
                logger.warning(
                    "Could not fetch NICE API root at %s -- taxonomy unavailable: %s",
                    root_url,
                    exc,
                )
                return result

            taxonomy_uri = _find_link(root_doc, "taxonomy")
            if not taxonomy_uri:
                available = [r.get("Rel", "") for r in root_doc.get("Resources", [])]
                logger.warning(
                    "NICE API root returned no taxonomy link. "
                    "Available Rel values: %s",
                    available,
                )
                return result

            # ── Step 2: fetch the taxonomy document (self-contained tree) ──
            tax_url = (
                taxonomy_uri
                if taxonomy_uri.endswith(".json")
                else f"{taxonomy_uri}.json"
            )
            try:
                tax_doc = await _get(client, tax_url)
            except RuntimeError as exc:
                logger.warning(
                    "Could not fetch NICE taxonomy document at %s: %s", tax_url, exc
                )
                return result

            top_categories = tax_doc.get("categories", [])
            if not top_categories:
                logger.warning(
                    "NICE taxonomy document at %s returned no categories. "
                    "Top-level keys present: %s",
                    tax_url,
                    list(tax_doc.keys()),
                )
                return result

            # ── Step 3: walk the inline tree (level 1 → level 2) ──────────
            # Level 1 = major area  (e.g. "Conditions and diseases")
            # Level 2 = subcategory (e.g. "Blood and immune system conditions")
            # Deeper levels are collected recursively into guideline_codes.
            for cat in top_categories:
                cat_title = cat.get("name", "")
                cat_id = _slug(cat_title)
                if not cat_title:
                    continue

                level2 = cat.get("categories", [])
                if not level2:
                    logger.warning(
                        "NICE taxonomy category '%s' has no sub-categories -- skipped.",
                        cat_title,
                    )
                    continue

                for sub in level2:
                    sub_title = sub.get("name", "")
                    sub_id = _slug(sub_title)
                    if not sub_title:
                        continue

                    codes = _collect_codes(sub)
                    result.append(
                        {
                            "category_id": cat_id,
                            "category_title": cat_title,
                            "subcategory_id": f"{cat_id}:{sub_id}",
                            "subcategory_title": sub_title,
                            "subcategory_uri": "",
                            "guideline_codes": codes,
                        }
                    )

        logger.info("NICE taxonomy walk complete: %d subcategories", len(result))
        return result

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
