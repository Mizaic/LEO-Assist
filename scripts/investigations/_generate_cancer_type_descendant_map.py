"""Generate an expanded _SITE_BY_CONCEPT_ID mapping for all IS_A descendants
of the cancer_types ValueSet base concepts.

The anchor detector's IS_A expansion (up to 5 levels) injects SNOMED subtypes
into the diagnosis bucket.  When patient graph nodes store c.name as a raw
numeric string (unresolved), episode_builder falls back to concept_id lookup.
This script builds the descendant -> site key mapping and writes the output.

Usage:
  python scripts/investigations/_generate_cancer_type_descendant_map.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient

# Site key for each of the 46 base cancer_types concept IDs.
# Matches _SITE_BY_CONCEPT_ID additions made in episode_builder.py.
_BASE_CONCEPT_SITE: dict[str, str] = {
    "372063002": "brain",
    "363461003": "other",
    "255056009": "head_and_neck",
    "363358000": "lung",
    "363432004": "lung",
    "363435002": "other",
    "363494000": "lung",
    "363495004": "leukaemia",
    "269457002": "oesophageal",
    "255080008": "stomach",
    "363403002": "small_intestine",
    "363508008": "colorectal",
    "93870000": "liver",
    "363415003": "gallbladder",
    "363418001": "pancreatic",
    "93849006": "renal",
    "363458004": "bladder",
    "93689003": "bladder",
    "399068003": "prostate",
    "363459007": "bladder",
    "363460002": "other",
    "236740006": "other",
    "363516004": "other",
    "363449006": "testicular",
    "188235006": "other",
    "363454002": "other",
    "363453008": "other",
    "363443007": "ovarian",
    "363444001": "ovarian",
    "371972005": "endometrial",
    "363354003": "cervical",
    "363445000": "vulval",
    "609519004": "endometrial",
    "363367000": "vulval",
    "254837009": "breast",
    "371982006": "non_site_specific",
    "372130007": "melanoma",
    "126598008": "sarcoma",
    "428281000": "sarcoma",
    "310504009": "non_site_specific",
    "128462008": "non_site_specific",
    "399935008": "breast",
    "447137006": "breast",
    "32102001": "breast",
    "716917000": "breast",
    "716918005": "breast",
}

_ISA_QUERY = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id, "
    "       coalesce(d.preferredTerm, d.id) AS display"
)


def main() -> None:
    kg = KnowledgeGraphClient()
    parent_ids = list(_BASE_CONCEPT_SITE.keys())

    print(
        f"Querying IS_A descendants for {len(parent_ids)} base cancer type concepts..."
    )
    rows = kg.run(_ISA_QUERY, ids=parent_ids)
    kg.close()

    if not rows:
        print("No descendants found. Check KG connectivity and Concept node structure.")
        return

    descendant_map: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    by_parent: dict[str, int] = {}

    for row in rows:
        pid = str(row.get("parent_id") or "")
        cid = str(row.get("child_id") or "")
        if not pid or not cid:
            continue
        site_key = _BASE_CONCEPT_SITE.get(pid)
        if not site_key:
            continue
        by_parent[pid] = by_parent.get(pid, 0) + 1
        if cid in descendant_map and descendant_map[cid] != site_key:
            conflicts.setdefault(cid, [descendant_map[cid]]).append(site_key)
        else:
            descendant_map[cid] = site_key

    print(f"Total descendants found: {len(descendant_map)}")
    print(f"Conflicts (same child, multiple parents): {len(conflicts)}")
    if conflicts:
        print("  Note: conflicts resolved by last-write (less specific parent wins)")
    print()
    print("Top parent concepts by descendant count:")
    top = sorted(by_parent.items(), key=lambda x: x[1], reverse=True)[:10]
    for pid, cnt in top:
        site = _BASE_CONCEPT_SITE.get(pid, "?")
        print(f"  {pid} ({site}): {cnt} descendants")

    # Save full descendant map as JSON for review
    out_path = (
        ROOT
        / "scripts"
        / "investigations"
        / "output"
        / "cancer_type_descendant_map.json"
    )
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(descendant_map, f, indent=2, sort_keys=True)
    print(f"\nFull map written to {out_path}")

    # Check which of the unresolved concept IDs from the audit are in the map
    _UNRESOLVED_FROM_AUDIT = [
        "10743008",
        "363478007",
        "84229001",
        "68496003",
        "62315008",
        "254701007",
        "262285001",
    ]
    print("\nAudit unresolved IDs coverage:")
    for cid in _UNRESOLVED_FROM_AUDIT:
        site = descendant_map.get(cid)
        print(f"  {cid}: {'-> ' + site if site else 'NOT in descendant map'}")


if __name__ == "__main__":
    main()
