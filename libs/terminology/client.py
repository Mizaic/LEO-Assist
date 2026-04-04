"""Canonical terminology resolution client.

Provides both synchronous and asynchronous clients for the Terminology API.
All pipeline code should import from here — do NOT duplicate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolver input normalisation
# Strips trailing numeric lab-value suffixes and EMIS local code suffixes
# from evidence phrases before they are sent to /terminology/resolve.
# The original text is preserved in Neo4j; only the lookup query is cleaned.
# ---------------------------------------------------------------------------

# Matches: " 1.05 mmol/L", " 160 g/L", " 1.3 mIU/L", " 10^9/L" etc.
_LAB_VALUE_RE = re.compile(
    r"\s+\d[\d.,]*\s*"
    r"(?:10\^[0-9]+/[a-zA-Z]+|[a-zA-Z/%][a-zA-Z0-9/^.]*)"
    r"\s*$",
    re.IGNORECASE,
)

# Matches trailing EMIS local code: " (X78gA)", " (Y41c9)", " (N1402)" etc.
_EMIS_CODE_RE = re.compile(r"\s*\([A-Z][a-zA-Z0-9]{3,6}\)\s*$")


def _normalise_for_resolve(text: str) -> str:
    """Strip lab-value suffixes and EMIS local codes before resolver lookup.

    Never returns an empty string -- falls back to the stripped original.
    """
    cleaned = _EMIS_CODE_RE.sub("", text.strip()).strip()
    cleaned = _LAB_VALUE_RE.sub("", cleaned).strip()
    return cleaned or text.strip()


# ---------------------------------------------------------------------------
# Terms that must NEVER be resolved, regardless of what the terminology
# server returns.  The pipeline should not produce any coding for these.
#
# NAD: ambiguous between "No abnormality detected" (281900007, a finding)
# and "No apparent distress" (no SNOMED code, a general observation).
# Because the correct meaning cannot be determined from the abbreviation
# alone, NAD is excluded from auto-coding.  Reviewers can code manually.
# ---------------------------------------------------------------------------
_ALWAYS_IGNORE_TERMS: frozenset[str] = frozenset({"nad"})

# ---------------------------------------------------------------------------
# Ambiguous-abbreviation concept blocklist (belt-and-suspenders).
# Maps normalised evidence text -> set of SNOMED concept IDs that are
# clinically incorrect in UK primary care context for that abbreviation.
# Applied after resolver returns results to suppress mismatches.
# ---------------------------------------------------------------------------
_ABBREV_BLOCKED_CONCEPTS: dict[str, set[str]] = {
    # No entries currently -- NAD is handled by _ALWAYS_IGNORE_TERMS above.
    # Add entries here for abbreviations where SOME concepts are correct and
    # only specific wrong concepts need suppressing.
}


def _filter_abbrev_noise(
    norm_text: str,
    candidates: list[Any],
) -> list[Any]:
    """Return empty list for always-ignored terms; remove blocked concept IDs
    for other known ambiguous abbreviations.

    Works on both ResolvedTerm objects (have .concept_id) and raw dicts
    (have 'snomed_concept_id' / 'concept_id' / 'conceptId' key).
    Returns the filtered list; original is unchanged if no block applies.
    """
    key = norm_text.lower().strip()

    if key in _ALWAYS_IGNORE_TERMS:
        logger.debug(
            "_filter_abbrev_noise: suppressing all results for always-ignored term '%s'",
            norm_text,
        )
        return []

    blocked = _ABBREV_BLOCKED_CONCEPTS.get(key)
    if not blocked:
        return candidates

    def _get_cid(c: Any) -> str:
        if isinstance(c, dict):
            return str(
                c.get("snomed_concept_id")
                or c.get("concept_id")
                or c.get("conceptId")
                or ""
            )
        return str(getattr(c, "concept_id", "") or "")

    filtered = [c for c in candidates if _get_cid(c) not in blocked]
    if len(filtered) < len(candidates):
        logger.debug(
            "_filter_abbrev_noise: suppressed %d concept(s) for '%s'",
            len(candidates) - len(filtered),
            norm_text,
        )
    return filtered

TERMINOLOGY_API_URL = os.getenv("TERMINOLOGY_API_URL", "http://localhost:8001")
_SERVICE_CONFIG_KEY = "terminology:resolve_runtime"
_SERVICE_CONFIG_CACHE_TTL_SECONDS = float(os.getenv("SERVICE_CONFIG_CACHE_TTL_SECONDS", "15"))


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


_DEFAULT_RUNTIME_CONFIG: dict[str, float | int] = {
    "timeout_seconds": _env_float("TERMINOLOGY_API_TIMEOUT", 15.0),
    "max_retries": _env_int("TERMINOLOGY_API_RETRIES", 3),
    "cooldown_seconds": _env_float("TERMINOLOGY_API_COOLDOWN_SECONDS", 60.0),
    "final_attempts": _env_int("TERMINOLOGY_API_FINAL_ATTEMPTS", 1),
    "max_concurrent_requests": _env_int("TERMINOLOGY_API_MAX_CONCURRENT_REQUESTS", 2),
    "max_terms_per_request": _env_int("TERMINOLOGY_API_MAX_TERMS_PER_REQUEST", 8),
}
_runtime_cache_lock = threading.Lock()
_runtime_cache_loaded_at = 0.0
_runtime_cache_value = dict(_DEFAULT_RUNTIME_CONFIG)


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
                concept_id=(
                    c.get("conceptId")
                    or c.get("concept_id")
                    or c.get("snomed_concept_id")
                ),
                term=(
                    c.get("term")
                    or c.get("preferredTerm")
                    or c.get("snomed_term")
                ),
                semantic_tag=c.get("semanticTag") or c.get("semantic_tag"),
                score=float(c.get("score", 0.0)),
                read_code=c.get("readCode") or c.get("read_code"),
                raw=c,
            )
            for c in candidates
        ]
    return parsed


def _parse_runtime_config(raw: dict[str, Any] | None) -> dict[str, float | int]:
    cfg = dict(_DEFAULT_RUNTIME_CONFIG)
    if raw:
        for key in cfg:
            if key in raw and raw[key] is not None:
                cfg[key] = raw[key]
    cfg["timeout_seconds"] = max(1.0, float(cfg["timeout_seconds"]))
    cfg["max_retries"] = max(0, int(cfg["max_retries"]))
    cfg["cooldown_seconds"] = max(0.0, float(cfg["cooldown_seconds"]))
    cfg["final_attempts"] = max(0, int(cfg["final_attempts"]))
    cfg["max_concurrent_requests"] = max(1, int(cfg["max_concurrent_requests"]))
    cfg["max_terms_per_request"] = max(1, int(cfg["max_terms_per_request"]))
    return cfg


def _load_runtime_config(force_refresh: bool = False) -> dict[str, float | int]:
    global _runtime_cache_loaded_at, _runtime_cache_value

    now = time.monotonic()
    with _runtime_cache_lock:
        if (
            not force_refresh
            and (now - _runtime_cache_loaded_at) < _SERVICE_CONFIG_CACHE_TTL_SECONDS
        ):
            return dict(_runtime_cache_value)

    config = dict(_DEFAULT_RUNTIME_CONFIG)
    try:
        from libs.cypher.service_config_queries import GET_SERVICE_CONFIG
        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        try:
            with client.session() as session:
                row = session.run(GET_SERVICE_CONFIG, key=_SERVICE_CONFIG_KEY).single()
        finally:
            client.close()
        if row and row.get("configJson"):
            raw = row.get("configJson")
            parsed = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            config = _parse_runtime_config(parsed)
    except Exception:
        logger.debug(
            "Terminology runtime config lookup failed; using defaults",
            exc_info=True,
        )

    with _runtime_cache_lock:
        _runtime_cache_loaded_at = now
        _runtime_cache_value = dict(config)
    return config


def get_runtime_config(force_refresh: bool = False) -> dict[str, float | int]:
    """Return the shared terminology runtime config currently in effect."""
    return _load_runtime_config(force_refresh=force_refresh)


class _ConcurrencyGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._active = 0

    @contextmanager
    def slot(self, limit: int):
        with self._cond:
            while self._active >= limit:
                self._cond.wait()
            self._active += 1
        try:
            yield
        finally:
            with self._cond:
                self._active = max(0, self._active - 1)
                self._cond.notify_all()


_RESOLVE_GATE = _ConcurrencyGate()


def _chunk_terms(terms: list[str], size: int) -> list[list[str]]:
    return [terms[i : i + size] for i in range(0, len(terms), size)]


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

    def _resolve_batch(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None,
        runtime: dict[str, float | int],
    ) -> dict[str, list[ResolvedTerm]]:
        import httpx

        timeout_seconds = float(runtime["timeout_seconds"])
        max_retries = int(runtime["max_retries"])
        cooldown_seconds = float(runtime["cooldown_seconds"])
        final_attempts = int(runtime["final_attempts"])
        max_concurrent_requests = int(runtime["max_concurrent_requests"])

        body: dict[str, Any] = {"terms": terms}
        if expected_tags:
            body["expected_tags"] = {
                term: tag
                for term, tag in expected_tags.items()
                if term in terms
            }

        total_initial_attempts = 1 + max_retries
        with _RESOLVE_GATE.slot(max_concurrent_requests):
            for attempt in range(total_initial_attempts):
                try:
                    with httpx.Client(timeout=timeout_seconds) as client:
                        resp = client.post(
                            f"{self._base_url}/terminology/resolve",
                            json=body,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        return _parse_results(data.get("results", {}))
                except Exception as exc:
                    if attempt < max_retries:
                        logger.warning(
                            "Terminology resolve batch failed on attempt %d/%d for %d term(s); retrying. Error: %s",
                            attempt + 1,
                            total_initial_attempts,
                            len(terms),
                            exc,
                        )
                        continue
                    logger.warning(
                        "Terminology resolve batch timed out or failed after %d attempt(s) for %d term(s); pausing workflow for %.0fs before final check.",
                        total_initial_attempts,
                        len(terms),
                        cooldown_seconds,
                        exc_info=True,
                    )
                    if cooldown_seconds > 0:
                        time.sleep(cooldown_seconds)
                    for final_attempt in range(final_attempts):
                        try:
                            with httpx.Client(timeout=timeout_seconds) as client:
                                resp = client.post(
                                    f"{self._base_url}/terminology/resolve",
                                    json=body,
                                )
                                resp.raise_for_status()
                                data = resp.json()
                                logger.info(
                                    "Terminology resolve recovered after cooldown on final attempt %d/%d for %d term(s).",
                                    final_attempt + 1,
                                    final_attempts,
                                    len(terms),
                                )
                                return _parse_results(data.get("results", {}))
                        except Exception:
                            if final_attempt + 1 == final_attempts:
                                logger.error(
                                    "Terminology resolve remained unavailable or too slow after cooldown and %d final attempt(s) for %d term(s); failing workflow.",
                                    final_attempts,
                                    len(terms),
                                    exc_info=True,
                                )
                                return {}
        return {}

    def resolve(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[ResolvedTerm]]:
        """Resolve a batch of terms to SNOMED concepts.

        Returns a dict mapping each input term to a list of candidates.
        Input terms are normalised before lookup (lab values and EMIS
        suffixes stripped) but results are re-keyed to the original terms.
        """
        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))

        # Build normalised-term -> [original terms] mapping for re-keying.
        norm_to_originals: dict[str, list[str]] = {}
        normalised_unique: list[str] = []
        for orig in unique:
            norm = _normalise_for_resolve(orig)
            if norm not in norm_to_originals:
                normalised_unique.append(norm)
            norm_to_originals.setdefault(norm, []).append(orig)

        # Rebuild expected_tags with normalised keys.
        norm_tags: dict[str, str] | None = None
        if expected_tags:
            norm_tags = {
                _normalise_for_resolve(k): v for k, v in expected_tags.items()
            }

        runtime = _load_runtime_config()
        runtime["timeout_seconds"] = float(max(self._timeout, float(runtime["timeout_seconds"])))
        runtime["max_retries"] = int(max(self._max_retries, int(runtime["max_retries"])))
        chunk_size = int(runtime["max_terms_per_request"])

        aggregated: dict[str, list[ResolvedTerm]] = {}
        for batch in _chunk_terms(normalised_unique, chunk_size):
            batch_results = self._resolve_batch(batch, norm_tags, runtime)
            if not batch_results and batch:
                return {}
            aggregated.update(batch_results)

        # Re-key results from normalised terms back to original terms.
        # Apply abbreviation noise filter during re-keying so both paths
        # (NER and LLM) benefit from the guard.
        rekeyed: dict[str, list[ResolvedTerm]] = {}
        for norm_key, candidates in aggregated.items():
            clean = _filter_abbrev_noise(norm_key, candidates)
            for orig in norm_to_originals.get(norm_key, [norm_key]):
                rekeyed[orig] = clean
        return rekeyed

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

    async def _resolve_batch_raw(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None,
        runtime: dict[str, float | int],
    ) -> dict[str, list[dict[str, Any]]]:
        import httpx

        timeout_seconds = float(runtime["timeout_seconds"])
        max_retries = int(runtime["max_retries"])
        cooldown_seconds = float(runtime["cooldown_seconds"])
        final_attempts = int(runtime["final_attempts"])

        body: dict[str, Any] = {"terms": terms}
        if expected_tags:
            body["expected_tags"] = {
                term: tag
                for term, tag in expected_tags.items()
                if term in terms
            }

        total_initial_attempts = 1 + max_retries
        for attempt in range(total_initial_attempts):
            try:
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    resp = await client.post(
                        f"{self._base_url}/terminology/resolve",
                        json=body,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("results", {})
            except Exception as exc:
                if attempt < max_retries:
                    logger.warning(
                        "Async terminology resolve batch failed on attempt %d/%d for %d term(s); retrying. Error: %s",
                        attempt + 1,
                        total_initial_attempts,
                        len(terms),
                        exc,
                    )
                    continue
                logger.warning(
                    "Async terminology resolve batch timed out or failed after %d attempt(s) for %d term(s); pausing workflow for %.0fs before final check.",
                    total_initial_attempts,
                    len(terms),
                    cooldown_seconds,
                    exc_info=True,
                )
                if cooldown_seconds > 0:
                    await asyncio.sleep(cooldown_seconds)
                for final_attempt in range(final_attempts):
                    try:
                        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                            resp = await client.post(
                                f"{self._base_url}/terminology/resolve",
                                json=body,
                            )
                            resp.raise_for_status()
                            data = resp.json()
                            logger.info(
                                "Async terminology resolve recovered after cooldown on final attempt %d/%d for %d term(s).",
                                final_attempt + 1,
                                final_attempts,
                                len(terms),
                            )
                            return data.get("results", {})
                    except Exception:
                        if final_attempt + 1 == final_attempts:
                            logger.error(
                                "Async terminology resolve remained unavailable or too slow after cooldown and %d final attempt(s) for %d term(s); failing workflow.",
                                final_attempts,
                                len(terms),
                                exc_info=True,
                            )
                            return {}
        return {}

    async def resolve(
        self,
        terms: list[str],
        expected_tags: dict[str, str] | None = None,
    ) -> dict[str, list[ResolvedTerm]]:
        """Resolve a batch of terms to SNOMED concepts (async)."""
        raw = await self.resolve_raw(terms, expected_tags=expected_tags)
        return _parse_results(raw)

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
        """Resolve returning raw dicts (for callers that need the original API shape).

        Input terms are normalised before lookup; results are re-keyed to
        the original (un-normalised) terms so callers need no changes.
        """
        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))

        norm_to_originals: dict[str, list[str]] = {}
        normalised_unique: list[str] = []
        for orig in unique:
            norm = _normalise_for_resolve(orig)
            if norm not in norm_to_originals:
                normalised_unique.append(norm)
            norm_to_originals.setdefault(norm, []).append(orig)

        norm_tags: dict[str, str] | None = None
        if expected_tags:
            norm_tags = {
                _normalise_for_resolve(k): v for k, v in expected_tags.items()
            }

        runtime = _load_runtime_config()
        runtime["timeout_seconds"] = float(max(self._timeout, float(runtime["timeout_seconds"])))
        chunk_size = int(runtime["max_terms_per_request"])

        aggregated: dict[str, list[dict[str, Any]]] = {}
        for batch in _chunk_terms(normalised_unique, chunk_size):
            batch_results = await self._resolve_batch_raw(batch, norm_tags, runtime)
            if not batch_results and batch:
                return {}
            aggregated.update(batch_results)

        rekeyed: dict[str, list[dict[str, Any]]] = {}
        for norm_key, candidates in aggregated.items():
            clean = _filter_abbrev_noise(norm_key, candidates)
            for orig in norm_to_originals.get(norm_key, [norm_key]):
                rekeyed[orig] = clean
        return rekeyed
