"""Audit every SurfaceForm MAPS_TO edge written by guideline_config_loader.

Connects directly to the knowledge-graph Neo4j instance and:
  1. Fetches all MAPS_TO edges whose provenance = 'guideline_config_loader'.
  2. Flags each one:
       SITUATION   - target semantic_tag = 'situation'
       INACTIVE    - target concept active = false
       BROAD_MENTAL - target is 74732009 (Mental disorder) -- catch-all
       BROAD_NEOPLASM - target is a generic 'neoplasm' that should be specific
       PROCEDURE   - target is a procedure (may be legitimate; flag for review)
  3. Prints a full report and writes JSON to surface_form_gcl_audit.json.

Usage: python scripts/investigations/_audit_gcl_surface_forms.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from neo4j import GraphDatabase

OUTPUT = ROOT / "scripts" / "investigations" / "surface_form_gcl_audit.json"

kg_uri  = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI",      "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# -- Query: all GCL-provenance MAPS_TO edges ---------------------------------
_GCL_QUERY = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
RETURN
  sf.normalized   AS normalized,
  sf.form         AS form,
  sf.source       AS source,
  sf.status       AS status,
  c.id            AS concept_id,
  c.fsn           AS concept_fsn,
  c.semantic_tag  AS semantic_tag,
  c.active        AS concept_active,
  m.confidence    AS confidence,
  m.provenance    AS provenance
ORDER BY sf.form
"""

# -- Query: for each flagged form, also fetch its OTHER MAPS_TO edges --------
_OTHER_MAPPINGS = """
MATCH (sf:SurfaceForm {normalized: $norm})-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance <> 'guideline_config_loader'
RETURN c.id AS concept_id, c.fsn AS fsn,
       c.semantic_tag AS semantic_tag, c.active AS active,
       m.confidence AS confidence, m.provenance AS provenance
ORDER BY m.confidence DESC
"""

# Known over-broad catch-all concept IDs
_BROAD_IDS = {
    "74732009",   # Mental disorder (disorder)
    "128462008",  # Metastatic malignant neoplasm (disorder)
    "372130007",  # Malignant neoplasm of skin (disorder)
    "267004000",  # History of musculoskeletal disease (situation)
    "275552000",  # History of kidney disease (situation)
    "308064009",  # History of cerebrovascular disease (situation)
    "270473001",  # History of chronic obstructive airway disease (situation)
    "472961001",  # History of disorder of connective tissue (situation)
    "161535005",  # History of liver disease (situation)
    "161465002",  # History of dementia (situation)
}


def _flags(row: dict) -> list[str]:
    flags = []
    tag = (row.get("semantic_tag") or "").lower()
    cid = str(row.get("concept_id") or "")

    if not row.get("concept_active"):
        flags.append("INACTIVE")
    if tag == "situation":
        flags.append("SITUATION")
    if cid in _BROAD_IDS:
        flags.append("BROAD_CATCH_ALL")
    if tag == "procedure":
        flags.append("PROCEDURE")
    return flags


def main() -> None:
    print(f"Connecting: {kg_uri}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    with driver.session() as s:
        gcl_rows = [dict(r) for r in s.run(_GCL_QUERY)]

    print(f"GCL MAPS_TO edges: {len(gcl_rows)}")

    # Fetch alternative mappings for any flagged row
    flagged = []
    clean = []
    for row in gcl_rows:
        fs = _flags(row)
        if fs:
            row["flags"] = fs
            flagged.append(row)
        else:
            row["flags"] = []
            clean.append(row)

    # For flagged rows, fetch what else the surface form maps to
    norms_to_check = {r["normalized"] for r in flagged}
    alternatives: dict[str, list[dict]] = {}
    with driver.session() as s:
        for norm in norms_to_check:
            alts = [dict(r) for r in s.run(_OTHER_MAPPINGS, norm=norm)]
            alternatives[norm] = alts

    driver.close()

    # Count flags
    flag_counts: dict[str, int] = {}
    for r in flagged:
        for f in r["flags"]:
            flag_counts[f] = flag_counts.get(f, 0) + 1

    # Print summary
    print()
    print("=" * 70)
    print("GCL SURFACE FORM AUDIT")
    print("=" * 70)
    print(f"  Total GCL edges : {len(gcl_rows)}")
    print(f"  Flagged         : {len(flagged)}")
    print(f"  Clean           : {len(clean)}")
    print()
    print("  Flag breakdown:")
    for f, n in sorted(flag_counts.items(), key=lambda x: -x[1]):
        print(f"    {f:<25s} {n}")

    # Group by flag priority for readability
    for priority_flag in ("BROAD_CATCH_ALL", "SITUATION", "INACTIVE", "PROCEDURE"):
        subset = [r for r in flagged if priority_flag in r["flags"]]
        if not subset:
            continue
        print()
        print(f"-- {priority_flag} ({len(subset)}) " + "-" * 50)
        for r in subset:
            norm = r["normalized"]
            alts = alternatives.get(norm, [])
            alt_str = ""
            if alts:
                best = alts[0]
                alt_str = (
                    f"  --> better: {best['concept_id']} | {best['fsn']}"
                    f" conf={best['confidence']} [{best['provenance']}]"
                )
            print(
                f"  {r['form']!r}\n"
                f"    GCL maps to: {r['concept_id']} | {r['concept_fsn']}"
                f" ({r['semantic_tag']}) active={r['concept_active']}\n"
                f"    conf={r['confidence']}{alt_str}"
            )

    # Write JSON
    report = {
        "total_gcl": len(gcl_rows),
        "flagged": flagged,
        "clean_count": len(clean),
        "flag_counts": flag_counts,
        "alternatives": {k: v for k, v in alternatives.items()},
    }
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"\nJSON report: {OUTPUT}")


if __name__ == "__main__":
    main()
