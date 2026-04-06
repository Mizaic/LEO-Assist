"""Fix all NG12 surface form pins using the correct graph schema.

The correct schema is:
  (SurfaceForm {normalized})-[:MAPS_TO {confidence}]->(Concept {id, fsn, semantic_tag, active})

Earlier scripts used wrong label SNOMEDConcept {concept_id} -- this script:
  1. Removes the incorrectly-labelled SNOMEDConcept nodes and their SurfaceForm edges
  2. Re-pins all surface forms against correctly-labelled Concept nodes
"""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets
load_keyvault_secrets()
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# All pins needed for NG12 fixes - using correct schema
PINS = [
    # Mesothelioma CXR - 1290960005 Plain X-ray of chest abnormal (finding)
    ("chest x-ray findings suggestive of mesothelioma", "chest X-ray findings suggestive of mesothelioma",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("chest x-ray findings consistent with mesothelioma", "chest X-ray findings consistent with mesothelioma",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("cxr findings suggestive of mesothelioma", "CXR findings suggestive of mesothelioma",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("pleural abnormality on chest x-ray", "pleural abnormality on chest X-ray",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("pleural thickening on chest x-ray", "pleural thickening on chest X-ray",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("pleural mass on chest x-ray", "pleural mass on chest X-ray",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("chest x-ray pleural finding", "chest X-ray pleural finding",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),
    ("abnormal chest x-ray mesothelioma", "abnormal chest X-ray mesothelioma",
     "1290960005", "Plain X-ray of chest abnormal (finding)", "finding"),

    # Pleural disease chest signs - 272016000 On examination - chest finding
    ("chest signs compatible with pleural disease", "chest signs compatible with pleural disease",
     "272016000", "On examination - chest finding (finding)", "finding"),
    ("chest signs consistent with pleural disease", "chest signs consistent with pleural disease",
     "272016000", "On examination - chest finding (finding)", "finding"),
    ("chest signs suggestive of pleural disease", "chest signs suggestive of pleural disease",
     "272016000", "On examination - chest finding (finding)", "finding"),
    ("chest signs consistent with lung cancer", "chest signs consistent with lung cancer",
     "272016000", "On examination - chest finding (finding)", "finding"),
    ("on examination chest finding", "on examination - chest finding",
     "272016000", "On examination - chest finding (finding)", "finding"),

    # New-onset diabetes - 405749004 Newly diagnosed diabetes mellitus
    ("new-onset diabetes mellitus", "new-onset diabetes mellitus",
     "405749004", "Newly diagnosed diabetes mellitus (disorder)", "disorder"),
    ("new onset diabetes mellitus", "new onset diabetes mellitus",
     "405749004", "Newly diagnosed diabetes mellitus (disorder)", "disorder"),
    ("newly diagnosed diabetes mellitus", "newly diagnosed diabetes mellitus",
     "405749004", "Newly diagnosed diabetes mellitus (disorder)", "disorder"),
    ("newly diagnosed diabetes", "newly diagnosed diabetes",
     "405749004", "Newly diagnosed diabetes mellitus (disorder)", "disorder"),
    ("new onset diabetes", "new onset diabetes",
     "405749004", "Newly diagnosed diabetes mellitus (disorder)", "disorder"),

    # Ascites - 389026000 (no finding exists, disorder is canonical)
    ("ascites", "ascites",
     "389026000", "Ascites (disorder)", "disorder"),
    ("abdominal ascites", "abdominal ascites",
     "389026000", "Ascites (disorder)", "disorder"),
    ("ascites clinical sign", "ascites clinical sign",
     "389026000", "Ascites (disorder)", "disorder"),

    # Gallbladder palpable - 271683004
    ("gallbladder palpable", "gallbladder palpable",
     "271683004", "Gallbladder palpable (finding)", "finding"),
    ("palpable gallbladder", "palpable gallbladder",
     "271683004", "Gallbladder palpable (finding)", "finding"),
    ("upper abdominal mass gallbladder", "upper abdominal mass gallbladder",
     "271683004", "Gallbladder palpable (finding)", "finding"),

    # Gallbladder enlarged - 300344005
    ("enlarged gallbladder", "enlarged gallbladder",
     "300344005", "Gallbladder enlarged (finding)", "finding"),
    ("gallbladder enlarged", "gallbladder enlarged",
     "300344005", "Gallbladder enlarged (finding)", "finding"),
    ("upper abdominal mass consistent with enlarged gall bladder",
     "upper abdominal mass consistent with enlarged gall bladder",
     "300344005", "Gallbladder enlarged (finding)", "finding"),

    # Testicular appearance - 300482003
    ("finding of appearance of testes", "finding of appearance of testes",
     "300482003", "Finding of appearance of testes (finding)", "finding"),
    ("change in shape of testis", "change in shape of testis",
     "300482003", "Finding of appearance of testes (finding)", "finding"),
    ("change in texture of testis", "change in texture of testis",
     "300482003", "Finding of appearance of testes (finding)", "finding"),
    ("change in appearance of testis", "change in appearance of testis",
     "300482003", "Finding of appearance of testes (finding)", "finding"),
    ("testicular appearance change", "testicular appearance change",
     "300482003", "Finding of appearance of testes (finding)", "finding"),

    # Abnormal nervous system function - 13028004
    ("abnormal nervous system function", "abnormal nervous system function",
     "13028004", "Abnormal nervous system function (finding)", "finding"),
    ("progressive loss of central neurological function",
     "progressive loss of central neurological function",
     "13028004", "Abnormal nervous system function (finding)", "finding"),
    ("progressive sub-acute loss of neurological function",
     "progressive sub-acute loss of neurological function",
     "13028004", "Abnormal nervous system function (finding)", "finding"),
    ("sub-acute neurological deterioration", "sub-acute neurological deterioration",
     "13028004", "Abnormal nervous system function (finding)", "finding"),
    ("progressive neurological deficit", "progressive neurological deficit",
     "13028004", "Abnormal nervous system function (finding)", "finding"),

    # Osteolysis - 30425001
    ("osteolysis", "osteolysis",
     "30425001", "Osteolysis (morphologic abnormality)", "morphologic abnormality"),
    ("bone destruction on x-ray", "bone destruction on X-ray",
     "30425001", "Osteolysis (morphologic abnormality)", "morphologic abnormality"),
    ("x-ray finding suggestive of bone sarcoma", "X-ray finding suggestive of bone sarcoma",
     "30425001", "Osteolysis (morphologic abnormality)", "morphologic abnormality"),
    ("abnormal bone x-ray finding", "abnormal bone X-ray finding",
     "30425001", "Osteolysis (morphologic abnormality)", "morphologic abnormality"),

    # Periosteal bone formation - 30397001
    ("periosteal bone formation", "periosteal bone formation",
     "30397001", "Periosteal bone formation, function (observable entity)", "observable entity"),
    ("periosteal reaction", "periosteal reaction",
     "30397001", "Periosteal bone formation, function (observable entity)", "observable entity"),

    # Mass of soft tissue - 444905003
    ("mass of soft tissue", "mass of soft tissue",
     "444905003", "Mass of soft tissue (finding)", "finding"),
    ("soft tissue mass", "soft tissue mass",
     "444905003", "Mass of soft tissue (finding)", "finding"),

    # Anal mass - 1812681000000102
    ("anal mass", "anal mass",
     "1812681000000102", "Mass of anal structure (finding)", "finding"),
    ("mass of anal structure", "mass of anal structure",
     "1812681000000102", "Mass of anal structure (finding)", "finding"),
    ("anal canal mass", "anal canal mass",
     "1812681000000102", "Mass of anal structure (finding)", "finding"),

    # Rectal mass - 248523006
    ("rectal mass", "rectal mass",
     "248523006", "Rectal mass (finding)", "finding"),
    ("mass in rectum", "mass in rectum",
     "248523006", "Rectal mass (finding)", "finding"),
    ("palpable rectal mass", "palpable rectal mass",
     "248523006", "Rectal mass (finding)", "finding"),
]

# Step 1: remove wrongly-created SNOMEDConcept nodes
CLEANUP = """
MATCH (sf:SurfaceForm)-[m:MAPS_TO]->(c:SNOMEDConcept)
DETACH DELETE c
"""

# Step 2: pin with correct schema - MERGE Concept (creates if absent)
UPSERT = """
MERGE (c:Concept {id: $cid})
ON CREATE SET c.fsn = $fsn,
              c.semantic_tag = $semantic_tag,
              c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.created_at = datetime(), sf.status = 'approved'
SET sf.form = $form,
    sf.source = 'manual_pin',
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
SET m.confidence = 1.0,
    m.approved_at = datetime(),
    m.provenance = 'ng12_guideline_pin',
    m.pinned = true
RETURN sf.normalized AS normalized, c.id AS cid
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    # Cleanup wrong nodes
    s.run(CLEANUP)
    print("Cleaned up SNOMEDConcept nodes.\n")

    # Re-pin correctly
    ok = 0
    for normalized, form, cid, fsn, semantic_tag in PINS:
        row = s.run(UPSERT, normalized=normalized, form=form,
                    cid=cid, fsn=fsn, semantic_tag=semantic_tag).single()
        if row:
            print(f"  OK  {row['normalized']!r:65s} -> {row['cid']}")
            ok += 1
        else:
            print(f"  ERR {normalized!r}")

driver.close()
print(f"\nDone. {ok}/{len(PINS)} surface forms pinned correctly.")
