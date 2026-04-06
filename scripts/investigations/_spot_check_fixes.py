"""Spot-check the critical surface form fixes are now honoured by the resolver."""
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from libs.terminology.client import TerminologyClient

client = TerminologyClient()

CHECKS = [
    ("FIT positive",                      "59614000",       "Occult blood detected"),
    ("faecal immunochemical test positive","59614000",       "Occult blood detected"),
    ("BCSP FIT positive",                 "71711000112103", "immunoassay detected"),
    ("CIN 2",                             "285838002",      "grade 2"),
    ("CIN 3",                             "92564006",       "Carcinoma in situ"),
    ("colposcopy",                        "392003006",      "Colposcopy procedure"),
    ("metatarsalgia",                     "10085004",       "Metatarsalgia"),
    ("CT coronary angiography",           "419545005",      "CT coronary"),
    ("total hysterectomy",                "116140006",      "Total hysterectomy"),
    ("urine ACR",                         "271075006",      "albumin creatinine"),
    ("urine albumin creatinine ratio",    "271075006",      "albumin creatinine"),
    ("albuminuria",                       "274769005",      "Albuminuria"),
    ("NAFLD",                             "1231824009",     "steatotic liver"),
    ("dementia",                          "52448006",       "Dementia"),
    ("type 2 diabetes",                   "44054006",       "Diabetes mellitus type 2"),
    ("bereavement",                       "74506000",       "Bereavement"),
    ("fit note issued",                   "774741000000101","Fitness for work"),
    ("MED3",                              "774741000000101","Fitness for work"),
    ("adjustment disorder",               "17226007",       "Adjustment disorder"),
    ("generalised lymphadenopathy",       "274741002",      "lymphadenopathy"),
]

fmt = "{:<12} {:<42} {:<20} {}"
print(fmt.format("STATUS", "SURFACE FORM", "EXPECTED", "RESOLVED"))
print("-" * 95)

wrong = 0
for form, expected_id, hint in CHECKS:
    results = client.resolve([form])
    hits = results.get(form, [])
    resolved_id = str(hits[0].concept_id) if hits else "MISS"
    status = "OK" if resolved_id == expected_id else "STILL WRONG"
    if status != "OK":
        wrong += 1
    print(fmt.format(status, form, f"[{expected_id}]", f"[{resolved_id}]"))
    time.sleep(0.05)

print()
print(f"Correct: {len(CHECKS) - wrong}/{len(CHECKS)}")
if wrong == 0:
    print("All critical fixes confirmed. Safe to run the audit.")
else:
    print("Some fixes are not yet honoured by the resolver. Investigate before auditing.")
