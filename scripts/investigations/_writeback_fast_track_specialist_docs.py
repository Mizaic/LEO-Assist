"""Write DOCUMENTS and HAS_FINDING relationships for 'Seen in fast track' encounters.

Reads the inventory from _inventory_fast_track_specialist_encounters.py, resolves
each phrase to a SNOMED concept via the terminology server (surface forms pinned by
_pin_fast_track_specialist_visits.py), then writes the DOCUMENTS relationship
directly to Neo4j following the same Cypher pattern as libs/cypher/documents_queries.py.

This bypasses LLM extraction intentionally: these administrative encounters are
suppressed by the encounter_classifier, sentence_splitter, and extraction prompt.
The writeback uses source='rule_based' and confidence=1.0 to mark it clearly.

Run (dry-run first):
    python scripts/investigations/_writeback_fast_track_specialist_docs.py --dry-run

Then live:
    python scripts/investigations/_writeback_fast_track_specialist_docs.py
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets

load_keyvault_secrets()

from libs.auth.service_auth import get_service_auth_header
from libs.terminology.surface_normalize import normalize_surface

import requests

BASE = "http://localhost:8001"
INVENTORY = (
    ROOT / "scripts" / "investigations" / "encounter_audit"
    / "fast_track_specialist_encounters.jsonl"
)

SESSION = requests.Session()
SESSION.headers.update(get_service_auth_header())

# -- Semantic tag and label for 'Seen in fast track' concepts --
_SEMANTIC_TAG = "Clinical_finding"
_LABEL = "Clinical_finding"
_REL_TYPE = "HAS_FINDING"

# -- Fallback concept for generic 'seen in fast track' without site --
# 382761000000101 = Seen in fast track suspected cancer clinic (finding)
_GENERIC_CONCEPT = {
    "concept_id": 382761000000101,
    "name": "Seen in fast track suspected cancer clinic (finding)",
    "semantic_tag": "Clinical_finding",
}

# -- Cypher: check if DOCUMENTS edge already exists --
_Q_EXISTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $eid AND c.conceptId = $concept_id
RETURN count(r) AS n
"""

# -- Cypher: write DOCUMENTS and HAS_FINDING --
# Mirrors _build_upsert_query in libs/cypher/documents_queries.py
_Q_UPSERT = f"""
MATCH (e:Encounter {{id: $encounter_id}})<-[:HAS_ENCOUNTER]-(p:Patient)
MERGE (s:{_LABEL} {{conceptId: $concept_id}})
SET s.semanticTag  = $semantic_tag,
    s.name         = $name,
    s.readCode     = $read_code,
    s.source       = $source,
    s.updated_at   = datetime(),
    s.created_at   = coalesce(s.created_at, datetime())
MERGE (e)-[r:DOCUMENTS {{conceptId: $concept_id}}]->(s)
SET r.coded_at          = datetime(),
    r.evidence          = $evidence,
    r.confidence        = $confidence,
    r.domain            = $domain,
    r.context           = $context,
    r.modifiers         = $modifiers,
    r.value             = $numeric_value,
    r.unit              = $unit,
    r.referenceRange    = $reference_range,
    r.source            = $source,
    r.model_name        = $model_name,
    r.model_version     = $model_version,
    r.contract_version  = $contract_version,
    r.run_id            = $run_id,
    r.audit_flag        = $audit_flag,
    r.decision_tier     = $decision_tier,
    r.evidence_sentence = $evidence_sentence,
    r.evidence_start    = $evidence_start,
    r.evidence_end      = $evidence_end,
    r.sentence_index    = $sentence_index,
    r.holdout           = $holdout
MERGE (p)-[:{_REL_TYPE}]->(s)
"""


def _resolve(phrase: str) -> dict | None:
    """Resolve phrase to concept dict via terminology server."""
    try:
        r = SESSION.post(
            f"{BASE}/terminology/resolve",
            json={"terms": [phrase]},
            timeout=20,
        )
        results = (r.json().get("results") or {}).get(phrase) or []
        top = results[0] if results else {}
        cid_raw = top.get("snomed_concept_id")
        if not cid_raw:
            return None
        return {
            "concept_id": int(cid_raw),
            "name": top.get("snomed_term", phrase),
            "semantic_tag": "Clinical_finding",
        }
    except Exception as exc:
        print(f"    RESOLVE ERROR for {phrase!r}: {exc}")
        return None


