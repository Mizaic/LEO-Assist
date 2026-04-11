"""Select and mark 500 stratified encounters as holdout for NER evaluation.

Queries Neo4j for encounters across clinical domains and marks them
holdout=true on their DOCUMENTS relationships. Guarantees minimum 20
encounters per safety-critical category. Outputs a manifest file showing
the stratification for audit and clinician assignment.

Safety-critical categories require minimum 20 encounters each so that
per-category F1 scores are statistically meaningful for:
  - cancer / oncology
  - safeguarding / mental health crisis
  - mental health (depression, anxiety, self-harm, suicide)

Design control: DI-LEO-AI-078, VT-LEO-AI-078
Risk: R-LEO-AI-053 (training/test contamination)

IMPORTANT: Run BEFORE any training data export. Holdout encounters must
never appear in any training JSONL file (enforced by export query filter).

Usage
-----
    python scripts/select_holdout_set.py --dry-run
    python scripts/select_holdout_set.py --yes
    python scripts/select_holdout_set.py --yes --manifest holdout_manifest.json

Do NOT run this script more than once. Holdout set is immutable after
selection. To verify current holdout set use --verify-only.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from dotenv import load_dotenv  # noqa: E402
from libs.keyvault.loader import load_keyvault_secrets  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)
load_keyvault_secrets()

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("select_holdout")

# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------

TOTAL_HOLDOUT = 500

DOMAINS: dict[str, dict[str, Any]] = {
    "oncology": {
        "keywords": [
            "cancer",
            "carcinoma",
            "malignant",
            "tumour",
            "tumor",
            "leukaemia",
            "lymphoma",
            "melanoma",
            "neoplasm",
        ],
        "target": 65,
        "min_required": 20,
        "safety_critical": True,
        "clinician_validation_required": True,
    },
    "mental_health": {
        "keywords": [
            "depression",
            "anxiety",
            "schizophrenia",
            "bipolar",
            "psychosis",
            "mental health",
            "ptsd",
            "eating disorder",
        ],
        "target": 60,
        "min_required": 20,
        "safety_critical": True,
        "clinician_validation_required": True,
    },
    "safeguarding": {
        "keywords": [
            "self-harm",
            "suicidal",
            "safeguarding",
            "suicide",
            "self harm",
            "overdose",
            "crisis",
            "at risk",
        ],
        "target": 25,
        "min_required": 20,
        "safety_critical": True,
        "clinician_validation_required": True,
    },
    "respiratory": {
        "keywords": [
            "asthma",
            "copd",
            "pneumonia",
            "bronchitis",
            "respiratory",
            "lung",
            "pleural",
            "emphysema",
            "dyspnoea",
        ],
        "target": 60,
        "min_required": 0,
        "safety_critical": False,
        "clinician_validation_required": False,
    },
    "cardiovascular": {
        "keywords": [
            "heart failure",
            "atrial fibrillation",
            "hypertension",
            "coronary",
            "angina",
            "myocardial",
            "cardiac",
            "stroke",
        ],
        "target": 60,
        "min_required": 0,
        "safety_critical": False,
        "clinician_validation_required": False,
    },
    "musculoskeletal": {
        "keywords": [
            "arthritis",
            "osteoporosis",
            "fracture",
            "back pain",
            "musculoskeletal",
            "joint",
            "rheumatoid",
        ],
        "target": 50,
        "min_required": 0,
        "safety_critical": False,
        "clinician_validation_required": False,
    },
    "endocrine": {
        "keywords": [
            "diabetes",
            "thyroid",
            "hyperthyroid",
            "hypothyroid",
            "adrenal",
            "insulin",
            "hba1c",
        ],
        "target": 50,
        "min_required": 0,
        "safety_critical": False,
        "clinician_validation_required": False,
    },
    "gastrointestinal": {
        "keywords": [
            "ibs",
            "crohn",
            "colitis",
            "gastro",
            "reflux",
            "bowel",
            "hepatitis",
            "liver",
            "gallstone",
            "coeliac",
        ],
        "target": 50,
        "min_required": 0,
        "safety_critical": False,
        "clinician_validation_required": False,
    },
    "dermatology": {
        "keywords": [
            "eczema",
            "psoriasis",
            "dermatitis",
            "rash",
            "acne",
            "urticaria",
            "cellulitis",
            "wound",
        ],
        "target": 30,
        "min_required": 0,
        "safety_critical": False,
        "clinician_validation_required": False,
    },
}

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_Q_SAMPLE_DOMAIN = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(s)
WHERE e.text IS NOT NULL
  AND trim(e.text) <> ''
  AND s.name IS NOT NULL
  AND any(kw IN $keywords WHERE toLower(s.name) CONTAINS kw)
  AND NOT EXISTS {
    MATCH (e)-[r2:DOCUMENTS]->()
    WHERE r2.holdout = true
  }
WITH DISTINCT p.id AS patient_id,
     e.id AS encounter_id,
     toString(e.date) AS date,
     $domain AS domain
ORDER BY rand()
LIMIT $limit
RETURN patient_id, encounter_id, date, domain
"""

