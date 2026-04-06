"""Find lung imaging SNOMED concepts - search Neo4j directly."""
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

SEARCHES = [
    ("atelectasis", ["atelectasis", "collapse"]),
    ("ground glass", ["ground.glass", "ground glass"]),
    ("hilar lymph", ["hilar", "lymphadenopathy"]),
    ("mediastinal lymph", ["mediastinal.*lymph", "lymphadenopathy.*mediastin"]),
    ("consolidation", ["consolidation", "lobar consolidation"]),
    ("lung collapse", ["lung.*collapse", "collapse.*lung"]),
    ("pleural thickening", ["pleural.*thickening", "thickening.*pleural"]),
]

_Q = """
MATCH (c:Concept)
WHERE c.fsn =~ $pattern
  AND c.semantic_tag IN ['finding', 'disorder', 'morphologic abnormality']
RETURN c.id AS cid, c.fsn AS fsn, c.semantic_tag AS tag
ORDER BY size(c.fsn)
LIMIT 6
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for label, patterns in SEARCHES:
            print(f"\n-- {label} --")
            seen = set()
            for p in patterns:
                rows = list(s.run(_Q, pattern=f"(?i).*{p}.*"))
                for r in rows:
                    key = r["cid"]
                    if key in seen:
                        continue
                    seen.add(key)
                    print(f"  {r['cid']:20s} [{r['tag']:25s}] {r['fsn']}")
    driver.close()


if __name__ == "__main__":
    main()
