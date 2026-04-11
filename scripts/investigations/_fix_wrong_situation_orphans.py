"""Fix the 215 'wrong situation orphans' -- GCL situation edges with no
better alternative, where the form text does NOT imply a historical/absence
context.

Three targeted operations:

  A. Delete ALL GCL edges to 415036007 (Parent has physical disability)
     where the surface form text does NOT contain 'parent'.
     These are patient neurological findings (hemiplegia, SCI, paraplegia
     etc.) wrongly mapped to a parent-context situation concept.

  B. Delete GCL edges to known wrong history-of situations where:
     - the form text has no history/past prefix, AND
     - the situation concept does NOT match the clinical domain of the form
       (e.g. 'Asthma' -> History of COPD, or 'Lupus' -> History of CTD).

  C. Upsert correct active-disorder concept IDs for high-priority forms
     that need an explicit mapping after deletion (not just fulltext fallback).

Usage
-----
  python scripts/investigations/_fix_wrong_situation_orphans.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import requests
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")
_API = "http://localhost:8001"
_TOKEN = os.getenv("SERVICE_TOKEN", "")

# ---------------------------------------------------------------------------
# A: Delete ALL GCL edges to 'Parent has physical disability' unless form
#    literally mentions 'parent' in it
# ---------------------------------------------------------------------------
_COUNT_PARENT_DISABILITY = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: '415036007'})
WHERE m.provenance = 'guideline_config_loader'
  AND NOT toLower(sf.form) CONTAINS 'parent'
RETURN count(m) AS n, collect(sf.form)[..15] AS sample
"""
_DELETE_PARENT_DISABILITY = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept {id: '415036007'})
WHERE m.provenance = 'guideline_config_loader'
  AND NOT toLower(sf.form) CONTAINS 'parent'
DELETE m
RETURN count(*) AS deleted
"""

# ---------------------------------------------------------------------------
# B: Delete GCL active-condition forms wrongly mapped to known history-of
#    situations, where the form text has no history/past prefix.
# These situation IDs should ONLY apply when the form itself says
# 'history of', 'past', 'previous', 'old', 'healed', 'h/o' etc.
# ---------------------------------------------------------------------------
_HISTORY_PREFIXES = [
    "history of ",
    "h/o ",
    "hx ",
    "hx. ",
    "past ",
    "previous ",
    "old ",
    "healed ",
    "prior ",
    "pre-existing ",
    "former ",
]
_WRONG_SITUATION_MAP = {
    "161445009": "History of diabetes mellitus",
    "161465002": "History of dementia",
    "161535005": "History of liver disease",
    "266995000": "History of cardiovascular disease",
    "266998003": "History of peptic ulcer",
    "267004000": "History of musculoskeletal disease",
    "270473001": "History of chronic obstructive airway disease",
    "272741003": "History of disorder",
    "275540007": "History of brain disorder",
    "275552000": "History of kidney disease",
    "308064009": "History of cerebrovascular disease",
    "399211009": "History of myocardial infarction",
    "414861001": "No evidence of recurrence of cancer",
    "473109007": "History of peripheral vascular disease",
    "472961001": "History of disorder of connective tissue",
}

_COUNT_ACTIVE_AS_SITUATION = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.id IN $sit_ids
  AND NOT any(prefix IN $prefixes WHERE toLower(sf.form) STARTS WITH prefix)
RETURN count(m) AS n, collect(sf.form)[..20] AS sample
"""
_DELETE_ACTIVE_AS_SITUATION = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:Concept)
WHERE m.provenance = 'guideline_config_loader'
  AND c.id IN $sit_ids
  AND NOT any(prefix IN $prefixes WHERE toLower(sf.form) STARTS WITH prefix)
