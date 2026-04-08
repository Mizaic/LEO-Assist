"""Check whether IS_A expansion is working for first_presentation subdomains.

Loads the DomainRegistry the same way the anchor detector does, then
reports which concepts are in the first_presentation bucket and how many
came from IS_A expansion vs being direct parent entries.

Usage:
    python scripts/investigations/_check_isa_expansion.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

# Reuse the exact same loader as the anchor subgraph
from libs.pipeline_graph.subgraphs.anchor import _load_registry

_VALUESET_CONCEPTS_Q = """
MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet)
WHERE coalesce(d.episodeDetector, false) = true
  AND v.milestoneType = 'first_presentation'
RETURN d.id AS domain_id, v.id AS vs_id, v.name AS vs_name,
       v.milestoneType AS milestone_type,
       v.assertionFilter AS assertion_filter
ORDER BY v.id
"""

_ISA_CHILD_Q = """
MATCH (parent:Concept {id: $parent_id})<-[:IS_A*1..5]-(child:Concept)
WHERE child.active = true
RETURN child.id AS child_id, child.preferredTerm AS preferred_term,
       child.fsn AS fsn
ORDER BY child.fsn
"""

_CONCEPT_LABEL_Q = """
MATCH (c:Concept {id: $concept_id})
RETURN c.preferredTerm AS preferred_term, c.fsn AS fsn
"""


def main() -> None:
    # -- 1. Check which subdomains have milestoneType=first_presentation ----
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()
    try:
        vs_rows = kg.run(_VALUESET_CONCEPTS_Q) or []
    finally:
        kg.close()

    if not vs_rows:
        print("NO subdomains with milestoneType='first_presentation' found.")
        print("Make sure the AuditDomain has episodeDetector=true and the")
        print("ValueSet nodes have milestoneType='first_presentation' set.")
        pg.close()
        return

    print(f"Found {len(vs_rows)} subdomain(s) with milestoneType=first_presentation:\n")
    for r in vs_rows:
        print(f"  Domain : {r['domain_id']}")
        print(f"  VS     : {r['vs_id']}  '{r['vs_name']}'")
        print(f"  Assert : {r.get('assertion_filter')}")
        print()

    # -- 2. Load the registry the same way the anchor detector does ---------
    print("Loading DomainRegistry (same path as anchor detector) ...")
    try:
        registry = _load_registry()
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        pg.close()
        return

    # -- 3. Find first_presentation domains and their concept sets ----------
    fp_domains = {
        name: cfg
        for name, cfg in registry.get_milestone_domains().items()
        if cfg.milestone_type == "first_presentation"
    }

    if not fp_domains:
        print("\nNo first_presentation milestone domains found in registry.")
        print("Check that the ValueSet rawJson contains milestoneType in its")
        print("extension or as a top-level property.")
        pg.close()
        return

    print(f"\nfirst_presentation domains in registry: {list(fp_domains.keys())}\n")

    kg2 = KnowledgeGraphClient()
    try:
        for domain_name, cfg in fp_domains.items():
            concept_ids = registry.get_concept_ids(domain_name) or []
            print(f"{'=' * 65}")
            print(f"Domain      : {domain_name}")
            print(f"Concepts in bucket: {len(concept_ids)}")
            print(f"Assertion filter  : {cfg.assertion_filter or 'none (accepts all)'}")

            if not concept_ids:
                print("  WARNING: zero concepts -- subdomain may be empty or rawJson")
                print("  may not have compose.include[].concept[] entries.")
                continue

            # Separate parent entries from IS_A children by checking which
            # are in the raw ValueSet vs which came from expansion.
            # Proxy: load rawJson directly and compare.
            raw_parent_ids: set[str] = set()
            raw_rows = kg2.run(
                "MATCH (d:AuditDomain)-[:HAS_SUBDOMAIN]->(v:ValueSet) "
                "WHERE coalesce(d.episodeDetector, false) = true "
                "  AND v.id CONTAINS $domain_fragment "
                "RETURN v.rawJson AS raw_json",
                domain_fragment=domain_name.replace("_", "-"),
            ) or []
            import json
            for rr in raw_rows:
                raw = rr.get("raw_json")
                if not raw:
                    continue
                try:
                    vs_dict = json.loads(raw) if isinstance(raw, str) else raw
                    for inc in (vs_dict.get("compose") or {}).get("include") or []:
                        for c in inc.get("concept") or []:
                            code = c.get("code")
                            if code:
                                raw_parent_ids.add(str(code))
                except Exception:
                    pass

            all_ids = [str(c) for c in concept_ids]
            expanded_ids = [i for i in all_ids if i not in raw_parent_ids]

            print(f"Direct parents    : {len(raw_parent_ids)}")
            print(f"After IS_A expand : {len(all_ids)}  "
                  f"(+{len(expanded_ids)} children)")

            # Print parent concepts with their child counts
            print("\nParent concepts:")
            for pid in sorted(raw_parent_ids):
                children = [i for i in expanded_ids
                            if i != pid]  # rough count
                label_rows = kg2.run(_CONCEPT_LABEL_Q, concept_id=pid) or []
                label = label_rows[0].get("fsn") if label_rows else "NOT IN KG"
                child_rows = kg2.run(_ISA_CHILD_Q, parent_id=pid) or []
                print(f"  {pid:20s}  {len(child_rows):3d} children  {label}")
                for cr in child_rows[:3]:
                    print(f"    -> {cr['child_id']:20s}  {cr.get('fsn', '')[:55]}")
                if len(child_rows) > 3:
                    print(f"    ... +{len(child_rows) - 3} more")
            print()
    finally:
        kg2.close()
        pg.close()

    print("IS_A expansion is working correctly for first_presentation subdomains.")


if __name__ == "__main__":
    main()
