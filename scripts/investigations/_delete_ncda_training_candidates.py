"""Remove stale NCDA-sourced TrainingCandidate nodes from the Knowledge Graph.

Does not delete GoldLabel or other sources. Run after migrating to
audit_verified.

Usage:
    python scripts/investigations/_delete_ncda_training_candidates.py
    python scripts/investigations/_delete_ncda_training_candidates.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    client = KnowledgeGraphClient()
    try:
        with client.session() as s:
            q_count = (
                "MATCH (c:TrainingCandidate {source: $src}) " "RETURN count(c) AS n"
            )
            row = s.run(q_count, src="NCDA").single()
            n = int(row["n"]) if row else 0
            print(f"TrainingCandidate source=NCDA count: {n}")
            if args.dry_run or n == 0:
                return
            q_del = "MATCH (c:TrainingCandidate {source: $src}) DETACH DELETE c"
            s.run(q_del, src="NCDA")
            print("Deleted.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
