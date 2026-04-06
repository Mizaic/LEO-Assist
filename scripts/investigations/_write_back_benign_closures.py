"""Write back 'No evidence of cancer found' (SNOMED 395100000) to specific
encounters for patients whose cancer 2WW investigations concluded benignly
but where this outcome was not captured in the GP record as a coded concept.

Source: 39-patient manual encounter review 2026-04-06.
Each entry was manually verified from the encounter text in the review files:
  - scripts/investigations/encounter_audit/no_diagnosis_1yr_review.txt
  - scripts/investigations/encounter_audit/referral_only_review.txt
  - scripts/investigations/encounter_audit/missing_patients_review.txt
  - scripts/investigations/encounter_audit/outcome_findings_39_patients.md

Run (dry run first):
    python scripts/investigations/_write_back_benign_closures.py --dry-run

Run (apply):
    python scripts/investigations/_write_back_benign_closures.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

# ---------------------------------------------------------------------------
# Write-back targets: (patient_id, from_date, to_date, evidence_phrase)
# from_date / to_date are inclusive ISO strings used to find the encounter.
# The encounter with the earliest matching date in the window receives the tag.
# ---------------------------------------------------------------------------
_TARGETS: list[tuple[str, str, str, str]] = [
    # Patient 4621680811 -- 2WW haematology (lymphoma pathway)
    # Evidence: "seen by haem- nil concerns raised about malig ... will likely be discharged"
    # GP note 2025-07-08
    (
        "4621680811",
        "2025-07-07",
        "2025-07-09",
        "seen by haem - nil concerns raised about malignancy, likely to be discharged",
    ),
    # Patient 7343840665 -- 2WW children's tumour pathway
    # Evidence: "Was seen on 2WW, nad so safe to administer live vaccine" 2024-11-20
    (
        "7343840665",
        "2024-11-19",
        "2024-11-21",
        "Was seen on 2WW, NAD -- safe to administer live vaccine",
    ),
    # Patient 7330683205 -- 2WW upper GI
    # Evidence: "has had OGD - shows small hiatus hernia only" GP note 2025-08-04
    (
        "7330683205",
        "2025-08-03",
        "2025-08-05",
        "OGD shows small hiatus hernia only - no upper GI malignancy",
    ),
    # Patient 4883794091 -- 2WW upper GI
    # Evidence: "Had endoscopy yearday which was normal. Paper report seen." GP 2025-07-17
    (
        "4883794091",
        "2025-07-16",
        "2025-07-18",
        "Endoscopy was normal - no upper GI malignancy on investigation",
    ),
    # Patient 4866803525 -- 2WW head and neck
    # Evidence: Presbycusis diagnosed, nasendoscopy/audiometry normal, ENT discharged
    # Seen in 2WW H&N clinic 2025-03-13; ENT discharged
    (
        "4866803525",
        "2025-03-12",
        "2025-03-14",
        "Seen in 2WW head and neck clinic - Presbycusis diagnosed, no malignancy found",
    ),
    # Patient 4808735946 -- 2WW lower GI (colorectal)
    # Evidence: "Tubular adenoma (Xa98X) - colonic - excised 01/05/25" 2025-05-27
    # Tubular adenoma is non-malignant; excised; colonoscopy otherwise NAD
    (
        "4808735946",
        "2025-05-26",
        "2025-05-28",
        "Tubular adenoma excised - no colorectal malignancy found on colonoscopy",
    ),
    # Patient 6519712760 -- 2WW lower GI
    # Evidence: Haemorrhoids confirmed on colonoscopy as cause of PR bleeding; FIT 12
    # Colonoscopy 2024-12-29
    (
        "6519712760",
        "2024-12-28",
        "2024-12-30",
        "Colonoscopy confirmed haemorrhoids as cause - no colorectal malignancy",
    ),
    # Patient 7319972905 -- 2WW head and neck
    # Evidence: "US scan of thyroid - mildly enlarged, otherwise NAD" + "US scan of neck - NAD"
    # Seen in 2WW H&N clinic 2025-06-25; USS on same day
    (
        "7319972905",
        "2025-06-24",
        "2025-06-26",
        "USS neck NAD, USS thyroid mildly enlarged otherwise NAD - no head and neck malignancy",
    ),
    # Patient 4983118659 -- 2WW upper GI (mislabelled lower_gi in episode)
    # Evidence: "no dysplasia or malignancy" (ICE result) GP note 2025-03-06
    (
        "4983118659",
        "2025-03-05",
        "2025-03-07",
        "OGD biopsy result - no dysplasia or malignancy",
    ),
    # Patient 7321643565 -- 2WW haematological episode
    # Evidence: "colonoscopy - polyp removed but no cancer" PCN note 2025-03-22
    (
        "7321643565",
        "2025-03-21",
        "2025-03-23",
        "colonoscopy - polyp removed but no cancer found",
    ),
    # Patient 4246428337 -- 2WW lower GI
    # Evidence: Ulcerative colitis diagnosed as cause of symptoms (alternative benign dx)
    # Colonoscopy 2025-08-11 coded UC, not cancer
    (
        "4246428337",
        "2025-08-10",
        "2025-08-12",
        "Colonoscopy - ulcerative colitis diagnosed, no colorectal malignancy",
    ),
    # Patient 4185994966 -- 2WW head and neck (also breast 2WW -> fibroadenoma)
    # Evidence H&N: globus sensation, normal nasendoscopy, no malignancy
    # Seen in 2WW H&N clinic 2025-01-24
    (
        "4185994966",
        "2025-01-23",
        "2025-01-25",
        "Seen in 2WW head and neck clinic - globus sensation, no malignancy found",
    ),
    # Patient 4220526579 -- gynae 2WW (USS pelvis NAD 3mm endometrium, HPV neg)
    # USS report received around 2024-07-19
    (
        "4220526579",
        "2024-07-18",
        "2024-07-20",
        "USS pelvis NAD, endometrium 3mm, HPV not detected - no gynaecological malignancy",
    ),
    # Patient 6280880796 -- upper GI 2WW
    # Evidence: "Biopsy shows iron pill gastritis" GP note 2025-04-02
    (
        "6280880796",
        "2025-04-01",
        "2025-04-03",
        "Gastric biopsy shows iron pill gastritis only - no upper GI malignancy",
    ),
    # Patient 6264541699 -- urology 2WW (PSA raised)
    # Evidence: Seen in 2WW urology clinic 2025-08-11; annual PSA surveillance plan
    # GP note 2025-09-24: "Annual PSA check as per letter 11/08/2025"
    (
        "6264541699",
        "2025-09-23",
        "2025-09-25",
        "Annual PSA monitoring plan after 2WW - no urological cancer diagnosed",
    ),
    # Patient 4822890058 -- head and neck 2WW
    # Evidence: Endocrine follow-up (thyrotoxicosis) after H&N 2WW; no malignancy
    # ENT letter 2025-02-10
    (
        "4822890058",
        "2025-02-09",
        "2025-02-11",
        "ENT 2WW clinic - thyroid nodule and thyrotoxicosis, no malignancy found",
    ),
]

# -- Cypher queries -----------------------------------------------------------

_FIND_ENCOUNTER_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND toString(e.date) >= $from_date
  AND toString(e.date) <= $to_date
RETURN toString(e.id) AS eid, toString(e.date) AS edate
ORDER BY edate
LIMIT 5
"""

