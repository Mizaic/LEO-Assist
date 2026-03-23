"""Migrate legacy TrainingLabel nodes into GDPR-isolated TrainingCandidate nodes.

Source:      Patient Graph (NEO4J_URI)          — where TrainingLabel nodes live
Destination: Knowledge Graph (KNOWLEDGE_GRAPH_NEO4J_URI) — de-identified model knowledge

Rules:
- Only the encounter TEXT is migrated. No entities_json, no quality_score, no assertions.
- candidate_id = SHA256(text)  — content-only hash, no patient linkage
- All candidates are written with status='pending' so the new pipeline processes them fresh.
- GoldLabel nodes are NOT created here — they are produced by running the new pipeline
  against these candidates after verification.
- After migration (DRY_RUN=false), legacy TrainingLabel nodes are deleted from Patient Graph.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "secrets" / ".env.config", override=True)
load_dotenv(ROOT / "secrets" / ".env", override=False)


READ_LEGACY = """
MATCH (t:TrainingLabel)
WHERE t.text IS NOT NULL AND trim(t.text) <> ''
RETURN
  t.text   AS text,
  t.source AS source
"""

# Only text goes in — no entities, no quality score, no patient linkage.
UPSERT_CANDIDATE = """
MERGE (c:TrainingCandidate {candidate_id: $candidate_id})
ON CREATE SET
  c.text         = $text,
  c.source       = $source,
  c.status       = 'pending',
  c.schema_version = 'v4',
  c.created_at   = datetime(),
  c.updated_at   = datetime()
ON MATCH SET
  c.text         = $text,
  c.source       = $source,
  c.updated_at   = datetime()
"""

DELETE_LEGACY = "MATCH (t:TrainingLabel) DETACH DELETE t"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _gold_label_id(text: str, entities_json: str) -> str:
    return _sha(f"{text}\n{entities_json}")


def main() -> None:
    # Patient Graph — source of legacy TrainingLabel nodes
    pg_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    pg_user = os.getenv("NEO4J_USER", "neo4j")
    pg_password = os.getenv("NEO4J_PASSWORD", "password")

    # Knowledge Graph — destination for TrainingCandidate / GoldLabel
    kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    kg_password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")

    dry_run = os.getenv("DRY_RUN", "true").lower() != "false"

    if not dry_run and not all([kg_uri, kg_user, kg_password]):
        raise RuntimeError(
            "Knowledge Graph credentials missing. "
            "Set KNOWLEDGE_GRAPH_NEO4J_URI, KNOWLEDGE_GRAPH_NEO4J_USERNAME, "
            "KNOWLEDGE_GRAPH_NEO4J_PASSWORD in secrets/.env"
        )

    pg_driver = GraphDatabase.driver(pg_uri, auth=(pg_user, pg_password))
    kg_driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_password)) if not dry_run else None

    migrated_candidates = 0

    print(f"Reading TrainingLabel nodes from Patient Graph ({pg_uri})…")
    with pg_driver.session() as pg_session:
        rows = list(pg_session.run(READ_LEGACY))
        print(f"Found {len(rows)} TrainingLabel nodes.")

        seen: set[str] = set()
        for row in rows:
            text = (row.get("text") or "").strip()
            if not text:
                continue
            source = row.get("source") or "legacy_migration"
            candidate_id = _sha(text)

            # Deduplicate by content hash (same text from different encounters = same candidate)
            if candidate_id in seen:
                continue
            seen.add(candidate_id)

            if not dry_run and kg_driver:
                with kg_driver.session() as kg_session:
                    kg_session.run(
                        UPSERT_CANDIDATE,
                        candidate_id=candidate_id,
                        text=text,
                        source=source,
                    )
            migrated_candidates += 1

        if not dry_run:
            print("Deleting legacy TrainingLabel nodes from Patient Graph…")
            pg_session.run(DELETE_LEGACY)

    pg_driver.close()
    if kg_driver:
        kg_driver.close()

    dest = "Knowledge Graph" if not dry_run else "DRY RUN (no writes)"
    print(
        f"Migration complete - {dest}\n"
        f"  candidates : {migrated_candidates} (text only, status=pending)\n"
        f"  dry_run    : {dry_run}\n"
        f"  NOTE: GoldLabel nodes are NOT created here.\n"
        f"        Run the new pipeline against these candidates to produce gold labels."
    )


if __name__ == "__main__":
    main()