DELETE m
RETURN count(*) AS deleted
"""

# ---------------------------------------------------------------------------
# C: Explicit correct mappings for high-priority forms after deletion.
#    These are common clinical terms the resolver struggles with if left to
#    fulltext alone.
# (form, correct_concept_id, correct_fsn_for_logging)
# ---------------------------------------------------------------------------
_CORRECT_MAPPINGS = [
    # Neurological paralysis/weakness -> correct SNOMED disorder/finding
    ("Hemiplegia", "50582007", "Hemiplegia (disorder)"),
    ("Hemiparesis", "278286009", "Hemiparesis (finding)"),
    ("Hemiparetic", "278286009", "Hemiparesis (finding)"),
    ("Hemiplegic", "50582007", "Hemiplegia (disorder)"),
    ("Left hemiplegia", "193093009", "Left hemiplegia (disorder)"),
    ("Right hemiplegia", "193092004", "Right hemiplegia (disorder)"),
    ("Left-sided weakness", "278286009", "Hemiparesis (finding)"),
    ("Right-sided weakness", "278286009", "Hemiparesis (finding)"),
    ("Paraplegia", "60654006", "Paraplegia (disorder)"),
    ("Paraplegic", "60654006", "Paraplegia (disorder)"),
    ("Paraparesis", "26538006", "Paraparesis (finding)"),
    ("Quadriplegia", "363456007", "Quadriplegia (disorder)"),
    ("Quadriplegic", "363456007", "Quadriplegia (disorder)"),
    ("Quadriparesis", "44695005", "Quadriparesis (finding)"),
    ("Tetraparesis", "44695005", "Quadriparesis (finding)"),
    ("Tetraplegic", "363456007", "Quadriplegia (disorder)"),
    ("Monoplegia", "65988001", "Monoplegia (disorder)"),
    ("Monoplegic", "65988001", "Monoplegia (disorder)"),
    ("Monoparesis", "20022007", "Monoparesis (finding)"),
    ("Diplegia", "9482001", "Diplegia (disorder)"),
    ("Diplegic", "9482001", "Diplegia (disorder)"),
    ("Spastic diplegia", "43171001", "Spastic diplegia (disorder)"),
    ("Spastic hemiplegia", "38484009", "Spastic hemiplegia (disorder)"),
    ("Dense hemiplegia", "50582007", "Hemiplegia (disorder)"),
    ("Flaccid hemiplegia", "1734006", "Flaccid hemiplegia (disorder)"),
    ("Spinal cord injury", "90584004", "Injury of spinal cord (disorder)"),
    ("Paralysis of legs", "60654006", "Paraplegia (disorder)"),
    ("Paralysed legs", "60654006", "Paraplegia (disorder)"),
    ("Lower limb paralysis", "60654006", "Paraplegia (disorder)"),
    ("B/L lower limb paralysis", "60654006", "Paraplegia (disorder)"),
    ("Paralysed", "44695005", "Quadriparesis (finding)"),
    ("Paralyzed", "44695005", "Quadriparesis (finding)"),
    ("Paralyzed from waist down", "60654006", "Paraplegia (disorder)"),
    ("Paralysis of all four limbs", "363456007", "Quadriplegia (disorder)"),
    ("Single limb paralysis", "65988001", "Monoplegia (disorder)"),
    ("Unilateral paralysis", "65988001", "Monoplegia (disorder)"),
    ("Unilateral weakness", "278286009", "Hemiparesis (finding)"),
    ("Post-stroke paralysis", "50582007", "Hemiplegia (disorder)"),
    ("Stroke with hemiparesis", "278286009", "Hemiparesis (finding)"),
    ("CVA with hemiplegia", "50582007", "Hemiplegia (disorder)"),
    ("LMN paralysis", "75508008", "Lower motor neuron disorder (disorder)"),
    ("UMN weakness", "57920002", "Upper motor neuron disorder (disorder)"),
    ("Lower motor neuron lesion", "75508008", "Lower motor neuron disorder (disorder)"),
    ("Upper motor neuron lesion", "57920002", "Upper motor neuron disorder (disorder)"),
    ("Cauda equina syndrome", "192970008", "Cauda equina syndrome (disorder)"),
    # Diabetes forms
    ("Diabetes mellitus type 1", "46635009", "Diabetes mellitus type 1 (disorder)"),
    (
        "Diabetes mellitus type 1 (disorder)",
        "46635009",
        "Diabetes mellitus type 1 (disorder)",
    ),
    ("Diabetes mellitus type 2", "44054006", "Diabetes mellitus type 2 (disorder)"),
    (
        "Diabetes mellitus type 2 (disorder)",
        "44054006",
        "Diabetes mellitus type 2 (disorder)",
    ),
    ("Type 1 diabetes", "46635009", "Diabetes mellitus type 1 (disorder)"),
    ("DM", "73211009", "Diabetes mellitus (disorder)"),
    # Rheumatological
    ("Lupus", "55464009", "Systemic lupus erythematosus (disorder)"),
    ("SLE", "55464009", "Systemic lupus erythematosus (disorder)"),
    (
        "Systemic lupus erythematosus",
        "55464009",
        "Systemic lupus erythematosus (disorder)",
    ),
    (
        "Systemic lupus erythematosus (disorder)",
        "55464009",
        "Systemic lupus erythematosus (disorder)",
    ),
    ("PMR", "61350008", "Polymyalgia rheumatica (disorder)"),
    ("Polymyalgia rheumatica", "61350008", "Polymyalgia rheumatica (disorder)"),
    (
        "Polymyalgia rheumatica (disorder)",
        "61350008",
        "Polymyalgia rheumatica (disorder)",
    ),
    ("Polymyositis", "31384009", "Polymyositis (disorder)"),
    ("Polymyositis (disorder)", "31384009", "Polymyositis (disorder)"),
    ("Scleroderma", "89155008", "Systemic sclerosis (disorder)"),
    ("Systemic sclerosis", "89155008", "Systemic sclerosis (disorder)"),
    ("Systemic sclerosis (disorder)", "89155008", "Systemic sclerosis (disorder)"),
    ("Rheumatoid arthritis (disorder)", "69896004", "Rheumatoid arthritis (disorder)"),
    # Vascular / cardiac
    ("Cerebrovascular accident", "230690007", "Cerebrovascular accident (disorder)"),
    (
        "Cerebrovascular accident (disorder)",
        "230690007",
        "Cerebrovascular accident (disorder)",
    ),
    ("Transient ischemic attack", "266257000", "Transient ischemic attack (disorder)"),
    (
        "Transient ischemic attack (disorder)",
        "266257000",
        "Transient ischemic attack (disorder)",
    ),
    ("Mini stroke", "266257000", "Transient ischemic attack (disorder)"),
    ("AAA", "233985008", "Abdominal aortic aneurysm (disorder)"),
    ("Abdominal aortic aneurysm", "233985008", "Abdominal aortic aneurysm (disorder)"),
    (
        "Abdominal aortic aneurysm (disorder)",
        "233985008",
        "Abdominal aortic aneurysm (disorder)",
    ),
    ("Intermittent claudication", "29819009", "Intermittent claudication (disorder)"),
    (
        "Intermittent claudication (finding)",
        "29819009",
        "Intermittent claudication (disorder)",
    ),
    (
        "Peripheral vascular disease",
        "400047006",
        "Peripheral vascular disease (disorder)",
    ),
    (
        "Peripheral vascular disease (disorder)",
        "400047006",
        "Peripheral vascular disease (disorder)",
    ),
    # Neurological
    ("Alzheimer's", "26929004", "Alzheimer's disease (disorder)"),
    ("Alzheimer's disease (disorder)", "26929004", "Alzheimer's disease (disorder)"),
    ("Vascular dementia", "429998004", "Vascular dementia (disorder)"),
    ("Vascular dementia (disorder)", "429998004", "Vascular dementia (disorder)"),
    ("Dementia (disorder)", "52448006", "Dementia (disorder)"),
    # Respiratory
    ("Asthma (disorder)", "195967001", "Asthma (disorder)"),
    ("Chronic bronchitis", "63480004", "Chronic bronchitis (disorder)"),
    ("Emphysema", "49601000", "Emphysema (disorder)"),
    ("Pulmonary emphysema", "49601000", "Emphysema (disorder)"),
    ("Pulmonary emphysema (disorder)", "49601000", "Emphysema (disorder)"),
    (
        "Chronic obstructive lung disease",
        "13645005",
        "Chronic obstructive pulmonary disease (disorder)",
    ),
    (
        "Chronic obstructive lung disease (disorder)",
        "13645005",
        "Chronic obstructive pulmonary disease (disorder)",
    ),
    # Hepatic
    ("Chronic hepatitis", "10295004", "Chronic hepatitis (disorder)"),
    ("Hepatitis B", "66071002", "Hepatitis B (disorder)"),
    ("Hepatitis C", "50711007", "Hepatitis C (disorder)"),
    ("Nonalcoholic fatty liver disease", "197321007", "Steatosis of liver (disorder)"),
    ("Steatosis of liver", "197321007", "Steatosis of liver (disorder)"),
    ("Steatosis of liver (disorder)", "197321007", "Steatosis of liver (disorder)"),
    # Renal
    (
        "Chronic kidney disease (disorder)",
        "709044004",
        "Chronic kidney disease (disorder)",
    ),
    (
        "Chronic kidney disease stage 3 (disorder)",
        "433144002",
        "Chronic kidney disease stage 3 (disorder)",
    ),
    (
        "Chronic kidney disease stage 4 (disorder)",
        "431857002",
        "Chronic kidney disease stage 4 (disorder)",
    ),
    (
        "Chronic kidney disease stage 5 (disorder)",
        "433146000",
        "Chronic kidney disease stage 5 (disorder)",
    ),
    ("ESRD", "433146000", "Chronic kidney disease stage 5 (disorder)"),
    (
        "End stage renal disease",
        "433146000",
        "Chronic kidney disease stage 5 (disorder)",
    ),
    (
        "End stage renal disease (disorder)",
        "433146000",
        "Chronic kidney disease stage 5 (disorder)",
    ),
    # GI
    ("Peptic ulcer", "13200003", "Peptic ulcer (disorder)"),
    ("Peptic ulcer (disorder)", "13200003", "Peptic ulcer (disorder)"),
    ("Gastric ulcer", "397825006", "Gastric ulcer (disorder)"),
    ("Gastric ulcer (disorder)", "397825006", "Gastric ulcer (disorder)"),
    ("Duodenal ulcer", "51868009", "Duodenal ulcer (disorder)"),
    ("Duodenal ulcer (disorder)", "51868009", "Duodenal ulcer (disorder)"),
    ("Stomach ulcer", "397825006", "Gastric ulcer (disorder)"),
    ("PUD", "13200003", "Peptic ulcer (disorder)"),
]


def _norm(text: str) -> str:
    low = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", low)
    return " ".join(nfkd.encode("ascii", "ignore").decode("ascii").split())


def _upsert(form: str, concept_id: str, dry_run: bool) -> bool:
    normalized = _norm(form)
    payload = {
        "normalized": normalized,
        "form": form,
        "concept_id": concept_id,
        "confidence": 1.0,
        "source": "manual",
        "provenance": "audit-fix-wrong-gcl-situations-2026-04",
    }
    if dry_run:
        print(f"      [DRY-RUN] UPSERT {form!r} -> {concept_id}")
        return True
    resp = requests.post(
        f"{_API}/terminology/surface-forms/upsert-mapping",
        json=payload,
        headers={"Authorization": f"Bearer {_TOKEN}"},
        timeout=60,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"      Upserted -> {data.get('concept_fsn')}")
        return True
    print(f"      UPSERT failed {resp.status_code}: {resp.text[:150]}")
    return False


def main(dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"Mode: {mode}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    with driver.session() as s:
        _step_a(s, dry_run)
        _step_b(s, dry_run)

    driver.close()

    _step_c(dry_run)
    print(f"\n[{mode}] Done.")


def _step_a(session, dry_run: bool) -> None:
    print("\n" + "=" * 70)
    print("A. Delete GCL edges to 'Parent has physical disability' (415036007)")
    result = session.run(_COUNT_PARENT_DISABILITY).data()
    n = result[0]["n"] if result else 0
    sample = result[0].get("sample", []) if result else []
    print(f"   Found: {n} edges")
    if sample:
        print(f"   Sample: {sample[:10]}")
    if dry_run:
        print("   [DRY-RUN] Would delete")
        return
    if n == 0:
        return
    r = session.run(_DELETE_PARENT_DISABILITY).data()
    deleted = r[0]["deleted"] if r else 0
    print(f"   Deleted: {deleted}")


def _step_b(session, dry_run: bool) -> None:
    print("\n" + "=" * 70)
    print("B. Delete GCL active-condition forms wrongly mapped to history situations")
    sit_ids = list(_WRONG_SITUATION_MAP.keys())
    result = session.run(
        _COUNT_ACTIVE_AS_SITUATION,
        sit_ids=sit_ids,
        prefixes=_HISTORY_PREFIXES,
    ).data()
    n = result[0]["n"] if result else 0
    sample = result[0].get("sample", []) if result else []
    print(f"   Found: {n} edges")
    if sample:
        print(f"   Sample: {sorted(sample)[:20]}")
    if dry_run:
        print("   [DRY-RUN] Would delete")
        return
    if n == 0:
        return
    r = session.run(
        _DELETE_ACTIVE_AS_SITUATION,
        sit_ids=sit_ids,
        prefixes=_HISTORY_PREFIXES,
    ).data()
    deleted = r[0]["deleted"] if r else 0
    print(f"   Deleted: {deleted}")


def _step_c(dry_run: bool) -> None:
    print("\n" + "=" * 70)
    print(f"C. Upsert correct disorder mappings ({len(_CORRECT_MAPPINGS)} forms)")
    ok = fail = 0
    for form, cid, fsn in _CORRECT_MAPPINGS:
        print(f"  {form!r} -> {cid} | {fsn}")
        if _upsert(form, cid, dry_run):
            ok += 1
        else:
            fail += 1
    print(f"\n   Upserted: {ok}  Failed: {fail}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
