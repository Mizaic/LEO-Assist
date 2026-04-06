"""Pin surface forms for the remaining NG12 Category 3 gaps.

  389026000   | Ascites (disorder)                               - no finding exists
  271683004   | Gallbladder palpable (finding)
  300344005   | Gallbladder enlarged (finding)
  300482003   | Finding of appearance of testes (finding)
  13028004    | Abnormal nervous system function (finding)
  30425001    | Osteolysis (morphologic abnormality)             - bone sarcoma X-ray
  30397001    | Periosteal bone formation, function (observable entity)
  444905003   | Mass of soft tissue (finding)
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

PINS = [
    # -- Ascites 1.5.1 --
    # No SNOMED finding exists; disorder is the canonical concept
    {
        "normalized": "ascites",
        "concept_id": "389026000",
        "preferred_term": "Ascites (disorder)",
        "semantic_tag": "disorder",
        "confidence": 1.0,
    },
    {
        "normalized": "abdominal ascites",
        "concept_id": "389026000",
        "preferred_term": "Ascites (disorder)",
        "semantic_tag": "disorder",
        "confidence": 1.0,
    },
    {
        "normalized": "ascites clinical sign",
        "concept_id": "389026000",
        "preferred_term": "Ascites (disorder)",
        "semantic_tag": "disorder",
        "confidence": 1.0,
    },

    # -- Palpable / enlarged gallbladder 1.2.10 --
    {
        "normalized": "gallbladder palpable",
        "concept_id": "271683004",
        "preferred_term": "Gallbladder palpable (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "palpable gallbladder",
        "concept_id": "271683004",
        "preferred_term": "Gallbladder palpable (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "upper abdominal mass gallbladder",
        "concept_id": "271683004",
        "preferred_term": "Gallbladder palpable (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "enlarged gallbladder",
        "concept_id": "300344005",
        "preferred_term": "Gallbladder enlarged (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "gallbladder enlarged",
        "concept_id": "300344005",
        "preferred_term": "Gallbladder enlarged (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "upper abdominal mass consistent with enlarged gall bladder",
        "concept_id": "300344005",
        "preferred_term": "Gallbladder enlarged (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },

    # -- Change in appearance/shape/texture of testis 1.6.7 --
    {
        "normalized": "finding of appearance of testes",
        "concept_id": "300482003",
        "preferred_term": "Finding of appearance of testes (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "change in shape of testis",
        "concept_id": "300482003",
        "preferred_term": "Finding of appearance of testes (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "change in texture of testis",
        "concept_id": "300482003",
        "preferred_term": "Finding of appearance of testes (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "change in appearance of testis",
        "concept_id": "300482003",
        "preferred_term": "Finding of appearance of testes (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "testicular appearance change",
        "concept_id": "300482003",
        "preferred_term": "Finding of appearance of testes (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },

    # -- Progressive sub-acute neurological deterioration 1.9.1 --
    {
        "normalized": "abnormal nervous system function",
        "concept_id": "13028004",
        "preferred_term": "Abnormal nervous system function (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "progressive loss of central neurological function",
        "concept_id": "13028004",
        "preferred_term": "Abnormal nervous system function (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "progressive sub-acute loss of neurological function",
        "concept_id": "13028004",
        "preferred_term": "Abnormal nervous system function (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "sub-acute neurological deterioration",
        "concept_id": "13028004",
        "preferred_term": "Abnormal nervous system function (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "progressive neurological deficit",
        "concept_id": "13028004",
        "preferred_term": "Abnormal nervous system function (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },

    # -- X-ray findings suggestive of bone sarcoma 1.11.1 --
    # Osteolysis: bone destruction visible on X-ray
    {
        "normalized": "osteolysis",
        "concept_id": "30425001",
        "preferred_term": "Osteolysis (morphologic abnormality)",
        "semantic_tag": "morphologic abnormality",
        "confidence": 1.0,
    },
    {
        "normalized": "bone destruction on x-ray",
        "concept_id": "30425001",
        "preferred_term": "Osteolysis (morphologic abnormality)",
        "semantic_tag": "morphologic abnormality",
        "confidence": 1.0,
    },
    {
        "normalized": "x-ray finding suggestive of bone sarcoma",
        "concept_id": "30425001",
        "preferred_term": "Osteolysis (morphologic abnormality)",
        "semantic_tag": "morphologic abnormality",
        "confidence": 1.0,
    },
    {
        "normalized": "abnormal bone x-ray finding",
        "concept_id": "30425001",
        "preferred_term": "Osteolysis (morphologic abnormality)",
        "semantic_tag": "morphologic abnormality",
        "confidence": 1.0,
    },
    # Periosteal reaction: also a key bone sarcoma X-ray sign
    {
        "normalized": "periosteal bone formation",
        "concept_id": "30397001",
        "preferred_term": "Periosteal bone formation, function (observable entity)",
        "semantic_tag": "observable entity",
        "confidence": 1.0,
    },
    {
        "normalized": "periosteal reaction",
        "concept_id": "30397001",
        "preferred_term": "Periosteal bone formation, function (observable entity)",
        "semantic_tag": "observable entity",
        "confidence": 1.0,
    },
    # Soft tissue mass: bone sarcoma soft tissue component
    {
        "normalized": "mass of soft tissue",
        "concept_id": "444905003",
        "preferred_term": "Mass of soft tissue (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "soft tissue mass",
        "concept_id": "444905003",
        "preferred_term": "Mass of soft tissue (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
]

UPSERT = """
MERGE (sf:SurfaceForm {normalized: $normalized})
SET sf.confidence = $confidence
WITH sf
MERGE (c:SNOMEDConcept {concept_id: $concept_id})
ON CREATE SET c.preferred_term = $preferred_term,
              c.semantic_tag = $semantic_tag
MERGE (sf)-[m:MAPS_TO]->(c)
SET m.confidence = $confidence,
    m.source = 'manual_pin',
    m.pinned = true
RETURN sf.normalized AS normalized, c.concept_id AS concept_id
"""

driver = GraphDatabase.driver(kg_uri, auth=(kg_user, kg_pass))
with driver.session() as s:
    for pin in PINS:
        row = s.run(UPSERT, **pin).single()
        if row:
            print(f"  Pinned: {row['normalized']!r} -> {row['concept_id']}")
        else:
            print(f"  ERROR:  no row for {pin['normalized']!r}")
driver.close()
print(f"\nDone. {len(PINS)} surface forms pinned.")
