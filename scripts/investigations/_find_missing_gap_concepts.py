"""Find correct concept IDs for CA125, gallbladder, and soft tissue lump."""

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
    ("CA 125", "ca125"),
    ("CA 125", "ca 125"),
    ("CA 125", "cancer antigen 125"),
    ("CA 125", "ovarian"),
    ("gallbladder palpable", "gall"),
    ("gallbladder palpable", "gallbladder"),
    ("soft tissue lump", "soft tissue"),
    ("soft tissue lump", "lump"),
    ("soft tissue lump", "swelling"),
]

driver = GraphDatabase.driver(uri, auth=(user, pwd))
with driver.session() as s:
    for label, kw in SEARCHES:
        rows = list(
            s.run(
                """
            MATCH (c:Concept)
            WHERE toLower(c.fsn) CONTAINS toLower($kw)
            AND c.semantic_tag IN ['finding','disorder','observable entity']
            RETURN c.id AS cid, c.fsn AS fsn, c.semantic_tag AS tag
            ORDER BY c.fsn
            LIMIT 6
            """,
                kw=kw,
            )
        )
        if rows:
            print(f"\n  [{label}] keyword={kw!r}")
            for r in rows:
                print(f"    {r['cid']:20s} ({r['tag']:22s}) {r['fsn'][:65]}")
driver.close()
