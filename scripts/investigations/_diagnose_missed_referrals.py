"""Diagnose why the 18 fast-track referral encounters were not coded.

Checks:
1. Encounter classification (admin_only / document_transfer / clinical)
2. Whether the encounter text would have been suppressed by the classifier
3. Whether the generic code 199251000000107 resolves correctly
4. Writes back the 5 generic '2WW referral' entries using the generic concept

Run:
    python scripts/investigations/_diagnose_missed_referrals.py
"""
from __future__ import annotations

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
from libs.auth.service_auth import get_service_auth_header
import requests

BASE = "http://localhost:8001"
SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

INVENTORY = ROOT / "scripts" / "investigations" / "encounter_audit" / "fast_track_referral_encounters.jsonl"

# Generic fast-track cancer referral concept
GENERIC_FTR_CONCEPT_ID = 199251000000107
GENERIC_FTR_NAME = "Fast track cancer referral (procedure)"

_Q_ENCOUNTER = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(e.id) = $eid
RETURN
    e.classification_content_type  AS classification,
    e.classification_model_a_type  AS classifier,
    coalesce(e.text, e.note, e.description, '') AS text,
    coalesce(toString(e.date), '')  AS date,
    toString(p.id) AS patient_id
"""

_Q_EXISTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid AND c.conceptId = $concept_id
RETURN count(r) AS n
"""

_Q_UPSERT_GENERIC = """
MATCH (e:Encounter {id: $encounter_id})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:Procedure {conceptId: $concept_id})
SET s.semanticTag  = 'procedure',
    s.name         = $name,
    s.source       = 'rule_based',
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {conceptId: $concept_id}]->(s)
SET r.coded_at          = datetime(),
    r.evidence          = $evidence,
    r.confidence        = $confidence,
    r.domain            = 'cancer',
    r.context           = $context,
    r.modifiers         = '{}',
    r.source            = 'rule_based',
    r.model_name        = 'rule_based_writeback',
    r.model_version     = '1.0',
    r.contract_version  = '1.0',
    r.run_id            = $run_id,
    r.audit_flag        = false,
    r.decision_tier     = 'auto',
    r.evidence_sentence = $evidence,
    r.evidence_start    = 0,
    r.evidence_end      = $ev_len,
    r.sentence_index    = 0,
    r.holdout           = false
MERGE (p)-[:HAS_PROCEDURE]->(s)
"""


def check_generic_code() -> bool:
    """Verify the generic fast-track cancer referral concept resolves."""
    print("=" * 70)
    print(f"Checking generic concept {GENERIC_FTR_CONCEPT_ID} ...")
    r = SESSION.post(
        f"{BASE}/terminology/resolve",
        json={"terms": [GENERIC_FTR_NAME, "fast track cancer referral", "fast track referral"]},
        timeout=20,
    )
    results = r.json().get("results") or {}
    for term, hits in results.items():
        top = hits[0] if hits else {}
        print(f"  {term!r}")
        print(f"    -> {top.get('snomed_concept_id')} | {top.get('snomed_term')} | score={top.get('score')}")
    print()
    return True


def classify_text(text: str) -> str:
    """Classify encounter text using the rule-based classifier."""
    from libs.classifiers.encounter_textcat import classify_text as _classify
    return _classify(text)


