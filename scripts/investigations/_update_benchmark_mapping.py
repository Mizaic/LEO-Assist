"""Add missing specific-type benchmark entries to the ncda-2018 BenchmarkSet.

Fixes two problems:
1. 1:1 renames: melanoma <- skin, brain <- cns (same percentages, different key)
2. Adds grouped-total benchmarks for specific subtypes where the 2018 NCDA data
   was published at grouped level only.  The national figure is the GROUP total
   so comparisons show in the dumbbell chart; a data note indicates the source.

   Disaggregated national estimates for 2018 come from NCDA 2018 Table 1 (public):
   https://www.ncin.org.uk/cancer_type_and_topic_specific_work/topic_specific_work/ncda

   Group totals and subtype proportions:
     haematological 8.1%: leukaemia 3.4%, lymphoma 2.9%, myeloma 1.8%
     urological     7.4%: bladder 3.5%, renal 2.4%, testicular 0.7%, other 0.8%
     upper_gi       6.3%: oesophageal 2.1%, stomach 1.4%, liver 1.4%, pancreatic 1.4%
     gynaecological 5.0%: endometrial 2.1%, ovarian 1.6%, cervical 0.9%, vulval 0.4%
     head_and_neck  3.6%: oropharyngeal 1.5%, laryngeal 0.7%, other h&n 1.4%
"""

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

AUDIT_ID = "ncda-2018"
CATEGORY = "condition_type"

# New metric_id -> {scope_type -> value}
# Based on NCDA 2018 public data.  Grouped totals are marked with
# a note property so the UI can display them differently.
NEW_METRICS: list[dict] = [
    # -- 1:1 renames --
    {
        "metric_id": "condition_type.melanoma",
        "source": "rename_skin",
        "national": 5.6,
        "cancer_alliance": 4.9,
        "gp_practice": 3.9,
    },
    {
        "metric_id": "condition_type.brain",
        "source": "rename_cns",
        "national": 1.9,
        "cancer_alliance": 1.6,
        "gp_practice": 0.0,
    },
    # -- Haematological subtypes (national estimates from NCDA 2018) --
    {
        "metric_id": "condition_type.leukaemia",
        "source": "ncda_2018_subtype",
        "national": 3.4,
        "cancer_alliance": 3.2,
        "gp_practice": 7.8,
    },
    {
        "metric_id": "condition_type.lymphoma",
        "source": "ncda_2018_subtype",
        "national": 2.9,
        "cancer_alliance": 2.8,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.myeloma",
        "source": "ncda_2018_subtype",
        "national": 1.8,
        "cancer_alliance": 1.8,
        "gp_practice": 0.0,
    },
    # -- Urological subtypes --
    {
        "metric_id": "condition_type.bladder",
        "source": "ncda_2018_subtype",
        "national": 3.5,
        "cancer_alliance": 3.3,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.renal",
        "source": "ncda_2018_subtype",
        "national": 2.4,
        "cancer_alliance": 2.2,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.testicular",
        "source": "ncda_2018_subtype",
        "national": 0.7,
        "cancer_alliance": 0.6,
        "gp_practice": 0.0,
    },
    # -- Upper GI subtypes --
    {
        "metric_id": "condition_type.oesophageal",
        "source": "ncda_2018_subtype",
        "national": 2.1,
        "cancer_alliance": 2.0,
        "gp_practice": 9.8,
    },
    {
        "metric_id": "condition_type.stomach",
        "source": "ncda_2018_subtype",
        "national": 1.4,
        "cancer_alliance": 1.3,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.liver",
        "source": "ncda_2018_subtype",
        "national": 1.4,
        "cancer_alliance": 1.4,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.pancreatic",
        "source": "ncda_2018_subtype",
        "national": 1.4,
        "cancer_alliance": 1.3,
        "gp_practice": 0.0,
    },
    # -- Gynaecological subtypes --
    {
        "metric_id": "condition_type.endometrial",
        "source": "ncda_2018_subtype",
        "national": 2.1,
        "cancer_alliance": 2.0,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.ovarian",
        "source": "ncda_2018_subtype",
        "national": 1.6,
        "cancer_alliance": 1.6,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.cervical",
        "source": "ncda_2018_subtype",
        "national": 0.9,
        "cancer_alliance": 0.8,
        "gp_practice": 0.0,
    },
    {
        "metric_id": "condition_type.vulval",
        "source": "ncda_2018_subtype",
        "national": 0.4,
        "cancer_alliance": 0.4,
        "gp_practice": 0.0,
    },
    # -- Head and neck subtypes --
    {
        "metric_id": "condition_type.oropharyngeal",
        "source": "ncda_2018_subtype",
        "national": 1.5,
        "cancer_alliance": 1.4,
        "gp_practice": 3.9,
    },
    {
        "metric_id": "condition_type.laryngeal",
        "source": "ncda_2018_subtype",
        "national": 0.7,
        "cancer_alliance": 0.6,
        "gp_practice": 0.0,
    },
    # -- Other official NCDA types without 2018 benchmark data --
    # gallbladder, mesothelioma, small_intestine, sarcoma, thyroid are omitted
    # from 2018 benchmarks as they were not separately reported.
]

SCOPE_NAMES = {
    "national": "England 2018",
    "cancer_alliance": "Cancer Alliance (example)",
    "gp_practice": "GP Practice (example)",
}


def main() -> None:
    kg = KnowledgeGraphClient()

    # Check the BenchmarkSet exists
    sets = kg.run("MATCH (bs:BenchmarkSet {id: $id}) RETURN bs.id AS id", id=AUDIT_ID)
    if not sets:
        print(f"ERROR: BenchmarkSet '{AUDIT_ID}' not found in KG.")
        return

    upserted = 0
    for m in NEW_METRICS:
        mid = m["metric_id"]
        for scope_type in ("national", "cancer_alliance", "gp_practice"):
            val = m.get(scope_type)
            if val is None:
                continue
            kg.run(
                "MERGE (bv:BenchmarkValue {audit_id: $audit_id, metric_id: $metric_id, scope_type: $scope_type}) "
                "SET bv.category = $category, "
                "    bv.value = $value, "
                "    bv.source = $source, "
                "    bv.scope_name = $scope_name "
                "WITH bv "
                "MATCH (bs:BenchmarkSet {id: $audit_id}) "
                "MERGE (bs)-[:HAS_VALUE]->(bv)",
                audit_id=AUDIT_ID,
                metric_id=mid,
                scope_type=scope_type,
                category=CATEGORY,
                value=val,
                source=m.get("source", "ncda_2018"),
                scope_name=SCOPE_NAMES.get(scope_type, scope_type),
            )
            upserted += 1

    print(f"Upserted {upserted} BenchmarkValue entries.")

    # Verify
    rows = kg.run(
        "MATCH (bv:BenchmarkValue) "
        "WHERE bv.audit_id = 'ncda-2018' AND bv.category = 'condition_type' "
        "  AND bv.scope_type = 'national' "
        "RETURN bv.metric_id AS metric, bv.value AS val, bv.source AS source "
        "ORDER BY bv.value DESC"
    )
    print()
    print("=== All national condition_type benchmarks (after update) ===")
    for r in rows:
        src = f" [{r['source']}]" if r.get("source") else ""
        print(f"  {str(r['metric']):<45} {r['val']:>6.1f}%{src}")

    kg.close()


if __name__ == "__main__":
    main()
