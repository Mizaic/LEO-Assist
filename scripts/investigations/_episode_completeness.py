"""Per-episode completeness: does each referral have a specialist visit and diagnosis?"""
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
from libs.neo4j_client.client import PatientGraphClient

Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id IS NOT NULL
RETURN
    ep.patient_id      AS pid,
    ep.condition_type  AS cond,
    ep.referral_date   AS rd,
    ep.specialist_seen AS spec,
    ep.status          AS status,
    ep.end_date        AS end_date
ORDER BY ep.patient_id, ep.referral_date
"""

client = PatientGraphClient()
with client.session() as s:
    rows = [dict(r) for r in s.run(Q)]
client.close()

total     = len(rows)
full      = sum(1 for r in rows if r["spec"] and r["status"] == "completed")
ref_spec  = sum(1 for r in rows if r["spec"] and r["status"] != "completed")
ref_diag  = sum(1 for r in rows if not r["spec"] and r["status"] == "completed")
ref_only  = sum(1 for r in rows if not r["spec"] and r["status"] != "completed")

print(f"Total episodes : {total}")
print()
print(f"  Referral + Specialist + Diagnosis : {full:3d}  ({full/total*100:.0f}%)")
print(f"  Referral + Specialist only        : {ref_spec:3d}  ({ref_spec/total*100:.0f}%)")
print(f"  Referral + Diagnosis only         : {ref_diag:3d}  ({ref_diag/total*100:.0f}%)")
print(f"  Referral only                     : {ref_only:3d}  ({ref_only/total*100:.0f}%)")
print()

# -- Per cancer site breakdown --
print(f"{'Cancer site':<22}  {'Total':>5}  {'Full':>5}  {'Ref+Spec':>8}  {'Ref+Diag':>8}  {'Ref only':>8}")
print("-" * 65)
by_site: dict[str, list[dict]] = defaultdict(list)
for r in rows:
    by_site[str(r["cond"] or "unknown")].append(r)

for site, eps in sorted(by_site.items(), key=lambda x: -len(x[1])):
    t  = len(eps)
    f  = sum(1 for e in eps if e["spec"] and e["status"] == "completed")
    rs = sum(1 for e in eps if e["spec"] and e["status"] != "completed")
    rd = sum(1 for e in eps if not e["spec"] and e["status"] == "completed")
    ro = sum(1 for e in eps if not e["spec"] and e["status"] != "completed")
    print(f"  {site:<20}  {t:5d}  {f:5d}  {rs:8d}  {rd:8d}  {ro:8d}")

# -- Episodes with no specialist and no diagnosis (pure referral only) --
print()
print("Episodes with referral only (no specialist visit, no diagnosis):")
for r in rows:
    if not r["spec"] and r["status"] != "completed":
        print(f"  pid={r['pid']}  cond={r['cond']:<20}  rd={r['rd']}")
