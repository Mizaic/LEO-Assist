"""
Apply tiebreak decisions for all multi-mapped SurfaceForm nodes.

Decisions:
  pre existing diabetes mellitus  -> keep 73211009  (Diabetes mellitus disorder)
  smoker                          -> keep 77176002  (Smoker finding)
  current smoker                  -> keep 77176002  (Smoker finding)
  obese                           -> keep 414915002 (Obese finding)
  night sweats                    -> keep 42984000  (Night sweats finding)
  congestive heart failure        -> keep 42343007  (Congestive heart failure disorder)
  monocyte count observation      -> keep 1107991000000100 (Monocyte count in blood obs)
  fit                             -> keep 1049361000000101 (Quantitative FIT observable)
  fit 10                          -> keep 1049361000000101 (Quantitative FIT observable)
  cin3                            -> keep 285636001 (CIN disorder - parent of CIN3)
  low back pain                   -> keep 279039007 (Low back pain finding)
  chest tightness                 -> keep 23924001  (Tight chest finding)
  urine protein creatinine ratio  -> keep 1028731000000100 (urine PCR observable)
  perennial rhinitis              -> keep 61582004  (Allergic rhinitis disorder)
  urine albumin creatinine ratio  -> keep 5801000237100 (urine ACR observable)
  faecal calprotectin             -> keep 1002571000000102 (Faecal calprotectin content obs)
  fecal calprotectin              -> keep 1002571000000102 (Faecal calprotectin content obs)
  faecal immunochemical test abnormal -> keep 1101371000000105 (BCSP FIT abnormal finding)
  fit result positive             -> keep 71711000112103 (Occult blood by immunoassay finding)
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

# normalized -> cid to KEEP (all others are deleted)
TIEBREAKS = {
    "pre existing diabetes mellitus": "73211009",
    "smoker": "77176002",
    "current smoker": "77176002",
    "obese": "414915002",
    "night sweats": "42984000",
    "congestive heart failure": "42343007",
    "monocyte count observation": "1107991000000100",
    "fit": "1049361000000101",
    "fit 10": "1049361000000101",
    "cin3": "285636001",
    "low back pain": "279039007",
    "chest tightness": "23924001",
    "urine protein creatinine ratio": "1028731000000100",
    "perennial rhinitis": "61582004",
    "urine albumin creatinine ratio": "5801000237100",
    "faecal calprotectin": "1002571000000102",
    "fecal calprotectin": "1002571000000102",
    "faecal immunochemical test abnormal": "1101371000000105",
    "fit result positive": "71711000112103",
}

_CHECK_Q = """
MATCH (sf:SurfaceForm {normalized: $norm})-[r:MAPS_TO]->(c:Concept)
RETURN c.id AS cid, c.fsn AS fsn, r.confidence AS conf
ORDER BY c.id
"""

_DELETE_Q = """
MATCH (sf:SurfaceForm {normalized: $norm})-[r:MAPS_TO]->(c:Concept)
WHERE c.id <> $keep_cid
DELETE r
RETURN count(r) AS deleted
"""


def run_fixes(driver: GraphDatabase.driver) -> None:
    with driver.session() as s:
        for norm, keep_cid in sorted(TIEBREAKS.items()):
            rows = list(s.run(_CHECK_Q, norm=norm))
            if not rows:
                print(f"  [MISS ] {norm!r:45s}  -- no SurfaceForm found")
                continue

            if len(rows) == 1:
                only = rows[0]
                if only["cid"] == keep_cid:
                    print(f"  [OK   ] {norm!r:45s}  already single -> {keep_cid}")
                else:
                    print(
                        f"  [WARN ] {norm!r:45s}  single mapping is {only['cid']}"
                        f" not {keep_cid} -- skipping"
                    )
                continue

            before = [r["cid"] for r in rows]
            if keep_cid not in before:
                print(
                    f"  [WARN ] {norm!r:45s}  keep_cid {keep_cid} not in"
                    f" current mappings {before} -- skipping"
                )
                continue

            result = s.run(_DELETE_Q, norm=norm, keep_cid=keep_cid)
            deleted = result.single()["deleted"]
            print(
                f"  [FIXED] {norm!r:45s}  deleted {deleted} edge(s),"
                f" kept {keep_cid}"
            )


def verify(driver: GraphDatabase.driver) -> None:
    print("\n-- Verification --")
    with driver.session() as s:
        for norm, keep_cid in sorted(TIEBREAKS.items()):
            rows = list(s.run(_CHECK_Q, norm=norm))
            cids = [r["cid"] for r in rows]
            if cids == [keep_cid]:
                print(f"  [PASS] {norm!r:45s}  -> {keep_cid}")
            elif not cids:
                print(f"  [MISS] {norm!r:45s}  -- no mapping at all")
            else:
                print(f"  [FAIL] {norm!r:45s}  -> {cids}")


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    try:
        print("Applying multi-mapped tiebreak fixes...\n")
        run_fixes(driver)
        verify(driver)
        print("\nDone.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
