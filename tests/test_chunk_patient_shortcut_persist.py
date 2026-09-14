"""Chunk persist must write Patient and Encounter links, not only Chunk DOCUMENTS.

Referral letters hang codes on Chunk. The patient shortcut and the
encounter copy were skipped: the chunk query bound an unlabelled node
(often the ReferralRequest) and never wrote Encounter-[:DOCUMENTS].

Atlas trace:
  DO: DO-728930A1
  DI: DI-58596C1A
  VT: VT-40032A1B
  Risk: R-FD6D9DCF
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-58596C1A")
"""

from __future__ import annotations

from libs.cypher.documents_queries import (
    _build_upsert_query,
    _collect_pending_document_writes,
)


def _chunk_query() -> str:
    return _build_upsert_query("Clinical_finding", "HAS_FINDING", source_label="Chunk")


def test_chunk_query_resolves_patient_via_document_reference() -> None:
    query = _chunk_query()
    assert "p_direct:Patient" in query
    assert "HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT" in query


def test_chunk_query_resolves_patient_via_referral_for_patient() -> None:
    query = _chunk_query()
    assert "p_via_rr:Patient" in query
    assert "FOR_PATIENT" in query
    assert "ReferralRequest" in query


def test_chunk_query_does_not_bind_unlabelled_owner() -> None:
    """HAS_DOCUMENT on a referral must not become the HAS_FINDING source."""
    query = _chunk_query()
    assert "<-[:HAS_DOCUMENT_REFERENCE|HAS_DOCUMENT]-(p)" not in query
    assert "coalesce(p_direct, p_via_rr) AS p" in query


def test_chunk_query_stamps_assertion_on_documents() -> None:
    query = _chunk_query()
    assert "r.assertion" in query


def test_documents_edge_stamps_value_unit_and_observed_at() -> None:
    query = _chunk_query()
    assert "r.value" in query
    assert "r.unit" in query
    assert "r.observed_at" in query


def _term() -> dict:
    return {
        "text": "Rheumatoid arthritis",
        "semantic_tag": "disorder",
        "assertion": "present",
        "coding": {
            "snomed_concept_id": "69896004",
            "snomed_term": "Rheumatoid arthritis",
        },
    }


def _observable_term() -> dict:
    return {
        "text": "Heart rate 70 bpm, 24 Nov 2025",
        "semantic_tag": "observable entity",
        "assertion": "present",
        "numeric_value": "70",
        "unit": "bpm",
        "observed_at": "2025-11-24",
        "coding": {
            "snomed_concept_id": "364075005",
            "snomed_term": "Heart rate",
        },
    }


def _payload() -> list[dict]:
    return [
        {
            "sentence_id": "chunk-7",
            "text": "Rheumatoid arthritis.",
            "persist_source_label": "Chunk",
            "terms": [_term()],
        }
    ]


def test_chunk_write_without_patient_id_does_not_mirror_encounter() -> None:
    writes = _collect_pending_document_writes(
        "rr-1:referral-assessment",
        _payload(),
        source="pipeline",
        model_name="",
        model_version="",
        contract_version="",
        run_id="run-1",
        source_label="Chunk",
        active_terms=set(),
    )
    assert len(writes) == 1
    assert "MATCH (src:Chunk" in writes[0].query


def test_observable_write_carries_value_unit_and_observed_at() -> None:
    writes = _collect_pending_document_writes(
        "enc-1",
        [
            {
                "sentence_id": "chunk-7",
                "text": "Heart rate 70 bpm, 24 Nov 2025",
                "persist_source_label": "Chunk",
                "terms": [_observable_term()],
            }
        ],
        source="pipeline",
        model_name="",
        model_version="",
        contract_version="",
        run_id="run-1",
        source_label="Chunk",
        active_terms=set(),
    )
    params = writes[0].params
    assert params["numeric_value"] == "70"
    assert params["unit"] == "bpm"
    assert params["observed_at"] == "2025-11-24"


def test_chunk_write_with_patient_id_also_writes_encounter() -> None:
    writes = _collect_pending_document_writes(
        "rr-1:referral-assessment",
        _payload(),
        source="pipeline",
        model_name="",
        model_version="",
        contract_version="",
        run_id="run-1",
        source_label="Chunk",
        active_terms=set(),
        patient_id="424559020",
    )
    assert len(writes) == 2
    sources = {item.params["source_id"] for item in writes}
    assert sources == {"chunk-7", "rr-1:referral-assessment"}
    encounter_writes = [item for item in writes if "MATCH (src:Encounter" in item.query]
    assert len(encounter_writes) == 1
    assert encounter_writes[0].params["source_id"] == "rr-1:referral-assessment"
