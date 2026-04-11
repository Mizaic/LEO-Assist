"""For each auto-closed episode, check if an IN-DOMAIN cancer concept was
coded AFTER the referral date.  That would mean the episode builder genuinely
missed a cancer diagnosis and the episode should have been 'completed'.

Domain concept sets come from the Neo4j ValueSet nodes (same as episode builder).

Run:
    python scripts/investigations/_autoclosed_domain_check.py
"""

from __future__ import annotations
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

# Fetch all cancer-type concept IDs for each cancer_category from Neo4j ValueSet
_Q_DOMAIN_CONCEPTS = """
MATCH (vs:ValueSet {id: 'ncda-cancer-types'})-[:HAS_MEMBER]->(c)
RETURN c.conceptId AS cid, c.name AS name
"""

# Fetch all auto-closed episodes
_Q_EPISODES = """
MATCH (ep:EpisodeOfCare)
WHERE ep.auto_closed = true
RETURN ep.patient_id AS pid,
       ep.cancer_type AS site,
       ep.referral_date AS ref,
       ep.status AS status,
       ep.auto_close_reason AS reason,
       ep.specialist_seen AS spec_seen,
       ep.episode_id AS ep_id
ORDER BY ep.auto_close_reason, ep.cancer_type, ep.referral_date
"""

# Fetch in-domain cancer concepts coded after referral (present assertion only)
_Q_IN_DOMAIN = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
  AND c.conceptId IN $concept_ids
  AND coalesce(doc.assertion, 'present') = 'present'
RETURN DISTINCT c.name AS name, c.conceptId AS cid, toString(e.date) AS edate
ORDER BY edate
LIMIT 5
"""

# Fetch benign outcome concepts coded after referral - includes 395100000 and common
# benign site-specific outcomes that primary care coders use instead of 395100000
_BENIGN_CIDS = [
    395100000,  # No evidence of cancer found
    415068001,  # Benign disorder
    160303001,  # No malignancy
    92814006,  # Fibroadenoma of breast
    416940007,  # Past history of benign neoplasm
    30811003,  # Diverticular disease of colon
    444657004,  # Tubular adenoma of colon (polyp, removed)
    449360000,  # Colonic polyp (benign removed)
]
_Q_BENIGN = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[doc:DOCUMENTS]->(c)
WHERE p.id = $pid
  AND toString(e.date) >= $from_date
  AND c.conceptId IN $benign_cids
RETURN DISTINCT c.name AS name, toString(e.date) AS edate
ORDER BY edate
LIMIT 3
"""

# Map cancer_type domain -> cancer_category label
_DOMAIN_TO_CATEGORY = {
    "breast": "breast",
    "lower_gi": "lower_gi",
    "upper_gi": "upper_gi",
    "lung": "lung",
    "skin": "skin",
    "urological": "urological",
    "haematological": "haematological",
    "head_and_neck": "head_and_neck",
    "gynaecological": "gynaecological",
    "non_site_specific": None,  # check any cancer domain
}


def main() -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()

    # Build full cancer concept ID set from ValueSet (no per-category breakdown in the graph)
    concept_rows = client.run(_Q_DOMAIN_CONCEPTS) or []
    all_cids = [int(r["cid"]) for r in concept_rows if r.get("cid")]
    print(f"Cancer concept IDs loaded from ValueSet: {len(all_cids)}\n")

    episodes = client.run(_Q_EPISODES) or []

    missed_cancer: list[tuple] = []
    missed_benign: list[tuple] = []
    truly_stale: list[tuple] = []

    for ep in episodes:
        pid = str(ep["pid"])
        site = ep["site"] or "unknown"
        ref = str(ep["ref"] or "")
        reason = ep.get("reason") or ""

        concept_ids = all_cids

        # Check for in-domain cancer
        in_domain_rows = (
            client.run(_Q_IN_DOMAIN, pid=pid, from_date=ref, concept_ids=concept_ids)
            or []
        )
        if in_domain_rows:
            for row in in_domain_rows:
                missed_cancer.append(
                    (pid, site, ref, ep["status"], reason, row["name"], row["edate"])
                )
            continue

        # Check for benign closure concepts
        benign_rows = (
            client.run(_Q_BENIGN, pid=pid, from_date=ref, benign_cids=_BENIGN_CIDS)
            or []
        )
        if benign_rows:
            for row in benign_rows:
                missed_benign.append(
                    (pid, site, ref, ep["status"], reason, row["name"], row["edate"])
                )
            continue

        truly_stale.append((pid, site, ref, ep["status"], reason))

    print(
        f"=== MISSED CANCER (episode builder failed to detect in-domain diagnosis) ==="
        f"  [{len(missed_cancer)} instances from {len({r[0] for r in missed_cancer})} patients]"
    )
    seen_combo: set[tuple] = set()
    for pid, site, ref, status, reason, name, edate in missed_cancer:
        combo = (pid, site, ref)
        if combo not in seen_combo:
            seen_combo.add(combo)
            print(f"  PID={pid}  site={site:20}  ref={ref}  status={status}")
            print(f"    first in-domain cancer: [{edate}] {name}")
    print()

    print(
        f"=== MISSED BENIGN CLOSURE (should be closed_benign) ==="
        f"  [{len({(r[0],r[1],r[2]) for r in missed_benign})} episodes]"
    )
    seen_b: set[tuple] = set()
    for pid, site, ref, status, reason, name, edate in missed_benign:
        combo = (pid, site, ref)
        if combo not in seen_b:
            seen_b.add(combo)
            print(f"  PID={pid}  site={site:20}  ref={ref}  status={status}")
            print(f"    benign concept: [{edate}] {name}")
    print()

    print(
        f"=== GENUINELY STALE (no in-domain cancer, no benign closure detected) ==="
        f"  [{len(truly_stale)} episodes]"
    )
    for pid, site, ref, status, reason in truly_stale:
        print(f"  PID={pid}  site={site:20}  ref={ref}  reason={reason}")
    print()

    print("=== SUMMARY ===")
    missed_eps = len({(r[0], r[1], r[2]) for r in missed_cancer})
    benign_eps = len({(r[0], r[1], r[2]) for r in missed_benign})
    print(f"  Missed cancer (should be completed)  : {missed_eps}")
    print(f"  Missed benign (should be closed_benign): {benign_eps}")
    print(f"  Genuinely stale (auto-close correct) : {len(truly_stale)}")
    print(f"  TOTAL                                : {len(episodes)}")

    client.close()


if __name__ == "__main__":
    main()
