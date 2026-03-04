"""Inspect entities with context_detection_failed flag."""
import sys, os, json, warnings
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")
from neo4j import GraphDatabase

d = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))
with d.session() as s:
    rows = s.run(
        "MATCH (t:TrainingLabel) WHERE t.include = true AND t.entities_json IS NOT NULL "
        "RETURN t.label_id AS id, t.entities_json AS ej, "
        "       t.verified_at AS verified_at, t.verification_agreement AS agreed"
    ).data()

    ctx_failed_labels = []
    clean_labels = 0
    for row in rows:
        ents = json.loads(row["ej"]) if row["ej"] else []
        flagged = [e for e in ents if e.get("context_detection_failed")]
        if flagged:
            ctx_failed_labels.append(row)
        else:
            clean_labels += 1

    print(f"Clean labels (no flag): {clean_labels}")
    print(f"Labels with context_detection_failed: {len(ctx_failed_labels)}")

    verified_count = sum(1 for r in ctx_failed_labels if r["verified_at"])
    agreed_count = sum(1 for r in ctx_failed_labels if r.get("agreed") is True)
    disagreed_count = sum(1 for r in ctx_failed_labels if r.get("agreed") is False)

    print(f"  - Verified: {verified_count}")
    print(f"  - Agreed: {agreed_count}")
    print(f"  - Disagreed: {disagreed_count}")

    total_ents = sum(len(json.loads(r["ej"] or "[]")) for r in ctx_failed_labels)
    flagged_ents = sum(
        sum(1 for e in json.loads(r["ej"] or "[]") if e.get("context_detection_failed"))
        for r in ctx_failed_labels
    )
    print(f"  - Total entities in affected labels: {total_ents}")
    print(f"  - Entities with flag: {flagged_ents}")
    print(f"  - Clean entities in affected labels: {total_ents - flagged_ents}")

    # Check assertion distribution of flagged entities
    from collections import Counter
    assertions = Counter()
    for r in ctx_failed_labels:
        ents = json.loads(r["ej"] or "[]")
        for e in ents:
            if e.get("context_detection_failed"):
                assertions[e.get("assertion", "present")] += 1
    print(f"\n  Assertion distribution of flagged entities:")
    for a, n in assertions.most_common():
        print(f"    {a}: {n}")

d.close()
