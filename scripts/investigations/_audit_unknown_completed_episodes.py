"""Audit unknown-cancer-type completed episodes.

Queries the graph to find the exact concept IDs and names driving
cancer_type = 'unknown' in completed EpisodeOfCare nodes.

Outputs two files:
  scripts/investigations/output/unknown_completed_diag_anchors.json
  scripts/investigations/output/unknown_completed_summary.json

Usage:
  python scripts/investigations/_audit_unknown_completed_episodes.py
"""

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

from libs.neo4j_client.client import PatientGraphClient

_OUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def main() -> None:
    client = PatientGraphClient()

    # -- Step 1: find all unknown completed episodes -------------------------
    unknown_rows = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "RETURN ep.episode_id AS episode_id, ep.patient_id AS patient_id "
        "LIMIT 200"
    )
    ep_ids = [r["episode_id"] for r in unknown_rows]
    print(f"Unknown completed episodes found: {len(ep_ids)}")

    if not ep_ids:
        print("Nothing to audit.")
        return

    # -- Step 2: find diagnosis-bucket encounters for those episodes ---------
    # IS_PART_OF edges with milestone_type 'diagnosis' or 'diagnosis_confirmed'
    anchor_rows = client.run(
        "UNWIND $ep_ids AS eid "
        "MATCH (enc:Encounter)-[r:IS_PART_OF]->(ep:EpisodeOfCare {episode_id: eid}) "
        "WHERE r.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] "
        "OPTIONAL MATCH (enc)-[:DOCUMENTS]->(c) "
        "RETURN eid AS episode_id, "
        "       toString(enc.id) AS encounter_id, "
        "       r.milestone_type AS milestone_type, "
        "       toString(c.conceptId) AS concept_id, "
        "       c.name AS concept_name "
        "ORDER BY eid, encounter_id",
        ep_ids=ep_ids,
    )

    print(f"Diagnosis anchor rows found: {len(anchor_rows)}")

    # -- Step 3: aggregate concept_id frequency ------------------------------
    concept_counts: dict[str, dict] = {}
    for row in anchor_rows:
        cid = str(row.get("concept_id") or "")
        cname = str(row.get("concept_name") or "")
        if not cid or cid == "None":
            continue
        if cid not in concept_counts:
            # Check if concept name looks like a raw ID (unresolved)
            name_is_numeric = cname.isdigit() or (
                cname and cname == cid
            )
            concept_counts[cid] = {
                "concept_id": cid,
                "concept_name": cname,
                "name_is_numeric": name_is_numeric,
                "episode_count": 0,
                "encounter_count": 0,
            }
        concept_counts[cid]["episode_count"] += 1
        concept_counts[cid]["encounter_count"] += 1

    sorted_concepts = sorted(
        concept_counts.values(),
        key=lambda x: x["episode_count"],
        reverse=True,
    )

    print("\nTop concept IDs in diagnosis anchors of unknown-type completed episodes:")
    print(f"{'concept_id':<15} {'episodes':>8}  {'name_numeric':>12}  concept_name")
    print("-" * 80)
    for entry in sorted_concepts[:30]:
        flag = "YES (unresolved)" if entry["name_is_numeric"] else ""
        print(
            f"{entry['concept_id']:<15} "
            f"{entry['episode_count']:>8}  "
            f"{flag:>16}  "
            f"{str(entry['concept_name'])[:50]}"
        )

    # -- Step 4: episodes with NO diagnosis anchor at all --------------------
    no_anchor_eps = [
        r["episode_id"]
        for r in unknown_rows
        if r["episode_id"]
        not in {row["episode_id"] for row in anchor_rows}
    ]
    print(f"\nEpisodes with NO diagnosis anchor linked: {len(no_anchor_eps)}")
    if no_anchor_eps:
        print("  (These likely completed via letter-inference or treatment signal)")
        for eid in no_anchor_eps[:10]:
            print(f"  {eid}")

    # -- Step 5: save outputs ------------------------------------------------
    os.makedirs(_OUT_DIR, exist_ok=True)

    summary = {
        "total_unknown_completed": len(ep_ids),
        "episodes_with_no_diagnosis_anchor": len(no_anchor_eps),
        "distinct_concept_ids_in_anchors": len(concept_counts),
        "top_concepts": sorted_concepts[:50],
    }

    summary_path = os.path.join(_OUT_DIR, "unknown_completed_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to {summary_path}")

    detail_path = os.path.join(_OUT_DIR, "unknown_completed_diag_anchors.json")
    with open(detail_path, "w") as f:
        json.dump(anchor_rows, f, indent=2, default=str)
    print(f"Full anchor detail written to {detail_path}")

    client.close()


if __name__ == "__main__":
    main()
