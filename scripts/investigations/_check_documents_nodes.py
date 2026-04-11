"""Check what node type/properties encounters DOCUMENTS to, and what conceptId they carry."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient

_Q_DOC_NODES = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
RETURN DISTINCT labels(c) AS node_labels, keys(c) AS node_keys
LIMIT 5
"""

_Q_DOC_SAMPLE = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
RETURN c.conceptId AS conceptId, c.id AS id, c.code AS code,
       c.name AS name, c.fsn AS fsn, labels(c) AS lbls
LIMIT 10
"""

_Q_CANCER_DIAG_CONCEPT = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE c.name CONTAINS 'cancer' OR c.name CONTAINS 'malignant' OR c.name CONTAINS 'neoplasm'
RETURN c.conceptId AS conceptId, c.id AS cid, c.name AS name, labels(c) AS lbls
LIMIT 10
"""

_Q_ANCHOR_QUERY_SAMPLE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c)
RETURN
    toString(e.id)              AS encounter_id,
    toString(e.date)            AS encounter_date,
    c.conceptId                 AS concept_id,
    c.name                      AS concept_name,
    c.semanticTag               AS semantic_tag
LIMIT 10
"""

_Q_ISA_FROM_DOCUMENTS = """
MATCH (e:Encounter)-[:DOCUMENTS]->(c)
WHERE c.name CONTAINS 'malignant' OR c.name CONTAINS 'carcinoma'
OPTIONAL MATCH (c)-[:IS_A]->(parent)
RETURN c.conceptId AS cid, c.name AS name, parent.id AS parent_id, parent.fsn AS parent_fsn
LIMIT 5
"""


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as s:
            print("=== Node types that Encounter DOCUMENTS to ===")
            for r in s.run(_Q_DOC_NODES).data():
                print(f"  labels: {r['node_labels']}, keys: {r['node_keys']}")

            print()
            print("=== Sample DOCUMENTS target node properties ===")
            for r in s.run(_Q_DOC_SAMPLE).data():
                print(
                    f"  conceptId={r['conceptId']}  id={r['id']}  code={r['code']}  name={str(r['name'])[:60]}  lbls={r['lbls']}"
                )

            print()
            print("=== Cancer-related DOCUMENTS target nodes ===")
            for r in s.run(_Q_CANCER_DIAG_CONCEPT).data():
                print(
                    f"  conceptId={r['conceptId']}  cid={r['cid']}  name={str(r['name'])[:70]}  lbls={r['lbls']}"
                )

            print()
            print("=== What _ANCHOR_QUERY actually returns (concept_id field) ===")
            for r in s.run(_Q_ANCHOR_QUERY_SAMPLE).data():
                print(
                    f"  concept_id={r['concept_id']}  name={str(r['concept_name'])[:60]}"
                )

            print()
            print("=== IS_A from malignant/carcinoma DOCUMENTS nodes ===")
            for r in s.run(_Q_ISA_FROM_DOCUMENTS).data():
                print(
                    f"  cid={r['cid']}  {str(r['name'])[:50]}  IS_A parent.id={r['parent_id']}"
                )
    finally:
        client.close()


if __name__ == "__main__":
    main()
