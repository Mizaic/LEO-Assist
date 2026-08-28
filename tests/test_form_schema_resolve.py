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
ORG_ID = "RK5"
SERVICE_ID = "7980224"
ORG_NAME = "Sherwood Forest Hospitals NHS Foundation Trust"
SERVICE_NAME = "Sherwood - Gynaecology Urgent Suspected Cancer Pathway"

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
        section_type="checkbox_multi",
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
        organization_name=ORG_NAME,
        service_name=SERVICE_NAME,
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
    assert out["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert out["form_schema_match"] == "org_service"
    assert out["form_schema_label"] == "SFH Gynae 2WW"


def test_resolve_form_schema_traced_reports_exact_hash() -> None:
    from libs.pipeline.form_schema_store import resolve_form_schema_traced

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

    schema, match, loaded_key, label = resolve_form_schema_traced(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert schema is not None
    assert match == "exact_hash"
    assert loaded_key == letter_hash
    assert label == "Taught from letter"


def test_resolve_form_schema_traced_reports_org_service() -> None:
    from libs.pipeline.form_schema_store import resolve_form_schema_traced

    letter_hash = form_fingerprint(LETTER)
    client = MagicMock()
    client.run.side_effect = [[], [_row(_seeded_schema())]]

    schema, match, loaded_key, label = resolve_form_schema_traced(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert schema is not None
    assert match == "org_service"
    assert loaded_key == SEEDED_FINGERPRINT
    assert label == "SFH Gynae 2WW"


def test_resolve_form_schema_traced_reports_none() -> None:
    from libs.pipeline.form_schema_store import resolve_form_schema_traced

    client = MagicMock()
    client.run.return_value = []

    schema, match, loaded_key, label = resolve_form_schema_traced(
        client,
        form_fingerprint(LETTER),
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert schema is None
    assert match == "none"
    assert loaded_key == "none"
    assert label == ""


def test_resolve_uses_ers_service_id_when_service_id_differs() -> None:
    """Service.ers_service_id is a node property and must equal FormSchema.service_id."""
    from libs.pipeline.form_schema_store import resolve_form_schema

    letter_hash = form_fingerprint(LETTER)
    client = MagicMock()
    client.run.side_effect = [[], [], [_row(_seeded_schema())]]

    schema = resolve_form_schema(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id="other-service-node",
        ers_service_id=SERVICE_ID,
    )
    assert schema is not None
    assert schema.fingerprint == SEEDED_FINGERPRINT
    assert schema.service_id == SERVICE_ID


def test_merge_results_bypasses_gate_for_matching_org_and_service() -> None:
    """Extract treats matching Organization.id + Service.id as a known form."""
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
                "entities": [{"text": "Cervix"}],
                "few_shot_max_similarity": 0.05,
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
                "healthcare_service_ers_id": SERVICE_ID,
            }
        )

    quality = out["document_quality"]
    assert quality["document_quality_score"] == 1.0
    assert quality["quality_reasons"] == []
    assert out["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert out["form_schema_match"] == "org_service"
    assert out["form_schema_label"] == "SFH Gynae 2WW"


def test_merge_results_writes_none_when_schema_misses() -> None:
    from libs.pipeline_graph.subgraphs.extraction import merge_results

    client = MagicMock()
    client.run.return_value = []

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
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
            }
        )

    assert out["form_schema_fingerprint"] == "none"
    assert out["form_schema_match"] == "none"
    assert out["form_schema_label"] == ""


def test_form_schema_state_fields_rejects_match_without_fingerprint() -> None:
    from libs.pipeline.form_schema_store import form_schema_state_fields

    fields = form_schema_state_fields("org_service", "none", "SFH Gynae 2WW")
    assert fields == {
        "form_schema_fingerprint": "none",
        "form_schema_match": "none",
        "form_schema_label": "",
    }


def test_form_schema_fields_from_state_re_resolves_orphan_match() -> None:
    from libs.pipeline.form_schema_store import form_schema_fields_from_state

    client = MagicMock()
    client.run.side_effect = [[], [_row(_seeded_schema())]]

    from unittest.mock import patch

    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=client,
    ):
        fields = form_schema_fields_from_state(
            {
                "form_schema_fingerprint": "none",
                "form_schema_match": "org_service",
                "form_schema_label": "",
            },
            LETTER,
            organization_id=ORG_ID,
            service_id=SERVICE_ID,
        )

    assert fields["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert fields["form_schema_match"] == "org_service"
    assert fields["form_schema_label"] == "SFH Gynae 2WW"


def test_resolve_form_schema_traced_rejects_empty_fingerprint_on_org_hit() -> None:
    from libs.pipeline.form_schema_store import resolve_form_schema_traced

    letter_hash = form_fingerprint(LETTER)
    broken = _seeded_schema()
    broken = FormSchema(
        schema_id=broken.schema_id,
        fingerprint="",
        form_name=broken.form_name,
        sections=broken.sections,
        created_by=broken.created_by,
        organization_id=broken.organization_id,
        service_id=broken.service_id,
    )
    client = MagicMock()
    client.run.side_effect = [[], [_row(broken)]]

    schema, match, loaded_key, label = resolve_form_schema_traced(
        client,
        letter_hash,
        organization_id=ORG_ID,
        service_id=SERVICE_ID,
    )
    assert schema is None
    assert match == "none"
    assert loaded_key == "none"
    assert label == ""


def test_load_document_chunks_resolves_sfh_gynae_by_healthcare_service_ids() -> None:
    """RK5 + 7980224 on state must yield sfh-gynae-2ww-v1 at chunk load."""
    from unittest.mock import MagicMock, patch

    from libs.pipeline.document_chunk_loader import DOCUMENT_CHUNKS_MODE
    from libs.pipeline_graph.subgraphs.extraction import load_document_chunks

    client = MagicMock()
    client.run.side_effect = [
        [{"chunk_id": "c1", "text": LETTER, "ordinal": 0, "char_start": 0, "char_end": len(LETTER)}],
        [],
        [_row(_seeded_schema())],
    ]

    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=client,
    ):
        out = load_document_chunks(
            {
                "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
                "chunk_ids": ["c1"],
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
            }
        )

    assert out["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert out["form_schema_match"] == "org_service"
    assert out["form_schema_label"] == "SFH Gynae 2WW"


def test_extract_entities_outputs_resolved_form_schema_fingerprint(monkeypatch) -> None:
    from unittest.mock import MagicMock, patch

    from libs.pipeline.document_chunk_loader import DOCUMENT_CHUNKS_MODE
    from libs.pipeline_graph.subgraphs.extraction import extract_entities

    client = MagicMock()
    client.run.side_effect = [[], [_row(_seeded_schema())]]

    def _fake_llm(*args, **kwargs):  # noqa: ANN002, ANN003
        return {
            "entities": [{"text": "PMB", "label": "finding"}],
            "extraction_route": "llm",
            "few_shot_max_similarity": 0.0,
            "extraction_model_name": "llm-small",
            "extraction_model_version": "extraction v1",
            "extraction_model_requested_version": "",
            "extraction_model_version_mismatch": False,
            "form_schema_fingerprint": SEEDED_FINGERPRINT,
            "form_schema_match": "org_service",
            "form_schema_label": "SFH Gynae 2WW",
        }

    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction",
        _fake_llm,
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.extraction._enrich_from_state",
        lambda result, *_args: result,
    )

    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=client,
    ):
        out = extract_entities(
            {
                "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
                "encounter_text": LETTER,
                "sentences": [
                    {
                        "sentence_id": "c1",
                        "text": LETTER,
                        "text_raw": LETTER,
                        "start": 0,
                        "end": len(LETTER),
                    }
                ],
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
                "form_schema_fingerprint": "none",
                "form_schema_match": "org_service",
            }
        )

    assert out["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert out["form_schema_match"] in {"org_service", "exact_hash"}


def test_chunk_load_payload_does_not_invent_orphan_match() -> None:
    from libs.pipeline_graph.subgraphs.extraction import _chunk_load_payload

    payload = _chunk_load_payload(
        {
            "encounter_text": LETTER,
            "sentences": [{"sentence_id": "c1", "text": LETTER}],
            "form_schema_match": "org_service",
        },
        [],
    )
    assert payload["form_schema_fingerprint"] == "none"
    assert payload["form_schema_match"] == "none"
    assert payload["form_schema_label"] == ""
