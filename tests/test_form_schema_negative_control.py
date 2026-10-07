"""Negative control: a taught form is recognised from text, per organisation.

Atlas trace: DI-E21DF9EF (form recognition; no hash or service fallback),
DO-E458EEC5, VT-B13F7C48. Tenant isolation: another organisation's taught
forms are never candidates.

The same Sherwood letter is recognised only when the Sherwood form is a
candidate for the receiving organisation. Another trust gets no Sherwood
candidate, so the same text is unrecognised and pauses for a person. The
service id plays no part: a service may have several forms.

Every Neo4j call here goes through a stub that filters the way
``LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG`` does. Nothing touches a live graph.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from libs.pipeline.document_chunk_loader import build_document_chunk_state
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_store import _schema_to_sections_json, reset_schema_cache
from tests.form_recognition_corpus import load_schemas

TAUGHT_ORG_ID = "RK5"
OTHER_ORG_ID = "RC9"
TAUGHT_FINGERPRINT = "sfh-gynae-2ww-v1"

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_schema_cache()
    yield
    reset_schema_cache()


def _sherwood(organization_id: str, service_id: str = "7980224") -> FormSchema:
    (schema,) = [s for s in load_schemas() if s.fingerprint == TAUGHT_FINGERPRINT]
    return replace(schema, organization_id=organization_id, service_id=service_id)


def _row(schema: FormSchema) -> dict[str, Any]:
    return {
        "schema_id": schema.schema_id or "seed-1",
        "fingerprint": schema.fingerprint,
        "form_name": schema.form_name,
        "sections_json": _schema_to_sections_json(schema),
        "chunk_section_map": "[]",
        "created_by": "seed",
        "version": 1,
        "status": "active",
        "organization_id": schema.organization_id,
        "service_id": schema.service_id,
    }


class _StubGraph:
    """Returns national forms plus forms taught for the queried organisation."""

    def __init__(self, stored: list[FormSchema]) -> None:
        self._stored = stored
        self.calls: list[dict[str, Any]] = []

    def run(self, _query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(params))
        org = params.get("organization_id") or ""
        return [
            _row(s)
            for s in self._stored
            if not s.organization_id or (org and s.organization_id == org)
        ]

    def close(self) -> None:
        return None


def _sherwood_rows() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        {"chunk_id": f"c{index}", "text": chunk["text"], "ordinal": index}
        for index, chunk in enumerate(payload["chunks"])
    ]


def _state(client: _StubGraph, organization_id: str) -> dict[str, Any]:
    with patch("libs.neo4j_client.client.PatientGraphClient", return_value=client):
        return build_document_chunk_state(
            _sherwood_rows(), organization_id=organization_id
        )


def _sherwood_outcome(state: dict[str, Any]) -> dict[str, Any]:
    return state["form_recognition"][0]


def test_the_sherwood_letter_is_recognised_for_its_own_trust() -> None:
    state = _state(_StubGraph([_sherwood(TAUGHT_ORG_ID)]), TAUGHT_ORG_ID)
    outcome = _sherwood_outcome(state)
    assert outcome["outcome"] == "recognised"
    assert outcome["fingerprint"] == TAUGHT_FINGERPRINT


def test_another_trust_never_gets_the_sherwood_form() -> None:
    """Same letter, other organisation: unrecognised, never bound."""
    client = _StubGraph([_sherwood(TAUGHT_ORG_ID)])
    state = _state(client, OTHER_ORG_ID)
    assert _sherwood_outcome(state)["outcome"] == "unrecognised"
    assert state["form_schema_fingerprint"] == "none"
    assert [call["organization_id"] for call in client.calls] == [OTHER_ORG_ID]


def test_no_taught_forms_anywhere_leaves_the_letter_unrecognised() -> None:
    state = _state(_StubGraph([]), TAUGHT_ORG_ID)
    assert _sherwood_outcome(state)["outcome"] == "unrecognised"
    assert state["form_schema_match"] in {"unrecognised", "failed"}


def test_the_service_id_plays_no_part() -> None:
    """A form taught on another service of the same trust is still recognised."""
    other_service = _sherwood(TAUGHT_ORG_ID, service_id="9999999")
    state = _state(_StubGraph([other_service]), TAUGHT_ORG_ID)
    assert _sherwood_outcome(state)["outcome"] == "recognised"


def test_a_blank_organisation_only_sees_national_forms() -> None:
    state = _state(_StubGraph([_sherwood(TAUGHT_ORG_ID)]), "")
    assert _sherwood_outcome(state)["outcome"] == "unrecognised"
