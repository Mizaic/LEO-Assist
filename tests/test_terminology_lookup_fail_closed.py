"""Site 8: a terminology outage must not read as "no such clinical term".

``TerminologyClient.resolve`` returned ``{}`` when the resolve service was
unreachable. The terminology subgraph then did ``results.get(lookup, [])``,
so every span came back with ``coding_candidates: []`` and
``terminology_unresolved: True`` -- the exact shape produced when the
service is healthy and genuinely holds no safe match. The run finished as
``completed`` with a warning, and persist dropped the facts.

`.cursor/rules/fail-closed-boundary.mdc` rule 2: "Lookups have three
answers, not two. A resolution lookup returns Found, NotFound, or
LookupFailed. None may only mean definitely not there. It must never
also mean we could not ask."

Clinical consequence: during a terminology outage a referral is coded as
though the letter contained nothing codeable. Real findings are silently
absent from the record, and the warning a reviewer sees says "no SNOMED
match found" -- which is untrue and points the reviewer at the letter
instead of at the outage.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F (degraded runs routed to human review)
  DI: DI-00DFB149 (look up recognised clinical terms for patient facts)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from libs.pipeline_graph.subgraphs.terminology import _resolve_terms
from libs.terminology.client import (
    AsyncTerminologyClient,
    ResolvedTerm,
    TerminologyClient,
    TerminologyUnavailable,
)

# Keep the retry ladder short so the tests do not sleep.
_FAST_RUNTIME: dict[str, float | int] = {
    "timeout_seconds": 1.0,
    "max_retries": 0,
    "cooldown_seconds": 0.0,
    "final_attempts": 1,
    "max_terms_per_request": 50,
    "max_concurrent_requests": 4,
}


class _DeadHttpClient:
    """httpx.Client stand-in whose every POST fails."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_DeadHttpClient":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False

    def post(self, *_args: Any, **_kwargs: Any):
        raise ConnectionError("terminology service unreachable")


