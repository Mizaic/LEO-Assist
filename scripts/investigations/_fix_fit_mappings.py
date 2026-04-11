"""Fix wrong FIT surface form mappings and add missing shorthand forms."""

import sys, os, requests, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from neo4j import GraphDatabase

BASE = "http://localhost:8001"
KG_URI = os.getenv("KNOWLEDGE_GRAPH_NEO4J_URI", "bolt://localhost:7688")
KG_USER = os.getenv("KNOWLEDGE_GRAPH_NEO4J_USERNAME", "neo4j")
KG_PASS = os.getenv("KNOWLEDGE_GRAPH_NEO4J_PASSWORD", "knowledge-dev")

PROV = "manual-fix-fit-2026-04-05"

# -- Concepts --
DETECTED = "71711000112103"  # Occult blood detected by immunoassay (positive)
NOT_DETECTED = "167667006"  # Occult blood not detected (negative)
OBSERVABLE = "1049361000000101"  # Quantitative FIT observable


# -- Helpers --
def _session_headers() -> dict:
    """Get auth headers for the terminology server."""
    try:
        from libs.terminology.client import TerminologyClient

        tc = TerminologyClient()
        if hasattr(tc, "_get_auth_headers"):
            return tc._get_auth_headers()
    except Exception:
        pass
    return {}


_headers: dict | None = None


def get_headers() -> dict:
    global _headers
    if _headers is None:
        _headers = _session_headers()
    return _headers


def delete_kg_mapping(driver, surface_form: str, concept_id: str) -> bool:
    """Delete a specific MAPS_TO relationship from the knowledge graph."""
    with driver.session() as s:
        result = s.run(
            """
            MATCH (sf:SurfaceForm {form: $form})-[r:MAPS_TO]->(c:Concept {id: $cid})
            DELETE r
            RETURN count(r) AS deleted
        """,
            form=surface_form,
            cid=concept_id,
        )
        deleted = result.single()["deleted"]
        return deleted > 0


def upsert_kg_mapping(
    driver, surface_form: str, concept_id: str, conf: float = 1.0
) -> bool:
    """Upsert a MAPS_TO relationship in the knowledge graph.

    Keys on normalized (lowercase) to avoid uniqueness constraint violations
    when surface forms differ only by case.
    """
    normalized = surface_form.lower().strip()
    with driver.session() as s:
        result = s.run(
            """
            MERGE (sf:SurfaceForm {normalized: $norm})
            ON CREATE SET sf.form = $form
            MERGE (c:Concept {id: $cid})
            MERGE (sf)-[r:MAPS_TO]->(c)
            ON CREATE SET r.confidence = $conf,
                          r.source     = 'manual',
                          r.provenance = $prov
            ON MATCH  SET r.confidence = $conf,
                          r.source     = 'manual',
                          r.provenance = $prov
            RETURN 1 AS ok
        """,
            norm=normalized,
            form=surface_form,
            cid=concept_id,
            conf=conf,
            prov=PROV,
        )
        return result.single() is not None


driver = GraphDatabase.driver(KG_URI, auth=(KG_USER, KG_PASS))

# ===========================================================================
# Step 1: Delete wrong mappings from the knowledge graph
# ===========================================================================
WRONG_MAPPINGS = [
    # (surface_form, wrong_concept_id, reason)
    ("FIT Neg", OBSERVABLE, "FIT Neg is negative result, not the test observable"),
    ("FIT pos", OBSERVABLE, "FIT pos is positive result, not the test observable"),
    (
        "FIT positive",
        OBSERVABLE,
        "FIT positive already has 2 correct mappings; 3rd to observable is noise",
    ),
    (
        "POSITIVE FIT",
        OBSERVABLE,
        "POSITIVE FIT is a positive result, not the test observable",
    ),
    (
        "negative FIT test",
        OBSERVABLE,
        "negative FIT test is a negative result, not the test observable",
    ),
    (
        "FIT posotive",
        OBSERVABLE,
        "FIT posotive (typo) is a positive result, not the test observable",
    ),
]

print("=== Step 1: Deleting wrong mappings ===\n")
for form, wrong_cid, reason in WRONG_MAPPINGS:
    ok = delete_kg_mapping(driver, form, wrong_cid)
    status = "DELETED" if ok else "NOT FOUND"
    print(f"  [{status}] {form!r} -> {wrong_cid}")
    print(f"            Reason: {reason}")

print()

# ===========================================================================
# Step 2: Upsert correct mappings for forms that had wrong targets
# ===========================================================================
CORRECT_MAPPINGS = [
    ("FIT Neg", NOT_DETECTED, "negative FIT result"),
    ("FIT neg", NOT_DETECTED, "negative FIT result (lowercase)"),
    ("FIT pos", DETECTED, "positive FIT result"),
    ("POSITIVE FIT", DETECTED, "positive FIT result phrasing"),
    ("negative FIT test", NOT_DETECTED, "negative FIT result phrasing"),
    ("FIT posotive", DETECTED, "positive FIT result (common typo)"),
]

print("=== Step 2: Upserting corrected mappings ===\n")
for form, cid, note in CORRECT_MAPPINGS:
    ok = upsert_kg_mapping(driver, form, cid, conf=1.0)
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {form!r:30s} -> {cid}  ({note})")

print()

# ===========================================================================
# Step 3: Add missing shorthand forms that don't exist yet
# ===========================================================================
NEW_FORMS = [
    ("FIT -", NOT_DETECTED, "shorthand negative FIT"),
    ("FIT +", DETECTED, "shorthand positive FIT"),
    (
        "FIT >10",
        DETECTED,
        "FIT above 10 ug/g threshold = positive per NHS England guidance",
    ),
    ("FIT>10", DETECTED, "FIT >10 without space"),
    ("FIT <10", NOT_DETECTED, "FIT below 10 ug/g threshold = negative"),
    ("FIT<10", NOT_DETECTED, "FIT <10 without space"),
]

print("=== Step 3: Adding new shorthand surface forms ===\n")
for form, cid, note in NEW_FORMS:
    ok = upsert_kg_mapping(driver, form, cid, conf=0.9)
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {form!r:30s} -> {cid}  ({note})")

driver.close()
print("\nDone. Restart the terminology server to flush in-memory cache.")
