"""Read place of presentation, referral route, and first presentation details
for the 17 unknown-type completed episodes."""

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


def main() -> None:
    client = PatientGraphClient()

    rows = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "RETURN ep.patient_id AS pid, "
        "       ep.referral_date AS ref_date, "
        "       ep.referral_route AS referral_route, "
        "       ep.place_of_presentation AS place, "
        "       ep.first_presentation_date AS fp_date, "
        "       ep.presenting_complaint AS complaint, "
        "       ep.specialist_seen AS specialist_seen, "
        "       ep.specialist_visit_date AS spec_date "
        "ORDER BY ep.patient_id"
    )

    print(f"Unknown completed episodes: {len(rows)}")
    print()
    print(
        f"{'Patient':<15} {'Ref Date':<12} {'Route':<18} {'Place of Presentation':<35} {'Complaint'}"
    )
    print("-" * 110)

    place_counts: dict[str, int] = {}
    route_counts: dict[str, int] = {}

    for r in rows:
        pid = str(r.get("pid", ""))
        ref = str(r.get("ref_date") or "no-ref")
        route = str(r.get("referral_route") or "unknown")
        place = str(r.get("place") or "not set")
        complaint = str(r.get("complaint") or "")[:40]
        spec = r.get("specialist_seen")
        spec_date = str(r.get("spec_date") or "")

        place_counts[place] = place_counts.get(place, 0) + 1
        route_counts[route] = route_counts.get(route, 0) + 1

        spec_flag = f" [specialist {spec_date}]" if spec else ""
        print(f"{pid:<15} {ref:<12} {route:<18} {place:<35} {complaint}{spec_flag}")

    print()
    print("=== Place of Presentation breakdown ===")
    for place, count in sorted(place_counts.items(), key=lambda x: -x[1]):
        print(f"  {place:<40} {count}")

    print()
    print("=== Referral Route breakdown ===")
    for route, count in sorted(route_counts.items(), key=lambda x: -x[1]):
        print(f"  {route:<25} {count}")

    # Also look up what the first-presentation encounters contain for these patients
    print()
    print("=== First presentation encounter details ===")
    ep_rows = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.status = 'completed' AND ep.cancer_type = 'unknown' "
        "OPTIONAL MATCH (enc:Encounter)-[r:IS_PART_OF {milestone_type: 'first_presentation'}]->(ep) "
        "OPTIONAL MATCH (enc)-[:DOCUMENTS]->(c) "
        "RETURN ep.patient_id AS pid, "
        "       ep.referral_date AS ref_date, "
        "       collect(DISTINCT c.name)[..5] AS fp_concepts "
        "ORDER BY ep.patient_id"
    )
    for r in ep_rows:
        concepts = [c for c in (r.get("fp_concepts") or []) if c]
        if concepts:
            print(
                f"  Patient {r['pid']} ({r['ref_date']}): {', '.join(str(c) for c in concepts[:5])}"
            )

    client.close()


if __name__ == "__main__":
    main()
