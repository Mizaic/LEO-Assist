"""List all active SNOMED descendants for a concept."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.neo4j_client.client import KnowledgeGraphClient

load_keyvault_secrets()

Q = """
MATCH (ancestor:Concept {id: $concept_id})<-[:IS_A*1..20]-(d:Concept)
WHERE d.active = true
RETURN DISTINCT
  d.id AS concept_id,
  coalesce(d.preferredTerm, d.fsn) AS preferred_term,
  d.fsn AS fsn,
  d.semantic_tag AS semantic_tag
ORDER BY preferred_term
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("concept_id")
    args = parser.parse_args()

    concept_id = str(args.concept_id)
    out_dir = ROOT / "scripts" / "investigations" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"descendants_{concept_id}.json"
    out_csv = out_dir / f"descendants_{concept_id}.csv"

    kg = KnowledgeGraphClient()
    try:
        rows = kg.run(Q, concept_id=concept_id) or []
    finally:
        kg.close()

    out_json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["concept_id", "preferred_term", "fsn", "semantic_tag"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"descendants={len(rows)}")
    print(f"json={out_json}")
    print(f"csv={out_csv}")


if __name__ == "__main__":
    main()
