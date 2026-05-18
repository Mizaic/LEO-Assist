"""Pin surface forms and write DOCUMENTS for the 3 confirmed cancer-exclusion encounters.

Confirmed encounters (manually reviewed against full encounter text):
  1. 9990010025 / 15911be4  - post-OGD: "no malignancy found"
  2. 9990010029 / 1783873c  - Brain Triage: "Cancer excluded - discharge to GP"
  3. 9990010043 / 8fbb5daf  - post-colonoscopy: "no malignancy detected"

Run:
    python scripts/investigations/_code_no_cancer_confirmed.py --dry-run
    python scripts/investigations/_code_no_cancer_confirmed.py
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

CONCEPT_ID = 395100000
CONCEPT_NAME = "No evidence of cancer found (situation)"
CONCEPT_TAG = "situation"
REL_TYPE = "HAS_SITUATION"

# The 3 confirmed encounters: (patient_id, encounter_id, evidence_text)
CONFIRMED = [
    (
        "9990010025",
        "15911be4-fc30-4de8-bb0c-8f54f3cb50f0",
        "no malignancy found",
        "OGD result: recent upper GI referral, OGD okay, hiatus hernia found, no malignancy found.",
    ),
    (
        "9990010029",
        "1783873c-6be2-4682-874d-21f17d905e1f",
        "cancer excluded",
        "Brain Triage: Cancer excluded - discharge to GP. No structural cause for symptoms demonstrated.",
    ),
    (
        "9990010043",
        "8fbb5daf-7bb7-411b-97f0-00c50b82ca1d",
        "no malignancy detected",
        "Screening colonoscopy-polypectomy August 2019: no malignancy detected.",
    ),
]

# Surface forms to pin -- phrases that should reliably map to 395100000
# (exclusion language only; post-diagnosis/surveillance phrases are excluded)
SURFACE_FORM_PINS = [
    "no evidence of cancer",
    "no evidence of cancer found",
    "no evidence of malignancy",
    "no malignancy",
    "no malignancy found",
    "no malignancy detected",
    "no malignancy seen",
    "negative for malignancy",
    "neg for malignancy",
    "negative for cancer",
    "malignancy excluded",
    "cancer excluded",
    "sarcoma excluded",
    "malignancy ruled out",
    "cancer ruled out",
    "sarcoma ruled out",
    "no malignant cells",
    "no malignant cells seen",
    "negative for malignant cells",
    "no evidence of malignant cells",
    "no evidence of neoplasm",
    "no neoplasm detected",
    "no evidence of tumour",
    "no evidence of tumor",
    "no evidence of carcinoma",
    "no evidence of sarcoma",
    "malignancy not identified",
    "cancer not identified",
    "malignancy not seen",
    "cancer not seen",
    "does not suggest malignancy",
    "does not support malignancy",
    "not in keeping with malignancy",
    "not in keeping with cancer",
    "in keeping with benign",
    "argues against malignancy",
    "inconsistent with malignancy",
    "inconsistent with cancer",
    "malignancy unlikely",
    "cancer unlikely",
    "benign histology",
    "benign on histology",
    "benign pathology",
    "benign on pathology",
    "benign cytology",
    "biopsy benign",
    "biopsy negative for malignancy",
    "histology benign",
    "histology negative for malignancy",
    "cytology benign",
    "cytology negative for malignancy",
    "no histological evidence of malignancy",
    "no pathological evidence of malignancy",
    "no neoplastic cells",
    "no tumour cells seen",
    "no tumor cells seen",
    "features are benign",
    "findings are benign",
]

_Q_UPSERT = """
MATCH (e:Encounter {id: $encounter_id})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:Situation {conceptId: $concept_id})
SET s.semanticTag  = $semantic_tag,
    s.name         = $name,
    s.source       = 'rule_based',
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {conceptId: $concept_id}]->(s)
SET r.coded_at          = datetime(),
    r.evidence          = $evidence,
    r.evidence_sentence = $evidence_sentence,
    r.confidence        = $confidence,
    r.domain            = 'cancer',
    r.context           = $context,
    r.modifiers         = '{}',
    r.source            = 'rule_based',
    r.model_name        = 'no-cancer-phrase-audit',
    r.model_version     = '1.0',
    r.contract_version  = '1.0',
    r.run_id            = $run_id,
    r.audit_flag        = false,
    r.decision_tier     = 'auto',
    r.evidence_start    = 0,
    r.evidence_end      = $ev_len,
    r.sentence_index    = 0,
    r.holdout           = false
