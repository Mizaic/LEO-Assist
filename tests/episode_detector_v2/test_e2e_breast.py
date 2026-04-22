"""End-to-end Phase-1 detector test for the patient that started this work.

Atlas trace:
  DI: DI-8A5FCF4F
  Mitigates R-1276F86C (silent-drop on patient 4920262426).

This test runs the full v2 pipeline against a synthetic timeline that
mirrors the three-pathway shape of patient 4920262426 in the
**live-graph row format** the production normaliser consumes:

  - breast: 2WW referral SNOMED + confirmed malignant biopsy code
  - upper_gi: 2WW referral SNOMED
  - lung: 2WW referral SNOMED with subsequent ruled-out closure code

Day-one stub behaviour means only the breast episode auto-publishes.
The other two pathways must still be visible to the coverage check
(so the runner reports them as unaccounted, which the orchestrator
turns into ``needs_human_review`` flags).

The test uses an in-memory fake patient_client that returns rows in
the same shape as the real Neo4j ``[:DOCUMENTS]`` aggregator. This
intentionally exercises the schema-binding layer in
``normaliser._row_from_live`` so the synthetic test stays anchored
to the live-graph contract.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from services.analysis_worker.app.episode_detector_v2.runner import build_episodes


PATIENT_ID = "4920262426"


def _doc(
    *,
    concept_id: str,
    display_name: str,
    semantic_tag: str = "Procedure",
    assertion: str = "present",
    negated: bool = False,
    value: Any = None,
    unit: str | None = None,
):
    return {
        "concept_id": concept_id,
        "display_name": display_name,
        "semantic_tag": semantic_tag,
        "assertion_json": json.dumps(
            {"assertion": assertion, "negated": negated}
        ),
        "modifiers_json": "{}",
        "evidence_sentence": display_name,
        "value": value,
        "unit": unit,
        "decision_tier": "high",
        "model_version": "v1",
    }


def _live_row(
    encounter_id: str,
    *,
    occurred_on: str,
    encounter_text: str = "",
    docs: list[dict[str, Any]] | None = None,
):
    return {
        "encounter_id": encounter_id,
        "occurred_on": occurred_on,
        "encounter_text": encounter_text,
        "raw_codes": docs or [],
    }


class FakePatientClient:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self.merge_calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **kwargs):  # noqa: D401 - matches Neo4j driver
        if "MATCH (p:Patient" in query and "HAS_ENCOUNTER" in query:
            return list(self._rows)
        self.merge_calls.append((query, kwargs))
        return []

    def close(self):
        return None


def _three_pathway_rows() -> list[dict[str, Any]]:
    """Synthetic three-pathway timeline using live-graph row shape."""
    return [
        _live_row(
            "ugi-2ww",
            occurred_on="2023-11-12",
            docs=[
                _doc(
                    concept_id="276551000000108",
                    display_name=(
                        "Fast track referral for suspected upper "
                        "gastrointestinal cancer (procedure)"
                    ),
                    semantic_tag="Procedure",
                )
            ],
        ),
        _live_row(
            "lung-2ww",
            occurred_on="2024-01-10",
            docs=[
                _doc(
                    concept_id="276401000000108",
                    display_name=(
                        "Fast track referral for suspected lung cancer "
                        "(procedure)"
                    ),
                    semantic_tag="Procedure",
                )
            ],
        ),
        _live_row(
            "breast-2ww",
            occurred_on="2024-03-15",
            docs=[
                _doc(
                    concept_id="276341000000100",
                    display_name=(
                        "Fast track referral for suspected breast cancer "
                        "(procedure)"
                    ),
                    semantic_tag="Procedure",
                )
            ],
        ),
        _live_row(
            "breast-clinic",
            occurred_on="2024-03-29",
            docs=[
                _doc(
                    concept_id="395557000",
                    display_name="Tumour of breast (disorder)",
                    semantic_tag="Disease",
                )
            ],
        ),
        _live_row(
            "breast-biopsy",
            occurred_on="2024-04-12",
            docs=[
                _doc(
                    concept_id="254837009",
                    display_name="Malignant neoplasm of breast (disorder)",
                    semantic_tag="Disease",
                ),
                _doc(
                    concept_id="439470001",
                    display_name="Biopsy of breast (procedure)",
                    semantic_tag="Observable_entity",
                    value="Invasive carcinoma identified",
                ),
            ],
        ),
        _live_row(
            "lung-ct",
            occurred_on="2024-02-01",
            docs=[
                _doc(
                    concept_id="266569009",
                    display_name="No abnormality detected (finding)",
                    semantic_tag="Clinical_finding",
                    assertion="present",
                    negated=True,
                )
            ],
        ),
    ]


def test_breast_episode_auto_publishes_other_pathways_flagged():
    rows = _three_pathway_rows()
    client = FakePatientClient(rows)
    result = asyncio.run(
        build_episodes(patient_id=PATIENT_ID, patient_client=client)
    )

    # At least one breast auto-episode is created
    assert result.episodes_created >= 1, result
    assert any("ep-v2-" in eid for eid in result.episode_ids)

    # The non-breast pathways have signals (pathway channel) but no
    # auto-episode -- coverage check must surface them as unaccounted
    # so the orchestrator can flag for human review.
    assert result.coverage_report is not None
    unaccounted = set(result.coverage_report.encounter_ids_unaccounted)
    assert "ugi-2ww" in unaccounted
    assert "lung-2ww" in unaccounted

    # The merge for auto-episodes must have been called for breast.
    # Live-graph schema: EpisodeOfCare label, HAS_EPISODE_OF_CARE edge,
    # IS_PART_OF from Encounter to EpisodeOfCare.
    merges = [c for c in client.merge_calls if "MERGE (e:EpisodeOfCare" in c[0]]
    assert merges, "Expected at least one EpisodeOfCare MERGE for breast"
    merge_query = merges[0][0]
    assert "MATCH (p:Patient {id: $patient_id})" in merge_query
    assert "MERGE (p)-[:HAS_EPISODE_OF_CARE]->(e)" in merge_query
    assert "MATCH (enc:Encounter {id: enc_id})" in merge_query
    assert "MERGE (enc)-[:IS_PART_OF]->(e)" in merge_query
    breast_merge_payload = merges[0][1]["episodes"]
    breast_eps = [
        ep for ep in breast_merge_payload if ep["site_key"] == "breast"
    ]
    assert breast_eps, "Expected the merge payload to contain a breast episode"
    # No duplicate breast episode_ids in the persist payload (Fix #1).
    breast_ids = [ep["episode_id"] for ep in breast_eps]
    assert len(breast_ids) == len(set(breast_ids)), (
        f"Duplicate breast episode_ids in payload: {breast_ids}"
    )
    assert any(ep["confidence_tier"] == "auto" for ep in breast_eps)
    # Confirmed breast episode stays open (no closure SNOMED) -- Fix #3.
    confirmed_breast = [
        ep
        for ep in breast_eps
        if ep["intent"] == "confirmed" and ep["confidence_tier"] == "auto"
    ]
    assert confirmed_breast, "Expected at least one confirmed breast episode"
    # The persist payload writes canonical EpisodeStatus values
    # (DI-C4CEFA32) -- a confirmed-intent episode with no curator
    # sign-off and no explicit closure signal stays "active" with a
    # null end_date. The boundary detector still uses "open" as its
    # internal label; the persist layer translates it.
    assert all(
        ep["status"] == "active" and ep["end_date"] is None
        for ep in confirmed_breast
    ), confirmed_breast
