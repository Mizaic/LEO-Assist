"""Verify surface form mappings by resolving each form and comparing the
returned concept ID to what we expect.

This uses TerminologyClient().resolve() -- the same path used in production --
so it tests what actually happens when the pipeline encounters these terms.
"""
import sys, json, time
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

# Format: (surface_form, expected_concept_id, clinical_note)
# expected_concept_id: what we added to the server.
# If the resolver returns a DIFFERENT concept, it is flagged as MISMATCH.
# If it returns the SAME concept, OK.
# clinical_note: explains what the concept should be.
ALL_MAPPINGS = [
    # Batch 7 - thyroid / metabolic
    ("underactive thyroid",          "40930008",  "Hypothyroidism"),
    ("hypothyroidism",               "40930008",  "Hypothyroidism"),
    ("iron deficiency anaemia",      "87522002",  "Iron deficiency anemia"),
    ("IDA",                          "87522002",  "Iron deficiency anemia"),
    ("GORD",                         "235595009", "Gastro-oesophageal reflux"),
    ("acid reflux",                  "698065002", "Acid reflux"),
    ("vitamin B12 deficiency",       "64117007",  "Vitamin B12 deficiency"),
    ("vitamin D deficiency",         "34713006",  "Vitamin D deficiency"),
    ("folate deficiency",            "190633005", "Folic acid deficiency"),
    ("macrocytosis",                 "72826005",  "Macrocytosis"),
    ("hypertriglyceridaemia",        "302870006", "Hypertriglyceridemia"),
    ("NAFLD",                        "1231824009","Metabolic steatotic liver disease"),
    ("non-alcoholic fatty liver disease","1231824009","Metabolic steatotic liver disease"),
    # Batch 7 - cardiovascular
    ("heart failure",                "84114007",  "Heart failure"),
    ("cardiac failure",              "84114007",  "Heart failure"),
    ("congestive heart failure",     "42343007",  "Congestive heart failure"),
    ("CCF",                          "42343007",  "Congestive heart failure"),
    ("LVF",                          "85232009",  "Left heart failure"),
    ("atrial fibrillation",          "49436004",  "Atrial fibrillation"),
    ("AF",                           "49436004",  "Atrial fibrillation"),
    ("persistent AF",                "440028005", "Permanent atrial fibrillation"),
    ("PAD",                          "840580004", "Peripheral arterial disease"),
    ("peripheral arterial disease",  "840580004", "Peripheral arterial disease"),
    # Batch 7 - urology / ENT / eye / resp / derm
    ("BPH",                          "266569009", "Benign prostatic hyperplasia"),
    ("LUTS",                         "307541003", "Lower urinary tract symptoms"),
    ("allergic rhinitis",            "61582004",  "Allergic rhinitis"),
    ("hayfever",                     "21719001",  "Allergic rhinitis caused by pollen"),
    ("OSA",                          "78275009",  "Obstructive sleep apnoea"),
    ("obstructive sleep apnoea",     "78275009",  "Obstructive sleep apnoea"),
    ("haemoptysis",                  "66857006",  "Hemoptysis"),
    ("dry eye syndrome",             "46152009",  "Tear film insufficiency / dry eye"),
    ("BCC",                          "254701007", "Basal cell carcinoma of skin"),
    ("SCC skin",                     "254651007", "Squamous cell carcinoma of skin"),
    ("psoriasis",                    "9014002",   "Psoriasis"),
    ("eczema",                       "43116000",  "Eczema"),
    ("atopic eczema",                "24079001",  "Atopic dermatitis"),
    # Batch 7 - neurology / pain / other
    ("peripheral neuropathy",        "302226006", "Peripheral nerve disease"),
    ("neuropathic pain",             "247398009", "Neuropathic pain"),
    ("chronic pain",                 "82423001",  "Chronic pain"),
    ("lower back pain",              "161891005", "Backache"),
    ("chronic back pain",            "134407002", "Chronic back pain"),
    ("erectile dysfunction",         "860914002", "Erectile dysfunction"),
    ("medication review done",       "314530002", "Medication review done"),
    ("structured medication review", "1239511000000100","Structured medication review"),
    ("anaemia",                      "271737000", "Anemia"),
    # Earlier batches
    ("weight loss",                  "262285001", "Weight decreased/loss"),
    ("type 2 diabetes mellitus",     "44054006",  "Diabetes mellitus type 2"),
    ("type 2 diabetes",              "44054006",  "Diabetes mellitus type 2"),
    ("hypertension",                 "38341003",  "Hypertensive disorder"),
    ("essential hypertension",       "38341003",  "Hypertensive disorder"),
    ("COPD",                         "13645005",  "COPD"),
    ("prediabetes",                  "714628002", "Prediabetes"),
    ("hypercholesterolaemia",        "13644009",  "Hypercholesterolemia"),
    ("dementia",                     "52448006",  "Dementia"),
    ("abdominal pain",               "21522001",  "Abdominal pain"),
    ("chronic kidney disease",       "709044004", "Chronic kidney disease"),
    ("chest pain",                   "29857009",  "Chest pain"),
    ("atypical chest pain",          "274668005", "Non-cardiac chest pain"),
    ("osteoporosis",                 "64859006",  "Osteoporosis"),
    ("change in bowel habit",        "88111009",  "Altered bowel function"),
    ("suicidal ideation",            "6471006",   "Suicidal thoughts"),
    ("TWOC",                         "170884001", "Trial without catheter"),
    ("bereavement",                  "308485004", "Bereavement"),
    ("colposcopy",                   "73572009",  "Colposcopy"),
    ("CIN 2",                        "285836003", "Cervical intraepithelial neoplasia grade 2"),
    ("CIN 3",                        "275398003", "Cervical intraepithelial neoplasia grade 3"),
    ("fit note issued",              "401236002", "Fit note"),
    ("MED3",                         "401236002", "Fit note"),
    ("metatarsalgia",                "95566004",  "Metatarsalgia"),
    ("generalised lymphadenopathy",  "111590001", "Generalised lymphadenopathy"),
    ("CT coronary angiography",      "41976001",  "CT coronary angiography"),
    ("adjustment disorder",          "309310005", "Adjustment disorder"),
    ("total hysterectomy",           "116028008", "Total hysterectomy"),
    ("influenza vaccination",        "86198006",  "Influenza vaccination"),
    ("faecal immunochemical test positive","167667006","FIT positive / occult blood detected"),
    ("FIT positive",                 "167667006", "FIT positive / occult blood detected"),
    ("BCSP FIT positive",            "167667006", "FIT positive / occult blood detected"),
    ("urine albumin creatinine ratio","365757006","Albumin creatinine ratio"),
    ("urine ACR",                    "365757006", "Albumin creatinine ratio"),
    ("albuminuria",                  "312975006", "Microalbuminuria / albuminuria"),
    ("statin declined",              "406149000", "Medication declined"),
]

