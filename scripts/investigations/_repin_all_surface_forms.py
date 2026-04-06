"""Re-pin ALL manual surface forms using the correct normalized property.

Previous upsert scripts used MERGE (sf:SurfaceForm {text: $form}) but the
resolver queries by {normalized: $normalized} where normalized is:
    " ".join(re.findall(r"[a-z0-9]+", form.lower()))

This script:
  1. Deletes all old 'text'-keyed SurfaceForm nodes we created
  2. Upserts them correctly using normalized as the primary key
  3. Covers: FTR referrals, mesothelioma, action concepts (endoscopy, PSA, etc.)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

PROV = "manual-fix-action-concepts"


def normalize_surface(text: str) -> str:
    """Mirror of CodingResolver.normalize_surface."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# ------------------------------------------------------------------ #
# Cypher - uses normalized as primary key (matches resolver)           #
# ------------------------------------------------------------------ #

_DELETE_OLD_TEXT_NODE = """
MATCH (sf:SurfaceForm {text: $text})
WHERE sf.normalized IS NULL
DETACH DELETE sf
RETURN count(sf) AS deleted
"""

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form       = $form,
              sf.source     = 'manual',
              sf.status     = 'active',
              sf.created_at = datetime()
SET sf.form = $form
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.created_at  = datetime(),
              r.approved_at = datetime()
SET r.confidence = $conf,
    r.provenance = $prov
RETURN sf.normalized AS normalized, sf.form AS form,
       c.id AS cid, r.confidence AS conf
"""

_DELETE_OTHER_MAPPINGS = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[r:MAPS_TO]->(c:Concept)
WHERE c.id <> $keep_cid
DELETE r
RETURN count(r) AS deleted
"""


# ------------------------------------------------------------------ #
# Surface form definitions                                             #
# (form_text, correct_concept_id, confidence)                         #
# ------------------------------------------------------------------ #

