"""Check whether key fast-track referral concepts are present in the graph."""
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

CHECKS = [
    ("276551000000108", "Fast track referral for suspected upper gastrointestinal cancer"),
    ("276491000000101", "Fast track referral for suspected lung cancer"),
    ("276461000000107", "Fast track referral for suspected head and neck cancer"),
    ("276371000000106", "Fast track referral for suspected colorectal cancer"),
    ("276281000000104", "Fast track referral for suspected lower gastrointestinal cancer"),
    ("276521000000103", "Fast track referral for suspected gynaecological cancer"),
    ("276581000000102", "Fast track referral for suspected urological cancer"),
    ("199251000000107", "Fast track referral for suspected cancer"),
    ("38661000000100",  "Fast track referral (procedure)"),
]

_QUERY = "MATCH (c:Concept {id: $cid}) RETURN c.id AS cid, c.fsn AS fsn"


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        for cid, label in CHECKS:
            rows = list(s.run(_QUERY, cid=cid))
            if rows:
                fsn = rows[0]["fsn"] or "(no fsn)"
                print(f"  FOUND   {cid} | {fsn[:60]}")
            else:
                print(f"  MISSING {cid} | {label}")
    driver.close()


if __name__ == "__main__":
    main()
