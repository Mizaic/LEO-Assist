"""
Audit the SNOMED concepts used for 'chest X-ray findings suggestive of lung cancer'
decomposition. Verify each is in graph, check its semantic tag, and list surface forms.
"""

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

# The radiological findings a chest X-ray report would record that
# are suggestive of lung cancer (per user's clinical description)
CONCEPTS = [
    # -- Direct tumour signs --
    ("309529002", "Lung mass (finding)"),
    ("786838002", "Nodule of lung (disorder)"),
    # -- Ground glass / adenocarcinoma pattern --
    ("271807003", "Ground glass opacity (finding) - check"),
    ("32659005", "Ground-glass opacity - alternate check"),
    # -- Indirect signs: collapse --
    ("35683001", "Atelectasis (disorder)"),
    # -- Indirect signs: fluid --
    ("60046008", "Pleural effusion (disorder)"),
    # -- Indirect signs: lymph nodes --
    ("37125009", "Hilar lymphadenopathy - check"),
    ("89551006", "Bilateral hilar lymphadenopathy - check"),
    ("396345004", "Mediastinal lymphadenopathy - check"),
    # -- Physical exam (n8) - separate criterion --
    ("272016000", "On examination - chest finding (physical exam n8)"),
    # -- Abnormal CXR (broad fallback) --
    ("1290960005", "Plain X-ray of chest abnormal (finding)"),
]

_Q = """
MATCH (c:Concept {id: $cid})
OPTIONAL MATCH (sf:SurfaceForm)-[:MAPS_TO]->(c)
RETURN c.id AS cid, c.fsn AS fsn, c.semantic_tag AS tag,
       collect(sf.normalized)[0..4] AS forms
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    print(f"{'ID':20s} {'Semantic tag':25s} FSN")
    print("-" * 100)
    with driver.session() as s:
        for cid, note in CONCEPTS:
            rows = list(s.run(_Q, cid=cid))
            if not rows or not rows[0]["fsn"]:
                print(f"  MISSING  {cid:20s} ({note})")
                continue
            r = rows[0]
            tag = r["tag"] or "?"
            forms = r["forms"] or []
            print(f"  FOUND    {r['cid']:20s} [{tag:20s}] {r['fsn']}")
            if forms:
                print(f"           forms: {', '.join(forms[:3])}")
    driver.close()
    print()
    print("n8 'chest signs consistent with lung cancer' -> 272016000")
    print("  This is a PHYSICAL EXAM finding, not a radiological finding.")
    print("  It is correct for n8. The CXR finding n2 should use the")
    print("  decomposition into lung mass / nodule / GGO / atelectasis etc.")


if __name__ == "__main__":
    main()