FORMS: list[tuple[str, str, float]] = [
    # ---- Fast-track cancer referrals -----------------------------------
    ("fast track referral for suspected sarcoma",                "276521000000103", 1.0),
    ("fast track referral for suspected lung cancer",            "276491000000101", 1.0),
    ("fast track referral for suspected skin cancer",            "276281000000104", 1.0),
    ("fast track referral for suspected brain tumour",           "276581000000102", 1.0),
    ("fast track referral for suspected breast cancer",          "276341000000100", 1.0),
    ("fast track referral for suspected childrens tumour",       "276371000000106", 1.0),
    ("fast track referral for suspected urological cancer",      "276431000000102", 1.0),
    ("fast track referral for suspected colorectal cancer",      "276401000000108", 1.0),
    ("fast track referral for suspected head and neck cancer",   "280521000000108", 1.0),
    ("fast track referral for suspected gynaecological cancer",  "276311000000101", 1.0),
    ("fast track referral for suspected haematology malignancy", "276461000000107", 1.0),
    ("fast track referral for suspected lower gastrointestinal cancer", "892201000000106", 1.0),
    ("fast track referral for suspected upper gastrointestinal cancer", "276551000000108", 1.0),
    ("fast track referral for suspected cancer due to non-site-specific symptoms", "1556551000000104", 1.0),
    # Mesothelioma -> lung cancer pathway (no separate UK code)
    ("fast track referral for suspected mesothelioma",           "276491000000101", 1.0),
    ("suspected mesothelioma referral",                          "276491000000101", 0.97),
    ("mesothelioma referral",                                    "276491000000101", 0.95),
    ("urgent referral for suspected mesothelioma",               "276491000000101", 0.95),
    # Site aliases
    ("fast track referral for suspected pancreatic cancer",      "276551000000108", 1.0),
    ("fast track referral for suspected stomach cancer",         "276551000000108", 1.0),
    ("fast track referral for suspected gastric cancer",         "276551000000108", 1.0),
    ("fast track referral for suspected oesophageal cancer",     "276551000000108", 1.0),
    ("fast track referral for suspected anal cancer",            "892201000000106", 1.0),
    ("fast track referral for suspected thyroid cancer",         "280521000000108", 1.0),
    ("fast track referral for suspected laryngeal cancer",       "280521000000108", 1.0),
    ("fast track referral for suspected myeloma",                "276461000000107", 1.0),
    ("fast track referral for suspected lymphoma",               "276461000000107", 1.0),
    # Bladder / prostate / kidney / testicular / cervical (urological/gynae)
    ("fast track referral for suspected bladder cancer",         "276431000000102", 1.0),
    ("fast track referral for suspected prostate cancer",        "276431000000102", 1.0),
    ("fast track referral for suspected kidney cancer",          "276431000000102", 1.0),
    ("fast track referral for suspected renal cancer",           "276431000000102", 1.0),
    ("fast track referral for suspected testicular cancer",      "276431000000102", 1.0),
    ("fast track referral for suspected cervical cancer",        "276311000000101", 1.0),
    ("fast track referral for suspected ovarian cancer",         "276311000000101", 1.0),
    ("fast track referral for suspected endometrial cancer",     "276311000000101", 1.0),
    ("fast track referral for suspected uterine cancer",         "276311000000101", 1.0),

    # ---- Upper GI endoscopy (OGD) --------------------------------------
    ("direct access upper gastrointestinal endoscopy",  "76009000", 1.0),
    ("upper gastrointestinal endoscopy",                "76009000", 1.0),
    ("direct access endoscopy",                         "76009000", 1.0),
    ("direct access upper GI endoscopy",                "76009000", 1.0),
    ("oesophagogastroduodenoscopy",                     "76009000", 1.0),
    ("OGD",                                             "76009000", 1.0),
    ("gastroscopy",                                     "76009000", 1.0),
    ("upper GI endoscopy",                              "76009000", 1.0),
    ("upper GI scope",                                  "76009000", 0.97),

    # ---- PSA -----------------------------------------------------------
    ("PSA test",         "63476009", 1.0),
    ("PSA",              "63476009", 0.97),
    ("PSA measurement",  "63476009", 1.0),
    ("serum PSA",        "63476009", 1.0),
    ("PSA level",        "63476009", 0.97),

    # ---- Ultrasound ----------------------------------------------------
    ("urgent ultrasound",                        "16310003", 1.0),
    ("urgent direct access ultrasound",          "16310003", 1.0),
    ("direct access ultrasound",                 "16310003", 1.0),
    ("urgent ultrasound scan",                   "16310003", 1.0),
    ("urgent abdominal ultrasound",              "45036003", 1.0),
    ("urgent direct access abdominal ultrasound","45036003", 1.0),
    ("urgent abdominal ultrasound scan",         "45036003", 1.0),
    ("urgent liver ultrasound",                  "105377009", 1.0),
    ("abdominal and pelvic ultrasound",          "45036003", 0.97),
    ("ultrasound abdomen and pelvis",            "45036003", 0.97),
    ("urgent neck ultrasound",                   "241453007", 1.0),
    ("neck ultrasound",                          "241453007", 1.0),
    ("thyroid ultrasound",                       "241453007", 0.97),

    # ---- CA-125 --------------------------------------------------------
    ("CA125",             "909121000000107", 1.0),
    ("CA 125",            "909121000000107", 1.0),
    ("CA-125",            "909121000000107", 1.0),
    ("CA125 measurement", "909121000000107", 1.0),
    ("CA125 test",        "909121000000107", 1.0),
    ("serum CA125",       "909121000000107", 1.0),

    # ---- Urine dipstick ------------------------------------------------
    ("urine dipstick",      "167226008", 1.0),
    ("urine dipstick test", "167226008", 1.0),
    ("urinalysis dipstick", "167226008", 0.97),

    # ---- Full blood count (procedure preferred for action context) ------
    ("full blood count",    "26604007", 1.0),
    ("FBC",                 "26604007", 1.0),

    # ---- Faecal occult blood -------------------------------------------
    ("faecal occult blood test", "104435004", 1.0),
    ("fecal occult blood test",  "104435004", 1.0),
    ("FOB test",                 "104435004", 1.0),
    ("FOBT",                     "104435004", 1.0),
    ("occult blood test",        "104435004", 0.97),
]


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    print(f"Pinning {len(FORMS)} surface forms with correct normalized property ...\n")
    ok = fail = cleaned = 0

    with driver.session() as s:
        for form, cid, conf in FORMS:
            normalized = normalize_surface(form)

            # Remove stale text-only nodes from earlier incorrect upserts
            r = list(s.run(_DELETE_OLD_TEXT_NODE, text=form))
            deleted_stale = r[0]["deleted"] if r else 0
            if deleted_stale:
                print(f"  CLEAN {form!r} (removed stale text-keyed node)")
                cleaned += deleted_stale

            # Upsert with correct normalized key
            rows = list(s.run(_UPSERT, normalized=normalized, form=form,
                               cid=cid, conf=conf, prov=PROV))
            if rows:
                # Ensure no competing mappings from other provenances
                s.run(_DELETE_OTHER_MAPPINGS, normalized=normalized, keep_cid=cid)
                ok += 1
            else:
                print(f"  MISS  {form!r} -> concept {cid} not found")
                fail += 1

    driver.close()
    print(f"\nDone.  OK={ok}  MISS={fail}  Stale nodes cleaned={cleaned}")

    # ------------------------------------------------------------------ #
    # Verify via live resolver                                             #
    # ------------------------------------------------------------------ #
    print("\nSpot-check via live resolver:")
    checks = [
        ("fast track referral for suspected lung cancer",       "276491000000101"),
        ("fast track referral for suspected pancreatic cancer", "276551000000108"),
        ("fast track referral for suspected mesothelioma",      "276491000000101"),
        ("direct access upper gastrointestinal endoscopy",      "76009000"),
        ("OGD",                                                  "76009000"),
        ("gastroscopy",                                          "76009000"),
        ("PSA test",                                             "63476009"),
        ("PSA",                                                  "63476009"),
        ("urgent ultrasound",                                    "16310003"),
        ("CA125",                                                "909121000000107"),
        ("urine dipstick",                                       "167226008"),
        ("full blood count",                                     "26604007"),
        ("faecal occult blood test",                             "104435004"),
        ("FOBT",                                                 "104435004"),
        ("FBC",                                                  "26604007"),
    ]
    try:
        resp = requests.post(
            "http://localhost:8001/terminology/resolve",
            json={"terms": [t for t, _ in checks], "top_k": 1},
            timeout=90,
        )
        if not resp.ok:
            print(f"  Resolver returned {resp.status_code}")
            return
        results = resp.json().get("results", {})
        passed = 0
        for term, expected in checks:
            candidates = results.get(term, [])
            got = candidates[0].get("snomed_concept_id") if candidates else "?"
            got_term = (candidates[0].get("snomed_term") or "?")[:50] if candidates else "?"
            status = "PASS" if got == expected else "FAIL"
            if status == "PASS":
                passed += 1
                print(f"  [PASS] {term!r}")
            else:
                print(f"  [FAIL] {term!r}")
                print(f"         got={got} | {got_term}")
                print(f"         want={expected}")
        print(f"\n  {passed}/{len(checks)} passed")
    except Exception as exc:
        print(f"  Resolver check skipped: {exc}")


if __name__ == "__main__":
    main()
