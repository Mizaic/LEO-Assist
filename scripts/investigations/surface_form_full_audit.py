"""Full audit of SurfaceForm nodes in the knowledge graph (Neo4j).

Runs read-only checks, writes JSON report, and optionally repairs data.

Checks:
  - missing or wrong `normalized` vs resolver rule (libs.terminology.surface_normalize)
  - legacy `text` without `form`
  - MAPS_TO to inactive concepts
  - MAPS_TO to suspicious semantic tags (body structure, organism, etc.)
  - multi-mapped forms (one SurfaceForm -> multiple concepts)
  - low-confidence edges (< 0.7)
  - orphan SurfaceForm nodes (no MAPS_TO)

Fix mode (--fix):
  - Sets `form` from `text` when needed
  - Sets `normalized` to canonical value when safe (no unique-constraint clash)
  - On clash: merges MAPS_TO from duplicate into canonical node, deletes duplicate
  - Removes redundant `text` after `form` is set
  - Does NOT delete orphans unless --delete-orphans

Usage:
    python scripts/investigations/surface_form_full_audit.py
    python scripts/investigations/surface_form_full_audit.py --fix
    python scripts/investigations/surface_form_full_audit.py --fix --delete-orphans
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
from libs.terminology.surface_normalize import normalize_surface  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

REPORT_PATH = Path(__file__).resolve().parent / "surface_form_full_audit_report.json"

BAD_TAGS = frozenset(
    {
        "qualifier value",
        "body structure",
        "organism",
        "substance",
        "attribute",
        "environment",
        "physical object",
    }
)

_FETCH_ALL = """
MATCH (sf:SurfaceForm)
OPTIONAL MATCH (sf)-[r:MAPS_TO]->(c:Concept)
RETURN elementId(sf) AS eid,
       sf.normalized AS normalized,
       sf.form AS form,
       sf.text AS text,
       sf.status AS status,
       sf.source AS source,
       collect(
         CASE WHEN c IS NULL THEN NULL
         ELSE {
           cid: c.id, fsn: c.fsn, tag: c.semantic_tag,
           active: c.active, conf: r.confidence, prov: r.provenance
         }
         END
       ) AS rels
"""

_COUNT_ORPHANS = """
MATCH (sf:SurfaceForm) WHERE NOT (sf)-[:MAPS_TO]->()
RETURN count(sf) AS n
"""

_DELETE_ORPHAN = """
MATCH (sf:SurfaceForm) WHERE NOT (sf)-[:MAPS_TO]->()
DETACH DELETE sf
RETURN count(sf) AS deleted
"""

_MERGE_REL_BY_KEEPER_ID = """
MATCH (keep:SurfaceForm) WHERE elementId(keep) = $keep_eid
MATCH (c:Concept {id: $cid})
MERGE (keep)-[nr:MAPS_TO]->(c)
ON CREATE SET nr.created_at = datetime(), nr.approved_at = datetime(),
              nr.confidence = $conf, nr.provenance = $prov
SET nr.confidence = CASE
      WHEN coalesce(nr.confidence, 0.0) >= coalesce($conf, 0.0)
      THEN nr.confidence ELSE $conf END,
    nr.provenance = CASE
      WHEN coalesce(nr.confidence, 0.0) >= coalesce($conf, 0.0)
      THEN nr.provenance ELSE $prov END
RETURN elementId(keep) AS eid
"""

_DELETE_SF_BY_ID = """
MATCH (sf:SurfaceForm) WHERE elementId(sf) = $eid
DETACH DELETE sf
RETURN count(sf) AS deleted
"""

_UPDATE_SF_FIELDS = """
MATCH (sf:SurfaceForm) WHERE elementId(sf) = $eid
SET sf.normalized = $norm,
    sf.form = $form
