"""An email attachment is not the taught referral form.

Building state for a communication thread went through
``build_document_chunk_state``, which fingerprints the chunks and looks the
fingerprint up as a taught referral form. Two things follow, both wrong.

The lookup fails closed when Neo4j cannot answer -- correctly, because a
missing safety layer must not look like "no schema found"
(``fail-closed-boundary.mdc`` rule 2). But that means assembling a
communication thread now depends on the graph being reachable for a lookup it
never needed. The symptom was ``tests/test_ag_pipeline_parity.py`` making a
real Bolt connection to localhost and dying with ``FormSchemaLookupError``.

It is also a wasted round trip per message, on a path that runs once per
message in a thread.

An attachment on a clinician's email is not the referral form the trust
taught us, so there is nothing to resolve. The caller says so explicitly.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  Risk: R-294446BF
"""

from __future__ import annotations

import pytest

from libs.pipeline.communication_thread_loader import (
    build_communication_thread_state,
)
from libs.pipeline.document_chunk_loader import build_document_chunk_state

ROWS = [{"chunk_id": "chunk-a", "text": "Hb 120 g/L", "ordinal": 1}]


@pytest.fixture
def no_graph(monkeypatch):
    """Make any Neo4j client construction an immediate, loud failure."""
    calls: list[str] = []

    def _explode(*_args, **_kwargs):
        calls.append("constructed")
        raise AssertionError("a Neo4j client was constructed")

    monkeypatch.setattr(
        "libs.neo4j_client.client.PatientGraphClient.__init__", _explode
    )
    return calls


def test_attachment_state_needs_no_graph(no_graph) -> None:
    state = build_document_chunk_state(ROWS, resolve_schema=False)

    assert [s["text"] for s in state["sentences"]] == ["Hb 120 g/L"]
    assert no_graph == []


def test_offsets_and_labels_are_unchanged_when_skipping(no_graph) -> None:
    state = build_document_chunk_state(ROWS, resolve_schema=False)

    sentence = state["sentences"][0]
    assert sentence["sentence_id"] == "s0"
    assert sentence["chunk_id"] == "chunk-a"
    assert state["chunk_id_by_sentence_id"] == {"s0": "chunk-a"}


def test_encounter_text_is_unchanged_when_skipping(no_graph) -> None:
    state = build_document_chunk_state(ROWS, resolve_schema=False)

    assert state["encounter_text"] == "Hb 120 g/L"


def test_schema_fields_say_the_lookup_was_not_attempted(no_graph) -> None:
    """Not "none": a lookup we chose not to make is not a lookup that missed."""
    state = build_document_chunk_state(ROWS, resolve_schema=False)

    assert state.get("form_schema_match") == "not_applicable"


def test_building_a_thread_needs_no_graph(no_graph) -> None:
    """The real regression: this used to open a Bolt connection."""
    loaded = build_communication_thread_state(
        communication_request_id="cr-1",
        thread_rows=[
            {
                "communication_id": "c1",
                "note": "See attachment",
                "category": "REQUESTER",
                "sent_datetime": "2026-01-01T09:00:00",
                "attachment_chunks": ROWS,
            }
        ],
        cr_attachment_rows=[],
        agr_response_text="Proceed with referral",
    )

    assert loaded["chunk_id_by_sentence_id"] == {"s0": "chunk-a"}
    assert no_graph == []


def test_the_referral_path_still_resolves_a_schema() -> None:
    """Skipping must be opt-in only; the referral bundle still looks up."""
    import inspect

    sig = inspect.signature(build_document_chunk_state)
    assert sig.parameters["resolve_schema"].default is True
