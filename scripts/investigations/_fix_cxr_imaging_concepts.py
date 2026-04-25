"""
Fix radiological finding surface forms for 'chest X-ray findings suggestive of lung cancer'.

Problems found:
- 271807003 was used for 'ground glass opacity' but is actually 'Eruption of skin'
- 35683001 (atelectasis) not in graph - correct is 46621007
- Hilar/mediastinal lymphadenopathy had wrong IDs

Correct SNOMED IDs (verified in graph):
- 9990010005 = Ground glass lung opacity (finding)
- 46621007   = Atelectasis (disorder)
- 308174005  = Collapse of lung (disorder)
- 87500009   = Hilar lymphadenopathy (disorder)
- 264508001  = Bilateral hilar adenopathy (disorder)
- 52324001   = Mediastinal lymphadenopathy (disorder)
- 95436008   = Lung consolidation (disorder)
- 309529002  = Lung mass (finding)                    [already correct]
- 786838002  = Nodule of lung (disorder)              [already correct]
- 60046008   = Pleural effusion (disorder)            [already correct]
"""

import os
import re
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

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


# Forms to ADD / correct
NEW_FORMS = [
    # -- Ground glass opacity (correct concept) --
    ("ground glass lung opacity", "9990010005"),
    ("ground glass opacity", "9990010005"),
    ("ground glass opacity lung", "9990010005"),
    ("GGO lung", "9990010005"),
    ("pulmonary ground glass opacity", "9990010005"),
    # -- Atelectasis / lung collapse --
    ("atelectasis", "46621007"),
    ("pulmonary atelectasis", "46621007"),
    ("lung atelectasis", "46621007"),
    ("collapse of lung", "308174005"),
    ("lung collapse", "308174005"),
    ("lobar collapse", "308174005"),
    # -- Hilar lymphadenopathy --
    ("hilar lymphadenopathy", "87500009"),
    ("hilar enlargement", "87500009"),
    ("enlarged hilar lymph nodes", "87500009"),
    ("bilateral hilar lymphadenopathy", "264508001"),
    ("bilateral hilar adenopathy", "264508001"),
    ("bilateral hilar enlargement", "264508001"),
    # -- Mediastinal lymphadenopathy --
    ("mediastinal lymphadenopathy", "52324001"),
    ("mediastinal lymph node enlargement", "52324001"),
    ("widened mediastinum", "52324001"),
    # -- Lung consolidation --
    ("lung consolidation", "95436008"),
    ("pulmonary consolidation", "95436008"),
    ("lobar consolidation", "95436008"),
]

# Wrong MAPS_TO edges to DELETE (ground glass was wrongly pointing to skin eruption)
_BAD_EDGES = [
    # normalized_form -> wrong_cid to delete
    ("ground glass lung opacity", "271807003"),
    ("ground glass opacity", "271807003"),
    ("ground glass opacity lung", "271807003"),
    ("ggo lung", "271807003"),
    ("pulmonary ground glass opacity", "271807003"),
]

_DELETE_EDGE = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[r:MAPS_TO]->(c:Concept {id: $cid})
DELETE r
RETURN count(r) AS deleted
"""

_UPSERT = """
MATCH (c:Concept {id: $cid})
MERGE (sf:SurfaceForm {normalized: $normalized})
ON CREATE SET sf.form = $form, sf.source = 'manual',
              sf.status = 'active', sf.created_at = datetime()
SET sf.form = $form
WITH sf, c
MERGE (sf)-[r:MAPS_TO]->(c)
ON CREATE SET r.confidence = 1.0, r.source = 'manual'
RETURN sf.normalized AS norm, c.id AS cid, c.fsn AS fsn
"""

_CHECK = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->(c:Concept)
RETURN c.id AS cid
"""


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    deleted_total = 0
    with driver.session() as s:
        # 1. Delete bad edges
        print("Deleting incorrect MAPS_TO edges ...")
        for form, bad_cid in _BAD_EDGES:
            norm = normalize(form)
            rows = list(s.run(_DELETE_EDGE, normalized=norm, cid=bad_cid))
            n = rows[0]["deleted"] if rows else 0
            if n:
                print(f"  [DEL ] {norm!r:50s} -> {bad_cid}")
                deleted_total += n

        # 2. Add correct edges
        print(f"\nAdding correct surface forms ...")
        added = skipped = errors = 0
        for form, cid in NEW_FORMS:
            norm = normalize(form)
            existing = list(s.run(_CHECK, normalized=norm))
            if existing and any(r["cid"] == cid for r in existing):
                print(f"  [SKIP] {norm!r:50s}")
                skipped += 1
                continue
            result = list(s.run(_UPSERT, form=form, normalized=norm, cid=cid))
            if result:
                row = result[0]
                print(f"  [ADD ] {norm!r:50s} -> {row['cid']} {row['fsn'][:40]}")
                added += 1
            else:
                print(f"  [ERR ] {norm!r:50s} concept {cid} not in graph")
                errors += 1

    driver.close()
    print(f"\nDeleted {deleted_total} bad edges")
    print(f"Added {added}, skipped {skipped}, errors {errors}/{len(NEW_FORMS)}")


if __name__ == "__main__":
    main()
