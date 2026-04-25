"""Batch 7 -- surface form mappings from top audit gaps.

Focus: common conditions and abbreviations flagged 60-216x as missing in the
post-remediation audit. Includes fixes for wrong auto-mappings (PAD, NAFLD,
underactive thyroid) plus reinforcement of key abbreviations and variants.
"""

import sys, requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.auth.service_auth import get_service_auth_header

BASE = "http://localhost:8001"
PROVENANCE = "batch7_audit_gap_april_2026"

SURFACE_FORMS = [
    # -- Thyroid --
    ("hypothyroidism", "40930008"),
    ("underactive thyroid", "40930008"),  # was wrongly -> "Underactive (qualifier)"
    ("thyroid underactive", "40930008"),
    ("on thyroxine", "40930008"),  # common clinical shorthand
    # -- Iron deficiency --
    ("iron deficiency anaemia", "87522002"),
    ("iron deficiency anemia", "87522002"),
    ("IDA", "87522002"),
    ("low iron", "87522002"),
    ("iron deficient", "87522002"),
    # -- Anaemia (general) --
    ("anaemia", "271737000"),
    ("anemia", "271737000"),
    # -- GORD / acid reflux --
    ("GORD", "235595009"),
    ("GERD", "235595009"),
    ("gastro-oesophageal reflux", "235595009"),
    ("gastro-esophageal reflux", "235595009"),
    ("reflux disease", "235595009"),
    # -- Heart failure --
    ("heart failure", "84114007"),
    ("cardiac failure", "84114007"),
    ("congestive heart failure", "42343007"),
    ("CCF", "42343007"),  # resolver: congestive heart failure
    ("LVF", "85232009"),  # resolver: left heart failure
    # -- Hypertriglyceridaemia --
    ("hypertriglyceridaemia", "302870006"),
    ("hypertriglyceridemia", "302870006"),
    ("high triglycerides", "302870006"),
    ("raised triglycerides", "302870006"),
    # -- Haemoptysis --
    ("haemoptysis", "66857006"),
    ("hemoptysis", "66857006"),
    ("coughing up blood", "66857006"),
    ("blood in sputum", "66857006"),
    # -- Atrial fibrillation --
    ("atrial fibrillation", "49436004"),
    ("AF", "49436004"),
    ("persistent AF", "440028005"),
    ("permanent AF", "440028005"),
    # paroxysmal AF excluded -- auto-maps to wrong concept (rapid ventricular response)
    # -- BPH / prostate --
    ("benign prostatic hyperplasia", "266569009"),
    ("BPH", "266569009"),
    ("enlarged prostate", "249607009"),
    ("benign prostate enlargement", "266569009"),
    ("LUTS", "307541003"),  # lower urinary tract symptoms (finding)
    # -- Allergic rhinitis --
    ("allergic rhinitis", "61582004"),
    ("hayfever", "21719001"),
    ("hay fever", "21719001"),
    ("seasonal rhinitis", "21719001"),
    ("perennial rhinitis", "61582004"),
    # -- Dry eye --
    ("dry eye syndrome", "46152009"),
    ("dry eyes", "46152009"),
    ("dry eye", "46152009"),
    # -- Erectile dysfunction --
    ("erectile dysfunction", "860914002"),
    ("impotence", "860914002"),
    ("ED", "860914002"),
    # -- Elevated BP (finding, not the disorder) --
    ("raised blood pressure reading", "163027005"),
    ("elevated blood pressure reading", "163027005"),
    ("blood pressure elevated", "24184005"),
    # -- Medication review --
    ("medication review done", "314530002"),
    ("medication review", "314530002"),
    ("structured medication review", "1239511000000100"),
    # SMR excluded -- resolves to "submucous resection of nasal septum"
    # -- Cholesterol / lipids --
    ("total cholesterol HDL ratio", "104583003"),
    ("cholesterol HDL ratio", "104583003"),
    ("TC HDL ratio", "104583003"),
    # -- NAFLD / MASLD --
    ("non-alcoholic fatty liver disease", "9990010007"),
    ("NAFLD", "9990010007"),  # was wrongly -> "history of liver disease"
    ("fatty liver", "9990010007"),
    ("hepatic steatosis", "9990010007"),
    ("MASLD", "9990010007"),
    # -- Sleep apnoea --
    ("sleep apnoea", "73430006"),
    ("sleep apnea", "73430006"),
    ("obstructive sleep apnoea", "78275009"),
    ("OSA", "78275009"),
    # CPAP excluded -- resolves to device (home CPAP unit), not condition
    # -- Neuropathy --
    ("peripheral neuropathy", "302226006"),
    ("neuropathic pain", "247398009"),
    # diabetic neuropathy excluded -- auto-maps to generic "complication due to DM"
    # -- Back pain --
    ("lower back pain", "161891005"),  # Backache (finding) -- what resolver returns
    ("low back pain", "161891005"),
    ("lumbar back pain", "161891005"),
    ("chronic back pain", "134407002"),
    ("chronic low back pain", "134407002"),
    # -- Peripheral arterial disease --
    ("peripheral arterial disease", "840580004"),
    ("PAD", "840580004"),  # was wrongly -> "Pad (morphologic abnormality)"
    # peripheral vascular disease and intermittent claudication excluded --
    # auto-map to historical situation concept, not active condition
    # -- Skin cancer --
    ("basal cell carcinoma", "254701007"),
    ("BCC", "254701007"),
    (
        "squamous cell carcinoma skin",
        "254651007",
    ),  # SCC of skin -- verified by resolver
    ("SCC skin", "254651007"),
    ("skin cancer", "372130007"),
    # -- Psoriasis / eczema --
    ("psoriasis", "9014002"),
    ("eczema", "43116000"),
    ("atopic eczema", "24079001"),
    ("atopic dermatitis", "24079001"),
    # -- Macrocytosis / B12 / D / folate --
    ("macrocytosis", "72826005"),
    ("vitamin B12 deficiency", "64117007"),  # resolver: B12 deficiency (non anemic)
    ("B12 deficiency", "64117007"),
    ("low B12", "64117007"),
    ("cobalamin deficiency", "64117007"),
    ("vitamin D deficiency", "34713006"),
    ("low vitamin D", "34713006"),
    ("folate deficiency", "190633005"),
    ("folic acid deficiency", "190633005"),
    ("low folate", "190633005"),
    # -- Chronic pain --
    ("chronic pain", "82423001"),
    ("chronic pain syndrome", "373621006"),
]


SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())


def upsert_one(form: str, concept_id: str) -> str:
    body = {
        "normalized": form.lower().strip(),
        "form": form,
        "concept_id": concept_id,
        "confidence": 0.95,
        "source": "manual",
        "provenance": PROVENANCE,
    }
    try:
        r = SESSION.post(
            f"{BASE}/terminology/surface-forms/upsert-mapping",
            json=body,
            timeout=30,
        )
        return "OK" if r.status_code in (200, 201) else f"FAIL({r.status_code})"
    except Exception as e:
        return f"ERR({e})"


print(f"Writing {len(SURFACE_FORMS)} batch-7 surface form mappings ...\n")
ok = fail = 0
for form, cid in SURFACE_FORMS:
    status = upsert_one(form, cid)
    marker = "  " if status == "OK" else "!!"
    print(f"{marker} [{status}] '{form}' -> {cid}")
    if status == "OK":
        ok += 1
    else:
        fail += 1

print(f"\nDone: {ok} OK, {fail} failed.")
