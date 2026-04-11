"""Post-fix verification: entity label distribution + HDL record check."""

from dotenv import load_dotenv
from pathlib import Path
import json, sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
load_dotenv(_REPO_ROOT / "secrets" / ".env.config", override=True)
load_dotenv(_REPO_ROOT / "secrets" / ".env", override=False)
from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()
try:
    # 1. Label distribution
    rows = client.run("""
        MATCH (tl:TrainingLabel)
        WHERE tl.include = true AND tl.entities_json IS NOT NULL
        RETURN tl.entities_json AS ej
        """)
    label_counts = {}
    total_entities = 0
    for r in rows:
        for e in json.loads(r["ej"]):
            total_entities += 1
            lbl = e.get("label", "?")
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

    print("=== Entity label distribution (post-fix) ===")
    for lbl, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"  {lbl:30s}: {cnt:>6}")
    print(f"\n  TOTAL: {total_entities}")

    # 2. Entity count distribution
    ent_count_dist = {}
    for r in rows:
        n = len(json.loads(r["ej"]))
        ent_count_dist[n] = ent_count_dist.get(n, 0) + 1
    print("\n=== Entity count per record ===")
    for k in sorted(ent_count_dist.keys()):
        print(f"  {k} entities: {ent_count_dist[k]:>5} records")

    # 3. Check the HDL record specifically
    print("\n=== HDL cholesterol record ===")
    hdl = client.run("""
        MATCH (tl:TrainingLabel)
        WHERE tl.label_id STARTS WITH '339f3d7fb3d2baffdd34'
        RETURN tl.label_id AS label_id, tl.text AS text, tl.entities_json AS ej
        """)
    for r in hdl:
        entities = json.loads(r["ej"])
        print(f"  encounter: {r['text']!r}")
        print(f"  entity count: {len(entities)}")
        for i, e in enumerate(entities):
            print(f"    [{i}] {e.get('label')!r}: {e.get('text')!r}")

    # 4. "Outside reference range" records
    print("\n=== 'Outside reference range' records ===")
    orr = client.run("""
        MATCH (tl:TrainingLabel)
        WHERE tl.include = true AND tl.entities_json IS NOT NULL
          AND tl.text CONTAINS 'Outside reference range'
        RETURN tl.entities_json AS ej
        """)
    with_finding = sum(1 for r in orr if '"finding"' in r["ej"])
    with_qv = sum(1 for r in orr if '"qualifier_value"' in r["ej"])
    print(f"  Total: {len(orr)}")
    print(f"  With finding entity: {with_finding}")
    print(f"  With qualifier_value entity: {with_qv}")

finally:
    client.close()
