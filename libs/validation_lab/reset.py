"""Purge all Validation Lab synthetic data sources.

Atlas trace:
  DO: DO-3A70C3DD
  DI: DI-724CD8A5
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-3A70C3DD")

Atlas: DI-724CD8A5

This module backs `scripts/reset_validation_lab.py`. It exists so the
purge Cypher lives next to the rest of the Validation Lab domain code
and can be unit tested without shelling out.

Deletes, per source, always bound to a `source` property (or label for
TestPatient) -- never a bare `MATCH (n) DETACH DELETE n`:

  - `:TestPatient` (knowledge graph) + `:RulesetReplay` snapshots.
  - `:ValidationCase` (patient graph) + scaffolded Patient graph,
    `source = 'validation-lab'`.
  - AI Summarisation scenario patients, `source = 'ai_summarisation_scenario'`.
  - Quick Test patients, `source = 'quick-test'`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_PURGE_TEST_PATIENTS = """
MATCH (tp:TestPatient)
WITH collect(tp) AS nodes, count(tp) AS deleted_count
UNWIND nodes AS tp
DETACH DELETE tp
RETURN deleted_count
"""

_PURGE_RULESET_REPLAYS = """
MATCH (rv:RulesetReplay)
WITH collect(rv) AS nodes, count(rv) AS deleted_count
UNWIND nodes AS rv
DETACH DELETE rv
RETURN deleted_count
"""

_PURGE_VALIDATION_CASES = """
MATCH (c:ValidationCase)
WITH collect(c) AS nodes, count(c) AS deleted_count
UNWIND nodes AS c
DETACH DELETE c
RETURN deleted_count
"""

# Patient-graph scaffolds are always bound to `source`; never a bare MATCH.
_PURGE_PATIENT_GRAPH_BY_SOURCE = """
MATCH (p:Patient {source: $source})
WITH collect(p) AS patients, count(p) AS deleted_count
UNWIND patients AS p
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter {source: $source})
OPTIONAL MATCH (p)-[:HAS_DOCUMENT_REFERENCE]->(dr:DocumentReference {source: $source})
OPTIONAL MATCH (dr)-[:HAS_CHUNK]->(c:Chunk)
OPTIONAL MATCH (rr:ReferralRequest {source: $source})-[:FOR_PATIENT]->(p)
OPTIONAL MATCH (cr:CommunicationRequest {source: $source})-[:FOR_PATIENT]->(p)
OPTIONAL MATCH (cr)-[:HAS_CONVERSATION]->(comm:Communication)
OPTIONAL MATCH (cr)-[:HAS_RESPONSE]->(agr:AdviceAndGuidanceResponse)
OPTIONAL MATCH (cr)-[:HAS_DOCUMENT]->(cr_dr:DocumentReference)
OPTIONAL MATCH (comm)-[:HAS_DOCUMENT]->(comm_dr:DocumentReference)
OPTIONAL MATCH (cr_dr)-[:HAS_CHUNK]->(cr_ch:Chunk)
OPTIONAL MATCH (comm_dr)-[:HAS_CHUNK]->(comm_ch:Chunk)
OPTIONAL MATCH (p)-[:HAS_CONDITION|HAS_MEDICATION_STATEMENT|HAS_ALLERGY]->(pmh)
OPTIONAL MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare {source: $source})
OPTIONAL MATCH (p)-[:REGISTERED_IN]->(org:Organization {source: $source})
DETACH DELETE e, c, dr, rr, pmh, p, cr, comm, agr, cr_dr, comm_dr,
              cr_ch, comm_ch, ep, org
RETURN deleted_count
"""

PATIENT_GRAPH_SOURCES: tuple[str, ...] = (
    "validation-lab",
    "ai_summarisation_scenario",
    "quick-test",
)


@dataclass
class ResetReport:
    """Per-source deletion counts for the reset run."""

    test_patients: int = 0
    ruleset_replays: int = 0
    validation_cases: int = 0
    patient_graph_by_source: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.patient_graph_by_source is None:
            self.patient_graph_by_source = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_patients": self.test_patients,
            "ruleset_replays": self.ruleset_replays,
            "validation_cases": self.validation_cases,
            "patient_graph_by_source": dict(self.patient_graph_by_source),
        }


def _first_count(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    return int(rows[0].get("deleted_count") or 0)


def reset_knowledge_graph(client: Any) -> tuple[int, int]:
    """Purge TestPatient + RulesetReplay from the knowledge graph.

    Returns (test_patients_deleted, ruleset_replays_deleted).
    """
    test_patients = _first_count(client.run(_PURGE_TEST_PATIENTS))
    ruleset_replays = _first_count(client.run(_PURGE_RULESET_REPLAYS))
    return test_patients, ruleset_replays


def reset_patient_graph(
    client: Any,
    *,
    sources: tuple[str, ...] = PATIENT_GRAPH_SOURCES,
) -> dict[str, int]:
    """Purge ValidationCase nodes plus scaffolded Patient graphs.

    Returns a per-source deletion count map.
    """
    counts: dict[str, int] = {}
    for source in sources:
        rows = client.run(_PURGE_PATIENT_GRAPH_BY_SOURCE, source=source)
        counts[source] = _first_count(rows)
    return counts


def reset_validation_lab(
    knowledge_client: Any,
    patient_client: Any,
    *,
    sources: tuple[str, ...] = PATIENT_GRAPH_SOURCES,
) -> ResetReport:
    """Purge every synthetic Validation Lab data source. Idempotent."""
    test_patients, ruleset_replays = reset_knowledge_graph(knowledge_client)
    validation_cases = _first_count(patient_client.run(_PURGE_VALIDATION_CASES))
    by_source = reset_patient_graph(patient_client, sources=sources)
    return ResetReport(
        test_patients=test_patients,
        ruleset_replays=ruleset_replays,
        validation_cases=validation_cases,
        patient_graph_by_source=by_source,
    )
