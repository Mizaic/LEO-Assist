"""A gold-synced fact must carry its assertion, like a pipeline fact does.

The runtime pipeline writes ``r.assertion`` on the ``:DOCUMENTS``
relationship (``libs/cypher/documents_queries.py``). ``PatientGraphWriter``
-- the writer behind gold sync and manual coded-link edits -- wrote only
the ``r.context`` JSON blob, so ``r.assertion`` stayed null on every
relationship it touched.

Clinical consequence: a reader that trusts ``r.assertion`` sees null for
a gold-synced fact. A finding the clinician recorded as historical, or
as absent, then reads as a current positive finding. "Breast lump,
historical" becomes "breast lump", which is the kind of fact that pulls
a patient onto an urgent cancer pathway.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-F71A6A69 (clinical facts storage)
  DO: DO-92F92EFB
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.services.patient_graph_writer import (  # noqa: E402
    PatientGraphWriter,
    SemanticLinkPayload,
)


class _RecordingSession:
    def __init__(self) -> None:
        self.query: str = ""
        self.params: dict[str, Any] = {}

    def run(self, query: str, **params: Any) -> None:
        self.query = query
        self.params = params


def _payload(assertion: str | None) -> SemanticLinkPayload:
    context: dict[str, Any] = {}
    if assertion is not None:
        context = {"assertion": assertion, "historical": assertion == "historical"}
    return SemanticLinkPayload(
        encounter_id="enc-1",
        semantic_tag="finding",
        concept_id="89164003",
        term="Breast lump",
        read_code=None,
        evidence="biopsy of a breast lump in January",
        confidence=0.93,
        domain="clinical",
        context=context,
        modifiers={},
        source="gold_sync",
    )


def _write(assertion: str | None) -> _RecordingSession:
    session = _RecordingSession()
    PatientGraphWriter().upsert_documents_link(_payload(assertion), session=session)
    return session


# ---------------------------------------------------------------------------
# The assertion must reach the relationship property, not only the JSON
# ---------------------------------------------------------------------------


def test_the_query_stamps_the_assertion_property() -> None:
    assert "r.assertion" in _write("historical").query


@pytest.mark.parametrize("assertion", ["historical", "absent", "negated", "present"])
def test_the_assertion_is_passed_through_for_each_value(assertion: str) -> None:
    assert _write(assertion).params.get("assertion") == assertion


def test_a_historical_finding_is_not_written_as_current() -> None:
    session = _write("historical")
    assert session.params.get("assertion") == "historical"
    assert session.params["assertion"] != "present"


def test_the_context_blob_still_carries_the_assertion() -> None:
    """The existing readers parse r.context. Do not break them."""
    session = _write("historical")
    assert json.loads(session.params["context"])["assertion"] == "historical"


def test_a_payload_with_no_assertion_defaults_to_present() -> None:
    """Matches the pipeline writer, which coerces a missing value."""
    assert _write(None).params.get("assertion") == "present"


def test_nothing_is_written_without_a_concept_id() -> None:
    session = _RecordingSession()
    payload = _payload("historical")
    blank = SemanticLinkPayload(**{**payload.__dict__, "concept_id": ""})
    PatientGraphWriter().upsert_documents_link(blank, session=session)
    assert session.query == ""