def diagnose_missed(rows: list[dict]) -> dict[str, list]:
    """Return {reason: [encounter_ids]} for each root-cause category."""
    from libs.neo4j_client.client import PatientGraphClient
    client = PatientGraphClient()
    reasons: dict[str, list] = {
        "admin_only_classification": [],
        "document_transfer_classification": [],
        "clinical_but_missed": [],
        "generic_2ww_no_site": [],
    }
    try:
        with client.session() as session:
            for row in rows:
                eid = row["encounter_id"]
                phrase = row.get("matched_phrase", "").lower()
                is_generic_2ww = phrase.startswith("2ww") or phrase.startswith("two week wait")

                rec = session.run(_Q_ENCOUNTER, eid=eid).single()
                if not rec:
                    continue

                saved_class = rec.get("classification") or ""
                enc_text = rec.get("text") or ""
                live_class = classify_text(enc_text) if enc_text else "empty"

                print(
                    f"  enc={eid}  saved={saved_class or 'not set'}"
                    f"  live={live_class}  phrase={phrase[:60]!r}"
                )
                if enc_text:
                    print(f"    text[:100]: {enc_text[:100]!r}")

                if is_generic_2ww:
                    reasons["generic_2ww_no_site"].append(eid)
                elif saved_class == "admin_only" or live_class == "admin_only":
                    reasons["admin_only_classification"].append(eid)
                elif saved_class == "document_transfer" or live_class == "document_transfer":
                    reasons["document_transfer_classification"].append(eid)
                else:
                    reasons["clinical_but_missed"].append(eid)
    finally:
        client.close()
    return reasons


def writeback_generic_2ww(rows: list[dict], run_id: str, dry_run: bool = False) -> int:
    """Write DOCUMENTS for generic 2WW encounters using the generic FTR concept."""
    from libs.neo4j_client.client import PatientGraphClient
    generic_rows = [
        r for r in rows
        if (r.get("matched_phrase", "").lower().startswith("2ww")
            or r.get("matched_phrase", "").lower().startswith("two week wait"))
        and r.get("referral_doc_count", 0) == 0
    ]

    if not generic_rows:
        print("No generic 2WW encounters to write.")
        return 0

    print(f"\nWriting generic FTR concept ({GENERIC_FTR_CONCEPT_ID}) for {len(generic_rows)} generic 2WW encounters ...")
    client = PatientGraphClient()
    written = 0
    try:
        with client.session() as session:
            for row in generic_rows:
                eid = row["encounter_id"]
                phrase = row.get("matched_phrase", "2WW referral")

                result = session.run(_Q_EXISTS, eid=eid, concept_id=GENERIC_FTR_CONCEPT_ID).single()
                if result and result["n"] > 0:
                    print(f"  [SKIP] enc={eid} already coded with generic concept")
                    continue

                if dry_run:
                    print(f"  [DRY ] enc={eid} -> {GENERIC_FTR_CONCEPT_ID} ({GENERIC_FTR_NAME})")
                    written += 1
                    continue

                try:
                    session.run(
                        _Q_UPSERT_GENERIC,
                        encounter_id=eid,
                        concept_id=GENERIC_FTR_CONCEPT_ID,
                        name=GENERIC_FTR_NAME,
                        evidence=phrase,
                        ev_len=len(phrase),
                        confidence=0.7,
                        context=json.dumps({"assertion": "present", "negated": False}),
                        run_id=run_id,
                    )
                    print(f"  [WRITE] enc={eid} -> {GENERIC_FTR_CONCEPT_ID} ({GENERIC_FTR_NAME})")
                    written += 1
                except Exception as exc:
                    print(f"  [ERROR] enc={eid}: {exc}")
    finally:
        client.close()
    return written


def main() -> None:
    check_generic_code()

    with INVENTORY.open() as fh:
        all_rows = [json.loads(l) for l in fh]

    uncoded = [r for r in all_rows if r.get("referral_doc_count", 0) == 0 and r.get("matched_phrase")]
    # Dedup by encounter_id for diagnosis
    seen: set[str] = set()
    unique_uncoded = []
    for r in uncoded:
        if r["encounter_id"] not in seen:
            seen.add(r["encounter_id"])
            unique_uncoded.append(r)

    print(f"Diagnosing {len(unique_uncoded)} uncoded encounters ...\n")
    reasons = diagnose_missed(unique_uncoded)

    print()
    print("=" * 70)
    print("Root cause summary:")
    for reason, eids in reasons.items():
        print(f"  {reason:<40}: {len(eids)}")

    run_id = str(uuid.uuid4())

    print()
    print("=" * 70)
    print("Writing generic 2WW encounters with 199251000000107 ...")
    written = writeback_generic_2ww(all_rows, run_id)
    print(f"Written: {written}")


if __name__ == "__main__":
    main()
