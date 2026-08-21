"""A NICE guideline re-ingest must never silently retire an approved rule.

Regression coverage for the 2026-07-30 incident: confirming a "Check for
updates" re-ingest on NG12 superseded every approved (``active``) rule in
one shot, emptying the review queue with no replacement rules generated.

Atlas: DI-C2DE7FDF / DO-F8CDEBBA / R-02B6E3E3 / VT-34F3B9C2

Unit-level (no live Neo4j): patches ``_kg_driver`` with an in-memory fake
that records every Cypher statement + params so we can assert on exactly
which rules a re-ingest is allowed to touch, and how.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# nice_graph_upserter.py uses an absolute `from app.services...` import that
# only resolves once services/api is on sys.path (as it is under uvicorn /
# the services/api/tests conftest). Root-level tests/ need the same setup.
_API_ROOT = Path(__file__).resolve().parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# A local `redis` shadow (or a missing extra) breaks collection via
# app.services.nice_api_client -> redis.asyncio.
pytest.importorskip("redis.asyncio")

from services.api.app.services import (  # noqa: E402
    nice_graph_upserter as upserter_module,
)
from services.api.app.services.nice_graph_upserter import (  # noqa: E402
    NiceGraphUpserter,
)


class _FakeResult:
    def __init__(self, record: dict[str, Any] | None) -> None:
        self._record = record

    def single(self) -> dict[str, Any] | None:
        return self._record


class _FakeSession:
    """Records every query run and returns a caller-supplied count per query."""

    def __init__(self, counts_by_marker: dict[str, int]) -> None:
        self.counts_by_marker = counts_by_marker
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> _FakeResult:
        self.calls.append((query, params))
        for marker, count in self.counts_by_marker.items():
            if marker in query:
                key = (
                    "superseded_count"
                    if "superseded_count" in query
                    else ("flagged_count" if "flagged_count" in query else None)
                )
                if key:
                    return _FakeResult({key: count})
        return _FakeResult(None)

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session

    def close(self) -> None:
        return None


def _patched_upserter(
    counts_by_marker: dict[str, int]
) -> tuple[NiceGraphUpserter, _FakeSession, _FakeDriver]:
    session = _FakeSession(counts_by_marker)
    driver = _FakeDriver(session)
    return NiceGraphUpserter(), session, driver


def test_full_ingest_never_supersedes_active_rules() -> None:
    """Full (non-selective) re-ingest: active rules must stay active."""
    upserter, session, driver = _patched_upserter(
        {"superseded_count": 3, "flagged_count": 7}
    )
    with patch.object(upserter_module, "_kg_driver", return_value=driver):
        result = upserter.clear_guideline_content("NG12", changed_numbers=None)

    assert result == {"superseded": 3, "flagged_active": 7}

    supersede_calls = [c for c in session.calls if "SET rule.status" in c[0]]
    assert len(supersede_calls) == 1, "exactly one query may ever set rule.status"
    supersede_query = supersede_calls[0][0]
    assert "rule.status = 'pending_review'" in supersede_query
    assert (
        "'active'" not in supersede_query
    ), "an ingest-driven supersede query must never match active (approved) rules"

    flag_calls = [c for c in session.calls if "guidelineTextChanged" in c[0]]
    assert len(flag_calls) == 1
    flag_query = flag_calls[0][0]
    assert "rule.status = 'active'" in flag_query
    assert (
        "SET rule.status" not in flag_query
    ), "flagging an approved rule must never change its status"


def test_selective_ingest_never_supersedes_active_rules() -> None:
    """Smart/selective re-ingest: same guarantee, scoped to changed_numbers."""
    upserter, session, driver = _patched_upserter(
        {"superseded_count": 1, "flagged_count": 2}
    )
    with patch.object(upserter_module, "_kg_driver", return_value=driver):
        result = upserter.clear_guideline_content(
            "NG12", changed_numbers=["1.5.9", "1.5.10"]
        )

    assert result == {"superseded": 1, "flagged_active": 2}

    supersede_calls = [c for c in session.calls if "SET rule.status" in c[0]]
    assert len(supersede_calls) == 1
    assert "rule.status = 'pending_review'" in supersede_calls[0][0]
    assert supersede_calls[0][1]["changed_numbers"] == ["1.5.9", "1.5.10"]

    flag_calls = [c for c in session.calls if "guidelineTextChanged" in c[0]]
    assert len(flag_calls) == 1
    assert "rule.status = 'active'" in flag_calls[0][0]
    assert "SET rule.status" not in flag_calls[0][0]
    assert flag_calls[0][1]["changed_numbers"] == ["1.5.9", "1.5.10"]
