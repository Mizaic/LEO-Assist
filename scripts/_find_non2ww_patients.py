"""Find patients who have no 2WW/fast-track text at all - how did they enter the dataset?"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()

rows = client.run("""
MATCH (p:Patient)
WHERE NOT EXISTS {
    MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
    WHERE e.text CONTAINS '2WW' OR e.text CONTAINS '2ww'
       OR e.text CONTAINS 'two week wait' OR e.text CONTAINS 'Two week wait'
       OR e.text CONTAINS 'Fast track referral' OR e.text CONTAINS 'fast track referral'
       OR e.text CONTAINS 'Seen in fast track' OR e.text CONTAINS 'seen in fast track'
}
WITH p
MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE e.text CONTAINS 'cancer' OR e.text CONTAINS 'Cancer'
   OR e.text CONTAINS 'malignant' OR e.text CONTAINS 'Malignant'
   OR e.text CONTAINS 'carcinoma' OR e.text CONTAINS 'Carcinoma'
   OR e.text CONTAINS 'tumour' OR e.text CONTAINS 'Tumour'
   OR e.text CONTAINS 'oncol' OR e.text CONTAINS 'Oncol'
   OR e.text CONTAINS 'referral' OR e.text CONTAINS 'Referral'
   OR e.text CONTAINS 'urgent' OR e.text CONTAINS 'Urgent'
WITH p, e
ORDER BY e.date
WITH p, collect({date: toString(e.date), text: left(e.text, 300)})[0..3] AS samples
RETURN toString(p.id) AS patient_id, samples
""")

results = [dict(r) for r in rows]
print(f"Found {len(results)} patients with NO 2WW/fast-track text but with cancer/referral keywords\n")

for r in results:
    print(f"{'='*80}")
    print(f"  Patient: {r['patient_id']}")
    for i, s in enumerate(r['samples']):
        print(f"\n  Sample {i+1} ({s['date']}):")
        text = s['text'].replace('\n', '\n    ')
        print(f"    {text}")
    print()

# Also count patients with zero cancer-related text at all
rows2 = client.run("""
MATCH (p:Patient)
WHERE NOT EXISTS {
    MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter)
    WHERE e.text CONTAINS '2WW' OR e.text CONTAINS '2ww'
       OR e.text CONTAINS 'Fast track referral' OR e.text CONTAINS 'fast track referral'
       OR e.text CONTAINS 'Seen in fast track' OR e.text CONTAINS 'seen in fast track'
       OR e.text CONTAINS 'cancer' OR e.text CONTAINS 'Cancer'
       OR e.text CONTAINS 'malignant' OR e.text CONTAINS 'Malignant'
       OR e.text CONTAINS 'carcinoma' OR e.text CONTAINS 'Carcinoma'
       OR e.text CONTAINS 'oncol' OR e.text CONTAINS 'Oncol'
}
RETURN count(p) AS n, collect(toString(p.id)) AS ids
""")
for r in rows2:
    d = dict(r)
    print(f"\nPatients with NO cancer text at all: {d['n']}")
    if d['ids']:
        print(f"  IDs: {', '.join(d['ids'][:20])}")

client.close()
