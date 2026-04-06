"""Pin surface forms for anal and rectal mass concepts.

  1812681000000102 | Mass of anal structure (finding)
  248523006        | Rectal mass (finding)
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
    # 1812681000000102 | Mass of anal structure (finding)
    {
        "normalized": "anal mass",
        "concept_id": "1812681000000102",
        "preferred_term": "Mass of anal structure (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "mass of anal structure",
        "concept_id": "1812681000000102",
        "preferred_term": "Mass of anal structure (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "anal canal mass",
        "concept_id": "1812681000000102",
        "preferred_term": "Mass of anal structure (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    # 248523006 | Rectal mass (finding)
    {
        "normalized": "rectal mass",
        "concept_id": "248523006",
        "preferred_term": "Rectal mass (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "mass in rectum",
        "concept_id": "248523006",
        "preferred_term": "Rectal mass (finding)",
        "semantic_tag": "finding",
        "confidence": 1.0,
    },
    {
        "normalized": "palpable rectal mass",
        "concept_id": "248523006",
        "preferred_term": "Rectal mass (finding)",
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
            print(f"  ERROR: no row returned for {pin['normalized']!r}")
driver.close()
print("\nDone.")
