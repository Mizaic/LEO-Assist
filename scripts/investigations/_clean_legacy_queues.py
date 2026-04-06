"""Delete legacy review nodes and report gold data / training candidate state."""
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

client = PatientGraphClient()
with client.session() as s:

    # -- Deletions -----------------------------------------------------------
    print("=== Deleting legacy review nodes ===")
    for label in ["AnchorReview", "LabelVerificationReview", "EncounterReview"]:
        result = s.run("MATCH (n:" + label + ") DETACH DELETE n RETURN count(*) AS n")
        row = result.single()
        n = row["n"] if row else 0
        print(f"  Deleted {n:>5} {label} nodes")

    # -- GoldLabel -----------------------------------------------------------
    print("\n=== GoldLabel ===")
    rows = [dict(x) for x in s.run("""
        MATCH (g:GoldLabel)
        RETURN
            coalesce(g.source, '?')         AS source,
            coalesce(g.verified, false)     AS verified,
            g.entities_json IS NOT NULL     AS has_entities,
            count(*)                        AS n
        ORDER BY source, verified
    """)]
    for row in rows:
        print(f"  source={str(row['source']):20s} verified={str(row['verified']):6s} "
              f"has_entities={str(row['has_entities']):6s} n={row['n']}")
    if not rows:
        print("  (none)")

    # -- TrainingCandidate ---------------------------------------------------
    print("\n=== TrainingCandidate ===")
    rows = [dict(x) for x in s.run("""
        MATCH (c:TrainingCandidate)
        RETURN
            coalesce(c.status, '?')  AS status,
            coalesce(c.source, '?')  AS source,
            count(*)                 AS n
        ORDER BY source, status
    """)]
    for row in rows:
        print(f"  source={str(row['source']):20s} status={str(row['status']):15s} n={row['n']}")
    if not rows:
        print("  (none)")

    # -- TrainingLabel -------------------------------------------------------
    print("\n=== TrainingLabel ===")
    rows = [dict(x) for x in s.run("""
        MATCH (t:TrainingLabel)
        RETURN
            coalesce(t.include, '?')    AS include,
            coalesce(t.source, '?')     AS source,
            count(*)                    AS n
        ORDER BY source, include
    """)]
    for row in rows:
        print(f"  source={str(row['source']):20s} include={str(row['include']):8s} n={row['n']}")
    if not rows:
        print("  (none)")

client.close()
