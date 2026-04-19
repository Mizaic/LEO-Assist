"""Verification tests for server-side search term expansion (VT-LEO-AI-524).

DI-LEO-AI-526 -- the dry-run review queue (`/api/training/candidates`
and `/api/training/gold-labels`) expands the reviewer's free-text query
into the same typo-corrected, synonym-expanded term list used by the
host encounter search on `/care/encounters`. The cypher then OR-matches
across the term list so a search for "lump" surfaces rows that wrote
"mass", "swelling", or "nodule" without a second server round-trip.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import require_admin
from app.routers.training import (
    COUNT_GOLD_LABELS_PAGE,
    COUNT_TRAINING_CANDIDATES_PAGE,
    GET_GOLD_LABELS_PAGE,
    GET_TRAINING_CANDIDATES_PAGE,
    router as training_router,
)
from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.search.term_expansion import expand_search_terms


@contextmanager
def admin_scope_override(app: FastAPI):
    scope = CallerScope(email="admin@example.com", is_admin=True, org_ids=[])
    app.dependency_overrides[get_caller_scope] = lambda: scope
    app.dependency_overrides[require_admin] = lambda: scope
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_caller_scope, None)
        app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(training_router)
    return test_app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-Requested-With": "XMLHttpRequest"})
        yield c


def _capture_session(monkeypatch_calls: list[tuple[str, dict]]):
    inner = MagicMock()

    def fake_run(query, **kwargs):
        monkeypatch_calls.append((query, dict(kwargs)))
        result = MagicMock()
        if query in (COUNT_TRAINING_CANDIDATES_PAGE, COUNT_GOLD_LABELS_PAGE):
            result.single.return_value = {"total": 0}
            return result
        result.__iter__ = lambda self: iter([])
        return result

    inner.run.side_effect = fake_run
    return inner


# ---------------------------------------------------------------------------
# VT-522-TC-001 -- expand_search_terms expands typos and synonyms
# ---------------------------------------------------------------------------
def test_expand_search_terms_expands_typo_and_synonyms() -> None:
    """A query with a typo + a synonym head expands to the full list."""
    terms = expand_search_terms("breat lump")
    assert terms[0] == "breast"
    assert "mammary" in terms
    assert "lump" in terms
    assert "mass" in terms
    assert "swelling" in terms


def test_expand_search_terms_returns_empty_for_blank() -> None:
    assert expand_search_terms("") == []
    assert expand_search_terms(None) == []
    assert expand_search_terms("   ") == []


# ---------------------------------------------------------------------------
# VT-522-TC-002 -- /candidates passes expanded terms to cypher
# ---------------------------------------------------------------------------
def test_list_training_candidates_forwards_expanded_terms_to_cypher(
    client,
) -> None:
    captured: list[tuple[str, dict]] = []
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = _capture_session(captured)
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/training/candidates?search=lump")
        assert r.status_code == 200

    page_calls = [c for c in captured if c[0] == GET_TRAINING_CANDIDATES_PAGE]
    count_calls = [c for c in captured if c[0] == COUNT_TRAINING_CANDIDATES_PAGE]
    assert page_calls and count_calls

    page_kwargs = page_calls[0][1]
    assert page_kwargs["search"] == "lump"
    assert page_kwargs["terms"] == ["lump", "mass", "swelling", "nodule"]

    count_kwargs = count_calls[0][1]
    assert count_kwargs["terms"] == page_kwargs["terms"]


# ---------------------------------------------------------------------------
# VT-522-TC-003 -- /candidates with no search passes empty terms list
# ---------------------------------------------------------------------------
def test_list_training_candidates_no_search_passes_empty_terms(client) -> None:
    captured: list[tuple[str, dict]] = []
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = _capture_session(captured)
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/training/candidates")
        assert r.status_code == 200

    page_kwargs = next(c[1] for c in captured if c[0] == GET_TRAINING_CANDIDATES_PAGE)
    assert page_kwargs["terms"] == []
    assert page_kwargs["search"] is None


# ---------------------------------------------------------------------------
# VT-522-TC-004 -- /gold-labels also forwards expanded terms
# ---------------------------------------------------------------------------
def test_list_gold_labels_forwards_expanded_terms_to_cypher(client) -> None:
    captured: list[tuple[str, dict]] = []
    with (
        admin_scope_override(client.app),
        patch("app.routers.training.KnowledgeGraphClient") as MockKG,
    ):
        kg = MockKG.return_value
        inner = _capture_session(captured)
        kg.session.return_value.__enter__ = lambda s: inner
        kg.session.return_value.__exit__ = MagicMock(return_value=False)

        r = client.get("/training/gold-labels?search=weight loss")
        assert r.status_code == 200

    page_kwargs = next(c[1] for c in captured if c[0] == GET_GOLD_LABELS_PAGE)
    count_kwargs = next(c[1] for c in captured if c[0] == COUNT_GOLD_LABELS_PAGE)
    assert "weight" in page_kwargs["terms"]
    assert "loss" in page_kwargs["terms"]
    assert "cachexia" in page_kwargs["terms"]
    assert page_kwargs["terms"] == count_kwargs["terms"]


# ---------------------------------------------------------------------------
# VT-522-TC-005 -- cypher uses CASE so terms takes precedence over search
# ---------------------------------------------------------------------------
def test_candidate_cypher_includes_terms_branch() -> None:
    """The cypher must branch: ANY(t IN $terms WHERE ... CONTAINS t)."""
    assert "$terms" in GET_TRAINING_CANDIDATES_PAGE
    assert "ANY(t IN $terms WHERE toLower(c.text) CONTAINS t)" in (
        GET_TRAINING_CANDIDATES_PAGE
    )
    assert "$terms" in COUNT_TRAINING_CANDIDATES_PAGE


def test_gold_label_cypher_includes_terms_branch() -> None:
    assert "$terms" in GET_GOLD_LABELS_PAGE
    assert "ANY(t IN $terms WHERE toLower(g.text) CONTAINS t)" in (
        GET_GOLD_LABELS_PAGE
    )
    assert "$terms" in COUNT_GOLD_LABELS_PAGE


# ---------------------------------------------------------------------------
# VT-522-TC-006 -- the deterministic floor stays in lock-step with the
# analytics layer (same TYPO_MAP / SYNONYM_MAP source)
# ---------------------------------------------------------------------------
def test_shared_term_expansion_is_single_source_of_truth() -> None:
    from libs.search.term_expansion import SYNONYM_MAP, TYPO_MAP
    from services.analytics_api.app.services import (
        encounter_query_understanding as eqi,
    )

    assert eqi._TYPO_MAP is TYPO_MAP
    assert eqi._SYNONYM_MAP is SYNONYM_MAP
