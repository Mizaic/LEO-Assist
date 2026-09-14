"""Dedup must not flip a historical fact into a present one.

``_dedupe_pending_writes`` used to keep one write per (source, concept)
and let the higher confidence win. A historical breast lump at 0.93 was
dropped in favour of a present copy at 0.95. That is a clinical flip:
a resolved finding is stored as current and can put the patient on an
urgent cancer pathway.

Assertion is part of the fact, not a guess about the same fact. Two
writes that share a source and a code, but differ in assertion, must
both be kept. The graph merge key must include assertion so a later
write cannot overwrite the other.

Same-assertion duplicates may still collapse, and the higher confidence
write is kept.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-C52645B7
  DO: DO-7B21CA73
  VT: VT-24330A67
  Risk: R-56E2D742
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.services.patient_graph_writer import (  # noqa: E402
    PatientGraphWriter,
    SemanticLinkPayload,
)
from libs.cypher.documents_queries import (  # noqa: E402
    _PendingDocWrite,
    _build_upsert_query,
    _build_upsert_query_patient_encounter,
    _collect_pending_document_writes,
    _dedupe_pending_writes,
)

_LUMP = "89164003"


def _write(
    assertion: str,
    confidence: float,
    *,
    concept_id: str = _LUMP,
    source_id: str = "enc-1",
) -> _PendingDocWrite:
    return _PendingDocWrite(
        sort_key=(concept_id, source_id, 0),
        query="MERGE",
        params={
            "concept_id": concept_id,
            "source_id": source_id,
            "assertion": assertion,
            "confidence": confidence,
        },
    )


def test_present_does_not_overwrite_historical_of_the_same_code() -> None:
    kept = _dedupe_pending_writes([_write("historical", 0.93), _write("present", 0.95)])
    assertions = {item.params["assertion"] for item in kept}
    assert assertions == {"historical", "present"}


def test_historical_is_not_dropped_when_present_has_higher_confidence() -> None:
    kept = _dedupe_pending_writes([_write("present", 0.95), _write("historical", 0.93)])
    historical = next(item for item in kept if item.params["assertion"] == "historical")
    assert historical.params["confidence"] == 0.93


def test_same_assertion_still_keeps_the_higher_confidence() -> None:
    kept = _dedupe_pending_writes([_write("present", 0.80), _write("present", 0.95)])
    assert len(kept) == 1
    assert kept[0].params["confidence"] == 0.95


def test_collect_pending_keeps_both_assertions_of_the_same_code() -> None:
    payload = [
        {
            "text": "Biopsy of a breast lump in January. New lump today.",
            "terms": [
                {
                    "text": "breast lump",
                    "semantic_tag": "finding",
                    "assertion": "historical",
                    "coding": {
                        "snomed_concept_id": _LUMP,
                        "snomed_term": "Breast lump",
                        "score": 0.93,
                    },
                },
                {
                    "text": "lump",
                    "semantic_tag": "finding",
                    "assertion": "present",
                    "coding": {
                        "snomed_concept_id": _LUMP,
                        "snomed_term": "Breast lump",
                        "score": 0.95,
                    },
                },
            ],
        }
    ]
    pending = _collect_pending_document_writes(
        "enc-1",
        payload,
        source="pipeline_runtime",
        model_name="",
        model_version="",
        contract_version="",
        run_id="run-1",
        source_label="Encounter",
        active_terms=set(),
    )
    assertions = {item.params["assertion"] for item in pending}
    assert assertions == {"historical", "present"}


def test_chunk_merge_key_includes_assertion() -> None:
    query = _build_upsert_query("Clinical_finding", "HAS_FINDING", source_label="Chunk")
    assert "DOCUMENTS {conceptId: $concept_id, assertion: $assertion}" in query


def test_encounter_merge_key_includes_assertion() -> None:
    query = _build_upsert_query_patient_encounter("Clinical_finding", "HAS_FINDING")
    assert "DOCUMENTS {conceptId: $concept_id, assertion: $assertion}" in query


def test_gold_sync_merge_key_includes_assertion() -> None:
    session = _RecordingSession()
    PatientGraphWriter().upsert_documents_link(
        SemanticLinkPayload(
            encounter_id="enc-1",
            semantic_tag="finding",
            concept_id=_LUMP,
            term="Breast lump",
            read_code=None,
            evidence="breast lump",
            confidence=0.93,
            domain="clinical",
            context={"assertion": "historical", "historical": True},
            modifiers={},
            source="gold_sync",
        ),
        session=session,
    )
    assert "DOCUMENTS {conceptId: $concept_id, assertion: $assertion}" in session.query


class _RecordingSession:
    def __init__(self) -> None:
        self.query = ""

    def run(self, query: str, **_params: object) -> None:
        self.query = query
