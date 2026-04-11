"""
Sample raw encounter text and classification metadata from stale HITL patients.
Shows what the text actually says, what classification metadata is present,
and whether that is enough to detect anchors without SNOMED codes.
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

# Pick a small set of stale HITL patients from the previous output
SAMPLE_PIDS = [
    "4203796334",  # stale skin x2
    "4246870471",  # stale upper_gi + lower_gi in_progress
    "4926916703",  # 5 HITL - lung, breast, lower_gi
    "4842019832",  # 3 HITL - head_and_neck, lower_gi
]

_Q = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND e.date >= '2023-01-01'
OPTIONAL MATCH (e)-[r:DOCUMENTS]->(c)
RETURN
    e.date AS date,
    e.coding_status AS coding_status,
    e.classification_content_type AS content_type,
    e.classification_clinical_significance AS significance,
    e.classification_domains AS domains,
    e.classification_encounter_purpose AS purpose,
    e.text AS text,
    collect({name: c.name, tag: c.semanticTag, assertion: r.assertion}) AS concepts
ORDER BY e.date
"""


def summarise_text(text: str, max_chars: int = 300) -> str:
    if not text:
        return "(no text)"
    text = text.replace("\n", " ").strip()
    # Strip non-ASCII to avoid Windows cp1252 encoding errors
    text = text.encode("ascii", errors="replace").decode("ascii")
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def main():
    pg = PatientGraphClient()
    try:
        for pid in SAMPLE_PIDS:
            print("=" * 80)
            print(f"PATIENT {pid}")
            print("=" * 80)
            with pg.session() as s:
                rows = s.run(_Q, pid=pid).data()

            for r in rows:
                concepts = [c for c in (r.get("concepts") or []) if c.get("name")]
                print(
                    f"\n  {r['date']}  [{r['coding_status']}]"
                    f"  type={r['content_type']}  sig={r['significance']}"
                    f"  purpose={r['purpose']}"
                )
                print(f"  domains={r['domains']}")
                if concepts:
                    for c in concepts[:4]:
                        print(f"    CODE: [{c['assertion']}] {c['name']} ({c['tag']})")
                else:
                    print("    CODE: (none)")
                print(f"  TEXT: {summarise_text(r['text'])}")
    finally:
        pg.close()


if __name__ == "__main__":
    main()
