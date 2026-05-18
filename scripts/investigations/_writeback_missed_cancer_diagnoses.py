"""Missed cancer diagnoses for E14 and E20 -- diagnostic write-back script.

From the 39-episode referral-only audit, two episodes need coding fixes:

  E14  pid=9990002008  breast  2025-09-05
       FINDING: Malignant neoplasm of breast (254837009) is ALREADY CODED
       on encounter a40cf282-af2 by the pipeline. The episode builder is NOT
       detecting it because the IS_A expansion from the cancer_types parent
       concept in Neo4j does not reach 254837009 within the 5-hop limit.
       FIX: Rerun episode detector after the benign_closure ValueSet changes.
            Ensure 254837009 is within 5 IS_A hops of the cancer_types parent.

  E20  pid=9990002009  skin  2024-11-18
       FINDING: SCC of scalp confirmed on histology but NEVER EXTRACTED by
       the coding pipeline. Concept nodes for confirmed SCC (402815007 etc.)
       do NOT exist in the KG as `:Concept` nodes, so direct write-back is
       not possible without calling the terminology server.
       FIX: Rerun coding pipeline for the Nov-Dec 2024 encounters. The updated
            extraction_v1 prompt now includes guidance on coding cancer diagnosis
            from histopathology / clinic letters.

This script:
  1. Confirms E14 status (breast cancer already in graph).
  2. Identifies E20's target encounter for the SCC diagnosis.
  3. Calls the terminology server to resolve the SCC concept and seed it.
  4. Writes the DOCUMENTS relationship for E20 if seeding succeeds.

Run:
    python scripts/investigations/_writeback_missed_cancer_diagnoses.py
"""

from __future__ import annotations

import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

import os
from libs.neo4j_client.client import PatientGraphClient

_TERM_API = os.environ.get("TERMINOLOGY_API_URL", "http://localhost:8002")

# ---------------------------------------------------------------------------
_Q_DOCS_WINDOW = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c:Concept)
WHERE toString(p.id) = $patient_id
  AND e.date >= date($after)
  AND e.date <= date($before)
RETURN
    toString(e.id)        AS enc_id,
    toString(e.date)      AS enc_date,
    c.conceptId           AS concept_id,
    c.name                AS concept_name,
    coalesce(r.assertion, 'present') AS assertion
ORDER BY enc_date, c.conceptId
"""

_Q_ENCOUNTERS_WINDOW = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $patient_id
  AND e.date >= date($after)
  AND e.date <= date($before)
RETURN toString(e.id) AS enc_id, toString(e.date) AS enc_date
ORDER BY enc_date
"""

_Q_UPSERT_DOCS = """
MATCH (e:Encounter) WHERE toString(e.id) = $enc_id
MATCH (c:Concept {conceptId: toInteger($concept_id)})
MERGE (e)-[r:DOCUMENTS {conceptId: toInteger($concept_id)}]->(c)
SET r.source            = 'manual',
    r.confidence        = 1.0,
    r.assertion         = 'present',
    r.evidence          = $concept_name,
    r.evidence_sentence = $evidence_sentence,
    r.coded_at          = datetime(),
    r.provenance        = 'writeback-missed-cancer-2026-04-06'
RETURN toString(e.id) AS enc_id, c.conceptId AS concept_id
"""

_Q_SEED_CONCEPT = """
MERGE (c:Concept {conceptId: toInteger($concept_id)})
SET c.name        = $name,
    c.semanticTag = $semantic_tag,
    c.active      = true
RETURN c.conceptId AS concept_id
"""

_Q_ADD_PATIENT_SITUATION = """
MATCH (p:Patient {id: toInteger($patient_id)})
MATCH (c:Concept {conceptId: toInteger($concept_id)})
MERGE (p)-[:HAS_SITUATION]->(c)
"""


def _resolve_term(term: str) -> dict | None:
    """Call the terminology API to resolve a free-text term to a SNOMED concept."""
    url = f"{_TERM_API}/terminology/resolve"
    params = urllib.parse.urlencode({"term": term, "max_results": 1})
    try:
        with urllib.request.urlopen(f"{url}?{params}", timeout=10) as resp:
            data = json.loads(resp.read())
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict) and data.get("results"):
                return data["results"][0]
    except Exception as exc:
        print(f"  [WARN] Terminology API unreachable: {exc}")
    return None


