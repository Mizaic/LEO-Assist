"""Find patients with 2WW mentions who weren't caught by the fast-track text search."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env")

from libs.neo4j_client.client import PatientGraphClient

client = PatientGraphClient()

# Patients with 2WW text but NOT matching our fast-track patterns
rows = client.run("""
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE (e.text CONTAINS '2WW' OR e.text CONTAINS '2ww'
       OR e.text CONTAINS 'two week wait' OR e.text CONTAINS 'Two week wait'
       OR e.text CONTAINS 'two-week wait' OR e.text CONTAINS 'Two-Week Wait'
       OR e.text CONTAINS 'cancer referral' OR e.text CONTAINS 'Cancer referral'
       OR e.text CONTAINS 'urgent referral' OR e.text CONTAINS 'Urgent referral')
WITH DISTINCT p
WHERE NOT EXISTS {
    MATCH (p)-[:HAS_ENCOUNTER]->(e2:Encounter)
    WHERE e2.text CONTAINS 'Fast track referral for suspected'
       OR e2.text CONTAINS 'fast track referral for suspected'
       OR e2.text CONTAINS 'Seen in fast track suspected'
       OR e2.text CONTAINS 'seen in fast track suspected'
}
MATCH (p)-[:HAS_ENCOUNTER]->(e3:Encounter)
WHERE e3.text CONTAINS '2WW' OR e3.text CONTAINS '2ww'
   OR e3.text CONTAINS 'two week wait' OR e3.text CONTAINS 'Two week wait'
   OR e3.text CONTAINS 'cancer referral' OR e3.text CONTAINS 'Cancer referral'
   OR e3.text CONTAINS 'urgent referral' OR e3.text CONTAINS 'Urgent referral'
WITH p, e3
ORDER BY e3.date
WITH p, collect({date: toString(e3.date), text: left(e3.text, 300)})[0..3] AS samples
RETURN toString(p.id) AS patient_id, samples
""")

results = [dict(r) for r in rows]
print(f"Found {len(results)} patients with 2WW/cancer referral text NOT matching fast-track patterns\n")

for r in results:
    print(f"{'='*80}")
    print(f"  Patient: {r['patient_id']}")
    for i, s in enumerate(r['samples']):
        print(f"\n  Sample {i+1} ({s['date']}):")
        text = s['text'].replace('\n', '\n    ')
        print(f"    {text}")
    print()

client.close()