def _load_inventory() -> list[dict]:
    if not INVENTORY.exists():
        print(f"ERROR: Inventory not found: {INVENTORY}")
        print("Run _inventory_fast_track_specialist_encounters.py first.")
        sys.exit(1)
    rows = []
    with INVENTORY.open(encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows


def _make_params(
    encounter_id: str,
    concept: dict,
    evidence: str,
    run_id: str,
) -> dict:
    return {
        "encounter_id": encounter_id,
        "concept_id": concept["concept_id"],
        "semantic_tag": concept["semantic_tag"],
        "name": concept["name"],
        "read_code": "",
        "source": "rule_based",
        "evidence": evidence,
        "confidence": 1.0,
        "domain": "cancer",
        "context": json.dumps({
            "assertion": "present",
            "negated": False,
            "refuted": False,
            "uncertain": False,
            "historical": False,
            "planned": False,
            "hypothetical": False,
            "family": False,
            "declined": False,
            "cancelled": False,
        }),
        "modifiers": json.dumps({}),
        "numeric_value": None,
        "unit": None,
        "reference_range": None,
        "model_name": "rule_based_writeback",
        "model_version": "1.0",
        "contract_version": "1.0",
        "run_id": run_id,
        "audit_flag": False,
        "decision_tier": "auto",
        "evidence_sentence": evidence,
        "evidence_start": 0,
        "evidence_end": len(evidence),
        "sentence_index": 0,
        "holdout": False,
    }


def main(dry_run: bool = False) -> None:
    from libs.neo4j_client.client import PatientGraphClient

    rows = _load_inventory()
    run_id = str(uuid.uuid4())

    print(f"Writeback run ID: {run_id}")
    print(f"Dry run: {dry_run}")
    print(f"Loaded {len(rows)} inventory rows.")
    print()

    # Deduplicate by (encounter_id, phrase) to avoid double writes
    seen_keys: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for row in rows:
        key = (row["encounter_id"], (row.get("matched_phrase") or "").lower())
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(row)

    print(f"After dedup: {len(deduped)} rows to process.")
    print()

    written = skipped = failed = no_concept = 0

    client = PatientGraphClient()
    try:
        with client.session() as session:
            for row in deduped:
                phrase = (row.get("matched_phrase") or "").strip()
                encounter_id = row["encounter_id"]

                if not phrase:
                    concept = _GENERIC_CONCEPT
                else:
                    concept = _resolve(phrase)
                    if concept is None:
                        print(f"  [NO_CONCEPT] enc={encounter_id} phrase={phrase!r}")
                        no_concept += 1
                        continue

                # Check if DOCUMENTS edge already exists
                result = session.run(
                    _Q_EXISTS,
                    eid=encounter_id,
                    concept_id=concept["concept_id"],
                ).single()
                if result and result["n"] > 0:
                    print(
                        f"  [SKIP] enc={encounter_id} concept={concept['concept_id']}"
                        f" ({concept['name']}) -- already coded"
                    )
                    skipped += 1
                    continue

                params = _make_params(encounter_id, concept, phrase, run_id)

                if dry_run:
                    print(
                        f"  [DRY ] enc={encounter_id} -> {concept['concept_id']}"
                        f" ({concept['name']})"
                    )
                    written += 1
                    continue

                try:
                    session.run(_Q_UPSERT, **params)
                    print(
                        f"  [WRITE] enc={encounter_id} -> {concept['concept_id']}"
                        f" ({concept['name']})"
                    )
                    written += 1
                except Exception as exc:
                    print(f"  [ERROR] enc={encounter_id}: {exc}")
                    failed += 1

    finally:
        client.close()

    print()
    print("=" * 70)
    if dry_run:
        print(f"DRY RUN complete. Would write: {written}  Skip: {skipped}"
              f"  No concept: {no_concept}")
    else:
        print(f"Done. Written: {written}  Skipped: {skipped}"
              f"  No concept: {no_concept}  Errors: {failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Write DOCUMENTS relationships for 'Seen in fast track' encounters"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching the graph.",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
