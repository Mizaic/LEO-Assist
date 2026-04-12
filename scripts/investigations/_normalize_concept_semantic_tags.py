"""Normalize Knowledge Graph Concept.semantic_tag values to canonical snake_case.

Usage:
  python scripts/investigations/_normalize_concept_semantic_tags.py --dry-run
  python scripts/investigations/_normalize_concept_semantic_tags.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

try:
    load_keyvault_secrets()
except ModuleNotFoundError:
    # Allow running in lightweight local Python envs without azure SDK.
    pass

from libs.neo4j_client.client import KnowledgeGraphClient  # noqa: E402
from libs.terminology.semantic_tag import normalise_semantic_tag  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates (default is dry-run).",
    )
    args = parser.parse_args()

    client = KnowledgeGraphClient()
    try:
        with client.session() as session:
            rows = list(session.run("""
                    MATCH (c:Concept)
                    WHERE c.semantic_tag IS NOT NULL
                      AND trim(c.semantic_tag) <> ''
                    RETURN c.id AS concept_id, c.semantic_tag AS semantic_tag
                    """))

            updates: list[dict[str, str]] = []
            for row in rows:
                current = str(row.get("semantic_tag") or "")
                target = normalise_semantic_tag(current)
                if current != target:
                    updates.append(
                        {
                            "concept_id": str(row.get("concept_id") or ""),
                            "before": current,
                            "after": target,
                        }
                    )

            print(f"Concept nodes checked: {len(rows)}")
            print(f"Tags needing update:  {len(updates)}")
            for sample in updates[:10]:
                print(
                    f"  {sample['concept_id']}: {sample['before']} -> {sample['after']}"
                )

            if not args.apply:
                print("\nDRY RUN only. Re-run with --apply to update.")
                return

            if not updates:
                print("\nNo updates needed.")
                return

            session.run(
                """
                UNWIND $rows AS r
                MATCH (c:Concept {id: r.concept_id})
                SET c.semantic_tag = r.after
                """,
                rows=updates,
            )
            print(f"\nApplied updates: {len(updates)}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