class _EmptyHttpClient:
    """A healthy service that holds no match for the term."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_EmptyHttpClient":
        return self

    def __exit__(self, *_exc: Any) -> bool:
        return False

    def post(self, *_args: Any, **_kwargs: Any):
        return _Response({"results": {"benign": []}})


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture(autouse=True)
def _hermetic():
    """No redis cache, no service-config lookup, no sleeping."""
    with (
        patch("libs.terminology.client._cache_get_json", return_value=None),
        patch("libs.terminology.client._cache_set_json", return_value=None),
        patch(
            "libs.terminology.client._load_runtime_config",
            return_value=dict(_FAST_RUNTIME),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# NotFound must keep working exactly as it did
# ---------------------------------------------------------------------------


def test_a_healthy_service_with_no_match_returns_an_empty_candidate_list() -> None:
    with patch("httpx.Client", _EmptyHttpClient):
        results = TerminologyClient().resolve(["benign"])
    assert results == {"benign": []}


def test_a_healthy_service_with_no_match_does_not_raise() -> None:
    """NotFound is a normal answer. Only LookupFailed is exceptional."""
    with patch("httpx.Client", _EmptyHttpClient):
        TerminologyClient().resolve(["benign"])


def test_no_terms_asked_is_not_a_failure() -> None:
    assert TerminologyClient().resolve([]) == {}


# ---------------------------------------------------------------------------
# Site 8 -- LookupFailed is a third answer, never NotFound
# ---------------------------------------------------------------------------


def test_an_unreachable_service_raises_instead_of_returning_empty() -> None:
    with patch("httpx.Client", _DeadHttpClient):
        with pytest.raises(TerminologyUnavailable):
            TerminologyClient().resolve(["benign"])


def test_the_outage_error_says_what_happened_in_plain_english() -> None:
    with patch("httpx.Client", _DeadHttpClient):
        with pytest.raises(TerminologyUnavailable) as excinfo:
            TerminologyClient().resolve(["benign"])
    message = str(excinfo.value)
    assert message.isascii()
    assert "could not" in message.lower()
    assert "terminolog" in message.lower()


def test_an_outage_is_not_reported_as_one_term_having_no_match() -> None:
    """The bug: every asked term came back keyed to an empty list."""
    with patch("httpx.Client", _DeadHttpClient):
        try:
            results = TerminologyClient().resolve(["benign", "breast lump"])
        except TerminologyUnavailable:
            return
    pytest.fail(
        "an outage must not be answered with per-term empty candidate "
        f"lists that look like a genuine miss: {results!r}"
    )


# ---------------------------------------------------------------------------
# The subgraph must degrade the run, not finish it
# ---------------------------------------------------------------------------


def _state() -> dict[str, Any]:
    return {
        "encounter_text": "The biopsy was reported as benign.",
        "entities": [
            {"text": "benign", "semantic_tag": "finding", "assertion": "present"}
        ],
    }


def test_a_terminology_outage_degrades_the_run() -> None:
    with patch.object(
        TerminologyClient,
        "resolve",
        side_effect=TerminologyUnavailable("could not reach terminology"),
    ):
        result = _resolve_terms(_state())  # type: ignore[arg-type]

    assert result.get("degraded") is True, (
        "a terminology outage must mark the run degraded so a person looks "
        f"at it, not finish as completed: {result!r}"
    )


def test_a_terminology_outage_is_not_stamped_as_terminology_unresolved() -> None:
    """``terminology_unresolved`` means "we asked and there is no safe code"."""
    with patch.object(
        TerminologyClient,
        "resolve",
        side_effect=TerminologyUnavailable("could not reach terminology"),
    ):
        result = _resolve_terms(_state())  # type: ignore[arg-type]

    for entity in result.get("entities") or []:
        assert entity.get("terminology_lookup_failed") is True, (
            "an entity we could not look up must carry the lookup failure, "
            f"not a plain unresolved flag: {entity!r}"
        )


def test_the_outage_reaches_a_human_readable_warning() -> None:
    with patch.object(
        TerminologyClient,
        "resolve",
        side_effect=TerminologyUnavailable("could not reach terminology"),
    ):
        result = _resolve_terms(_state())  # type: ignore[arg-type]

    said = " ".join(
        list(result.get("warnings") or []) + list(result.get("errors") or [])
    )
    assert said.isascii()
    assert "terminolog" in said.lower()
    assert "no SNOMED match" not in said, (
        "an outage must never be described to a reviewer as the letter "
        f"having no matching code: {said!r}"
    )


def test_a_genuine_miss_still_completes_without_degrading() -> None:
    """Regression guard: NotFound must not start pausing every run."""
    with patch.object(TerminologyClient, "resolve", return_value={"benign": []}):
        result = _resolve_terms(_state())  # type: ignore[arg-type]

    assert result.get("degraded") is not True
    entities = result.get("entities") or []
    assert entities and entities[0].get("terminology_unresolved") is True
    assert not entities[0].get("terminology_lookup_failed")


def test_the_async_client_also_raises_rather_than_answering_empty() -> None:
    """The pipeline has two clients. Fixing one would leave the site open."""
    import asyncio

    class _DeadAsyncClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def __aenter__(self) -> "_DeadAsyncClient":
            return self

        async def __aexit__(self, *_exc: Any) -> bool:
            return False

        async def post(self, *_a: Any, **_k: Any):
            raise ConnectionError("terminology service unreachable")

    with patch("httpx.AsyncClient", _DeadAsyncClient):
        with pytest.raises(TerminologyUnavailable):
            asyncio.run(AsyncTerminologyClient().resolve(["benign"]))


def test_a_resolved_term_still_codes_normally() -> None:
    candidate = ResolvedTerm(
        text="benign",
        concept_id="395100000",
        term="No evidence of cancer found (situation)",
        semantic_tag="situation",
        score=0.97,
        had_exact_match=True,
    )
    with patch.object(
        TerminologyClient, "resolve", return_value={"benign": [candidate]}
    ):
        result = _resolve_terms(_state())  # type: ignore[arg-type]

    assert result.get("degraded") is not True
    assert not (result.get("entities") or [{}])[0].get("terminology_lookup_failed")