print(f"Verifying {len(ALL_MAPPINGS)} surface form mappings via resolver")
print()
fmt = "{:<10} {:<48} {:<18} {:<18} {}"
print(fmt.format("STATUS", "SURFACE FORM", "EXPECTED ID", "RESOLVED ID", "CLINICAL NOTE"))
print("-" * 130)

wrong = []
ok_count = miss_count = 0
mismatches = []

for form, expected_id, note in ALL_MAPPINGS:
    try:
        results = client.resolve([form])
        hits = results.get(form, [])
    except Exception as e:
        print(fmt.format("ERROR", form, expected_id, str(e)[:16], note))
        continue

    if not hits:
        status = "MISS"
        resolved_id = "not_resolved"
        miss_count += 1
        mismatches.append((form, expected_id, "not_resolved", note))
    else:
        resolved_id = str(hits[0].concept_id)
        if resolved_id == expected_id:
            status = "OK"
            ok_count += 1
        else:
            status = "MISMATCH"
            mismatches.append((form, expected_id, resolved_id, note))

    print(fmt.format(status, form, expected_id, resolved_id, note[:50]))
    time.sleep(0.03)

print()
print("=" * 130)
print(f"OK: {ok_count}  |  MISMATCH/MISS: {len(mismatches)}")

if mismatches:
    print()
    print("!!! ISSUES FOUND !!!")
    for form, expected, resolved, note in mismatches:
        print(f"\n  Surface form : '{form}'")
        print(f"  Expected     : {expected}  ({note})")
        print(f"  Resolver got : {resolved}")
        if resolved != "not_resolved":
            print("  => Resolver is returning a DIFFERENT concept.")
            print("     This surface form needs its mapping updated.")
        else:
            print("  => Surface form is not being resolved at all.")
            print("     Check if the mapping was written correctly.")
else:
    print()
    print("All surface form mappings verified - resolver returns the expected concept for every form.")
