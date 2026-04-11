"""End-to-end check: IS_A expansion per subdomain vs what encounters actually contain."""

from __future__ import annotations
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

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

DOMAIN_ID = "cancer_audit"

_Q_VALUESETS = (
    "MATCH (d:AuditDomain {id: $domain_id})-[:HAS_SUBDOMAIN]->(v:ValueSet) "
    "RETURN v.id AS id, v.rawJson AS raw_json, v.milestoneType AS mt"
)

_Q_ISA_EXPANSION = (
    "MATCH (ancestor:Concept)<-[:IS_A*1..5]-(d:Concept) "
    "WHERE ancestor.id IN $ids AND d.active = true "
    "RETURN ancestor.id AS parent_id, d.id AS child_id, "
    "       coalesce(d.preferredTerm, d.fsn, d.id) AS display"
)

# Which encounter concepts in the graph are NOT covered by the expanded set?
_Q_UNCOVERED = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
WHERE NOT toString(c.conceptId) IN $covered_ids
  AND (c.semanticTag IN ['Disease', 'Clinical_finding', 'Procedure', 'Situation'])
  AND (
    toLower(c.name) CONTAINS 'cancer' OR
    toLower(c.name) CONTAINS 'malignant' OR
    toLower(c.name) CONTAINS 'carcinoma' OR
    toLower(c.name) CONTAINS 'neoplasm' OR
    toLower(c.name) CONTAINS 'fast track' OR
    toLower(c.name) CONTAINS 'fast-track' OR
    toLower(c.name) CONTAINS 'two week' OR
    toLower(c.name) CONTAINS '2ww' OR
    toLower(c.name) CONTAINS 'suspected' AND toLower(c.name) CONTAINS 'clinic'
  )
RETURN DISTINCT c.conceptId AS conceptId, c.name AS name, c.semanticTag AS tag,
       count(DISTINCT e) AS enc_count
ORDER BY enc_count DESC
LIMIT 30
"""


def main() -> None:
    kg = KnowledgeGraphClient()
    pg = PatientGraphClient()

    try:
        # Load ValueSets
        rows = kg.run(_Q_VALUESETS, domain_id=DOMAIN_ID)
        valuesets: dict = {}
        for r in rows or []:
            raw = r.get("raw_json")
            if not raw:
                continue
            vs = json.loads(raw) if isinstance(raw, str) else raw
            vs["_milestone_type"] = r.get("mt") or vs.get("milestoneType")
            valuesets[r["id"]] = vs

        # Per-subdomain expansion
        all_expanded_ids: set[str] = set()
        subdomain_coverage: dict[str, dict] = {}

        for vs_id, vs in valuesets.items():
            mt = vs.get("_milestone_type", "")
            if mt not in (
                "diagnosis",
                "referral",
                "specialist_visit",
                "benign_closure",
            ):
                continue

            parent_ids = [
                c.get("code", "")
                for inc in (vs.get("compose") or {}).get("include") or []
                for c in inc.get("concept") or []
                if c.get("code")
            ]
            if not parent_ids:
                continue

            desc_rows = kg.run(_Q_ISA_EXPANSION, ids=parent_ids)
            desc_ids = {str(r["child_id"]) for r in (desc_rows or [])}
            all_ids = set(str(p) for p in parent_ids) | desc_ids

            all_expanded_ids.update(all_ids)
            subdomain_coverage[vs_id] = {
                "milestone_type": mt,
                "parent_count": len(parent_ids),
                "parent_ids": parent_ids,
                "descendant_count": len(desc_ids),
                "total_ids": len(all_ids),
            }

            print(f"  {vs_id}")
            print(f"    milestone_type : {mt}")
            print(f"    parent concepts: {len(parent_ids)}")
            print(f"    IS_A descendants (depth<=5): {len(desc_ids)}")
            print(f"    TOTAL in bucket: {len(all_ids)}")
            print(f"    UI reports: +N variants (check UI against above)")

            # Show specific descendants for small domains
            if len(desc_ids) <= 20:
                for r in desc_rows or []:
                    print(f"      -> {r['child_id']}  {r.get('display','')[:70]}")
            print()

        print("=" * 70)
        print(f"All expanded IDs across milestone domains: {len(all_expanded_ids)}")

        print()
        print(
            "=== Cancer/referral/clinic concepts in patient encounters NOT covered ==="
        )
        with pg.session() as s:
            uncovered = s.run(_Q_UNCOVERED, covered_ids=list(all_expanded_ids)).data()
            if not uncovered:
                print("  None -- all relevant encounter concepts are covered!")
            else:
                print(f"  {'conceptId':<20} {'enc_count':>5}  name")
                print("  " + "-" * 90)
                for r in uncovered:
                    print(
                        f"  {str(r['conceptId']):<20} {r['enc_count']:>5}  {str(r['name'])[:70]}"
                    )

    finally:
        kg.close()
        pg.close()


if __name__ == "__main__":
    main()
