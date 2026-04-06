"""Query Neo4j for all pending HITL-related task queues."""
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

    print("=== HITLTask ===")
    rows = [dict(x) for x in s.run("""
        MATCH (t:HITLTask)
        RETURN t.task_type AS task_type, t.status AS status, count(*) AS n
        ORDER BY task_type, status
    """)]
    for row in rows:
        print(f"  {str(row['task_type']):40s} {str(row['status']):15s} {row['n']}")
    if not rows:
        print("  (none)")

    print("\n=== SurfaceFormTask ===")
    rows = [dict(x) for x in s.run("""
        MATCH (t:SurfaceFormTask)
        RETURN coalesce(t.review_type,'?') AS review_type,
               coalesce(t.status,'?') AS status, count(*) AS n
        ORDER BY review_type, status
    """)]
    for row in rows:
        print(f"  {row['review_type']:40s} {row['status']:15s} {row['n']}")
    if not rows:
        print("  (none)")

    print("\n=== CodingReview (unresolved) ===")
    rows = [dict(x) for x in s.run("""
        MATCH (cr:CodingReview)
        WHERE cr.resolved = false
        RETURN coalesce(cr.assertion,'present') AS assertion,
               coalesce(cr.auto_resolved, false) AS auto_resolved,
               count(*) AS n
        ORDER BY auto_resolved, assertion
    """)]
    for row in rows:
        print(f"  assertion={str(row['assertion']):15s} auto_resolved={str(row['auto_resolved']):6s} {row['n']}")
    if not rows:
        print("  (none)")

    print("\n=== ReviewTask (EncounterCandidate pipeline) ===")
    rows = [dict(x) for x in s.run("""
        MATCH (c:EncounterCandidate)-[:HAS_TASK]->(t:ReviewTask)
        RETURN coalesce(t.status,'?') AS status, count(*) AS n
        ORDER BY status
    """)]
    for row in rows:
        print(f"  {row['status']:20s} {row['n']}")
    if not rows:
        print("  (none)")

    print("\n=== All Task/Review node labels ===")
    rows = [dict(x) for x in s.run("""
        CALL db.labels() YIELD label
        WHERE label CONTAINS 'Task' OR label CONTAINS 'HITL' OR label CONTAINS 'Review'
        RETURN label ORDER BY label
    """)]
    for row in rows:
        print(f"  {row['label']}")

    print("\n=== AnchorReview / EncounterReview / LabelVerificationReview ===")
    for label in ["AnchorReview", "EncounterReview", "LabelVerificationReview"]:
        query = "MATCH (n:" + label + ") RETURN coalesce(n.status, '?') AS status, count(*) AS n ORDER BY status"
        rows = [dict(x) for x in s.run(query)]
        print(f"  {label}:")
        for row in rows:
            print(f"    {row['status']:20s} {row['n']}")
        if not rows:
            print("    (none)")

    print("\n=== Legacy node property inspection ===")
    for label in ["AnchorReview", "LabelVerificationReview"]:
        q = "MATCH (n:" + label + ") RETURN keys(n) AS props LIMIT 1"
        rows = [dict(x) for x in s.run(q)]
        print(f"  {label} props: {rows[0]['props'] if rows else 'n/a'}")
        q2 = "MATCH (n:" + label + ")-[r]-() RETURN type(r) AS rel, count(*) AS n ORDER BY n DESC LIMIT 3"
        rels = [dict(x) for x in s.run(q2)]
        for rel in rels:
            print(f"    -{rel['rel']}-> x{rel['n']}")

client.close()
