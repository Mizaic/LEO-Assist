"""Migrate persisted v2 AppropriatenessRule.logicJson to the synonym-set shape.

DI-LEO-AI-508 / UN-LEO-AI-093.

Walks every active or pending v2 AppropriatenessRule, upgrades each CONCEPT
leaf to the new criterion shape (seeds populated from the existing single
``snomed_concept_id``; ``primary_concept_id`` set to that id;
``excluded_concept_ids: []``), and writes the upgraded JSON back. The legacy
``snomed_concept_id`` field is preserved so a partial roll-back of the API
layer leaves criteria readable.

The upgrade is **lossless and idempotent**: running the script twice on the
same rule produces a byte-identical second-pass output, and the int-id set
that the bitmap compiler will pass to ``put_bitmap`` is unchanged.

Usage::

    source .venv/bin/activate
    python -m scripts.migrations.2026_logic_criterion_synonym_set --dry-run
    python -m scripts.migrations.2026_logic_criterion_synonym_set --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Default IS_A descendant depth used by the bitmap compiler when distance_child
# is absent on the legacy criterion. Mirrors guideline_compiler defaults.
DEFAULT_DESCENDANT_DEPTH = 3


def upgrade_concept_leaf(criterion: dict[str, Any]) -> dict[str, Any]:
    """Upgrade one CONCEPT criterion to the synonym-set shape.

    Idempotent: if ``seeds`` is already populated the criterion is returned
    unchanged (modulo dict ordering normalisation).
    """
    seeds_in = list(criterion.get("seeds") or [])
    primary_id = criterion.get("primary_concept_id") or ""
    excluded = list(criterion.get("excluded_concept_ids") or [])

    if seeds_in:
        # Already migrated; normalise primary + legacy fields.
        primary_id = primary_id or seeds_in[0]["snomed_concept_id"]
        primary_seed = next(
            (s for s in seeds_in if s["snomed_concept_id"] == primary_id),
            seeds_in[0],
        )
        return {
            "snomed_concept_id": primary_id,
            "preferred_term": criterion.get("preferred_term")
            or primary_seed.get("preferred_term", ""),
            "semantic_tag": criterion.get("semantic_tag")
            or primary_seed.get("semantic_tag", ""),
            "term": criterion.get("term", ""),
            "seeds": [_normalise_seed(s) for s in seeds_in],
            "excluded_concept_ids": list(excluded),
            "primary_concept_id": primary_id,
        }

    # Legacy single-seed shape; promote.
    cid = criterion.get("snomed_concept_id", "")
    if not cid:
        # Cannot migrate a malformed criterion; return unchanged so the
        # operator notices and fixes it.
        return dict(criterion)
    distance_child = criterion.get("distance_child")
    seed = {
        "snomed_concept_id": cid,
        "preferred_term": criterion.get("preferred_term", ""),
        "semantic_tag": criterion.get("semantic_tag", ""),
        "include_descendants": True,
        "distance_child": (
            int(distance_child) if distance_child is not None else None
        ),
    }
    return {
        "snomed_concept_id": cid,
        "preferred_term": criterion.get("preferred_term", ""),
        "semantic_tag": criterion.get("semantic_tag", ""),
        "term": criterion.get("term", ""),
        "seeds": [_normalise_seed(seed)],
        "excluded_concept_ids": [],
        "primary_concept_id": cid,
    }


def _normalise_seed(seed: dict[str, Any]) -> dict[str, Any]:
    return {
        "snomed_concept_id": seed["snomed_concept_id"],
        "preferred_term": seed.get("preferred_term", ""),
        "semantic_tag": seed.get("semantic_tag", ""),
        "include_descendants": bool(seed.get("include_descendants", True)),
        "distance_child": (
            int(seed["distance_child"]) if seed.get("distance_child") is not None else None
        ),
    }


def upgrade_logic_tree(node: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recursively upgrade every CONCEPT leaf in a logic tree."""
    if not node:
        return node
    kind = str(node.get("kind") or "").lower()
    if kind == "concept":
        criterion = node.get("criterion") or {}
        return {**node, "criterion": upgrade_concept_leaf(criterion)}
    children = node.get("children") or []
    if not children:
        return node
    return {**node, "children": [upgrade_logic_tree(c) for c in children]}


# -- Cypher ---------------------------------------------------------------

_FETCH_RULES = """
MATCH (r:AppropriatenessRule)
WHERE r.schemaVersion = 2 AND r.status IN ['active', 'pending_review']
RETURN r.id AS rule_id, r.logicJson AS logic_json
"""

_WRITE_RULE = """
MATCH (r:AppropriatenessRule {id: $rule_id})
SET r.logicJson = $logic_json,
    r.synonymSetMigratedAt = datetime()
RETURN r.id AS id
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes back")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args(argv)

    if not args.apply and not args.dry_run:
        parser.error("Pass --dry-run or --apply explicitly.")

    # Defer driver import so unit tests can import upgrade_concept_leaf
    # without a Neo4j dependency.
    from dotenv import load_dotenv  # noqa: WPS433
    from neo4j import GraphDatabase  # noqa: WPS433

    root = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root / "secrets" / ".env.config", override=True)
    load_dotenv(root / "secrets" / ".env", override=False)

    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER"))
    password = os.getenv(
        "KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD")
    )
    if not uri or not user or not password:
        print("Missing Neo4j credentials in secrets/.env*; aborting.", file=sys.stderr)
        return 2

    driver = GraphDatabase.driver(uri, auth=(user, password))
    upgraded = 0
    skipped = 0
    with driver.session() as session:
        rows = list(session.run(_FETCH_RULES))
        for row in rows:
            rule_id = row["rule_id"]
            raw = row.get("logic_json") or "{}"
            try:
                tree = json.loads(raw)
            except Exception as exc:  # noqa: BLE001
                print(f"SKIP {rule_id}: invalid JSON ({exc})", file=sys.stderr)
                skipped += 1
                continue

            new_tree = upgrade_logic_tree(tree)
            new_json = json.dumps(new_tree, sort_keys=True)
            old_json = json.dumps(tree, sort_keys=True)
            if new_json == old_json:
                skipped += 1
                continue

            if args.apply:
                session.run(_WRITE_RULE, rule_id=rule_id, logic_json=new_json)
            upgraded += 1
            print(f"{'APPLIED' if args.apply else 'WOULD UPGRADE'} {rule_id}")

    driver.close()
    print(f"upgraded={upgraded} skipped={skipped} mode={'apply' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
