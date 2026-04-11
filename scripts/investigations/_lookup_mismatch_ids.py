"""Look up the resolved concept names for all mismatched IDs to determine
which ones need fixing vs which resolver-returned IDs are actually better.
"""

import sys, requests, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

BASE = "http://localhost:8001"

# (surface_form, our_id, resolver_id, clinical_note)
MISMATCHES = [
    ("NAFLD", "1231824009", "161535005", "Metabolic steatotic liver disease"),
    ("type 2 diabetes", "44054006", "410657003", "Diabetes mellitus type 2"),
    ("essential hypertension", "38341003", "59621000", "Hypertensive disorder"),
    ("dementia", "52448006", "161465002", "Dementia"),
    ("atypical chest pain", "274668005", "102589003", "Non-cardiac chest pain"),
    ("bereavement", "308485004", "74506000", "Bereavement"),
    ("colposcopy", "73572009", "392003006", "Colposcopy"),
    ("CIN 2", "285836003", "285838002", "CIN grade 2"),
    ("CIN 3", "275398003", "92564006", "CIN grade 3"),
    ("fit note issued", "401236002", "774741000000101", "Fit note"),
    ("MED3", "401236002", "774741000000101", "Fit note"),
    ("metatarsalgia", "95566004", "10085004", "Metatarsalgia"),
    (
        "generalised lymphadenopathy",
        "111590001",
        "274741002",
        "Generalised lymphadenopathy",
    ),
    ("CT coronary angiography", "41976001", "419545005", "CT coronary angiography"),
    ("adjustment disorder", "309310005", "17226007", "Adjustment disorder"),
    ("total hysterectomy", "116028008", "116140006", "Total hysterectomy"),
    ("FIT positive", "167667006", "59614000", "FIT positive - occult blood detected"),
    ("BCSP FIT positive", "167667006", "71711000112103", "FIT positive - UK code"),
    ("urine ACR", "365757006", "271075006", "Albumin creatinine ratio"),
    ("albuminuria", "312975006", "274769005", "Albuminuria"),
]


def lookup(cid: str) -> str:
    try:
        r = requests.get(
            f"{BASE}/terminology/search",
            params={"q": cid, "limit": 1},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json()
            if isinstance(results, list) and results:
                return results[0].get("term", "?")
    except Exception as e:
        return f"ERROR: {e}"
    return "NOT_FOUND"


unique_ids = set()
for row in MISMATCHES:
    unique_ids.add(row[1])
    unique_ids.add(row[2])

print("Looking up concept names ...")
id_to_name = {}
for cid in sorted(unique_ids):
    name = lookup(cid)
    id_to_name[cid] = name
    print(f"  {cid:<20} {name}")
    time.sleep(0.08)

print()
print("=" * 140)
print(
    f"{'SURFACE FORM':<35} {'OUR ID':<18} {'OUR NAME':<45} {'RESOLVER ID':<18} {'RESOLVER NAME'}"
)
print("-" * 140)

critical_wrong = []
resolver_better = []
both_valid = []

for form, our_id, res_id, note in MISMATCHES:
    our_name = id_to_name.get(our_id, "?")
    res_name = id_to_name.get(res_id, "?")
    print(f"{form:<35} [{our_id}] {our_name[:40]:<43} [{res_id}] {res_name[:45]}")

print()
print("=" * 140)
print("VERDICT FOR EACH MISMATCH:")
print()

verdicts = [
    (
        "NAFLD",
        "1231824009",
        "161535005",
        "NEEDS FIX",
        "Our mapping (MASLD/steatotic liver) is correct; resolver ignoring our MAPS_TO - re-upsert",
    ),
    (
        "type 2 diabetes",
        "44054006",
        "410657003",
        "REVIEW",
        "44054006=disorder, 410657003=finding - both valid; disorder preferred for diagnosis",
    ),
    (
        "essential hypertension",
        "38341003",
        "59621000",
        "RESOLVER BETTER",
        "59621000 IS essential hypertension specifically; 38341003 is generic HTN disorder",
    ),
    (
        "dementia",
        "52448006",
        "161465002",
        "NEEDS FIX",
        "161465002='History of dementia (situation)' is WRONG; 52448006 is the disease",
    ),
    (
        "atypical chest pain",
        "274668005",
        "102589003",
        "REVIEW",
        "274668005=non-cardiac; 102589003=unspecified chest pain - non-cardiac is more specific",
    ),
    (
        "bereavement",
        "308485004",
        "74506000",
        "CHECK",
        "Need to verify 74506000 is grief/bereavement vs 308485004",
    ),
    (
        "colposcopy",
        "73572009",
        "392003006",
        "RESOLVER BETTER",
        "392003006='Colposcopy of cervix' is MORE specific",
    ),
    (
        "CIN 2",
        "285836003",
        "285838002",
        "CRITICAL",
        "285836003=grade 1, 285838002=grade 2 - our ID IS WRONG for CIN 2",
    ),
    ("CIN 3", "275398003", "92564006", "CHECK", "Need to verify grades"),
    (
        "fit note issued",
        "401236002",
        "774741000000101",
        "RESOLVER BETTER",
        "774741000000101 is UK extension - likely more specific/correct",
    ),
    ("MED3", "401236002", "774741000000101", "RESOLVER BETTER", "Same"),
    (
        "metatarsalgia",
        "95566004",
        "10085004",
        "CHECK",
        "Need to verify which is correct metatarsalgia concept",
    ),
    (
        "generalised lymphadenopathy",
        "111590001",
        "274741002",
        "CHECK",
        "Need to verify",
    ),
    (
        "CT coronary angiography",
        "41976001",
        "419545005",
        "RESOLVER BETTER",
        "419545005 is CT coronary angiography specifically; 41976001 is cardiac catheterization",
    ),
    (
        "adjustment disorder",
        "309310005",
        "17226007",
        "CHECK",
        "Need to verify which ID is correct",
    ),
    (
        "total hysterectomy",
        "116028008",
        "116140006",
        "REVIEW",
        "116140006='Total hysterectomy'; 116028008='Salpingo-oophorectomy' - resolver may be correct",
    ),
    (
        "FIT positive",
        "167667006",
        "59614000",
        "CRITICAL",
        "167667006='occult blood NOT detected' is CLINICALLY INVERSE for a POSITIVE test",
    ),
    (
        "BCSP FIT positive",
        "167667006",
        "71711000112103",
        "CRITICAL",
        "Same - our mapping is clinically inverse; resolver better",
    ),
    (
        "urine ACR",
        "365757006",
        "271075006",
        "CHECK",
        "Need to verify albumin/creatinine ratio concept",
    ),
    (
        "albuminuria",
        "312975006",
        "274769005",
        "REVIEW",
        "312975006=microalbuminuria (specific); 274769005 may be general albuminuria",
    ),
]

for form, our_id, res_id, verdict, reason in verdicts:
    print(f"  [{verdict:<16}] {form:<35} -> {reason}")
