"""Verify all audit page data after fixes."""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter
from datetime import date as _date

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.neo4j_client.client import PatientGraphClient

_CLOSED = {
    "closed", "completed", "merged", "excluded",
    "closed_benign", "closed_related", "closed_phantom",
    "stale_no_diagnosis", "stale_post_specialist",
}


def main() -> None:
    c = PatientGraphClient()
    try:
        # Basic episode props
        eps = c.run("""
            MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
            RETURN ep.status AS status, ep.cancer_type AS ct,
                   ep.referral_route AS route, ep.place_of_presentation AS place,
                   ep.end_date AS end_date, ep.referral_date AS ref_date,
                   ep.inferred_outcome AS io, ep.inferred_outcome_date AS iod,
                   p.gender AS gender, p.birthDate AS dob
        """)

        total = len(eps)
        active = sum(1 for e in eps if e["status"] not in _CLOSED)

        print(f"=== /care/audit data verification ===")
        print(f"  Total pathways (HAS_EPISODE_OF_CARE) : {total}")
        print(f"  Active (in_progress)                 : {active}")

        # Cancer type
        ct_counts = Counter(e["ct"] for e in eps if e["ct"] and e["ct"] != "unknown")
        print(f"\n  Cancer type breakdown ({sum(ct_counts.values())} episodes with known type):")
        for ct, n in ct_counts.most_common():
            print(f"    {ct:<25} {n:4d}  ({100*n//total}%)")

        # Referral route
        route_counts = Counter(e["route"] or "Not recorded" for e in eps)
        print(f"\n  Referral routes:")
        for r, n in route_counts.most_common():
            print(f"    {r:<25} {n:4d}")

        # Place of presentation
        place_counts = Counter(e["place"] or "Not recorded" for e in eps)
        print(f"\n  Place of presentation:")
        for p, n in place_counts.most_common():
            print(f"    {p:<25} {n:4d}")

        # Confirmed count (effective diag date)
        confirmed = 0
        for e in eps:
            if e["status"] == "completed" and e["end_date"]:
                confirmed += 1
            elif e["io"] == "cancer" and e["iod"]:
                confirmed += 1
        print(f"\n  Confirmed cancers (effective_diag_date): {confirmed}")
        print(f"    completed with end_date: {sum(1 for e in eps if e['status']=='completed' and e['end_date'])}")
        print(f"    inferred cancer: {sum(1 for e in eps if e['io']=='cancer' and e['iod'])}")

        # Demographics - gender
        gender_counts = Counter(e["gender"] or "Unknown" for e in eps)
        print(f"\n  Demographics - gender (from Patient):")
        for g, n in gender_counts.most_common():
            print(f"    {g:<15} {n:4d}")

        # PCI/DI intervals
        di_vals = []
        pci_vals = []
        for e in eps:
            ref = e["ref_date"]
            end = None
            if e["status"] == "completed" and e["end_date"]:
                end = str(e["end_date"])
            elif e["io"] == "cancer" and e["iod"]:
                end = str(e["iod"])
            if ref and end:
                try:
                    d = (_date.fromisoformat(str(end)) - _date.fromisoformat(str(ref))).days
                    if d >= 0:
                        di_vals.append(d)
                except Exception:
                    pass
            # PCI = 0 since no first_presentation_date separate from referral_date
            if ref:
                pci_vals.append(0)

        di_vals.sort()
        def median(v):
            if not v: return None
            n = len(v)
            return v[n//2] if n%2 else (v[n//2-1]+v[n//2])/2

        print(f"\n  Intervals:")
        print(f"    PCI (first presentation to referral): 0 days (fallback = referral date, n={len(pci_vals)})")
        print(f"    DI  (referral to diagnosis):          {median(di_vals):.0f} days (n={len(di_vals)})" if di_vals else "    DI: no data")

        # Consultations - via HAS_ENCOUNTER in window
        sample = c.run("""
            MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare)
            WHERE ep.referral_date IS NOT NULL
            WITH p, ep LIMIT 10
            OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)
              WHERE enc.date >= ep.referral_date
              AND enc.date <= coalesce(ep.end_date, ep.referral_date + duration('P180D'))
            RETURN ep.episode_id AS ep, count(enc) AS consult_count
        """)
        consult_vals = [r["consult_count"] for r in sample]
        print(f"\n  Consultations (sample 10 episodes via HAS_ENCOUNTER in window):")
        print(f"    Counts: {consult_vals}")
        print(f"    Mean: {sum(consult_vals)/len(consult_vals):.1f}" if consult_vals else "    No data")

    finally:
        c.close()


if __name__ == "__main__":
    main()
