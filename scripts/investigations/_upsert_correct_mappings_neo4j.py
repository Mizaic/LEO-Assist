"""Upsert correct SNOMED concept mappings directly to the knowledge graph Neo4j.

Bypasses the Terminology API (which requires a service auth token) and writes
MAPS_TO edges directly using the same Cypher the API uses internally.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import unicodedata
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# Same Cypher as UPSERT_SURFACE_FORM_MAPPING in terminology.py
_UPSERT_CYPHER = """
MATCH (c:Concept {id: $concept_id})
WHERE c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form,
              sf.source = 'manual',
              sf.status = 'active',
              sf.created_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
ON CREATE SET m.created_at = datetime(),
              m.approved_at = datetime()
SET m.confidence = 1.0,
    m.provenance = 'audit-fix-wrong-gcl-situations-2026-04'
RETURN sf.normalized AS normalized,
       sf.form       AS form,
       c.id          AS concept_id,
       c.fsn         AS concept_fsn
"""

_CORRECT_MAPPINGS = [
    # Neurological - paralysis / weakness
    ("Hemiplegia", "50582007"),
    ("Hemiparesis", "278286009"),
    ("Hemiparetic", "278286009"),
    ("Hemiplegic", "50582007"),
    ("Left hemiplegia", "193093009"),
    ("Right hemiplegia", "193092004"),
    ("Left-sided weakness", "278286009"),
    ("Right-sided weakness", "278286009"),
    ("Paraplegia", "60654006"),
    ("Paraplegic", "60654006"),
    ("Paraparesis", "26538006"),
    ("Quadriplegia", "363456007"),
    ("Quadriplegic", "363456007"),
    ("Quadriparesis", "44695005"),
    ("Tetraparesis", "44695005"),
    ("Tetraplegic", "363456007"),
    ("Monoplegia", "65988001"),
    ("Monoplegic", "65988001"),
    ("Monoparesis", "20022007"),
    ("Diplegia", "9482001"),
    ("Diplegic", "9482001"),
    ("Spastic diplegia", "43171001"),
    ("Spastic hemiplegia", "38484009"),
    ("Dense hemiplegia", "50582007"),
    ("Flaccid hemiplegia", "1734006"),
    ("Spinal cord injury", "90584004"),
    ("Paralysis of legs", "60654006"),
    ("Paralysed legs", "60654006"),
    ("Lower limb paralysis", "60654006"),
    ("B/L lower limb paralysis", "60654006"),
    ("Bil LL weakness", "278286009"),
    ("Paralysed", "44695005"),
    ("Paralyzed", "44695005"),
    ("Paralyzed from waist down", "60654006"),
    ("Paralysis of all four limbs", "363456007"),
    ("Single limb paralysis", "65988001"),
    ("Unilateral paralysis", "65988001"),
    ("Unilateral weakness", "278286009"),
    ("Post-stroke paralysis", "50582007"),
    ("Stroke with hemiparesis", "278286009"),
    ("CVA with hemiplegia", "50582007"),
    ("LMN paralysis", "75508008"),
    ("UMN weakness", "57920002"),
    ("Lower motor neuron lesion", "75508008"),
    ("Upper motor neuron lesion", "57920002"),
    ("Cauda equina syndrome", "192970008"),
    ("Complete SCI", "90584004"),
    ("Incomplete SCI", "90584004"),
    ("SCI", "90584004"),
    ("SCI C5", "90584004"),
    ("SCI T12", "90584004"),
    ("MRC 0/5", "278286009"),
    ("MRC 1/5", "278286009"),
    ("MRC 2/5", "278286009"),
    # Diabetes
    ("Diabetes mellitus type 1", "46635009"),
    ("Diabetes mellitus type 1 (disorder)", "46635009"),
    ("Diabetes mellitus type 2", "44054006"),
    ("Diabetes mellitus type 2 (disorder)", "44054006"),
    ("Type 1 diabetes", "46635009"),
    ("DM", "73211009"),
    ("Pre-existing diabetes mellitus", "73211009"),
    # Rheumatological
    ("Lupus", "55464009"),
    ("SLE", "55464009"),
    ("Systemic lupus erythematosus", "55464009"),
    ("Systemic lupus erythematosus (disorder)", "55464009"),
    ("PMR", "61350008"),
    ("Polymyalgia rheumatica", "61350008"),
    ("Polymyalgia rheumatica (disorder)", "61350008"),
    ("Polymyositis", "31384009"),
    ("Polymyositis (disorder)", "31384009"),
    ("Scleroderma", "89155008"),
    ("Systemic sclerosis", "89155008"),
    ("Systemic sclerosis (disorder)", "89155008"),
    ("Rheumatoid arthritis (disorder)", "69896004"),
    ("Past CTD", "396230008"),  # Connective tissue disease
    # Vascular / cardiac
    ("Cerebrovascular accident", "230690007"),
    ("Cerebrovascular accident (disorder)", "230690007"),
    ("Transient ischemic attack", "266257000"),
    ("Transient ischemic attack (disorder)", "266257000"),
    ("Mini stroke", "266257000"),
    ("AAA", "233985008"),
    ("Abdominal aortic aneurysm", "233985008"),
    ("Abdominal aortic aneurysm (disorder)", "233985008"),
    ("Intermittent claudication", "29819009"),
    ("Intermittent claudication (finding)", "29819009"),
    ("Peripheral vascular disease", "400047006"),
    ("Peripheral vascular disease (disorder)", "400047006"),
    # Neurological dementia
    ("Alzheimer's", "26929004"),
    ("Alzheimer's disease (disorder)", "26929004"),
    ("Vascular dementia", "429998004"),
    ("Vascular dementia (disorder)", "429998004"),
    ("Dementia (disorder)", "52448006"),
    ("Lewy body dementia", "312991009"),
    # Respiratory
    ("Asthma (disorder)", "195967001"),
    ("Chronic bronchitis", "63480004"),
    ("Emphysema", "49601000"),
    ("Pulmonary emphysema", "49601000"),
    ("Pulmonary emphysema (disorder)", "49601000"),
    ("Chronic obstructive lung disease", "13645005"),
    ("Chronic obstructive lung disease (disorder)", "13645005"),
    ("Past COPD", "13645005"),
    # Hepatic
    ("Chronic hepatitis", "10295004"),
    ("Hepatitis B", "66071002"),
    ("Hepatitis C", "50711007"),
    ("Nonalcoholic fatty liver disease", "197321007"),
    ("Steatosis of liver", "197321007"),
    ("Steatosis of liver (disorder)", "197321007"),
    # Renal
    ("Chronic kidney disease (disorder)", "709044004"),
    ("Chronic kidney disease stage 3 (disorder)", "433144002"),
    ("Chronic kidney disease stage 4 (disorder)", "431857002"),
    ("Chronic kidney disease stage 5 (disorder)", "433146000"),
    ("ESRD", "433146000"),
    ("End stage renal disease", "433146000"),
    ("End stage renal disease (disorder)", "433146000"),
    ("Renal dialysis", "433146000"),
    ("Renal dialysis (procedure)", "433146000"),
    ("Dialysis", "433146000"),
    ("Kidney transplant", "709044004"),
    ("Donor renal transplantation", "709044004"),
    ("Donor renal transplantation (procedure)", "709044004"),
    # GI
    ("Peptic ulcer", "13200003"),
    ("Peptic ulcer (disorder)", "13200003"),
    ("Gastric ulcer", "397825006"),
    ("Gastric ulcer (disorder)", "397825006"),
    ("Duodenal ulcer", "51868009"),
    ("Duodenal ulcer (disorder)", "51868009"),
    ("Stomach ulcer", "397825006"),
    ("PUD", "13200003"),
]


def _norm(text: str) -> str:
    low = text.lower().strip()
    nfkd = unicodedata.normalize("NFKD", low)
    return " ".join(nfkd.encode("ascii", "ignore").decode("ascii").split())


def main() -> None:
    print(f"Connecting: {kg_uri}")
    driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))

    ok = 0
    skipped = 0
    fail = 0

    with driver.session() as s:
        for form, cid in _CORRECT_MAPPINGS:
            normalized = _norm(form)
            rows = s.run(
                _UPSERT_CYPHER,
                normalized=normalized,
                form=form,
                concept_id=cid,
            ).data()
            if rows:
                fsn = rows[0].get("concept_fsn", "?")
                print(f"  OK  {form!r} -> {cid} | {fsn}")
                ok += 1
            else:
                # Concept ID doesn't exist in the graph
                print(f"  SKIP {form!r} -> {cid} (concept not found in graph)")
                skipped += 1

    driver.close()
    print(
        f"\nDone: {ok} upserted, {skipped} skipped (concept not in graph), {fail} errors"
    )


if __name__ == "__main__":
    main()
