"""Neo4j client wrappers for Patient Graph and Knowledge Graph.

Atlas trace:
  DO: DO-448BFA1A
  DI: DI-84F44836
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-448BFA1A")

Ported from Primary-care-audit services/api/app/db/neo4j_client.py.
Renamed CodingGraphClient -> KnowledgeGraphClient to reflect the merged
terminology + FHIR resource graph.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Fallback for scripts and test harnesses that import this lib directly without
# going through a service main.py (which calls load_keyvault_secrets() first).
# Services always call load_keyvault_secrets() before importing, so KV wins.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
import atexit
import random
import threading
import time
from contextlib import contextmanager
from typing import Any

from neo4j import AsyncGraphDatabase, GraphDatabase
from neo4j.exceptions import (
    ConfigurationError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

logger = logging.getLogger("libs.neo4j_client")

_RETRYABLE_EXCEPTIONS = (ServiceUnavailable, SessionExpired, TransientError, OSError)
_MAX_RETRIES = 4
_BASE_DELAY = 1.0
_MAX_DELAY = 30.0


def run_with_retry(
    client: "_BaseClient",
    query: str,
    **params: Any,
) -> list[dict[str, Any]]:
    """Execute a Cypher query with automatic retry on transient connection errors."""
    last_exc: BaseException | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with client.session() as s:
                return [dict(r) for r in s.run(query, **params)]
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = min(_MAX_DELAY, _BASE_DELAY * (2**attempt)) + random.uniform(0, 0.5)
            logger.warning(
                "Neo4j transient error (attempt %d/%d): %s -- retrying in %.1fs",
                attempt + 1,
                _MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Neo4j request failed after retries")


# -- Process-wide driver singletons -----------------------------------------
# A Neo4j driver is designed to be a long-lived, thread-safe singleton; it
# manages its own connection pool internally. Constructing one per request
# pays the full TLS handshake to Aura on every call. We cache the driver
# keyed by (uri, username) so multiple wrapper instantiations share the same
# pool without the call sites having to change.

_DRIVER_CACHE: dict[tuple[str, str], Any] = {}
_DRIVER_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


def _close_all_cached_drivers() -> None:
    """Close every cached driver at interpreter shutdown."""
    with _DRIVER_LOCK:
        drivers = list(_DRIVER_CACHE.values())
        _DRIVER_CACHE.clear()
    for d in drivers:
        try:
            d.close()
        except Exception:
            pass


def _build_driver(
    uri: str,
    username: str,
    password: str,
    notifications_min_severity: str,
):
    # liveness_check_timeout: if a pooled connection has been idle for this
    # many seconds the driver sends a lightweight check before reusing it.
    # This prevents SSLEOFError when Aura closes idle TCP connections during
    # long-running operations (e.g. LLM disambiguation batches).
    # max_connection_pool_size: bound per-process pool. Aura's default is 100;
    # 50 is plenty for a single uvicorn worker and prevents any one process
    # from exhausting the cluster-wide quota.
    _pool_kwargs: dict = {
        "liveness_check_timeout": 5,
        "max_connection_lifetime": int(
            os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "240")
        ),
        "max_connection_pool_size": int(os.getenv("NEO4J_MAX_POOL_SIZE", "50")),
        "connection_acquisition_timeout": float(
            os.getenv("NEO4J_ACQUIRE_TIMEOUT", "60")
        ),
    }
    try:
        return GraphDatabase.driver(
            uri,
            auth=(username, password),
            notifications_min_severity=notifications_min_severity,
            **_pool_kwargs,
        )
    except ConfigurationError:
        try:
            return GraphDatabase.driver(
                uri,
                auth=(username, password),
                **_pool_kwargs,
            )
        except ConfigurationError:
            return GraphDatabase.driver(uri, auth=(username, password))


def _get_or_create_driver(
    uri: str,
    username: str,
    password: str,
    *,
    notifications_min_severity: str = "OFF",
):
    """Return the process-wide driver for `(uri, username)`, creating once."""
    global _ATEXIT_REGISTERED
    key = (uri, username)
    cached = _DRIVER_CACHE.get(key)
    if cached is not None:
        return cached
    with _DRIVER_LOCK:
        cached = _DRIVER_CACHE.get(key)
        if cached is not None:
            return cached
        driver = _build_driver(uri, username, password, notifications_min_severity)
        _DRIVER_CACHE[key] = driver
        if not _ATEXIT_REGISTERED:
            atexit.register(_close_all_cached_drivers)
            _ATEXIT_REGISTERED = True
        logger.info(
            "Neo4j driver pool initialised for uri=%s user=%s (cached=%d)",
            uri,
            username,
            len(_DRIVER_CACHE),
        )
        return driver


class _BaseClient:
    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        *,
        notifications_min_severity: str = "OFF",
    ) -> None:
        if not all([uri, username, password]):
            raise RuntimeError(f"Neo4j credentials missing for {uri or 'unknown'}")
        self._driver = _get_or_create_driver(
            uri,
            username,
            password,
            notifications_min_severity=notifications_min_severity,
        )

    def close(self) -> None:
        # Cached drivers are closed at interpreter exit. Per-instance close()
        # is intentionally a no-op so legacy `client.close()` calls do not
        # tear down the shared pool out from under concurrent callers.
        return None

    @contextmanager
    def session(self):
        s = self._driver.session()
        try:
            yield s
        finally:
            s.close()

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        return run_with_retry(self, query, **params)


class PatientGraphClient(_BaseClient):
    """Connects to the Patient Graph (NEO4J_URI).

    Contains: Patient, Encounter, EncounterCandidate, ReviewTask,
    Approval, Change, EpisodeOfCare, SafetyNetAlert, Benchmark, etc.
    """

    def __init__(self) -> None:
        super().__init__(
            os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", ""),
            os.getenv("NEO4J_USER", "")
            or os.getenv("NEO4J_PATIENT_USER", "")
            or "neo4j",
            os.getenv("NEO4J_PASSWORD", "") or os.getenv("NEO4J_PATIENT_PASSWORD", ""),
        )


class KnowledgeGraphClient(_BaseClient):
    """Connects to the Knowledge Graph (KNOWLEDGE_GRAPH_NEO4J_URI).

    Contains anonymous/de-identified model knowledge — no patient identifiers:
      Terminology:   Concept, Term, SurfaceForm, ReadCode, Icd10Code, ValueSet,
                     ConceptMap, CodingDecision, SurfaceFormTask
      Learning loop: TrainingCandidate, GoldLabel  (GDPR-isolated)
      Pipeline:      PromptConfig, PipelineConfig, Device, PlanDefinition,
                     ModelVersion, ModelRegistryConfig, ModelPreset
      Org/FHIR:      Measure, Library, MeasureReport, Organization
    """

    def __init__(self) -> None:
        super().__init__(
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "")
            or os.getenv("NEO4J_KNOWLEDGE_URI", ""),
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
            or os.getenv("NEO4J_KNOWLEDGE_USER", "")
            or "neo4j",
            os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
            or os.getenv("NEO4J_KNOWLEDGE_PASSWORD", ""),
        )


def _async_pool_kwargs() -> dict:
    """Hardening kwargs shared by every async driver.

    - liveness_check_timeout: lightweight ping before reusing a pooled
      connection that has been idle for more than this many seconds.
      Catches connections that the Aura load-balancer closed silently
      while the worker was busy with an LLM call.
    - max_connection_lifetime: forcibly recycle connections after this
      many seconds. Aura closes the underlying TCP socket after roughly
      five minutes of idleness, which surfaces as BrokenPipeError on the
      next write. Recycling at four minutes stays inside that window.
    - max_connection_pool_size: bound per-process pool. Async workers
      tend to fan out -- 50 is plenty for a single uvicorn worker and
      keeps any one process from exhausting the cluster-wide quota.
    - connection_acquisition_timeout: do not hang forever waiting for a
      pooled connection if the pool is saturated.
    """
    return {
        "liveness_check_timeout": 5,
        "max_connection_lifetime": int(
            os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "240")
        ),
        "max_connection_pool_size": int(os.getenv("NEO4J_MAX_POOL_SIZE", "50")),
        "connection_acquisition_timeout": float(
            os.getenv("NEO4J_ACQUIRE_TIMEOUT", "60")
        ),
    }


def _build_async_driver(uri: str, username: str, password: str):
    """Create an async driver with the hardening kwargs, falling back if
    the installed neo4j package does not recognise one of them."""
    kwargs = _async_pool_kwargs()
    try:
        return AsyncGraphDatabase.driver(uri, auth=(username, password), **kwargs)
    except ConfigurationError:
        return AsyncGraphDatabase.driver(uri, auth=(username, password))


def get_async_driver():
    """Return an async Neo4j driver for the Knowledge Graph.

    Workflow plans, actions, and activity definitions are stored in the
    knowledge graph, so the pipeline worker needs an async KG driver rather
    than the patient-graph client wrappers above.
    """
    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    username = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "") or "neo4j"
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, username, password]):
        raise RuntimeError("Neo4j credentials missing for async knowledge graph driver")
    return _build_async_driver(uri, username, password)


def get_async_patient_driver():
    """Return an async Neo4j driver for the Patient Graph."""
    uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "")
    username = (
        os.getenv("NEO4J_USER", "") or os.getenv("NEO4J_PATIENT_USER", "") or "neo4j"
    )
    password = os.getenv("NEO4J_PASSWORD", "") or os.getenv(
        "NEO4J_PATIENT_PASSWORD", ""
    )
    if not all([uri, username, password]):
        raise RuntimeError("Neo4j credentials missing for async patient graph driver")
    return _build_async_driver(uri, username, password)
