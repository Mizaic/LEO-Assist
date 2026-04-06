"""Audit all FIT-related surface forms and flag gaps."""
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

FIT_KEYWORDS = ["fit", "faecal", "fecal", "immunochemical", "occult", "qfit", "fobt"]

_QUERY = """
MATCH (sf:SurfaceForm)-[r:MAPS_TO]->(c:Concept)
WHERE any(kw IN $keywords WHERE toLower(sf.normalized) CONTAINS kw
       OR toLower(sf.form) CONTAINS kw)
RETURN sf.normalized AS norm, sf.form AS form,
       c.id AS cid, c.fsn AS fsn, r.confidence AS conf
ORDER BY c.id, sf.normalized
"""

# What clinical phrasings should exist, grouped by target concept
EXPECTED = {
    "1049361000000101 - Quantitative FIT (observable)": [
        "fit",
        "fit test",
        "fit 10",
        "qfit",
        "quantitative fit",
        "faecal immunochemical test",
        "fecal immunochemical test",
        "fit score",
        "fit result",
        "fit level",
        "fit value",
    ],
    "71711000112103 - FIT positive (finding)": [
        "fit positive",
        "fit result positive",
        "fit raised",
        "fit elevated",
        "fit abnormal",
        "positive fit",
        "raised fit",
        "fit above threshold",
        "occult blood detected in faeces by immunoassay",
        "occult blood detected in feces by immunoassay",
    ],
    "167667006 - FIT negative (finding)": [
        "fit negative",
        "fit result negative",
        "fit normal",
        "negative fit",
        "occult blood not detected in faeces",
        "occult blood not detected in feces",
    ],
    "1101371000000105 - BCSP FIT abnormal (finding)": [
        "faecal immunochemical test abnormal",
        "bowel cancer screening fit abnormal",
        "bcsp fit abnormal",
    ],
    "1101361000000103 - BCSP FIT normal (finding)": [
        "faecal immunochemical test normal",
        "bcsp fit normal",
        "bowel cancer screening fit normal",
    ],
}


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        rows = list(s.run(_QUERY, keywords=FIT_KEYWORDS))
    driver.close()

    print(f"Found {len(rows)} FIT-related surface forms in graph:\n")
    existing_norms = set()
    for row in rows:
        print(
            f"  norm={row['norm']!r:45s}"
            f" cid={row['cid']:25s} fsn={row['fsn'][:60]}"
        )
        existing_norms.add(row["norm"])

    print("\n\n=== GAP ANALYSIS ===\n")
    all_missing = []
    for group, phrases in EXPECTED.items():
        missing = [p for p in phrases if p not in existing_norms]
        covered = [p for p in phrases if p in existing_norms]
        status = "COMPLETE" if not missing else f"MISSING {len(missing)}"
        print(f"[{status}] {group}")
        for p in covered:
            print(f"    OK  {p!r}")
        for p in missing:
            print(f"    GAP {p!r}")
            all_missing.append((group, p))
        print()

    print(f"Total gaps: {len(all_missing)}")


if __name__ == "__main__":
    main()