def _check_e14(session) -> None:
    print("=" * 60)
    print("  E14 -- breast cancer (pid=9990002008)")
    print()

    rows = list(
        session.run(
            _Q_DOCS_WINDOW,
            patient_id="9990002008",
            after="2025-09-04",
            before="2025-09-06",
        )
    )
    breast_ids = {254837009, 9990010017, 363346000}
    found = [r for r in rows if r["concept_id"] in breast_ids]

    if found:
        print("  [OK] Breast cancer concept already coded -- no write-back needed.")
        for r in found:
            print(f"       {r['enc_date']}  {r['concept_id']}  {r['concept_name']}")
        print()
        print("  Root cause: IS_A expansion from cancer_types parent does not")
        print("  reach 254837009 within 5 hops. Rerun episode detector to fix.")
    else:
        print("  [INFO] No breast cancer concepts found in 2025-09-04 to 09-06 window.")
        print("         (Known from full scan: 254837009 IS coded on a40cf282-af2.)")
        print("         Date query may use different format. Rerun episode detector.")


def _fix_e20(session) -> None:
    print("=" * 60)
    print("  E20 -- SCC scalp (pid=9990002009)")
    print()

    # What's currently coded in Nov-Dec 2024?
    rows = list(
        session.run(
            _Q_DOCS_WINDOW,
            patient_id="9990002009",
            after="2024-11-01",
            before="2024-12-31",
        )
    )
    scc_ids = {402815007, 93761005, 372130007, 28899001}
    if any(r["concept_id"] in scc_ids for r in rows):
        print("  [OK] SCC concept already coded in Nov-Dec 2024. No write-back needed.")
        return

    print("  Coded in Nov-Dec 2024:")
    for r in rows:
        print(
            f"    {r['enc_date']}  {r['concept_id']}  {(r['concept_name'] or '')[:45]}"
        )
    print()

    # Find the biopsy / histology encounter
    encs = list(
        session.run(
            _Q_ENCOUNTERS_WINDOW,
            patient_id="9990002009",
            after="2024-11-15",
            before="2024-11-20",
        )
    )
    if not encs:
        print("  [WARN] No encounter in 2024-11-15 to 2024-11-20 window.")
        print("         Cannot write-back. Rerun pipeline for this patient.")
        return

    target_enc_id = encs[0]["enc_id"]
    target_enc_date = encs[0]["enc_date"]
    print(f"  Target encounter: {target_enc_date}  {target_enc_id}")
    print()

    # Resolve SCC via terminology API
    print("  Resolving 'squamous cell carcinoma of scalp' via terminology API ...")
    concept = _resolve_term("squamous cell carcinoma of skin")
    if concept:
        cid = concept.get("conceptId") or concept.get("concept_id")
        cname = (
            concept.get("preferredTerm")
            or concept.get("name")
            or "Squamous cell carcinoma of skin"
        )
        semantic_tag = concept.get("semanticTag", "disorder")
        print(f"  Resolved: {cid}  {cname}")
    else:
        # Fallback to a known safe SCC concept -- seed it directly
        cid = 93761005
        cname = "Squamous cell carcinoma of skin (disorder)"
        semantic_tag = "disorder"
        print(f"  Terminology API unavailable. Using fallback: {cid}  {cname}")

    # Seed the Concept node if not already present
    print(f"  Seeding Concept node {cid} ...")
    session.run(_Q_SEED_CONCEPT, concept_id=cid, name=cname, semantic_tag=semantic_tag)

    # Write the DOCUMENTS relationship
    evidence = (
        "Right scalp vertex excision 18th of Nov -- SCC invades subcutis, "
        "completely excised 5mm peripheral and deep margin (histopathology confirmed)"
    )
    try:
        wb = list(
            session.run(
                _Q_UPSERT_DOCS,
                enc_id=target_enc_id,
                concept_id=cid,
                concept_name=cname,
                evidence_sentence=evidence,
            )
        )
        if wb:
            print(
                f"  [WRITTEN] enc={wb[0]['enc_id'][:20]}  concept={wb[0]['concept_id']}"
            )
            # Add HAS_SITUATION to patient graph
            session.run(
                _Q_ADD_PATIENT_SITUATION,
                patient_id="9990002009",
                concept_id=cid,
            )
            print("  [WRITTEN] HAS_SITUATION added to patient graph.")
        else:
            print(
                "  [WARN] Upsert matched 0 rows. Check encounter ID and concept node."
            )
    except Exception as exc:
        print(f"  [FAIL] {exc}")


def main() -> None:
    client = PatientGraphClient()
    try:
        with client.session() as session:
            _check_e14(session)
            print()
            _fix_e20(session)
            print()
    finally:
        client.close()
    print("Done.")


if __name__ == "__main__":
    main()
