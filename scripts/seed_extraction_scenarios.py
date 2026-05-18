"""Seed ExtractionScenario nodes into the Knowledge Graph.

Reads every case from tests/fixtures/clinical_extraction_scenarios/expected_strings.json
and upserts a corresponding :ExtractionScenario node into the knowledge graph.

Only seeds when no ExtractionScenario nodes exist; skips if any are already
present to avoid overwriting user-modified review_status or reviewed_by data.

Usage
-----
    python -m scripts.seed_extraction_scenarios

    # or directly:
    python3 scripts/seed_extraction_scenarios.py

Linked design controls (Atlas):
    VAL-87173594 (phrase-level F1 validation)
    VT-29880CC8  (extraction scenario verification)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
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
    COUNT_EXTRACTION_SCENARIOS,
    MERGE_EXTRACTION_SCENARIO,
    REFRESH_EXTRACTION_SCENARIO_MARKDOWN_BODY,
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


def _refresh_markdown_bodies(client: object, cases: list[dict], now: str) -> int:
    """Refresh old bodies that still contain metadata or answer sections."""
    refreshed = 0
    for case in cases:
        rows = client.run(
            REFRESH_EXTRACTION_SCENARIO_MARKDOWN_BODY,
            case_id=case["case_id"],
            markdown_body=_markdown_body(case),
            updated_at=now,
        )
        refreshed += len(rows)
    return refreshed


def seed_if_missing(client: object) -> None:  # type: ignore[type-arg]
    """MERGE :ExtractionScenario nodes from fixture file.

    Skips entirely if any ExtractionScenario nodes already exist.
    """
    fixture = _load_fixture()
    cases = fixture.get("cases", [])
    now = datetime.now(timezone.utc).isoformat()
    result = client.run(COUNT_EXTRACTION_SCENARIOS)
    existing = result[0]["count"] if result else 0
    if existing > 0:
        refreshed = _refresh_markdown_bodies(client, cases, now)
        logger.info(
            "[ExtractionScenarioSeed] Skipped create -- %d node(s) already "
            "present; refreshed %d old markdown body value(s).",
            existing,
            refreshed,
        )
        return

    seeded = 0

    for case in cases:
        params = {
            "case_id": case["case_id"],
            "site": case.get("site", ""),
            "format": case.get("format", ""),
            "phrase_classes": json.dumps(case.get("phrase_classes", [])),
            "difficulty": json.dumps(case.get("difficulty", [])),
            "review_status": case.get("review_status", "draft_for_clinician_approval"),
            "expected_strings": json.dumps(case.get("expected_strings", [])),
            "expected_observables": json.dumps(case.get("expected_observables", [])),
            "must_not_extract": json.dumps(case.get("must_not_extract", [])),
            "markdown_body": _markdown_body(case),
            "source_template_markdown": case.get("source_template_markdown", ""),
            "notes_for_clinician_review": case.get("notes_for_clinician_review", ""),
            "synthetic_patient": json.dumps(case.get("synthetic_patient", {})),
            "blood_results": json.dumps(case.get("blood_results", [])),
            "schema_version": fixture.get("schema_version", 1),
            "created_at": now,
        }
        client.run(MERGE_EXTRACTION_SCENARIO, **params)
        seeded += 1

    logger.info(
        "[ExtractionScenarioSeed] Seeded %d ExtractionScenario node(s).", seeded
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.db.neo4j_client import CodingGraphClient

    client = CodingGraphClient()
    try:
        seed_if_missing(client)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
