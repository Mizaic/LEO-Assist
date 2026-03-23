"""Canonical terminology resolution client.

Provides both synchronous and asynchronous clients for the Terminology API.
All pipeline code should import from here — do NOT duplicate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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
        """
        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))
        runtime = _load_runtime_config()
        # Preserve explicit constructor overrides if they are stricter than defaults.
        runtime["timeout_seconds"] = float(max(self._timeout, float(runtime["timeout_seconds"])))
        runtime["max_retries"] = int(max(self._max_retries, int(runtime["max_retries"])))
        chunk_size = int(runtime["max_terms_per_request"])
        aggregated: dict[str, list[ResolvedTerm]] = {}
        for batch in _chunk_terms(unique, chunk_size):
            batch_results = self._resolve_batch(batch, expected_tags, runtime)
            if not batch_results and batch:
                return {}
            aggregated.update(batch_results)
        return aggregated

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
        """Resolve returning raw dicts (for callers that need the original API shape)."""
        if not terms:
            return {}

        unique = list(dict.fromkeys(terms))
        runtime = _load_runtime_config()
        runtime["timeout_seconds"] = float(max(self._timeout, float(runtime["timeout_seconds"])))
        chunk_size = int(runtime["max_terms_per_request"])
        aggregated: dict[str, list[dict[str, Any]]] = {}
        for batch in _chunk_terms(unique, chunk_size):
            batch_results = await self._resolve_batch_raw(batch, expected_tags, runtime)
            if not batch_results and batch:
                return {}
            aggregated.update(batch_results)
        return aggregated
