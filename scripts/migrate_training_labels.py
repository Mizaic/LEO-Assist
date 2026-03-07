"""Migrate legacy TrainingLabel nodes into GDPR-isolated TrainingCandidate/GoldLabel.

Rules:
- Removes patient/encounter/source_ref linkage fields.
- candidate_id = SHA256(text)
- label_id = SHA256(text + sorted entity texts)
- quality >= 0.8 and entities present -> GoldLabel
- otherwise -> TrainingCandidate
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env", override=False)


READ_LEGACY = """
MATCH (t:TrainingLabel)
RETURN
  t.label_id AS legacy_label_id,
  t.text AS text,
  t.entities_json AS entities_json,
  t.quality_score AS quality_score,
  t.source AS source
"""

UPSERT_CANDIDATE = """
MERGE (c:TrainingCandidate {candidate_id: $candidate_id})
ON CREATE SET
  c.text = $text,
  c.source = $source,
  c.status = 'pending',
  c.schema_version = 'v4',
  c.created_at = datetime(),
  c.updated_at = datetime()
ON MATCH SET
  c.text = $text,
  c.source = $source,
  c.updated_at = datetime()
"""

UPSERT_GOLD = """
MERGE (g:GoldLabel {label_id: $label_id})
ON CREATE SET
  g.text = $text,
  g.entities_json = $entities_json,
  g.quality_score = $quality_score,
  g.source = $source,
  g.verified_by = 'migration',
  g.verified_at = datetime(),
  g.candidate_id = $candidate_id,
  g.schema_version = 'v4',
  g.created_at = datetime(),
  g.updated_at = datetime()
ON MATCH SET
  g.text = $text,
  g.entities_json = $entities_json,
  g.quality_score = $quality_score,
  g.source = $source,
  g.verified_by = 'migration',
  g.verified_at = datetime(),
  g.candidate_id = $candidate_id,
  g.updated_at = datetime()
WITH g
MATCH (c:TrainingCandidate {candidate_id: $candidate_id})
MERGE (c)-[:PRODUCED]->(g)
"""

DELETE_LEGACY = "MATCH (t:TrainingLabel) DETACH DELETE t"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _gold_label_id(text: str, entities_json: str) -> str:
    try:
        entities = json.loads(entities_json or "[]")
    except Exception:
        entities = []
    parts = sorted(str(e.get("text", "")) for e in entities if isinstance(e, dict))
    return _sha(text + "|" + "|".join(parts))


def main() -> None:
    uri = os.getenv("PATIENT_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user = os.getenv("PATIENT_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv("PATIENT_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "password"))
    dry_run = os.getenv("DRY_RUN", "true").lower() != "false"

    driver = GraphDatabase.driver(uri, auth=(user, password))
    migrated_candidates = 0
    migrated_gold = 0

    with driver.session() as session:
        rows = list(session.run(READ_LEGACY))
        for row in rows:
            text = (row.get("text") or "").strip()
            if not text:
                continue
            entities_json = row.get("entities_json") or "[]"
            quality = float(row.get("quality_score") or 0.0)
            source = row.get("source") or "legacy_migration"

            candidate_id = _sha(text)
            label_id = _gold_label_id(text, entities_json)

            if not dry_run:
                session.run(
                    UPSERT_CANDIDATE,
                    candidate_id=candidate_id,
                    text=text,
                    source=source,
                )
            migrated_candidates += 1

            entities_present = False
            try:
                entities_present = len(json.loads(entities_json or "[]")) > 0
            except Exception:
                entities_present = False
            if quality >= 0.8 and entities_present:
                if not dry_run:
                    session.run(
                        UPSERT_GOLD,
                        label_id=label_id,
                        text=text,
                        entities_json=entities_json,
                        quality_score=quality,
                        source=source,
                        candidate_id=candidate_id,
                    )
                migrated_gold += 1

        if not dry_run:
            session.run(DELETE_LEGACY)

    driver.close()
    print(
        f"migration complete dry_run={dry_run} candidates={migrated_candidates} gold={migrated_gold}"
    )


if __name__ == "__main__":
    main()

