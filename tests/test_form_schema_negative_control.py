"""Negative control: taught-form binding is data-driven, not hardcoded.

Atlas trace: DI-26546721 (organisation and service bind)

The same Sherwood letter text must bind to a taught :FormSchema only when the
receiving Organization.id and Service.id on pipeline state match the ones
stored on the schema node. Change either id and the same text must stop
binding. That proves the pipeline reads the graph rather than recognising
Sherwood from the letter itself.

Every Neo4j call here goes through a stub. Nothing in this module touches a
live graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from libs.pipeline.document_chunk_loader import bundle_fingerprint
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import (
    _schema_to_sections_json,
    reset_schema_cache,
    resolve_form_schema_traced,
)

TAUGHT_ORG_ID = "RK5"
TAUGHT_SERVICE_ID = "7980224"
TAUGHT_FINGERPRINT = "sfh-gynae-2ww-v1"

OTHER_ORG_ID = "RC9"
OTHER_SERVICE_ID = "7956422"

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)


@pytest.fixture(scope="module")
def sherwood_letter_fingerprint() -> str:
    """Fingerprint of the real de-identified Sherwood bundle."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return bundle_fingerprint([c["text"] for c in payload["chunks"]])


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_schema_cache()
    yield
    reset_schema_cache()


def _schema(organization_id: str, service_id: str) -> FormSchema:
    return FormSchema(
        schema_id="seed-1",
        fingerprint=TAUGHT_FINGERPRINT,
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="section_c_clinical_details",
                section_type="free_text",
                label="Section C: Further Clinical details",
                start_pattern="Section C",
                items=[],
            )
        ],
        created_by="seed",
        status="active",
        organization_id=organization_id,
        service_id=service_id,
    )


def _row(schema: FormSchema) -> dict[str, Any]:
    return {
        "schema_id": schema.schema_id,
        "fingerprint": schema.fingerprint,
        "form_name": schema.form_name,
        "sections_json": _schema_to_sections_json(schema),
        "chunk_section_map": "[]",
        "created_by": schema.created_by,
        "version": 1,
        "status": schema.status,
        "organization_id": schema.organization_id,
        "service_id": schema.service_id,
    }


class _StubGraph:
    """Answers the two FormSchema lookups the way Neo4j would.

    ``GET_FORM_SCHEMA_BY_FINGERPRINT`` matches on the exact fingerprint.
    ``GET_ACTIVE_FORM_SCHEMA_BY_ORG_SERVICE`` matches only when BOTH the
    organisation and the service on the node equal the query parameters,
    which is what the real Cypher does.
    """

    def __init__(self, stored: FormSchema | None) -> None:
        self._stored = stored
        self.calls: list[dict[str, Any]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append(dict(params))
        if self._stored is None:
            return []
        if "fingerprint: $fingerprint" in query:
            if params.get("fingerprint") == self._stored.fingerprint:
                return [_row(self._stored)]
            return []
        if params.get("organization_id") != self._stored.organization_id:
            return []
        if params.get("service_id") != self._stored.service_id:
            return []
        return [_row(self._stored)]

    def close(self) -> None:
        return None


def test_no_taught_schema_anywhere_yields_no_match(
    sherwood_letter_fingerprint: str,
) -> None:
    """An untaught org and service must produce match=none, never a fingerprint."""
    client = _StubGraph(None)

    schema, match, loaded_key, label = resolve_form_schema_traced(
        client,
        sherwood_letter_fingerprint,
        organization_id=OTHER_ORG_ID,
        service_id=OTHER_SERVICE_ID,
    )

    assert schema is None
    assert match == "none"
    assert loaded_key == "none"
    assert label == ""
    assert TAUGHT_FINGERPRINT not in loaded_key


def test_different_org_does_not_inherit_the_sherwood_schema(
    sherwood_letter_fingerprint: str,
) -> None:
    """Another trust must never pick up the Sherwood template."""
    client = _StubGraph(_schema(TAUGHT_ORG_ID, TAUGHT_SERVICE_ID))

    schema, match, loaded_key, _label = resolve_form_schema_traced(
        client,
        sherwood_letter_fingerprint,
        organization_id=OTHER_ORG_ID,
        service_id=TAUGHT_SERVICE_ID,
    )

    assert schema is None
    assert match == "none"
    assert loaded_key == "none"


def test_rebinding_the_schema_to_another_service_breaks_the_same_letter(
    sherwood_letter_fingerprint: str,
) -> None:
    """Identical letter text stops binding when the schema's ids change.

    This is the core negative control. The letter is byte-for-byte the same
    in both halves of this test. Only the graph data differs.
    """
    correct = _StubGraph(_schema(TAUGHT_ORG_ID, TAUGHT_SERVICE_ID))
    _schema_hit, match_hit, key_hit, _label = resolve_form_schema_traced(
        correct,
        sherwood_letter_fingerprint,
        organization_id=TAUGHT_ORG_ID,
        service_id=TAUGHT_SERVICE_ID,
    )
    assert match_hit == "org_service"
    assert key_hit == TAUGHT_FINGERPRINT

    reset_schema_cache()

    rebound = _StubGraph(_schema(OTHER_ORG_ID, OTHER_SERVICE_ID))
    schema_miss, match_miss, key_miss, _label2 = resolve_form_schema_traced(
        rebound,
        sherwood_letter_fingerprint,
        organization_id=TAUGHT_ORG_ID,
        service_id=TAUGHT_SERVICE_ID,
    )
    assert schema_miss is None
    assert match_miss == "none"
    assert key_miss == "none"


def test_blank_service_id_can_never_bind(
    sherwood_letter_fingerprint: str,
) -> None:
    """A blank service short-circuits the lookup before any query runs.

    This is the failure mode a referral bundle hits today, because
    document_chunks mode never writes healthcare_service_id onto state.
    """
    client = _StubGraph(_schema(TAUGHT_ORG_ID, TAUGHT_SERVICE_ID))

    schema, match, loaded_key, _label = resolve_form_schema_traced(
        client,
        sherwood_letter_fingerprint,
        organization_id=TAUGHT_ORG_ID,
        service_id="",
    )

    assert schema is None
    assert match == "none"
    assert loaded_key == "none"
    org_service_calls = [c for c in client.calls if "organization_id" in c]
    assert org_service_calls == []


def test_gp_practice_org_id_does_not_bind_the_receiving_trust_schema(
    sherwood_letter_fingerprint: str,
) -> None:
    """org_id holds the patient's GP practice, which must not match RK5."""
    client = _StubGraph(_schema(TAUGHT_ORG_ID, TAUGHT_SERVICE_ID))

    schema, match, _key, _label = resolve_form_schema_traced(
        client,
        sherwood_letter_fingerprint,
        organization_id="Y05690",
        service_id=TAUGHT_SERVICE_ID,
    )

    assert schema is None
    assert match == "none"
