"""Re-pin all NG12 surface forms using the canonical normalize_surface function.

The resolver uses libs.terminology.surface_normalize.normalize_surface which
strips all non-alphanumeric chars (including hyphens) and lowercases.
Earlier pins used raw strings with hyphens -> resolver lookup will miss them.
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
from libs.terminology.surface_normalize import normalize_surface
from neo4j import GraphDatabase

kg_uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
kg_user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
kg_pass = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

# (display_form, concept_id, fsn, semantic_tag)
RAW_FORMS = [
    # 9990010014 Plain X-ray of chest abnormal (finding)
    (
        "chest X-ray findings suggestive of mesothelioma",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "chest X-ray findings consistent with mesothelioma",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "CXR findings suggestive of mesothelioma",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "pleural abnormality on chest X-ray",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "pleural thickening on chest X-ray",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "pleural mass on chest X-ray",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "chest X-ray pleural finding",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    (
        "abnormal chest X-ray mesothelioma",
        "9990010014",
        "Plain X-ray of chest abnormal (finding)",
        "finding",
    ),
    # 272016000 On examination - chest finding (finding)
    (
        "chest signs compatible with pleural disease",
        "272016000",
        "On examination - chest finding (finding)",
        "finding",
    ),
    (
        "chest signs consistent with pleural disease",
        "272016000",
        "On examination - chest finding (finding)",
        "finding",
    ),
    (
        "chest signs suggestive of pleural disease",
        "272016000",
        "On examination - chest finding (finding)",
        "finding",
    ),
    (
        "chest signs consistent with lung cancer",
        "272016000",
        "On examination - chest finding (finding)",
        "finding",
    ),
    (
        "on examination chest finding",
        "272016000",
        "On examination - chest finding (finding)",
        "finding",
    ),
    # 405749004 Newly diagnosed diabetes mellitus (disorder)
    (
        "new-onset diabetes mellitus",
        "405749004",
        "Newly diagnosed diabetes mellitus (disorder)",
        "disorder",
    ),
    (
        "new onset diabetes mellitus",
        "405749004",
        "Newly diagnosed diabetes mellitus (disorder)",
        "disorder",
    ),
    (
        "newly diagnosed diabetes mellitus",
        "405749004",
        "Newly diagnosed diabetes mellitus (disorder)",
        "disorder",
    ),
    (
        "newly diagnosed diabetes",
        "405749004",
        "Newly diagnosed diabetes mellitus (disorder)",
        "disorder",
    ),
    (
        "new onset diabetes",
        "405749004",
        "Newly diagnosed diabetes mellitus (disorder)",
        "disorder",
    ),
    # 389026000 Ascites (disorder)
    ("ascites", "389026000", "Ascites (disorder)", "disorder"),
    ("abdominal ascites", "389026000", "Ascites (disorder)", "disorder"),
    ("ascites clinical sign", "389026000", "Ascites (disorder)", "disorder"),
    # 271683004 Gallbladder palpable (finding)
    ("gallbladder palpable", "271683004", "Gallbladder palpable (finding)", "finding"),
    ("palpable gallbladder", "271683004", "Gallbladder palpable (finding)", "finding"),
    (
        "upper abdominal mass gallbladder",
        "271683004",
        "Gallbladder palpable (finding)",
        "finding",
    ),
    # 300344005 Gallbladder enlarged (finding)
    ("enlarged gallbladder", "300344005", "Gallbladder enlarged (finding)", "finding"),
    ("gallbladder enlarged", "300344005", "Gallbladder enlarged (finding)", "finding"),
    (
        "upper abdominal mass consistent with enlarged gall bladder",
        "300344005",
        "Gallbladder enlarged (finding)",
        "finding",
    ),
    # NICE / LLM variants (different tokenisation of gall bladder vs gallbladder, optional "an")
    (
        "upper abdominal mass consistent with an enlarged gall bladder",
        "300344005",
        "Gallbladder enlarged (finding)",
        "finding",
    ),
    (
        "upper abdominal mass consistent with enlarged gallbladder",
        "300344005",
        "Gallbladder enlarged (finding)",
        "finding",
    ),
    (
        "upper abdominal mass consistent with an enlarged gallbladder",
        "300344005",
        "Gallbladder enlarged (finding)",
        "finding",
    ),
    ("distended gallbladder", "300344005", "Gallbladder enlarged (finding)", "finding"),
    # After removing "consistent with" in _expanded_search_terms (no comma kept)
    (
        "upper abdominal mass an enlarged gall bladder",
        "300344005",
        "Gallbladder enlarged (finding)",
        "finding",
    ),
    # 300482003 Finding of appearance of testes (finding)
    (
        "finding of appearance of testes",
        "300482003",
        "Finding of appearance of testes (finding)",
        "finding",
    ),
    (
        "change in shape of testis",
        "300482003",
        "Finding of appearance of testes (finding)",
        "finding",
    ),
    (
        "change in texture of testis",
        "300482003",
        "Finding of appearance of testes (finding)",
        "finding",
    ),
    (
        "change in appearance of testis",
        "300482003",
        "Finding of appearance of testes (finding)",
        "finding",
    ),
    (
        "testicular appearance change",
        "300482003",
        "Finding of appearance of testes (finding)",
        "finding",
    ),
    # 13028004 Abnormal nervous system function (finding)
    (
        "abnormal nervous system function",
        "13028004",
        "Abnormal nervous system function (finding)",
        "finding",
    ),
    (
        "progressive loss of central neurological function",
        "13028004",
        "Abnormal nervous system function (finding)",
        "finding",
    ),
    (
        "progressive sub-acute loss of neurological function",
        "13028004",
        "Abnormal nervous system function (finding)",
        "finding",
    ),
    (
        "sub-acute neurological deterioration",
        "13028004",
        "Abnormal nervous system function (finding)",
        "finding",
    ),
    (
        "progressive neurological deficit",
        "13028004",
        "Abnormal nervous system function (finding)",
        "finding",
    ),
    # 30425001 Osteolysis (morphologic abnormality)
    (
        "osteolysis",
        "30425001",
        "Osteolysis (morphologic abnormality)",
        "morphologic abnormality",
    ),
    (
        "bone destruction on X-ray",
        "30425001",
        "Osteolysis (morphologic abnormality)",
        "morphologic abnormality",
    ),
    (
        "X-ray finding suggestive of bone sarcoma",
        "30425001",
        "Osteolysis (morphologic abnormality)",
        "morphologic abnormality",
    ),
    (
        "abnormal bone X-ray finding",
        "30425001",
        "Osteolysis (morphologic abnormality)",
        "morphologic abnormality",
    ),
    # 30397001 Periosteal bone formation
    (
        "periosteal bone formation",
        "30397001",
        "Periosteal bone formation, function (observable entity)",
        "observable entity",
    ),
    (
        "periosteal reaction",
        "30397001",
        "Periosteal bone formation, function (observable entity)",
        "observable entity",
    ),
    # 444905003 Mass of soft tissue (finding)
    ("mass of soft tissue", "444905003", "Mass of soft tissue (finding)", "finding"),
    ("soft tissue mass", "444905003", "Mass of soft tissue (finding)", "finding"),
    # 1812681000000102 Mass of anal structure (finding)
    ("anal mass", "1812681000000102", "Mass of anal structure (finding)", "finding"),
    (
        "mass of anal structure",
        "1812681000000102",
        "Mass of anal structure (finding)",
        "finding",
    ),
    (
        "anal canal mass",
        "1812681000000102",
        "Mass of anal structure (finding)",
        "finding",
    ),
    # 248523006 Rectal mass (finding)
    ("rectal mass", "248523006", "Rectal mass (finding)", "finding"),
    ("mass in rectum", "248523006", "Rectal mass (finding)", "finding"),
    ("palpable rectal mass", "248523006", "Rectal mass (finding)", "finding"),
]

UPSERT = """
MERGE (c:Concept {id: $cid})
ON CREATE SET c.fsn = $fsn, c.semantic_tag = $semantic_tag, c.active = true
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.created_at = datetime(), sf.status = 'approved'
SET sf.form = $form,
    sf.source = 'manual_pin',
    sf.last_seen_at = datetime()
MERGE (sf)-[m:MAPS_TO]->(c)
SET m.confidence = 1.0,
    m.approved_at = datetime(),
    m.provenance  = 'ng12_guideline_pin',
    m.pinned      = true
RETURN sf.normalized AS normalized, c.id AS cid
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
ok = skipped = 0
seen: set[tuple[str, str]] = set()

with driver.session() as s:
    for form, cid, fsn, semantic_tag in RAW_FORMS:
        normalized = normalize_surface(form)
        key = (normalized, cid)
        if key in seen:
            continue
        seen.add(key)

        row = s.run(
            UPSERT,
            normalized=normalized,
            form=form,
            cid=cid,
            fsn=fsn,
            semantic_tag=semantic_tag,
        ).single()
        if row:
            print(f"  OK  {row['normalized']!r:65s} -> {row['cid']}")
            ok += 1
        else:
            print(f"  ERR {normalized!r}")

driver.close()
print(f"\nDone. {ok} surface forms pinned with canonical normalization.")