MERGE (p)-[:HAS_SITUATION]->(s)
"""

_Q_EXISTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid AND c.conceptId = $cid
RETURN count(r) AS n
"""


def pin_surface_forms(dry_run: bool) -> None:
    from libs.auth.service_auth import get_service_auth_header
    import requests
    from libs.terminology.surface_normalize import normalize_surface

    session = requests.Session()
    session.headers.update(get_service_auth_header())
    base = "http://localhost:8001"

    print(
        f"Pinning {len(SURFACE_FORM_PINS)} surface forms -> {CONCEPT_ID} ({CONCEPT_NAME})"
    )
    ok_count = fail_count = skip_count = 0

    for form in SURFACE_FORM_PINS:
        if dry_run:
            print(f"  [DRY ] {form!r}")
            skip_count += 1
            continue
        norm = normalize_surface(form)
        payload = {
            "form": form,
            "normalized": norm,
            "concept_id": str(CONCEPT_ID),
            "confidence": 1.0,
            "source": "manual",
            "provenance": "no-cancer-phrase-audit-2026-04-06",
        }
        try:
            r = session.post(
                f"{base}/terminology/surface-forms/upsert-mapping",
                json=payload,
                timeout=60,
            )
            ok = r.status_code in (200, 201, 204)
            print(f"  [{'OK  ' if ok else 'FAIL'}] HTTP {r.status_code}  {form!r}")
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        except Exception as exc:
            print(f"  [ERR ] {form!r}: {exc}")
            fail_count += 1

    if dry_run:
        print(f"DRY RUN: would pin {skip_count} forms.")
    else:
        print(f"Pinned: {ok_count}  Failed: {fail_count}")


def write_documents(dry_run: bool, run_id: str) -> None:
    from libs.neo4j_client.client import PatientGraphClient

    print(f"\nWriting DOCUMENTS for {len(CONFIRMED)} confirmed encounters ...")
    client = PatientGraphClient()
    written = 0
    skipped = 0

    try:
        with client.session() as session:
            for patient_id, encounter_id, evidence, full_sentence in CONFIRMED:
                existing = session.run(
                    _Q_EXISTS, eid=encounter_id, cid=CONCEPT_ID
                ).single()
                if existing and existing["n"] > 0:
                    print(f"  [SKIP] enc={encounter_id[:8]}  already coded")
                    skipped += 1
                    continue

                if dry_run:
                    print(
                        f"  [DRY ] enc={encounter_id[:8]}  pid={patient_id}  ev={evidence!r}"
                    )
                    written += 1
                    continue

                session.run(
                    _Q_UPSERT,
                    encounter_id=encounter_id,
                    concept_id=CONCEPT_ID,
                    semantic_tag=CONCEPT_TAG,
                    name=CONCEPT_NAME,
                    evidence=evidence,
                    evidence_sentence=full_sentence,
                    ev_len=len(full_sentence),
                    confidence=0.95,
                    context=json.dumps({"assertion": "present", "negated": False}),
                    run_id=run_id,
                )
                print(
                    f"  [WRITE] enc={encounter_id[:8]}  pid={patient_id}  ev={evidence!r}"
                )
                written += 1
    finally:
        client.close()

    tag = "DRY RUN" if dry_run else "DONE"
    print(f"\n{tag}: written={written}  skipped={skipped}")


def main(dry_run: bool) -> None:
    run_id = str(uuid.uuid4())
    print(f"Run ID: {run_id}  dry_run={dry_run}")
    print()

    pin_surface_forms(dry_run)
    write_documents(dry_run, run_id)

    if not dry_run:
        print("\nVerifying ...")
        from libs.neo4j_client.client import PatientGraphClient

        client = PatientGraphClient()
        with client.session() as s:
            for _, eid, evidence, _ in CONFIRMED:
                r = s.run(_Q_EXISTS, eid=eid, cid=CONCEPT_ID).single()
                coded = r["n"] > 0 if r else False
                print(f"  enc={eid[:8]}  coded={coded}  ev={evidence!r}")
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
