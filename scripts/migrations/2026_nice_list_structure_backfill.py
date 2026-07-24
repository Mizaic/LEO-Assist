"""Backfill ``listStructureJson`` onto already-ingested NICE Recommendation nodes.

Highlight-to-build rule wizard plan, "Ingestion" section (``nice-list-
schema-backfill`` todo). Guidelines ingested before the recursive
HTML list-tree parser existed (``app.services.nice_list_parser``) only
have ``verbatim`` -- flattening a ``<ul>``/``<li>`` tree into plain text
cannot be reversed, so the only way to add structure to them is to
re-fetch the same NICE Syndication API section JSON and re-run the new
parser, exactly as a fresh ingest would.

This script does that, writing **only** ``listStructureJson`` (plus a
``listStructureBackfilledAt`` timestamp) -- ``verbatim`` and every other
Recommendation property, and everything downstream that already reads
``verbatim``, is left untouched.

**Idempotent by construction**: unlike the synonym-set migration this
mirrors, no shape-transformation check is needed -- writing the same
parsed structure twice is a no-op ``SET`` the second time, because the
source (the guideline's own published HTML) does not change between
runs of this script for an unchanged recommendation.

Matches by ``(guideline_id, number)`` rather than the version-scoped
``Recommendation.id`` -- ``listStructureJson`` is a property of the
guideline's own markup, not of any one ingest version, so a
recommendation that has been re-ingested unchanged across several
versions gets the SAME structure written to every one of its version
nodes.

Usage::

    source .venv/bin/activate
    python -m scripts.migrations.2026_nice_list_structure_backfill --codes NG12 --dry-run
    python -m scripts.migrations.2026_nice_list_structure_backfill --codes NG12 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "services" / "api"))

# -- Cypher -----------------------------------------------------------------

_COUNT_MATCHING = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE r.number = $number
RETURN count(r) AS matched
"""

_WRITE_LIST_STRUCTURE = """
MATCH (g:Guideline {id: $guideline_id})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE r.number = $number
SET r.listStructureJson = $list_structure_json,
    r.listStructureBackfilledAt = datetime()
RETURN count(r) AS updated
"""


async def fetch_all_recommendations(client: Any, code: str) -> list[dict[str, Any]]:
    """Fetch every recommendation dict for ``code``, re-running the SAME
    section parser the live ingest path uses (``_extract_recommendations_from_section``)
    so this backfill can never drift from what a fresh ingest would produce.
    """
    from app.routers.nice_guidance import _extract_recommendations_from_section

    recs: list[dict[str, Any]] = []
    chapters = await client.get_chapters(code)
    for chapter in chapters:
        href = chapter.get("Href", "") or chapter.get("Uri", "")
        if not href:
            continue
        try:
            chapter_data = await client.get_chapter_content(href)
        except RuntimeError:
            continue
        for sec_uri in client.get_section_uris(chapter_data):
            try:
                section_data = await client.get_section_content(sec_uri)
            except RuntimeError:
                continue
            recs.extend(_extract_recommendations_from_section(section_data, code))
    return recs


def backfill_guideline(
    session: Any,
    code: str,
    recs: list[dict[str, Any]],
    apply: bool,
) -> tuple[int, int]:
    """Write ``listStructureJson`` for every rec that has structure.

    Returns ``(updated, skipped)``. A rec is skipped when it has no
    ``ListStructure`` (plain-sentence recommendation -- nothing to
    backfill) or when no matching ``Recommendation`` node exists yet
    for this guideline (rare -- e.g. a recommendation NICE has since
    added that has not been ingested at all).
    """
    guideline_id = code.upper()
    updated = 0
    skipped = 0
    for rec in recs:
        structure = rec.get("ListStructure")
        number = rec.get("Title", "")
        if not structure or not number:
            skipped += 1
            continue

        if apply:
            result = session.run(
                _WRITE_LIST_STRUCTURE,
                guideline_id=guideline_id,
                number=number,
                list_structure_json=json.dumps(structure),
            )
            matched = (result.single() or {}).get("updated", 0)
        else:
            result = session.run(
                _COUNT_MATCHING, guideline_id=guideline_id, number=number
            )
            matched = (result.single() or {}).get("matched", 0)

        if not matched:
            skipped += 1
            continue
        updated += 1
        item_count = len(structure.get("items", []))
        verb = "APPLIED" if apply else "WOULD BACKFILL"
        print(f"{verb} {guideline_id} {number} ({item_count} item(s))")
    return updated, skipped


def _bootstrap_secrets() -> None:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
    load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
    if os.environ.get("AZURE_KEYVAULT_URL"):
        from libs.keyvault.loader import load_keyvault_secrets

        load_keyvault_secrets()


def _neo4j_driver():
    from neo4j import GraphDatabase

    uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", os.getenv("NEO4J_URI"))
    user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", os.getenv("NEO4J_USER"))
    password = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD"))
    if not uri or not user or not password:
        print("Missing Neo4j credentials in secrets/.env*; aborting.", file=sys.stderr)
        return None
    return GraphDatabase.driver(uri, auth=(user, password))


async def _run(codes: list[str], apply: bool) -> int:
    from app.services.nice_api_client import NiceApiClient

    if not os.environ.get("NICE_API_KEY"):
        print(
            "NICE_API_KEY not set -- run 'az login' or set it in secrets/.env",
            file=sys.stderr,
        )
        return 2

    driver = _neo4j_driver()
    if driver is None:
        return 2

    client = NiceApiClient()
    total_updated = 0
    total_skipped = 0
    try:
        with driver.session() as session:
            for code in codes:
                print(f"--- {code} ---")
                recs = await fetch_all_recommendations(client, code)
                updated, skipped = backfill_guideline(session, code, recs, apply)
                total_updated += updated
                total_skipped += skipped
    finally:
        driver.close()

    mode = "apply" if apply else "dry-run"
    print(f"updated={total_updated} skipped={total_skipped} mode={mode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codes",
        default="NG12",
        help="Comma-separated NICE guidance codes to backfill (default: NG12).",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes back")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args(argv)

    if not args.apply and not args.dry_run:
        parser.error("Pass --dry-run or --apply explicitly.")

    _bootstrap_secrets()
    codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()]
    return asyncio.run(_run(codes, args.apply))


if __name__ == "__main__":
    sys.exit(main())
