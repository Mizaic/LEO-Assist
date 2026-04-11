"""Write back approved surface-form mappings to Neo4j.

Input is the prototype coder JSONL output.
Rows are written only when confidence/approval gates pass.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    ROOT
    / "services"
    / "terminology"
    / "data"
    / "training"
    / "surface_forms_9990000001.prototype_coding.jsonl"
)

UPSERT_QUERY = """
UNWIND $rows AS r
MATCH (c:Concept {id: r.concept_id})
MERGE (sf:SurfaceForm {normalized: r.normalized})
ON CREATE SET sf.created_at = datetime(), sf.created_by = r.approved_by
SET sf.form = r.form,
    sf.source = r.source,
    sf.status = r.status,
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(), m.created_by = r.approved_by
SET m.confidence = r.confidence,
    m.method = r.method,
    m.approved_by = r.approved_by,
    m.approved_at = datetime(),
    m.provenance = r.provenance
"""


@dataclass
class Stats:
    input_entities: int = 0
    skipped: int = 0
    eligible: int = 0
    written: int = 0


def normalize(text: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def load_neo4j_config() -> tuple[str, str, str]:
    load_dotenv(ROOT / "secrets" / ".env")
    uri = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_URI", "")
    user = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "")
    password = os.environ.get("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "")
    if not all([uri, user, password]):
        raise RuntimeError("Missing Neo4j credentials in secrets/.env")
    return uri, user, password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approved-by", default="ai.reviewer")
    parser.add_argument("--source", default="surface_forms_training")
    parser.add_argument("--status", default="approved")
    parser.add_argument(
        "--min-confidence-band", choices=("high", "medium"), default="medium"
    )
    return parser.parse_args()


def _band_ok(band: str, minimum: str) -> bool:
    if minimum == "high":
        return band == "high"
    return band in {"high", "medium"}


def extract_rows(
    path: Path, minimum_band: str, approved_by: str, source: str, status: str
) -> tuple[list[dict], Stats]:
    stats = Stats()
    out = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            for er in row.get("entity_results", []):
                stats.input_entities += 1
                if er.get("requires_hitl"):
                    stats.skipped += 1
                    continue
                band = str(er.get("confidence_band", ""))
                if not _band_ok(band, minimum_band):
                    stats.skipped += 1
                    continue
                selected = er.get("selected") or {}
                concept_id = str(selected.get("concept_id", "")).strip()
                mention = str(er.get("mention", "")).strip()
                if not concept_id or not mention:
                    stats.skipped += 1
                    continue
                stats.eligible += 1
                out.append(
                    {
                        "form": mention,
                        "normalized": normalize(mention),
                        "concept_id": concept_id,
                        "confidence": float(selected.get("score", 0.0)),
                        "method": str(er.get("decision_source", "retrieval")),
                        "approved_by": approved_by,
                        "source": source,
                        "status": status,
                        "provenance": "prototype_clinical_coder",
                    }
                )
    return out, stats


def main() -> None:
    args = parse_args()
    rows, stats = extract_rows(
        path=args.input,
        minimum_band=args.min_confidence_band,
        approved_by=args.approved_by,
        source=args.source,
        status=args.status,
    )
    print(f"Input entities: {stats.input_entities}")
    print(f"Eligible mappings: {stats.eligible}")
    print(f"Skipped mappings: {stats.skipped}")
    if args.dry_run:
        print("Dry run only. No writes performed.")
        return
    if not rows:
        print("No rows to write.")
        return

    uri, user, password = load_neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            for i in range(0, len(rows), args.batch_size):
                chunk = rows[i : i + args.batch_size]
                session.run(UPSERT_QUERY, rows=chunk)
                stats.written += len(chunk)
                print(f"Wrote {stats.written}/{len(rows)} rows...")
    finally:
        driver.close()

    print("Write-back complete.")
    print(f"Rows written: {stats.written}")


if __name__ == "__main__":
    main()