_Q_MARK_HOLDOUT_BATCH = """
UNWIND $encounter_ids AS eid
MATCH (e:Encounter {id: eid})-[r:DOCUMENTS]->()
SET r.holdout = true, r.holdout_set_date = $set_date
RETURN count(r) AS updated
"""

_Q_COUNT_EXISTING_HOLDOUT = """
MATCH ()-[r:DOCUMENTS]->()
WHERE r.holdout = true
RETURN count(r) AS count
"""

_Q_VERIFY_HOLDOUT = """
MATCH (e:Encounter)-[r:DOCUMENTS]->()
WHERE r.holdout = true
WITH DISTINCT e.id AS encounter_id
RETURN count(encounter_id) AS holdout_encounter_count
"""


def _check_existing_holdout(client: PatientGraphClient) -> int:
    """Return count of DOCUMENTS relationships already marked holdout."""
    rows = client.run(_Q_COUNT_EXISTING_HOLDOUT)
    return rows[0]["count"] if rows else 0


def _sample_domain(
    client: PatientGraphClient,
    domain: str,
    config: dict[str, Any],
    oversample: int = 3,
) -> list[dict[str, Any]]:
    limit = config["target"] * oversample
    rows = client.run(
        _Q_SAMPLE_DOMAIN,
        keywords=config["keywords"],
        domain=domain,
        limit=limit,
    )
    return [
        {
            "patient_id": str(r["patient_id"]),
            "encounter_id": str(r["encounter_id"]),
            "date": r["date"],
            "domain": domain,
        }
        for r in (rows or [])
    ]


def _select_stratified(
    client: PatientGraphClient,
) -> dict[str, list[dict[str, Any]]]:
    """Sample encounters per domain, enforcing minimums."""
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_ids: set[str] = set()

    for domain, config in DOMAINS.items():
        candidates = _sample_domain(client, domain, config)
        for enc in candidates:
            if len(selected[domain]) >= config["target"]:
                break
            if enc["encounter_id"] in all_ids:
                continue
            selected[domain].append(enc)
            all_ids.add(enc["encounter_id"])

        got = len(selected[domain])
        min_req = config["min_required"]
        if got < min_req:
            raise RuntimeError(
                f"Domain '{domain}' safety-critical minimum not met: "
                f"found {got}, required {min_req}. "
                "Ensure sufficient encounters with relevant SNOMED codings exist. "
                "Do not proceed until this is resolved."
            )
        logger.info("Domain %s: selected %d encounters", domain, got)

    return dict(selected)


def _mark_holdout(
    client: PatientGraphClient,
    encounter_ids: list[str],
    set_date: str,
    dry_run: bool,
) -> int:
    """Set holdout=true on DOCUMENTS relationships for the given encounters."""
    if dry_run:
        logger.info("DRY RUN: would mark %d encounters as holdout", len(encounter_ids))
        return len(encounter_ids)

    batch_size = 100
    total_updated = 0
    for i in range(0, len(encounter_ids), batch_size):
        batch = encounter_ids[i : i + batch_size]
        rows = client.run(_Q_MARK_HOLDOUT_BATCH, encounter_ids=batch, set_date=set_date)
        updated = rows[0]["updated"] if rows else 0
        total_updated += updated
        logger.info(
            "Batch %d-%d: marked %d DOCUMENTS relationships",
            i,
            i + len(batch),
            updated,
        )
    return total_updated


