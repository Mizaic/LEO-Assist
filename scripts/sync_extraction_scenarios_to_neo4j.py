"""Push clinical extraction scenario fixtures into Neo4j.

Reads tests/fixtures/clinical_extraction_scenarios/expected_strings.json
and upserts every case into :ExtractionScenario nodes in the knowledge graph.

Existing nodes are updated from the fixture for all content fields. Clinician
approval fields (review_status, reviewed_by, reviewed_at) are preserved on
update so a fixture sync does not undo sign-off work done in the admin UI.

Usage
-----
    python3 scripts/sync_extraction_scenarios_to_neo4j.py

    # or:
    python -m scripts.sync_extraction_scenarios_to_neo4j
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
_API_DIR = REPO_ROOT / "services" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "clinical_extraction_scenarios"
    / "expected_strings.json"
)

load_dotenv(REPO_ROOT / "secrets" / ".env.secrets")
load_dotenv(REPO_ROOT / "secrets" / ".env.config", override=True)

from libs.cypher.extraction_scenario_queries import (  # noqa: E402
    EXTRACTION_SCENARIO_CONSTRAINTS,
    SYNC_EXTRACTION_SCENARIO,
)

logger = logging.getLogger(__name__)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _markdown_body(case: dict) -> str:
    source_md = case.get("source_markdown", "")
    md_path = REPO_ROOT / source_md if source_md else None
    if md_path and md_path.exists():
        return md_path.read_text(encoding="utf-8")
    return ""


def _case_params(case: dict, fixture: dict, now: str) -> dict:
    return {
        "case_id": case["case_id"],
        "site": case.get("site", ""),
        "format": case.get("format", ""),
        "phrase_classes": json.dumps(case.get("phrase_classes", [])),
        "difficulty": json.dumps(case.get("difficulty", [])),
        "review_status": case.get("review_status", "draft_for_clinician_approval"),
        "expected_strings": json.dumps(case.get("expected_strings", [])),
        "expected_observables": json.dumps(case.get("expected_observables", [])),
        "expected_analysis": json.dumps(case.get("expected_analysis") or {}),
        "expected_sbar": json.dumps(case.get("expected_sbar") or {}),
        "must_not_extract": json.dumps(case.get("must_not_extract", [])),
        "markdown_body": _markdown_body(case),
        "source_template_markdown": case.get("source_template_markdown", ""),
        "notes_for_clinician_review": case.get("notes_for_clinician_review", ""),
        "synthetic_patient": json.dumps(case.get("synthetic_patient", {})),
        "blood_results": json.dumps(case.get("blood_results", [])),
        "schema_version": fixture.get("schema_version", 1),
        "source": "fixture",
        "created_at": now,
        "updated_at": now,
    }


def sync_fixtures_to_neo4j(client: object) -> dict[str, int]:  # type: ignore[type-arg]
    """Upsert every fixture case into Neo4j."""
    fixture = _load_fixture()
    cases = fixture.get("cases", [])
    now = datetime.now(timezone.utc).isoformat()

    for statement in EXTRACTION_SCENARIO_CONSTRAINTS:
        client.run(statement)

    synced = 0
    for case in cases:
        rows = client.run(SYNC_EXTRACTION_SCENARIO, **_case_params(case, fixture, now))
        if rows:
            synced += 1

    return {"synced": synced, "fixture_cases": len(cases)}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.db.neo4j_client import CodingGraphClient

    client = CodingGraphClient()
    try:
        summary = sync_fixtures_to_neo4j(client)
        logger.info(
            "[ExtractionScenarioSync] Upserted %d of %d fixture case(s) to Neo4j.",
            summary["synced"],
            summary["fixture_cases"],
        )
        print(
            f"Synced {summary['synced']} extraction scenario(s) to Neo4j "
            f"from {summary['fixture_cases']} fixture case(s)."
        )
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
