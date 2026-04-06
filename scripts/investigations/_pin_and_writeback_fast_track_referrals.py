"""Fix mismapped surface forms and write back uncoded fast-track referral encounters.

Two jobs:
1. PIN: fix the 'lower GI' surface form aliases that the resolver mismatches to upper GI.
2. WRITEBACK: write DOCUMENTS + HAS_PROCEDURE relationships for the 18 encounters
   that have a referral phrase in text but no matching DOCUMENTS relationship.

Run:
    python scripts/investigations/_pin_and_writeback_fast_track_referrals.py

    # Dry-run (no writes):
    python scripts/investigations/_pin_and_writeback_fast_track_referrals.py --dry-run
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
from libs.auth.service_auth import get_service_auth_header
from libs.terminology.surface_normalize import normalize_surface
import requests

BASE = "http://localhost:8001"
PROVENANCE = "pin-fast-track-referral-aliases-2026-04-06"
INVENTORY = ROOT / "scripts" / "investigations" / "encounter_audit" / "fast_track_referral_encounters.jsonl"

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# ---------------------------------------------------------------------------
# Surface forms that need pinning or correcting
# ---------------------------------------------------------------------------
_FIX_PINS = [
    # "lower GI" aliases were resolving to upper GI -- fix to lower GI
    (
        "fast track referral for suspected lower gi cancer",
        "892201000000106",
        "Fast track referral for suspected lower gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected lower gastrointestinal cancer",
        "892201000000106",
        "Fast track referral for suspected lower gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected lower gi",
        "892201000000106",
        "Fast track referral for suspected lower gastrointestinal cancer (procedure)",
    ),
    # "upper GI" aliases -- confirm correct mapping
    (
        "fast track referral for suspected upper gi cancer",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
    (
        "fast track referral for suspected upper gi",
        "276551000000108",
        "Fast track referral for suspected upper gastrointestinal cancer (procedure)",
    ),
]

# Phrase -> concept_id lookup (built from the resolved results)
_PHRASE_MAP = {
    normalize_surface("2ww referral"): ("306206005", "Referral to service (procedure)", "Situation"),
    normalize_surface("2ww Referral"): ("306206005", "Referral to service (procedure)", "Situation"),
    normalize_surface("fast track referral for suspected brain tumour"): ("276581000000102", "Fast track referral for suspected brain tumour (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected breast cancer"): ("276341000000100", "Fast track referral for suspected breast cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected cancer due to non-site-specific symptoms"): ("1556551000000104", "Fast track referral for suspected cancer due to non-site-specific symptoms (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected childrens tumour"): ("276371000000106", "Fast track referral for suspected childrens tumour (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected colorectal cancer"): ("276401000000108", "Fast track referral for suspected colorectal cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected gynaecological cancer"): ("276311000000101", "Fast track referral for suspected gynaecological cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected haematology malignancy"): ("276461000000107", "Fast track referral for suspected haematology malignancy (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected haematological malignancy"): ("276461000000107", "Fast track referral for suspected haematology malignancy (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected head and neck cancer"): ("280521000000108", "Fast track referral for suspected head and neck cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected lower gi cancer"): ("892201000000106", "Fast track referral for suspected lower gastrointestinal cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected lower gastrointestinal cancer"): ("892201000000106", "Fast track referral for suspected lower gastrointestinal cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected lung cancer"): ("276491000000101", "Fast track referral for suspected lung cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected skin cancer"): ("276281000000104", "Fast track referral for suspected skin cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected upper gi cancer"): ("276551000000108", "Fast track referral for suspected upper gastrointestinal cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected upper gastrointestinal cancer"): ("276551000000108", "Fast track referral for suspected upper gastrointestinal cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected urological cancer"): ("276431000000102", "Fast track referral for suspected urological cancer (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected sarcoma"): ("276521000000103", "Fast track referral for suspected sarcoma (procedure)", "Procedure"),
    normalize_surface("fast track referral for suspected gynaecological cancer"): ("276311000000101", "Fast track referral for suspected gynaecological cancer (procedure)", "Procedure"),
}

# Cypher: DOCUMENTS write for procedures
_LABEL = "Procedure"
_REL_TYPE = "HAS_PROCEDURE"

_Q_EXISTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid AND c.conceptId = $concept_id
RETURN count(r) AS n
"""

_Q_UPSERT = f"""
MATCH (e:Encounter {{id: $encounter_id}})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:{_LABEL} {{conceptId: $concept_id}})
SET s.semanticTag  = $semantic_tag,
    s.name         = $name,
    s.source       = $source,
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {{conceptId: $concept_id}}]->(s)
SET r.coded_at          = datetime(),
    r.evidence          = $evidence,
    r.confidence        = $confidence,
    r.domain            = $domain,
    r.context           = $context,
    r.modifiers         = $modifiers,
    r.value             = null,
    r.unit              = null,
    r.referenceRange    = null,
    r.source            = $source,
    r.model_name        = $model_name,
    r.model_version     = $model_version,
    r.contract_version  = $contract_version,
    r.run_id            = $run_id,
    r.audit_flag        = false,
    r.decision_tier     = 'auto',
    r.evidence_sentence = $evidence,
    r.evidence_start    = 0,
    r.evidence_end      = $ev_len,
    r.sentence_index    = 0,
    r.holdout           = false
MERGE (p)-[:{_REL_TYPE}]->(s)
"""


