"""Extraction state for taught forms: recognition only, no fallback.

There is no letter-hash lookup and no organisation-and-service bind. A
document is a taught form only when recognition says so. Retired match
values (``exact_hash``, ``org_service``) are never trusted: the letter is
recognised again. Only a fully recognised bundle may skip the
document-quality gate.

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6. Replaces the DI-26546721 bind tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.pipeline.document_chunk_loader import (
    DOCUMENT_CHUNKS_MODE,
    recognition_fields_from_state,
)
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import (
    _schema_to_sections_json,
    form_schema_state_fields,
    reset_schema_cache,
)
from libs.pipeline_graph.subgraphs.extraction import (
    _chunk_load_payload,
    extract_entities,
    load_document_chunks,
    merge_results,
)

SEEDED_FINGERPRINT = "sfh-gynae-2ww-v1"
ORG_ID = "RK5"
SERVICE_ID = "7980224"

LETTER = (
    "Section A: cancer type suspected\n"
    "Cervix [X] Ovary [ ]\n"
    "Section B: 14-day rule criteria\n"
    "B1 PMB [X]\n"
    "please take bloods today\n"
)


def _seeded_schema() -> FormSchema:
    return FormSchema(
        schema_id="seed-1",
        fingerprint=SEEDED_FINGERPRINT,
        form_name="SFH Gynae 2WW",
        sections=[
            FormSection(
                section_id="A",
                section_type="checkbox_multi",
                label="Cancer type",
                start_pattern="Section A: cancer type suspected",
                items=[],
            ),
            FormSection(
                section_id="B",
                section_type="checkbox_multi",
                label="14-day rule criteria",
                start_pattern="Section B: 14-day rule criteria",
                items=[],
            ),
        ],
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


def _graph(*answers: list) -> MagicMock:
    client = MagicMock()
    client.run.side_effect = list(answers)
    return client


def _merge(client: MagicMock, extra: dict | None = None) -> dict:
    with (
        patch("libs.neo4j_client.client.PatientGraphClient", return_value=client),
        patch(
            "libs.pipeline.form_fingerprint_registry.known_fingerprints",
            return_value={},
        ),
    ):
        return merge_results(
            {
                "encounter_text": LETTER,
                "entities": [{"text": "PMB"}],
                "few_shot_max_similarity": 0.05,
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
                **(extra or {}),
            }
        )


@pytest.mark.parametrize("retired", ["exact_hash", "org_service", "known_fingerprint"])
def test_retired_match_values_are_never_trusted(retired: str) -> None:
    fields = form_schema_state_fields(retired, SEEDED_FINGERPRINT, "SFH Gynae 2WW")
    assert fields == {
        "form_schema_fingerprint": "none",
        "form_schema_match": "none",
        "form_schema_label": "",
    }


def test_recognised_without_a_key_is_none() -> None:
    fields = form_schema_state_fields("recognised", "none", "SFH Gynae 2WW")
    assert fields["form_schema_match"] == "none"


def test_merge_results_bypasses_the_gate_for_a_recognised_form() -> None:
    out = _merge(_graph([_row(_seeded_schema())]))
    quality = out["document_quality"]
    assert out["form_schema_match"] == "recognised"
    assert out["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert quality["document_quality_score"] == 1.0


def test_merge_results_does_not_bypass_the_gate_for_an_unrecognised_form() -> None:
    """The organisation and service on state no longer bind any form."""
    out = _merge(_graph([]))
    assert out["form_schema_match"] == "unrecognised"
    assert out["form_schema_fingerprint"] == "none"
    assert out["document_quality"]["document_quality_score"] < 1.0


def test_a_retired_match_on_state_is_recognised_again() -> None:
    state = {
        "form_schema_fingerprint": SEEDED_FINGERPRINT,
        "form_schema_match": "org_service",
    }
    with patch("libs.neo4j_client.client.PatientGraphClient", return_value=_graph([])):
        fields = recognition_fields_from_state(state, LETTER, ORG_ID)
    assert fields["form_schema_match"] == "unrecognised"
    assert fields["form_schema_fingerprint"] == "none"


def test_a_settled_recognition_is_reused_without_a_lookup() -> None:
    client = _graph()
    state = {
        "form_schema_fingerprint": SEEDED_FINGERPRINT,
        "form_schema_match": "recognised",
        "form_schema_label": "SFH Gynae 2WW",
        "form_recognition": [{"outcome": "recognised"}],
    }
    with patch("libs.neo4j_client.client.PatientGraphClient", return_value=client):
        fields = recognition_fields_from_state(state, LETTER, ORG_ID)
    assert fields["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert fields["form_recognition"] == [{"outcome": "recognised"}]
    client.run.assert_not_called()


def test_load_document_chunks_ignores_the_healthcare_service_ids() -> None:
    chunk = {
        "chunk_id": "c1",
        "text": LETTER,
        "ordinal": 0,
        "char_start": 0,
        "char_end": len(LETTER),
    }
    client = _graph([chunk], [])
    with patch("libs.neo4j_client.client.PatientGraphClient", return_value=client):
        out = load_document_chunks(
            {
                "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
                "chunk_ids": ["c1"],
                "healthcare_service_org_id": ORG_ID,
                "healthcare_service_id": SERVICE_ID,
            }
        )
    assert out["form_schema_match"] == "unrecognised"
    assert out["form_recognition"][0]["outcome"] == "unrecognised"
    candidate_call = client.run.call_args_list[1]
    assert "service_id" not in candidate_call.kwargs


def test_extract_entities_keeps_the_recognition_on_state(monkeypatch) -> None:
    def _fake_llm(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return {"entities": [{"text": "PMB", "label": "finding"}]}

    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction", _fake_llm
    )
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs.extraction._enrich_from_state",
        lambda result, *_args: result,
    )
    out = extract_entities(
        {
            "text_segmentation_mode": DOCUMENT_CHUNKS_MODE,
            "encounter_text": LETTER,
            "sentences": [
                {"sentence_id": "c1", "text": LETTER, "start": 0, "end": len(LETTER)}
            ],
            "form_schema_fingerprint": SEEDED_FINGERPRINT,
            "form_schema_match": "recognised",
            "form_recognition": [{"outcome": "recognised"}],
        }
    )
    assert out["form_schema_fingerprint"] == SEEDED_FINGERPRINT
    assert out["form_schema_match"] == "recognised"
    assert out["form_recognition"] == [{"outcome": "recognised"}]


def test_chunk_load_payload_does_not_trust_a_retired_match() -> None:
    payload = _chunk_load_payload(
        {
            "encounter_text": LETTER,
            "sentences": [{"sentence_id": "c1", "text": LETTER}],
            "form_schema_fingerprint": SEEDED_FINGERPRINT,
            "form_schema_match": "org_service",
            "form_schema_label": "SFH Gynae 2WW",
            "form_recognition": [{"outcome": "unrecognised"}],
        },
        [],
    )
    assert payload["form_schema_fingerprint"] == "none"
    assert payload["form_schema_match"] == "none"
    assert payload["form_recognition"] == [{"outcome": "unrecognised"}]
