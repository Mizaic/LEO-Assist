"""Extraction schema lookup: hash first, then org+service.

Atlas trace: DI-26546721
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from libs.pipeline.document_quality import form_fingerprint
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import (
    _schema_to_sections_json,
    reset_schema_cache,
)


SEEDED_FINGERPRINT = "sfh-gynae-2ww-v1"
ORG_ID = "sfh-nhs-trust"
SERVICE_ID = "sfh-gynae-2ww"

LETTER = (
    "Section A: cancer type suspected\n"
    "Cervix [X] Ovary [ ]\n"
    "Section B: 14-day rule criteria\n"
    "B1 PMB [X]\n"
    "please take bloods today\n"
)


def _section() -> FormSection:
    return FormSection(
        section_id="A",
        section_type="checkbox",
        label="Cancer type",
        start_pattern="Section A: cancer type suspected",
        items=[],
    )


def _seeded_schema() -> FormSchema:
    return FormSchema(
        schema_id="seed-1",
        fingerprint=SEEDED_FINGERPRINT,
        form_name="SFH Gynae 2WW",
        sections=[_section()],
        created_by="seed",
        status="active",
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )


def _row(schema: FormSchema) -> dict:
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


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_schema_cache()
    yield
    reset_schema_cache()


def test_letter_hash_is_not_the_seeded_alias() -> None:
    """A real letter hashes to 16 hex chars, not sfh-gynae-2ww-v1."""
    letter_hash = form_fingerprint(LETTER)
    assert letter_hash != SEEDED_FINGERPRINT
    assert len(letter_hash) == 16
    int(letter_hash, 16)


def test_load_form_schema_misses_when_only_alias_is_stored() -> None:
    """Exact-hash GET cannot find the seeded alias from a letter hash."""
    from libs.pipeline.form_schema_store import load_form_schema

    letter_hash = form_fingerprint(LETTER)
    client = MagicMock()
    client.run.return_value = []
    assert load_form_schema(client, letter_hash) is None
    kwargs = client.run.call_args.kwargs
    assert kwargs["fingerprint"] == letter_hash
    assert kwargs["fingerprint"] != SEEDED_FINGERPRINT


def test_resolve_uses_org_and_service_when_hash_misses() -> None:
    """After a hash miss, an active schema for the same org and service is used."""
    from libs.pipeline.form_schema_store import resolve_form_schema

    letter_hash = form_fingerprint(LETTER)
    seeded = _seeded_schema()
    client = MagicMock()
    client.run.side_effect = [[], [_row(seeded)]]

    schema = resolve_form_schema(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert schema is not None
    assert schema.fingerprint == SEEDED_FINGERPRINT
    assert schema.organization_id == ORG_ID
    assert schema.service_id == SERVICE_ID


def test_resolve_does_not_use_another_org_schema() -> None:
    """Org plus service fallback must not apply another trust's template."""
    from libs.pipeline.form_schema_store import resolve_form_schema

    letter_hash = form_fingerprint(LETTER)
    client = MagicMock()
    client.run.return_value = []

    schema = resolve_form_schema(
        client,
        letter_hash,
        organization_id="other-trust",
        service_id=SERVICE_ID,
    )
    assert schema is None


def test_resolve_prefers_exact_hash_over_org_service() -> None:
    """A taught letter hash still wins when both lookups could match."""
    from libs.pipeline.form_schema_store import resolve_form_schema

    letter_hash = form_fingerprint(LETTER)
    hashed = FormSchema(
        schema_id="taught-hash",
        fingerprint=letter_hash,
        form_name="Taught from letter",
        sections=[_section()],
        created_by="teacher",
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    client = MagicMock()
    client.run.return_value = [_row(hashed)]

    schema = resolve_form_schema(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert schema is not None
    assert schema.schema_id == "taught-hash"
    assert client.run.call_count == 1


def test_is_known_schema_true_after_org_service_resolve() -> None:
    from libs.pipeline.form_schema_store import is_known_schema

    letter_hash = form_fingerprint(LETTER)
    client = MagicMock()
    client.run.side_effect = [[], [_row(_seeded_schema())]]
    known = is_known_schema(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert known is True


def test_merge_results_bypasses_gate_when_org_service_schema_exists() -> None:
    """Worker merge_results treats the seeded alias as a known schema."""
    from libs.pipeline_graph.subgraphs.extraction import merge_results

    client = MagicMock()
    client.run.side_effect = [[], [_row(_seeded_schema())]]

    from unittest.mock import patch

    with (
        patch(
            "libs.neo4j_client.client.PatientGraphClient",
            return_value=client,
        ),
        patch(
            "libs.pipeline.form_fingerprint_registry.known_fingerprints",
            return_value={},
        ),
    ):
        out = merge_results(
            {
                "encounter_text": LETTER,
                "entities": [{"text": "PMB"}],
                "few_shot_max_similarity": 0.05,
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
            }
        )

    quality = out["document_quality"]
    assert quality["document_quality_score"] == 1.0
    assert quality["quality_reasons"] == []
