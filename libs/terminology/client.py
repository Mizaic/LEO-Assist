"""Canonical terminology resolution client.

Provides both synchronous and asynchronous clients for the Terminology API.
All pipeline code should import from here — do NOT duplicate.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")


@dataclass(frozen=True)
class ResolvedTerm:
    """A single terminology resolution result."""
    text: str
    concept_id: str | None = None
    term: str | None = None
    semantic_tag: str | None = None
    score: float = 0.0
    read_code: str | None = None
    raw: dict = field(default_factory=dict)


def _parse_results(
    raw_results: dict[str, list[dict[str, Any]]],
) -> dict[str, list[ResolvedTerm]]:
    """Parse raw API response into ResolvedTerm objects."""
    parsed: dict[str, list[ResolvedTerm]] = {}
    for term_text, candidates in raw_results.items():
        parsed[term_text] = [
            ResolvedTerm(
                text=term_text,
                concept_id=c.get("conceptId") or c.get("concept_id"),
                term=c.get("term") or c.get("preferredTerm"),
                semantic_tag=c.get("semanticTag") or c.get("semantic_tag"),
                score=float(c.get("score", 0.0)),
                read_code=c.get("readCode") or c.get("read_code"),
                raw=c,
            )
            for c in candidates
        ]
    return parsed


class TerminologyClient:
    """Synchronous terminology resolution client."""

    def __init__(
        self,
        base_url: str = TERMINOLOGY_API_URL,
        timeout: float = 60.0,
        max_retries: int = 1,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries

    def resolve(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[ResolvedTerm]]:
        """Resolve a batch of terms to SNOMED concepts.

        Returns a dict mapping each input term to a list of candidates.
        """
        import httpx

        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))
        body: dict[str, Any] = {"terms": unique}
        if expected_tags:
            body["expected_tags"] = expected_tags

        for attempt in range(1 + self._max_retries):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(
                        f"{self._base_url}/terminology/resolve",
                        json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return _parse_results(data.get("results", {}))
            except Exception:
                if attempt == self._max_retries:
                    logger.warning(
                        "Terminology resolve failed after %d attempts",
                        attempt + 1,
                        exc_info=True,
                    )
                    return {}

        return {}  # unreachable but satisfies type checker

    def resolve_one(
        self,
        text: str,
        label: str | None = None,
    ) -> ResolvedTerm | None:
        """Resolve a single term, returning the best candidate or None."""
        expected_tags = {text: label} if label else None
        results = self.resolve([text], expected_tags=expected_tags)
        candidates = results.get(text, [])
        return candidates[0] if candidates else None

    def get_related(self, concept_id: str) -> list[dict[str, Any]]:
        """Retrieve related SNOMED concepts for a given concept ID."""
        import httpx

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}/terminology/concepts/{concept_id}/related",
                )
                resp.raise_for_status()
                return resp.json().get("related", [])
        except Exception:
            logger.warning("get_related(%s) failed", concept_id, exc_info=True)
            return []

    def get_hierarchy(self, concept_id: str) -> list[dict[str, Any]]:
        """Retrieve the hierarchy path for a given concept ID."""
        import httpx

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}/terminology/concepts/{concept_id}/hierarchy",
                )
                resp.raise_for_status()
                return resp.json().get("path", [])
        except Exception:
            logger.warning("get_hierarchy(%s) failed", concept_id, exc_info=True)
            return []


class AsyncTerminologyClient:
    """Asynchronous terminology resolution client for pipeline use."""

    def __init__(
        self,
        base_url: str = TERMINOLOGY_API_URL,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def resolve(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[ResolvedTerm]]:
        """Resolve a batch of terms to SNOMED concepts (async)."""
        import httpx

        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))
        body: dict[str, Any] = {"terms": unique}
        if expected_tags:
            body["expected_tags"] = expected_tags

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/terminology/resolve",
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return _parse_results(data.get("results", {}))
        except Exception:
            logger.warning(
                "Async terminology resolve failed",
                exc_info=True,
            )
            return {}

    async def resolve_one(
        self,
        text: str,
        label: str | None = None,
    ) -> ResolvedTerm | None:
        """Resolve a single term (async), returning the best candidate or None."""
        expected_tags = {text: label} if label else None
        results = await self.resolve([text], expected_tags=expected_tags)
        candidates = results.get(text, [])
        return candidates[0] if candidates else None

    async def resolve_raw(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Resolve returning raw dicts (for callers that need the original API shape)."""
        import httpx

        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))
        body: dict[str, Any] = {"terms": unique}
        if expected_tags:
            body["expected_tags"] = expected_tags

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/terminology/resolve",
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", {})
        except Exception:
            logger.warning(
                "Async terminology resolve_raw failed",
                exc_info=True,
            )
            return {}
