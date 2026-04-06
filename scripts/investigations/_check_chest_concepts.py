"""Check SNOMED concepts used for chest signs/findings criteria."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402
load_keyvault_secrets()
from neo4j import GraphDatabase  # noqa: E402

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

CONCEPTS = [
    ("272016000", "On examination - chest finding (verifier choice)"),
    ("58840004", "Decreased breath sounds (alternative)"),
    ("88075009", "Disorder of pleura (broad)"),
    ("127088000", "Supraclavicular lymphadenopathy"),
    ("127086001", "Cervical lymphadenopathy"),
    ("274744005", "Localized enlarged lymph nodes"),
    ("30760008", "Finger clubbing (disorder)"),
    ("367004", "Clubbing (morphologic abnormality)"),
    ("6631009", "Thrombocytosis (disorder)"),
    ("415115007", "Platelet count above reference range (finding)"),
]

_Q = """
MATCH (c:Concept {id: $cid})
OPTIONAL MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c)
RETURN c.id AS cid, c.fsn AS fsn,
       collect(sf.normalized)[0..3] AS sample_forms
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for cid, label in CONCEPTS:
            rows = list(s.run(_Q, cid=cid))
            if not rows or not rows[0]["fsn"]:
                print(f"  MISSING  {cid} | {label}")
                continue
            r = rows[0]
            forms = ", ".join(r["sample_forms"] or []) or "(no surface forms)"
            print(f"  FOUND    {r['cid']} | {r['fsn']}")
            print(f"           label={label}")
            print(f"           forms={forms}")
    driver.close()


if __name__ == "__main__":
    main()
