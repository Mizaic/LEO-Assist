"""
Fetch every NG12 normative recommendation verbatim and identify phrases
that will likely need surface forms or prompt guidance.

Categories we look for:
  IMAGING  - "X-ray findings", "CT findings", "scan findings", etc.
  EXAM     - "signs consistent/compatible/suggestive of"
  AMBIG    - known ambiguous short terms (FIT, CIN, PSA, etc.)
  REFERRAL - referral action phrases
  OBS      - observable entities / lab tests with thresholds
  QUALIFY  - "new-onset", "unexplained", "persistent", "recurrent"
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

_FETCH = """
MATCH (g:Guideline {id: 'NG12'})-[:HAS_RECOMMENDATION]->(r:Recommendation)
WHERE coalesce(r.isNormative, false) = true
RETURN r.id AS id, r.title AS title, r.verbatim AS verbatim,
       r.urgency AS urgency
ORDER BY r.id
"""

PATTERNS = {
    "IMAGING": re.compile(
        r"(x[\s\-]?ray findings|ct findings|scan findings|imaging findings"
        r"|radiolog|ultrasound findings|mri findings"
        r"|findings (that |which )?(suggest|consistent|suspicious|indicat))",
        re.I,
    ),
    "EXAM_SIGN": re.compile(
        r"signs? (consistent|compatible|suggestive) (with|of)"
        r"|mass consistent with"
        r"|features? (consistent|suggestive|compatible) (with|of)"
        r"|clinical (signs?|features?) (of|suggest)",
        re.I,
    ),
    "AMBIG_TERM": re.compile(
        r"\bFIT\b|\bCIN\b|\bPSA\b|\bCA[\s\-]?125\b|\bCEA\b"
        r"|\bFOBT\b|\bHRT\b|\bIBS\b|\bIBD\b",
    ),
    "LAB_THRESHOLD": re.compile(
        r"\d+\s*(ug|mcg|ng|µg|mmol|mg|g\/l|u\/l|%)"
        r"|\bcount\b.*\braised?\b|\braised?\b.*\bcount\b"
        r"|\bthreshold\b|\blevel\b.*\braised?\b",
        re.I,
    ),
    "IMAGING_PROCEDURE": re.compile(
        r"\bchest x[\s\-]?ray\b|\bCT\b|\bMRI\b|\bultrasound\b"
        r"|\bendoscopy\b|\bcolonoscopy\b|\bcystoscopy\b"
        r"|\bOGD\b|\bflexible sigmoidoscopy\b",
        re.I,
    ),
    "UNEXPLAINED": re.compile(
        r"\bunexplained\b|\bpersistent\b|\brecurrent\b|\bnew.onset\b"
        r"|\bprogressive\b|\bworsening\b",
        re.I,
    ),
}


def flag_verbatim(text: str) -> dict[str, list[str]]:
    flags: dict[str, list[str]] = {}
    for category, pat in PATTERNS.items():
        matches = pat.findall(text or "")
        if matches:
            flags[category] = [m if isinstance(m, str) else m[0] for m in matches]
    return flags


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        recs = [dict(r) for r in s.run(_FETCH)]
    driver.close()

    print(f"Fetched {len(recs)} normative NG12 recommendations\n")
    print("=" * 80)

    imaging_needed: list[tuple] = []
    exam_needed: list[tuple] = []
    ambig_needed: list[tuple] = []

    for rec in recs:
        flags = flag_verbatim(rec.get("verbatim", ""))
        if not flags:
            continue

        print(f"\n[{rec['id']}] {rec['title']}")
        if rec.get("verbatim"):
            snippet = rec["verbatim"][:300].replace("\n", " ")
            snippet = snippet.encode("ascii", errors="replace").decode("ascii")
            print(f"  text: {snippet}...")

        for cat, matches in flags.items():
            safe = [m.encode("ascii", errors="replace").decode("ascii") for m in matches]
            print(f"  [{cat}] {safe}")
            if cat == "IMAGING":
                imaging_needed.append((rec["id"], rec["title"], matches))
            elif cat == "EXAM_SIGN":
                exam_needed.append((rec["id"], rec["title"], matches))
            elif cat == "AMBIG_TERM":
                ambig_needed.append((rec["id"], rec["title"], matches))

    print("\n\n" + "=" * 80)
    print("SUMMARY - rules needing surface form or prompt attention")
    print("=" * 80)

    print(f"\n>> IMAGING FINDINGS ({len(imaging_needed)} rules):")
    for rid, title, m in imaging_needed:
        print(f"  [{rid}] {title}  |  matches: {m}")

    print(f"\n>> EXAM SIGNS ({len(exam_needed)} rules):")
    for rid, title, m in exam_needed:
        print(f"  [{rid}] {title}  |  matches: {m}")

    print(f"\n>> AMBIGUOUS TERMS ({len(ambig_needed)} rules):")
    for rid, title, m in ambig_needed:
        print(f"  [{rid}] {title}  |  matches: {m}")


if __name__ == "__main__":
    main()
