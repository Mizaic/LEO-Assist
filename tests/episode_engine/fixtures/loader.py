"""Helpers for using the synthetic SYN-EE-* fixtures in episode-engine VTs.

These helpers give tests a small, in-memory shim that mimics the
``PatientGraphClient.run()`` contract used by the timeline loader, so
the engine can be exercised end-to-end without a live Neo4j instance.

Only the ``MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter)``
shape is supported -- it's all the timeline_loader needs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

_FIXTURES_DIR = Path(__file__).parent
_SYN_EE_001 = _FIXTURES_DIR / "SYN-EE-001-timeline.json"


def load_fixture(synthetic_id: str) -> dict[str, Any]:
    """Return the parsed JSON fixture for ``synthetic_id``."""

    if synthetic_id == "SYN-EE-001":
        path = _SYN_EE_001
    else:
        raise FileNotFoundError(
            f"No fixture for synthetic id {synthetic_id!r}. "
            "Add a JSON file under tests/episode_engine/fixtures/."
        )
    return json.loads(path.read_text(encoding="utf-8"))


class FakePatientGraphClient:
    """Minimal stand-in for ``libs.neo4j_client.client.PatientGraphClient``.

    Holds a synthetic encounter list keyed by patient id and answers the
    ``run(query, patient_id=...)`` shape used by the episode engine's
    timeline_loader. Returns rows in the same dict shape Neo4j would.
    """

    def __init__(self, encounters_by_patient: dict[str, Iterable[dict[str, Any]]]):
        self._by_patient = {
            pid: list(rows) for pid, rows in encounters_by_patient.items()
        }
        self.run_calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    @classmethod
    def from_fixture(cls, synthetic_id: str) -> "FakePatientGraphClient":
        fixture = load_fixture(synthetic_id)
        rows = [
            {
                "encounter_id": e["id"],
                "date": e["date"],
                "text": e["text"],
                "flags": None,
                "coding_status": None,
            }
            for e in fixture["encounters"]
        ]
        return cls({synthetic_id: rows})

    def run(self, _query: str, **params: Any):
        self.run_calls.append((_query, params))
        pid = params.get("patient_id")
        return list(self._by_patient.get(pid, []))

    def close(self) -> None:
        self.closed = True
