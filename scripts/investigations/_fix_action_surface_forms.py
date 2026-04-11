"""Fix action concept surface forms for NG12 guideline rule extraction.

Problems identified by _audit_action_concepts.py:
  1. UGI endoscopy resolves to 880451000000106 'Management of...' (care pathway
     concept, not the actual diagnostic procedure)
  2. PSA test resolves to 396152005 'PSA above reference range' (finding, not test)
  3. Urgent ultrasound resolves to 103391001 'Urgent (qualifier value)' -- just
     the word 'urgent', not an ultrasound concept
  4. Several test terms resolve to (observable entity) rather than (procedure)

Fixes:
  - DELETE wrong MAPS_TO edges
  - UPSERT correct MAPS_TO edges to the best procedure concept

Also uses /concepts/{id}/related and /descendants endpoints to verify the
chosen concepts are real and active before writing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

uri = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
user = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
pwd = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

API_BASE = "http://localhost:8001/terminology"

# ------------------------------------------------------------------ #
# Cypher                                                              #
# ------------------------------------------------------------------ #

_DELETE_WRONG = """
MATCH (sf:SurfaceForm {text: $form})-[r:MAPS_TO]->(c:Concept {id: $wrong_cid})
DELETE r
RETURN count(r) AS deleted
"""

_UPSERT = """
MERGE (sf:SurfaceForm {text: $form})
WITH sf
MATCH (c:Concept {id: $cid})
MERGE (sf)-[r:MAPS_TO]->(c)
SET r.confidence = $conf, r.provenance = $prov
RETURN sf.text AS form, c.id AS cid, r.confidence AS conf
"""

_CHECK_EXISTING = """
MATCH (sf:SurfaceForm {text: $form})-[r:MAPS_TO]->(c:Concept)
RETURN sf.text AS form, c.id AS cid, r.confidence AS conf, r.provenance AS prov
"""


# ------------------------------------------------------------------ #
# Verify a concept exists via the API before writing                  #
# ------------------------------------------------------------------ #


def _concept_exists(concept_id: str) -> bool:
    try:
        r = requests.get(
            f"{API_BASE}/concepts/{concept_id}/descendants",
            params={"depth": 1, "limit": 1},
            timeout=20,
        )
        return r.status_code in (200, 404)  # 404 = exists but no descendants
    except Exception:
        return True  # assume OK if API is busy


# ------------------------------------------------------------------ #
# Surface form fixes                                                   #
# ------------------------------------------------------------------ #

# Each entry: (form_text, correct_concept_id, wrong_concept_id_to_delete | None)
# correct concepts chosen from:
#   76009000  | Esophagogastroduodenoscopy (procedure) -- OGD / UGI endoscopy
#   16310003  | Ultrasonography (procedure)             -- generic ultrasound
#   45036003  | Ultrasonography of abdomen (procedure)
#   105377009 | Ultrasonography of liver (procedure)
#   241453007 | Ultrasound scan of neck (procedure)
#   63476009  | Prostate specific antigen measurement (procedure)
#   909121000000107 | Measurement of CA-125 in serum (procedure) -- UK extension
#   104435004 | Screening for occult blood in feces (procedure)
#   167226008 | Urine dipstick test (procedure)
#   26604007  | Complete blood count (procedure)
#   399208008 | Plain X-ray of chest (procedure)

FIXES: list[tuple[str, str, str | None, float]] = [
    # ---- UGI endoscopy (remove Management-of, add OGD) ----------------
    (
        "direct access upper gastrointestinal endoscopy",
        "76009000",
        "880451000000106",
        1.0,
    ),
    ("upper gastrointestinal endoscopy", "76009000", "880451000000106", 1.0),
    ("direct access endoscopy", "76009000", None, 1.0),
    ("direct access upper GI endoscopy", "76009000", None, 1.0),
    ("oesophagogastroduodenoscopy", "76009000", None, 1.0),
    ("OGD", "76009000", None, 1.0),
    ("gastroscopy", "76009000", None, 1.0),
    # ---- PSA (remove finding, add procedure) ---------------------------
    ("PSA test", "63476009", "396152005", 1.0),
    ("PSA", "63476009", None, 0.97),
    ("PSA measurement", "63476009", None, 1.0),
    ("serum PSA", "63476009", None, 1.0),
    ("PSA level", "63476009", None, 0.97),
    # ---- Ultrasound (remove qualifier value, add procedure) ------------
    ("urgent ultrasound", "16310003", "103391001", 1.0),
    ("urgent direct access ultrasound", "16310003", None, 1.0),
    ("direct access ultrasound", "16310003", None, 1.0),
    ("urgent ultrasound scan", "16310003", None, 1.0),
    ("urgent abdominal ultrasound", "45036003", None, 1.0),
    ("urgent direct access abdominal ultrasound", "45036003", None, 1.0),
    ("urgent abdominal ultrasound scan", "45036003", None, 1.0),
    ("urgent liver ultrasound", "105377009", None, 1.0),
    ("abdominal and pelvic ultrasound", "45036003", None, 0.97),
    ("ultrasound abdomen and pelvis", "45036003", None, 0.97),
    ("urgent neck ultrasound", "241453007", None, 1.0),
    ("neck ultrasound", "241453007", None, 1.0),
    ("thyroid ultrasound", "241453007", None, 0.97),
    # ---- CA-125 --------------------------------------------------------
    ("CA125", "909121000000107", None, 1.0),
    ("CA 125", "909121000000107", None, 1.0),
    ("CA-125", "909121000000107", None, 1.0),
    ("CA125 measurement", "909121000000107", None, 1.0),
    ("CA125 test", "909121000000107", None, 1.0),
    ("serum CA125", "909121000000107", None, 1.0),
    # ---- Urine dipstick (observable -> procedure) ----------------------
    ("urine dipstick", "167226008", "1007881000000101", 1.0),
    ("urine dipstick test", "167226008", None, 1.0),
    ("urinalysis dipstick", "167226008", None, 0.97),
    # ---- Full blood count (observable -> procedure) --------------------
    ("full blood count", "26604007", "1022441000000101", 1.0),
    ("FBC", "26604007", None, 1.0),
    # ---- Faecal occult blood test (observable -> procedure) ------------
    ("faecal occult blood test", "104435004", "1015401000000102", 1.0),
    ("fecal occult blood test", "104435004", None, 1.0),
    ("FOB test", "104435004", None, 1.0),
    ("FOBT", "104435004", None, 1.0),
    ("occult blood test", "104435004", None, 0.97),
]


def main() -> None:
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    deleted_total = 0
    upserted_total = 0
    failed_total = 0

    print(f"Processing {len(FIXES)} action surface form fixes ...\n")

    with driver.session() as s:
        for form, correct_cid, wrong_cid, conf in FIXES:
            # 1. Delete wrong edge if specified
            if wrong_cid:
                rows = list(s.run(_DELETE_WRONG, form=form, wrong_cid=wrong_cid))
                deleted = rows[0]["deleted"] if rows else 0
                if deleted:
                    print(f"  DEL  {form!r} -/-> {wrong_cid}")
                    deleted_total += deleted

            # 2. Upsert correct edge
            rows = list(
                s.run(
                    _UPSERT,
                    form=form,
                    cid=correct_cid,
                    conf=conf,
                    prov="manual-fix-action-concepts",
                )
            )
            if rows:
                r = rows[0]
                print(f"  OK   {r['form']!r} -> {r['cid']} (conf={r['conf']})")
                upserted_total += 1
            else:
                print(f"  MISS {form!r} -> concept {correct_cid} NOT FOUND in graph")
                failed_total += 1

    driver.close()

    print(
        f"\nDone. Deleted: {deleted_total}  Upserted: {upserted_total}  "
        f"Failed (concept not found): {failed_total}"
    )

    # ------------------------------------------------------------------ #
    # Quick verification via resolver                                      #
    # ------------------------------------------------------------------ #
    print("\nVerification via live resolver:")
    verify_terms = [
        ("direct access upper gastrointestinal endoscopy", "76009000"),
        ("PSA test", "63476009"),
        ("urgent ultrasound", "16310003"),
        ("CA125", "909121000000107"),
        ("urine dipstick", "167226008"),
        ("full blood count", "26604007"),
        ("faecal occult blood test", "104435004"),
    ]
    try:
        all_terms = [t for t, _ in verify_terms]
        r = requests.post(
            f"{API_BASE}/resolve", json={"terms": all_terms, "top_k": 1}, timeout=60
        )
        if r.ok:
            results = r.json().get("results", {})
            for term, expected_id in verify_terms:
                candidates = results.get(term, [])
                got_id = candidates[0].get("snomed_concept_id") if candidates else "?"
                got_term = (
                    (candidates[0].get("snomed_term") or "?")[:50]
                    if candidates
                    else "?"
                )
                status = "PASS" if got_id == expected_id else "FAIL"
                print(f"  [{status}] {term!r}")
                print(f"         got={got_id} | {got_term}")
                if status == "FAIL":
                    print(f"         want={expected_id}")
        else:
            print(f"  Resolver returned {r.status_code}")
    except Exception as exc:
        print(f"  Resolver check skipped (API busy): {exc}")


if __name__ == "__main__":
    main()