REMOVE sf.text
RETURN sf.normalized AS normalized, sf.form AS form
"""


def _clean_rels(rels: list) -> list[dict[str, Any]]:
    out = []
    for x in rels or []:
        if x is None:
            continue
        if isinstance(x, dict) and x.get("cid"):
            out.append(x)
    return out


def collect_audit(session) -> dict[str, Any]:
    rows = list(session.run(_FETCH_ALL))
    missing_norm: list[dict] = []
    norm_mismatch: list[dict] = []
    legacy_text: list[dict] = []
    bad_tag: list[dict] = []
    inactive: list[dict] = []
    multi_map: list[dict] = []
    low_conf: list[dict] = []
    ok_count = 0

    for row in rows:
        eid = row["eid"]
        norm = row["normalized"]
        form = row["form"]
        text = row["text"]
        rels = _clean_rels(row["rels"])
        display = (form or text or "").strip()
        expected = normalize_surface(display) if display else ""

        entry_base = {
            "neo4j_element_id": eid,
            "normalized_stored": norm,
            "form": form,
            "text": text,
            "expected_normalized": expected,
            "mapping_count": len(rels),
        }

        if text and not form:
            legacy_text.append({**entry_base})

        if not display:
            continue

        if norm is None or norm == "":
            missing_norm.append({**entry_base})
        elif norm != expected:
            norm_mismatch.append({**entry_base})

        if len(rels) > 1:
            multi_map.append(
                {
                    **entry_base,
                    "targets": [
                        {
                            "cid": r["cid"],
                            "fsn": (r.get("fsn") or "")[:80],
                            "conf": r.get("conf"),
                        }
                        for r in rels
                    ],
                }
            )

        for r in rels:
            tag = (r.get("tag") or "").strip()
            if tag in BAD_TAGS:
                bad_tag.append(
                    {
                        "neo4j_element_id": eid,
                        "form": display,
                        "cid": r["cid"],
                        "fsn": (r.get("fsn") or "")[:80],
                        "tag": tag,
                        "conf": r.get("conf"),
                    }
                )
            if r.get("active") is False:
                inactive.append(
                    {
                        "neo4j_element_id": eid,
                        "form": display,
                        "cid": r["cid"],
                        "fsn": (r.get("fsn") or "")[:80],
                    }
                )
            conf = r.get("conf")
            if conf is not None and float(conf) < 0.7:
                low_conf.append(
                    {
                        "neo4j_element_id": eid,
                        "form": display,
                        "cid": r["cid"],
                        "conf": conf,
                        "prov": r.get("prov"),
                    }
                )

        if norm == expected and display and len(rels) <= 1 and not (text and not form):
            ok_count += 1

    orphan_n = session.run(_COUNT_ORPHANS).single()["n"]

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "surface_forms_with_any_mapping": len(
                [r for r in rows if _clean_rels(r["rels"])]
            ),
            "surface_form_nodes_total": len(rows),
            "orphans_no_maps_to": orphan_n,
            "missing_normalized": len(missing_norm),
            "normalized_mismatch": len(norm_mismatch),
            "legacy_text_only": len(legacy_text),
            "bad_semantic_tag_hits": len(bad_tag),
            "inactive_concept_hits": len(inactive),
            "multi_mapped_forms": len(multi_map),
            "low_confidence_edges": len(low_conf),
        },
        "missing_normalized": missing_norm[:500],
        "normalized_mismatch": norm_mismatch[:500],
        "legacy_text_only": legacy_text[:500],
        "bad_semantic_tag": bad_tag[:500],
        "inactive_concept": inactive[:200],
        "multi_mapped": multi_map[:200],
        "low_confidence": low_conf[:200],
    }


def fix_normalized_and_legacy(session, dry_run: bool) -> dict[str, int]:
    """Repair form/text/normalized; merge duplicate SurfaceForms (same key)."""
    stats = {
        "groups_processed": 0,
        "duplicate_nodes_removed": 0,
        "keeper_fields_updated": 0,
        "skipped_empty_display": 0,
        "neo4j_errors": 0,
    }
    rows = list(session.run(_FETCH_ALL))
    nodes: list[dict[str, Any]] = []
    for row in rows:
        rels = _clean_rels(row["rels"])
        display = (row["form"] or row["text"] or "").strip()
        expected = normalize_surface(display) if display else ""
        nodes.append(
            {
                "eid": row["eid"],
                "norm": row["normalized"],
                "form": row["form"],
                "text": row["text"],
                "display": display,
                "expected": expected,
                "rels": rels,
            }
        )

    groups: dict[str, list] = defaultdict(list)
    for n in nodes:
        if not n["expected"]:
            stats["skipped_empty_display"] += 1
            continue
        groups[n["expected"]].append(n)

    def pick_keeper(members: list) -> Any:
        def score(m: dict) -> tuple:
            right = 1 if m["norm"] == m["expected"] else 0
            return (right, len(m["rels"]))

        return max(members, key=score)

    for _expected_norm, members in groups.items():
        stats["groups_processed"] += 1
        keeper = pick_keeper(members)
        rest = [m for m in members if m["eid"] != keeper["eid"]]
        form_val = (keeper["form"] or keeper["text"] or keeper["display"]).strip()

        if dry_run:
            if rest:
                stats["duplicate_nodes_removed"] += len(rest)
            if (
                keeper["norm"] != keeper["expected"]
                or keeper["text"]
                or rest
                or not keeper["form"]
            ):
                stats["keeper_fields_updated"] += 1
            continue

        try:
            session.run(
                _UPDATE_SF_FIELDS,
                eid=keeper["eid"],
                norm=keeper["expected"],
                form=form_val,
            )
            for m in rest:
                for rel in m["rels"]:
                    session.run(
                        _MERGE_REL_BY_KEEPER_ID,
                        keep_eid=keeper["eid"],
                        cid=rel["cid"],
                        conf=float(rel.get("conf") or 1.0),
                        prov=rel.get("prov") or "surface-form-audit-merge",
                    )
                session.run(_DELETE_SF_BY_ID, eid=m["eid"])
                stats["duplicate_nodes_removed"] += 1
            stats["keeper_fields_updated"] += 1
        except Exception:
            stats["neo4j_errors"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Full SurfaceForm audit (Neo4j)")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Repair normalized/form/text and merge duplicate SurfaceForm nodes",
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="DETACH DELETE SurfaceForm nodes with no MAPS_TO (use with care)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --fix, report counts only without writing",
    )
    args = parser.parse_args()

    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as session:
        report = collect_audit(session)
        if args.fix:
            fix_stats = fix_normalized_and_legacy(session, dry_run=args.dry_run)
            report["fix_stats"] = fix_stats
            if args.delete_orphans and not args.dry_run:
                del_rows = session.run(_DELETE_ORPHAN)
                report["orphans_deleted"] = del_rows.single()["deleted"]
            elif args.delete_orphans:
                report["orphans_deleted"] = "dry_run_no_delete"
            if not args.dry_run:
                report["post_fix_summary"] = collect_audit(session)["summary"]

    driver.close()

    report["needs_clinical_review"] = {
        "bad_semantic_tag_count": report["summary"]["bad_semantic_tag_hits"],
        "multi_mapped_count": report["summary"]["multi_mapped_forms"],
        "note": (
            "After --fix, duplicate SurfaceForms with the same normalized key are "
            "merged; if they pointed at different concepts, the keeper may now have "
            "multiple MAPS_TO edges. Use POST /terminology/surface-forms/deduplicate "
            "or manual review to keep the best single target per form."
        ),
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    s = report["summary"]
    print("Surface form full audit")
    print("=" * 60)
    print(f"  Nodes total:              {s['surface_form_nodes_total']}")
    print(f"  With MAPS_TO:             {s['surface_forms_with_any_mapping']}")
    print(f"  Orphans (no MAPS_TO):     {s['orphans_no_maps_to']}")
    print(f"  Missing normalized:       {s['missing_normalized']}")
    print(f"  Normalized mismatch:      {s['normalized_mismatch']}")
    print(f"  Legacy text-only:         {s['legacy_text_only']}")
    print(f"  Bad semantic tag:         {s['bad_semantic_tag_hits']}")
    print(f"  Inactive concept:         {s['inactive_concept_hits']}")
    print(f"  Multi-mapped forms:       {s['multi_mapped_forms']}")
    print(f"  Low confidence (<0.7):    {s['low_confidence_edges']}")
    ncr = report.get("needs_clinical_review", {})
    if ncr.get("bad_semantic_tag_count") or ncr.get("multi_mapped_count"):
        print("\n  Needs clinical / curator review (see report JSON):")
        print(f"    Bad semantic tag rows:  {ncr.get('bad_semantic_tag_count', 0)}")
        print(f"    Multi-mapped forms:     {ncr.get('multi_mapped_count', 0)}")
    print(f"\n  Report: {REPORT_PATH}")
    if args.fix:
        print(f"\n  Fix stats: {report.get('fix_stats', {})}")
        if "post_fix_summary" in report:
            print(f"  Post-fix summary: {report['post_fix_summary']}")


if __name__ == "__main__":
    main()
