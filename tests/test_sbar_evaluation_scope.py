"""Tests for EvaluationScope in SBARRequestPayload and assessment_formatter.

VT: covers DI-8DD23CE2 and backwards compatibility of guideline_ids.

TC-001: EvaluationScope(mode="global") calls evaluate with scope_type=global.
TC-002: EvaluationScope(mode="guideline", guideline_ids=["NG12"]) does
        per-guideline loop (existing behaviour, scope_type=guideline).
TC-003: EvaluationScope(mode="pick", pick_scope_id="lower-gi") calls evaluate
        with scope_type=custom, scope_id=lower-gi (single call, no loop).
TC-004: Legacy guideline_ids=["NG12"] still works when evaluation_scope=None.
TC-005: SBARRequestPayload serialises and deserialises evaluation_scope.
TC-006: evaluation_scope=None and guideline_ids=[] falls back to global scope.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, call

import pytest

from libs.sbar.events import EvaluationScope, SBARRequestPayload


# -- TC-005: model round-trip -----------------------------------------------


def test_evaluation_scope_default_is_global():
    """TC-005a: default mode is global."""
    scope = EvaluationScope()
    assert scope.mode == "global"
    assert scope.guideline_ids == []
    assert scope.pick_scope_id is None


def test_evaluation_scope_guideline_mode():
    """TC-005b: guideline mode round-trips."""
    scope = EvaluationScope(mode="guideline", guideline_ids=["NG12", "NG151"])
    assert scope.guideline_ids == ["NG12", "NG151"]


def test_evaluation_scope_pick_mode():
    """TC-005c: pick mode carries scope_id."""
    scope = EvaluationScope(mode="pick", pick_scope_id="lower-gi")
    assert scope.pick_scope_id == "lower-gi"


def test_sbar_request_payload_accepts_evaluation_scope(minimal_payload):
    """TC-005d: SBARRequestPayload accepts evaluation_scope field."""
    payload = SBARRequestPayload(
        **minimal_payload,
        evaluation_scope=EvaluationScope(mode="pick", pick_scope_id="lower-gi"),
    )
    assert payload.evaluation_scope is not None
    assert payload.evaluation_scope.pick_scope_id == "lower-gi"


def test_sbar_request_payload_evaluation_scope_defaults_to_none(minimal_payload):
    """TC-005e: evaluation_scope is None by default -- backwards compat."""
    payload = SBARRequestPayload(**minimal_payload)
    assert payload.evaluation_scope is None


# -- TC-001 to TC-006: evaluate_codes_against_guidelines routing ------------


@pytest.fixture()
def minimal_payload():
    return {
        "run_id": "test-run",
        "situation": {
            "patient_id": "P001",
            "encounter_date": "2026-09-15",
            "coded_findings": [],
        },
    }


@pytest.fixture()
def empty_eval_response():
    return {"matched_rules": [], "active_version": "v1", "scope": "global"}


def _mock_http_response(data):
    from unittest.mock import MagicMock
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=data)
    return resp


@pytest.mark.asyncio
async def test_global_scope_calls_evaluate_global(empty_eval_response):
    """TC-001: mode=global -> scope_type=global, scope_id=default."""
    posted_bodies = []

    async def fake_post(url, *, json, **kw):
        posted_bodies.append(json)
        return _mock_http_response(empty_eval_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from libs.sbar.assessment_formatter import evaluate_codes_against_guidelines

        await evaluate_codes_against_guidelines(
            patient_codes=["12345"],
            evaluation_scope=EvaluationScope(mode="global"),
        )

    assert len(posted_bodies) == 1
    assert posted_bodies[0]["scope_type"] == "global"
    assert posted_bodies[0]["scope_id"] == "default"


@pytest.mark.asyncio
async def test_guideline_scope_loops_per_guideline(empty_eval_response):
    """TC-002: mode=guideline with two IDs -> two POST calls."""
    posted_bodies = []

    async def fake_post(url, *, json, **kw):
        posted_bodies.append(json)
        return _mock_http_response(empty_eval_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from libs.sbar.assessment_formatter import evaluate_codes_against_guidelines

        await evaluate_codes_against_guidelines(
            patient_codes=["12345"],
            evaluation_scope=EvaluationScope(
                mode="guideline", guideline_ids=["NG12", "NG151"]
            ),
        )

    assert len(posted_bodies) == 2
    scope_types = {b["scope_type"] for b in posted_bodies}
    scope_ids = {b["scope_id"] for b in posted_bodies}
    assert scope_types == {"guideline"}
    assert scope_ids == {"NG12", "NG151"}


@pytest.mark.asyncio
async def test_pick_scope_calls_custom_single(empty_eval_response):
    """TC-003: mode=pick -> single call with scope_type=custom, scope_id=lower-gi."""
    posted_bodies = []

    async def fake_post(url, *, json, **kw):
        posted_bodies.append(json)
        return _mock_http_response(empty_eval_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from libs.sbar.assessment_formatter import evaluate_codes_against_guidelines

        await evaluate_codes_against_guidelines(
            patient_codes=["12345"],
            evaluation_scope=EvaluationScope(
                mode="pick", pick_scope_id="lower-gi"
            ),
        )

    assert len(posted_bodies) == 1
    assert posted_bodies[0]["scope_type"] == "custom"
    assert posted_bodies[0]["scope_id"] == "lower-gi"


@pytest.mark.asyncio
async def test_legacy_guideline_ids_still_works(empty_eval_response):
    """TC-004: evaluation_scope=None + guideline_ids=["NG12"] uses guideline scope."""
    posted_bodies = []

    async def fake_post(url, *, json, **kw):
        posted_bodies.append(json)
        return _mock_http_response(empty_eval_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from libs.sbar.assessment_formatter import evaluate_codes_against_guidelines

        await evaluate_codes_against_guidelines(
            patient_codes=["12345"],
            guideline_ids=["NG12"],
            evaluation_scope=None,
        )

    assert len(posted_bodies) == 1
    assert posted_bodies[0]["scope_type"] == "guideline"
    assert posted_bodies[0]["scope_id"] == "NG12"


@pytest.mark.asyncio
async def test_no_scope_and_no_guideline_ids_falls_back_to_global(empty_eval_response):
    """TC-006: evaluation_scope=None and guideline_ids=[] -> global scope."""
    posted_bodies = []

    async def fake_post(url, *, json, **kw):
        posted_bodies.append(json)
        return _mock_http_response(empty_eval_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from libs.sbar.assessment_formatter import evaluate_codes_against_guidelines

        await evaluate_codes_against_guidelines(
            patient_codes=["12345"],
            evaluation_scope=None,
        )

    assert len(posted_bodies) == 1
    assert posted_bodies[0]["scope_type"] == "global"
