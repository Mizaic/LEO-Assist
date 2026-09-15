"""Seed no-evidence-of-cancer surface forms into the Knowledge Graph.

Reads the reviewed phrase list in libs/terminology/no_cancer_phrases.py and
maps each phrase to 395100000 No evidence of cancer found (situation).

Existing SurfaceForm nodes are never overwritten. A phrase already mapped to
the target concept is skipped. A phrase mapped to a different concept is
reported as a conflict and left alone, so a human decides.

Atlas trace:
  DI: DI-F03B0113
  VT: VT-BDD72AC6

Run:
    python scripts/seed_no_cancer_surface_forms.py --dry-run
    python scripts/seed_no_cancer_surface_forms.py
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from libs.terminology.no_cancer_phrases import (  # noqa: E402
    NEVER_NO_CANCER_PHRASES,
    NO_CANCER_RESULT_PHRASES,
    NO_EVIDENCE_OF_CANCER_CONCEPT_ID,
    NO_EVIDENCE_OF_CANCER_TERM,
)
from libs.terminology.surface_normalize import normalize_surface  # noqa: E402

SOURCE = "manual"
PROVENANCE = "di-f03b0113-benign-outcome-seed"
CREATED_BY = "seed_no_cancer_surface_forms"

FIND_EXISTING = """
MATCH (sf:SurfaceForm {normalized: $normalized})
OPTIONAL MATCH (sf)-[:MAPS_TO]->(c:Concept)
RETURN collect(toString(c.id)) AS concept_ids
"""

UPSERT = """
MATCH (c:Concept) WHERE toString(c.id) = $concept_id
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.created_at = datetime(),
              sf.created_by = $created_by,
              sf.form = $form,
              sf.source = $source,
              sf.status = 'approved'
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.created_by = $created_by,
              m.confidence = 1.0,
              m.provenance = $provenance
RETURN sf.normalized AS normalized
"""


@dataclass
class Stats:
    created: int = 0
    already_correct: int = 0
    conflicts: list[tuple[str, list[str]]] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)


def load_kg_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env.config", override=False)
    load_dotenv(ROOT / "secrets" / ".env", override=False)
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing knowledge-graph Neo4j credentials")
    return uri, user, password


def banned_phrases() -> list[str]:
    """Phrases that must never reach the target concept."""
    banned = {normalize_surface(text) for text in NEVER_NO_CANCER_PHRASES}
    return [
        phrase
        for phrase in NO_CANCER_RESULT_PHRASES
        if normalize_surface(phrase) in banned
    ]


def seed_phrase(session, phrase: str, stats: Stats, dry_run: bool) -> None:
    normalized = normalize_surface(phrase)
    row = session.run(FIND_EXISTING, normalized=normalized).single()
    existing = [cid for cid in (row["concept_ids"] if row else []) if cid]

    if NO_EVIDENCE_OF_CANCER_CONCEPT_ID in existing:
        stats.already_correct += 1
        return
    if existing:
        stats.conflicts.append((phrase, existing))
        print(f"  [CONFLICT] {phrase!r} already maps to {existing}")
        return
    if dry_run:
        stats.created += 1
        print(f"  [DRY ] {phrase!r}")
        return

    session.run(
        UPSERT,
        normalized=normalized,
        form=phrase,
        concept_id=NO_EVIDENCE_OF_CANCER_CONCEPT_ID,
        created_by=CREATED_BY,
        source=SOURCE,
        provenance=PROVENANCE,
    ).consume()
    stats.created += 1
    print(f"  [NEW ] {phrase!r}")


def report(stats: Stats, dry_run: bool) -> None:
    verb = "would create" if dry_run else "created"
    print()
    print(f"{verb}: {stats.created}")
    print(f"already correct: {stats.already_correct}")
    print(f"conflicts left for a human: {len(stats.conflicts)}")
    if stats.refused:
        print(f"REFUSED (on the never-map list): {stats.refused}")


def main(dry_run: bool) -> int:
    refused = banned_phrases()
    if refused:
        print("Refusing to seed: phrases on the never-map list are in the")
        print(f"approved list: {refused}")
        return 1

    uri, user, password = load_kg_config()
    stats = Stats()
    print(
        f"Seeding {len(NO_CANCER_RESULT_PHRASES)} phrases -> "
        f"{NO_EVIDENCE_OF_CANCER_CONCEPT_ID} ({NO_EVIDENCE_OF_CANCER_TERM})"
    )
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            for phrase in NO_CANCER_RESULT_PHRASES:
                seed_phrase(session, phrase, stats, dry_run)
    finally:
        driver.close()

    report(stats, dry_run)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(main(dry_run=args.dry_run))