def _build_manifest(
    selected: dict[str, list[dict[str, Any]]],
    total_marked: int,
    set_date: str,
) -> dict[str, Any]:
    """Build the holdout manifest for audit purposes."""
    total_encounters = sum(len(v) for v in selected.values())
    safety_critical_counts = {
        domain: len(encs)
        for domain, encs in selected.items()
        if DOMAINS[domain]["safety_critical"]
    }
    category_minimums_met = all(
        len(selected.get(d, [])) >= DOMAINS[d]["min_required"]
        for d in DOMAINS
        if DOMAINS[d]["min_required"] > 0
    )

    return {
        "metadata": {
            "created_at": set_date,
            "purpose": "holdout_set",
            "total_encounters_selected": total_encounters,
            "total_documents_marked": total_marked,
            "category_minimums_met": category_minimums_met,
            "safety_critical_counts": safety_critical_counts,
            "clinician_validation_required": [
                d for d, c in DOMAINS.items() if c["clinician_validation_required"]
            ],
            "clinician_validation_owner": "GP partner / clinical safety lead",
            "estimated_validation_effort_hours": 25,
            "validation_deadline": "Complete before Sprint 1 begins",
        },
        "stratification": {
            domain: {
                "count": len(encs),
                "safety_critical": DOMAINS[domain]["safety_critical"],
                "min_required": DOMAINS[domain]["min_required"],
                "minimum_met": len(encs) >= DOMAINS[domain]["min_required"],
            }
            for domain, encs in selected.items()
        },
        "encounter_ids_by_domain": {
            domain: [enc["encounter_id"] for enc in encs]
            for domain, encs in selected.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Select 500 holdout encounters and mark with holdout=true. "
            "Run ONCE before any training data export."
        )
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm: write holdout flags to Neo4j (required to actually run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show stratification plan without writing to Neo4j",
    )
    parser.add_argument(
        "--manifest",
        default="scripts/holdout_manifest.json",
        help="Output manifest file path",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Count existing holdout encounters and exit",
    )
    args = parser.parse_args()

    client = PatientGraphClient()

    if args.verify_only:
        rows = client.run(_Q_VERIFY_HOLDOUT)
        count = rows[0]["holdout_encounter_count"] if rows else 0
        logger.info(
            "Existing holdout encounters: %d (target: %d)", count, TOTAL_HOLDOUT
        )
        return

    existing = _check_existing_holdout(client)
    if existing > 0 and not args.dry_run:
        logger.error(
            "Holdout encounters already exist (%d DOCUMENTS marked). "
            "Use --verify-only to inspect. "
            "Do NOT re-run selection: the holdout set is immutable.",
            existing,
        )
        sys.exit(1)

    if not args.yes and not args.dry_run:
        logger.error(
            "Pass --yes to confirm writing holdout flags to Neo4j, "
            "or --dry-run to preview."
        )
        sys.exit(1)

    set_date = datetime.utcnow().isoformat() + "Z"
    logger.info(
        "Selecting %d holdout encounters across %d domains...",
        TOTAL_HOLDOUT,
        len(DOMAINS),
    )

    selected = _select_stratified(client)
    total_selected = sum(len(v) for v in selected.values())
    logger.info("Total encounters selected: %d", total_selected)

    all_encounter_ids = [
        enc["encounter_id"] for encs in selected.values() for enc in encs
    ]

    total_marked = _mark_holdout(client, all_encounter_ids, set_date, args.dry_run)

    manifest = _build_manifest(selected, total_marked, set_date)
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("Holdout manifest written to: %s", manifest_path)

    if manifest["metadata"]["category_minimums_met"]:
        logger.info("All safety-critical category minimums met.")
    else:
        logger.warning(
            "One or more safety-critical category minimums NOT met. "
            "Do not proceed to training until resolved."
        )

    logger.info(
        "NEXT STEP: Assign clinician validation to: %s. "
        "Estimated effort: ~25 hours over 2-3 weeks.",
        ", ".join(manifest["metadata"]["clinician_validation_required"]),
    )


if __name__ == "__main__":
    main()
