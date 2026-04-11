"""Test the merge/NSS-close Cypher queries on a known problem patient."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

# Test on the worst offender
PATIENT_ID = "4808735946"

client = PatientGraphClient()
try:
    rows = client.run(
        "MATCH (ep:EpisodeOfCare {patient_id: $pid}) "
        "RETURN ep.episode_id AS eid, ep.cancer_type AS ctype, ep.status AS status, "
        "       toString(ep.referral_date) AS rdate ORDER BY rdate",
        pid=PATIENT_ID,
    )
    print("Before:")
    for r in rows:
        print(f"  {r['eid'][:12]}  {r['ctype']:25s}  {r['status']:25s}  {r['rdate']}")

    # Test NSS close directly
    result = client.run(
        "MATCH (ep:EpisodeOfCare) "
        "WHERE ep.patient_id = $patient_id "
        "  AND ep.cancer_type = 'non_site_specific' "
        "  AND NOT ep.status IN ['closed_related', 'closed_phantom', 'merged'] "
        "  AND coalesce(ep.auto_closed, false) <> true "
        "WITH ep "
        "MATCH (other:EpisodeOfCare) "
        "WHERE other.patient_id = $patient_id "
        "  AND other.cancer_type <> 'non_site_specific' "
        "  AND other.episode_id <> ep.episode_id "
        "  AND NOT other.status IN ['merged', 'closed_phantom'] "
        "  AND abs(duration.inDays(date(other.referral_date), date(ep.referral_date)).days) <= $window "
        "SET ep.status = 'closed_related', ep.auto_closed = true "
        "RETURN count(ep) AS n",
        patient_id=PATIENT_ID,
        window=180,
    )
    print(f"\nNSS close affected: {result[0]['n'] if result else 0} episodes")

    rows2 = client.run(
        "MATCH (ep:EpisodeOfCare {patient_id: $pid}) "
        "RETURN ep.episode_id AS eid, ep.cancer_type AS ctype, ep.status AS status, "
        "       toString(ep.referral_date) AS rdate ORDER BY rdate",
        pid=PATIENT_ID,
    )
    print("\nAfter NSS close:")
    for r in rows2:
        print(f"  {r['eid'][:12]}  {r['ctype']:25s}  {r['status']:25s}  {r['rdate']}")

    # Test same-site merge using Python logic
    episodes = [r for r in rows2 if r["status"] not in ("merged", "closed_phantom")]
    from collections import defaultdict

    by_site = defaultdict(list)
    for r in episodes:
        by_site[r["ctype"]].append(r)

    merged = 0
    for ctype, eps in by_site.items():
        if ctype == "non_site_specific" or len(eps) < 2:
            continue
        eps_sorted = sorted(eps, key=lambda e: e["rdate"])
        primary = eps_sorted[0]
        for dup in eps_sorted[1:]:
            from datetime import date

            d1 = date.fromisoformat(primary["rdate"])
            d2 = date.fromisoformat(dup["rdate"])
            gap = (d2 - d1).days
            if gap <= 180:
                print(
                    f"\n  Would merge {dup['eid'][:12]} ({ctype}, {dup['rdate']}) into {primary['eid'][:12]} ({primary['rdate']}) gap={gap}d"
                )
                client.run(
                    "MATCH (ep:EpisodeOfCare {episode_id: $eid}) "
                    "SET ep.status = 'merged', ep.merged_into = $primary, "
                    "    ep.merged_at = datetime(), "
                    "    ep.merge_reasoning = 'Auto-merged: same site within ' + toString($gap) + ' days' "
                    "RETURN ep.episode_id",
                    eid=dup["eid"],
                    primary=primary["eid"],
                    gap=gap,
                )
                merged += 1

    print(f"\nSame-site merges: {merged}")

    rows3 = client.run(
        "MATCH (ep:EpisodeOfCare {patient_id: $pid}) "
        "RETURN ep.episode_id AS eid, ep.cancer_type AS ctype, ep.status AS status, "
        "       toString(ep.referral_date) AS rdate ORDER BY rdate",
        pid=PATIENT_ID,
    )
    print("\nFinal:")
    for r in rows3:
        print(f"  {r['eid'][:12]}  {r['ctype']:25s}  {r['status']:25s}  {r['rdate']}")
finally:
    client.close()
