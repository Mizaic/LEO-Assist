"""
Inspect what text fields are available on Encounter nodes and linked note nodes.
Check for a sample of stale patients to understand what the source of truth looks like.
"""

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

_Q_ENC_PROPS = """
MATCH (e:Encounter)
RETURN keys(e) AS k
LIMIT 1
"""

_Q_ENC_SAMPLE = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
RETURN e.id AS eid, e.date AS date, keys(e) AS props,
       e.text AS text, e.note AS note, e.description AS description,
       e.raw_text AS raw_text, e.source_text AS source_text,
       e.display AS display, e.title AS title, e.type AS type,
       e.category AS category
ORDER BY e.date DESC
LIMIT 5
"""

# What nodes are directly linked to encounters
_Q_LINKED_NODES = """
MATCH (e:Encounter)-[r]->(n)
WHERE e.id = $eid
RETURN type(r) AS rel, labels(n) AS lbl, keys(n) AS nkeys,
       n.text AS text, n.note AS note, n.description AS description,
       n.content AS content, n.name AS name, n.value AS value
LIMIT 20
"""

# Check if there's a ClinicalNote or similar text node
_Q_TEXT_NODES = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
MATCH (e)-[r]->(n)
WHERE n.text IS NOT NULL OR n.note IS NOT NULL
   OR n.description IS NOT NULL OR n.content IS NOT NULL
RETURN type(r) AS rel, labels(n) AS lbl, n.text AS text,
       n.note AS note, n.content AS content, e.date AS date
ORDER BY e.date DESC
LIMIT 10
"""

# Check full encounter node for a stale patient on the referral date
_Q_FULL_ENC = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid AND e.date = $date
RETURN e AS enc
"""

# Sample of encounters across all patients - get encounter IDs
_Q_SAMPLE_ENC_IDS = """
MATCH (e:Encounter)
RETURN e.id AS eid
LIMIT 3
"""


SAMPLE_PIDS = ["4203796334", "4921442355", "4940120139"]


def main():
    pg = PatientGraphClient()
    try:
        print("=== Encounter node properties ===")
        with pg.session() as s:
            r = s.run(_Q_ENC_PROPS).single()
        enc_keys = sorted(r["k"]) if r else []
        print(f"  Keys: {enc_keys}")

        print()
        print("=== Sample encounter records (first stale patient) ===")
        with pg.session() as s:
            rows = s.run(_Q_ENC_SAMPLE, pid=SAMPLE_PIDS[0]).data()
        for r in rows:
            print(f"  date={r['date']} id={r['eid']}")
            for prop in [
                "text",
                "note",
                "description",
                "raw_text",
                "source_text",
                "display",
                "title",
                "type",
                "category",
            ]:
                if r.get(prop) is not None:
                    val = str(r[prop])[:200]
                    print(f"    {prop}: {val}")

        print()
        print("=== Nodes linked from encounters ===")
        with pg.session() as s:
            sample_ids = s.run(_Q_SAMPLE_ENC_IDS).data()
        for id_row in sample_ids:
            eid = id_row["eid"]
            print(f"  Encounter {eid}:")
            with pg.session() as s:
                linked = s.run(_Q_LINKED_NODES, eid=eid).data()
            for ln in linked:
                text_val = (
                    ln.get("text")
                    or ln.get("note")
                    or ln.get("description")
                    or ln.get("content")
                    or ln.get("name")
                    or ln.get("value")
                )
                print(f"    -[{ln['rel']}]-> {ln['lbl']} | {text_val!r:.100}")

        print()
        print("=== Text nodes linked to stale patient encounters ===")
        for pid in SAMPLE_PIDS:
            with pg.session() as s:
                rows = s.run(_Q_TEXT_NODES, pid=pid).data()
            if rows:
                print(f"  Patient {pid} - has text-bearing linked nodes:")
                for r in rows:
                    text = r.get("text") or r.get("note") or r.get("content")
                    print(
                        f"    date={r['date']} -{r['rel']}-> {r['lbl']}: {str(text)[:150]!r}"
                    )
            else:
                print(f"  Patient {pid} - no text-bearing nodes linked to encounters")

        print()
        print("=== Full encounter node on referral date (4203796334 / 2024-08-05) ===")
        with pg.session() as s:
            rows = s.run(_Q_FULL_ENC, pid="4203796334", date="2024-08-05").data()
        for r in rows:
            enc = dict(r["enc"])
            for k, v in sorted(enc.items()):
                val = str(v)[:300] if v is not None else None
                if val:
                    print(f"  {k}: {val}")

    finally:
        pg.close()


if __name__ == "__main__":
    main()