_CHECK_CODED_Q = """
MATCH (e:Encounter {id: $eid})-[:DOCUMENTS]->(c)
WHERE c.conceptId = $concept_id
RETURN count(c) AS already_coded
"""

_WRITE_BACK_Q = """
MATCH (e:Encounter {id: $eid})
MATCH (c) WHERE c.conceptId = $concept_id
MERGE (e)-[r:DOCUMENTS]->(c)
ON CREATE SET
    r.assertion    = 'present',
    r.source       = 'audit_write_back',
    r.confidence   = 0.95,
    r.evidence     = $evidence
RETURN toString(e.id) AS eid, toString(e.date) AS edate, type(r) AS rel
"""

_NO_CANCER_CONCEPT_ID = 395100000


def _run(client, query: str, **params) -> list[dict]:
    try:
        return client.run(query, **params) or []
    except Exception as exc:
        print(f"    [ERROR] query failed: {exc}", file=sys.stderr)
        return []


def process(dry_run: bool = True) -> None:
    from libs.neo4j_client.client import PatientGraphClient

    client = PatientGraphClient()
    total = written = skipped = not_found = 0

    for patient_id, from_date, to_date, evidence in _TARGETS:
        total += 1
        print(f"\n  pid={patient_id}  window={from_date} -> {to_date}")
        print(f"  evidence: {evidence[:80]}")

        encs = _run(client, _FIND_ENCOUNTER_Q,
                    patient_id=patient_id, from_date=from_date, to_date=to_date)
        if not encs:
            print(f"    [SKIP] No encounters found in date window")
            not_found += 1
            continue

        # Use the first (earliest) encounter in the window
        enc = encs[0]
        eid = enc["eid"]
        edate = enc["edate"]
        print(f"    target encounter: {eid[:8]}... date={edate} ({len(encs)} in window)")

        already = _run(client, _CHECK_CODED_Q,
                       eid=eid, concept_id=_NO_CANCER_CONCEPT_ID)
        if already and already[0].get("already_coded", 0) > 0:
            print(f"    [SKIP] 395100000 already coded on this encounter")
            skipped += 1
            continue

        if dry_run:
            print(f"    [DRY ] would write 395100000 to enc={eid[:8]}...")
            written += 1
            continue

        rows = _run(client, _WRITE_BACK_Q,
                    eid=eid,
                    concept_id=_NO_CANCER_CONCEPT_ID,
                    evidence=evidence)
        if rows:
            print(f"    [DONE] wrote 395100000 -> enc={eid[:8]}... date={edate}")
            written += 1
        else:
            print(f"    [FAIL] write returned no rows -- check concept node exists")
            not_found += 1

    print()
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"[{mode}] total={total}  written={written}  skipped_already_coded={skipped}  not_found={not_found}")
    if dry_run:
        print("Re-run with --apply to commit writes to Neo4j.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to Neo4j (default is dry run)",
    )
    args = parser.parse_args()
    process(dry_run=not args.apply)