def _upsert_surface_form(form: str, concept_id: str, label: str) -> bool:
    payload = {
        "form": form,
        "normalized": normalize_surface(form),
        "concept_id": concept_id,
        "confidence": 1.0,
        "source": "manual",
        "provenance": PROVENANCE,
    }
    try:
        r = SESSION.post(f"{BASE}/terminology/surface-forms/upsert-mapping", json=payload, timeout=30)
        return r.status_code in (200, 201)
    except Exception:
        return False


def _resolve(phrase: str) -> dict | None:
    norm = normalize_surface(phrase)
    hit = _PHRASE_MAP.get(norm)
    if hit:
        cid, name, sem_tag = hit
        return {"concept_id": int(cid), "name": name, "semantic_tag": sem_tag}
    # Fallback: ask terminology server
    try:
        r = SESSION.post(f"{BASE}/terminology/resolve", json={"terms": [phrase]}, timeout=20)
        hits = (r.json().get("results") or {}).get(phrase) or []
        top = hits[0] if hits else {}
        cid = top.get("snomed_concept_id")
        if not cid:
            return None
        tag = top.get("semantic_tag", "procedure")
        label_map = {"finding": "Clinical_finding", "procedure": "Procedure", "situation": "Situation"}
        sem_label = label_map.get(tag.lower(), "Procedure")
        return {"concept_id": int(cid), "name": top.get("snomed_term", phrase), "semantic_tag": sem_label}
    except Exception:
        return None


def step1_pin(dry_run: bool) -> None:
    print("=" * 70)
    print("Step 1 -- Pin / fix surface form aliases")
    print("=" * 70)
    ok = fail = 0
    for form, cid, label in _FIX_PINS:
        if dry_run:
            print(f"  [DRY ] Would pin {form!r} -> {cid}")
            ok += 1
            continue
        success = _upsert_surface_form(form, cid, label)
        if success:
            print(f"  [PIN ] {form!r} -> {cid} ({label})")
            ok += 1
        else:
            print(f"  [FAIL] {form!r}")
            fail += 1

    print(f"\nPinned: {ok}  Failed: {fail}")
    if fail:
        sys.exit(1)


def step2_writeback(dry_run: bool) -> None:
    print()
    print("=" * 70)
    print("Step 2 -- Writeback missing DOCUMENTS for uncoded encounters")
    print("=" * 70)

    with INVENTORY.open() as fh:
        rows = [json.loads(l) for l in fh]

    # Only process rows where referral_doc_count == 0 (no referral DOCUMENTS yet)
    uncoded = [r for r in rows if r.get("referral_doc_count", 0) == 0 and r.get("matched_phrase")]
    # Dedup by (encounter_id, phrase)
    seen: set[tuple] = set()
    deduped = []
    for row in uncoded:
        key = (row["encounter_id"], row["matched_phrase"].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    print(f"Uncoded encounters to process: {len(deduped)}")
    print()

    if not deduped:
        print("Nothing to write -- all referral encounters already coded.")
        return

    from libs.neo4j_client.client import PatientGraphClient
    run_id = str(uuid.uuid4())
    written = skipped = failed = no_concept = 0

    client = PatientGraphClient()
    try:
        with client.session() as session:
            for row in deduped:
                phrase = row["matched_phrase"].strip()
                encounter_id = row["encounter_id"]

                # Skip generic "2WW referral" -- too non-specific for a DOCUMENTS write
                if phrase.lower().startswith("2ww") or phrase.lower().startswith("two week wait"):
                    print(f"  [SKIP] enc={encounter_id} -- generic 2WW phrase, no specific concept")
                    skipped += 1
                    continue

                concept = _resolve(phrase)
                if not concept:
                    print(f"  [NO CONCEPT] enc={encounter_id} phrase={phrase!r}")
                    no_concept += 1
                    continue

                result = session.run(_Q_EXISTS, eid=encounter_id, concept_id=concept["concept_id"]).single()
                if result and result["n"] > 0:
                    print(f"  [SKIP] enc={encounter_id} concept={concept['concept_id']} already coded")
                    skipped += 1
                    continue

                params = {
                    "encounter_id": encounter_id,
                    "concept_id": concept["concept_id"],
                    "semantic_tag": concept["semantic_tag"],
                    "name": concept["name"],
                    "source": "rule_based",
                    "evidence": phrase,
                    "ev_len": len(phrase),
                    "confidence": 1.0,
                    "domain": "cancer",
                    "context": json.dumps({"assertion": "present", "negated": False,
                                           "historical": False, "hypothetical": False}),
                    "modifiers": json.dumps({}),
                    "model_name": "rule_based_writeback",
                    "model_version": "1.0",
                    "contract_version": "1.0",
                    "run_id": run_id,
                }

                if dry_run:
                    print(f"  [DRY ] enc={encounter_id} -> {concept['concept_id']} ({concept['name']})")
                    written += 1
                    continue

                try:
                    session.run(_Q_UPSERT, **params)
                    print(f"  [WRITE] enc={encounter_id} -> {concept['concept_id']} ({concept['name']})")
                    written += 1
                except Exception as exc:
                    print(f"  [ERROR] enc={encounter_id}: {exc}")
                    failed += 1
    finally:
        client.close()

    print()
    print("=" * 70)
    verb = "Would write" if dry_run else "Written"
    print(f"{verb}: {written}  Skipped: {skipped}  No concept: {no_concept}  Errors: {failed}")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    step1_pin(args.dry_run)
    step2_writeback(args.dry_run)


if __name__ == "__main__":
    main()
