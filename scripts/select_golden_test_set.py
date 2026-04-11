"""Select 100-encounter golden test set for auditor validation.

Queries Neo4j for encounters stratified across clinical domains and outputs
a JSON file listing encounter IDs grouped by domain. The output is used as
input to validate_auditor.py after a clinician has labelled the ground truth.

Required coverage:
  - respiratory
  - cardiovascular
  - oncology
  - mental_health
  - musculoskeletal
  - dermatology
  - endocrine (e.g. diabetes, thyroid)
  - gastrointestinal

Design control: DI-LEO-AI-072, VT-LEO-AI-072
Acceptance criterion: safety-critical recall >= 0.90 (VT-072-TC-004)

Usage
-----
    python scripts/select_golden_test_set.py
    python scripts/select_golden_test_set.py --output golden_test_set.json
    python scripts/select_golden_test_set.py --encounters-per-domain 15 --min-domains 8
    python scripts/select_golden_test_set.py --dry-run

Do NOT run this in production -- outputs encounter IDs for clinician review.
The clinician completes the ground truth JSON manually before running the
auditor validation harness.
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
logger = logging.getLogger("select_golden")

# ---------------------------------------------------------------------------
# Clinical domain definitions
# SNOMED semantic tags and concept name keywords used to classify encounters
# ---------------------------------------------------------------------------

DOMAINS: dict[str, dict[str, Any]] = {
    "respiratory": {
        "semantic_tags": ["disorder"],
        "keywords": [
            "asthma",
            "copd",
            "pneumonia",
            "bronchitis",
            "respiratory",
            "lung",
            "pleural",
            "emphysema",
            "inhaler",
            "dyspnoea",
        ],
        "target": 13,
        "safety_critical": False,
    },
    "cardiovascular": {
        "semantic_tags": ["disorder", "finding"],
        "keywords": [
            "heart failure",
            "atrial fibrillation",
            "hypertension",
            "coronary",
            "angina",
            "myocardial",
            "cardiac",
            "cardiovascular",
            "arrhythmia",
            "stroke",
            "tia",
        ],
        "target": 13,
        "safety_critical": False,
    },
    "oncology": {
        "semantic_tags": ["disorder"],
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
            "oncology",
        ],
        "target": 13,
        "safety_critical": True,
    },
    "mental_health": {
        "semantic_tags": ["disorder", "finding"],
        "keywords": [
            "depression",
            "anxiety",
            "schizophrenia",
            "bipolar",
            "psychosis",
            "mental",
            "psychiatric",
            "ptsd",
            "eating disorder",
            "self-harm",
            "suicidal",
            "safeguarding",
        ],
        "target": 13,
        "safety_critical": True,
    },
    "musculoskeletal": {
        "semantic_tags": ["disorder", "finding"],
        "keywords": [
            "arthritis",
            "osteoporosis",
            "fracture",
            "back pain",
            "musculoskeletal",
            "joint",
            "tendon",
            "rheumatoid",
            "gout",
        ],
        "target": 12,
        "safety_critical": False,
    },
    "dermatology": {
        "semantic_tags": ["disorder", "finding"],
        "keywords": [
            "eczema",
            "psoriasis",
            "dermatitis",
            "rash",
            "skin",
            "acne",
            "urticaria",
            "cellulitis",
            "melanoma",
            "wound",
        ],
        "target": 12,
        "safety_critical": False,
    },
    "endocrine": {
        "semantic_tags": ["disorder", "finding"],
        "keywords": [
            "diabetes",
            "thyroid",
            "hyperthyroid",
            "hypothyroid",
            "endocrine",
            "adrenal",
            "insulin",
            "hba1c",
            "glucose",
        ],
        "target": 12,
        "safety_critical": False,
    },
    "gastrointestinal": {
        "semantic_tags": ["disorder", "finding"],
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
            "pancreatitis",
            "coeliac",
        ],
        "target": 12,
        "safety_critical": False,
    },
}

# Cypher: find encounters where any coded concept name matches domain keywords
_Q_DOMAIN_ENCOUNTERS = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(s)
WHERE e.text IS NOT NULL
  AND trim(e.text) <> ''
  AND s.name IS NOT NULL
  AND any(kw IN $keywords WHERE toLower(s.name) CONTAINS kw)
WITH DISTINCT p.id AS patient_id,
     e.id AS encounter_id,
     toString(e.date) AS date,
     collect(DISTINCT s.name)[0..5] AS sample_concepts,
     $domain AS domain
ORDER BY rand()
LIMIT $limit
RETURN patient_id, encounter_id, date, sample_concepts, domain
"""

# Cypher: verify encounter exists and has text
_Q_ENCOUNTER_CHECK = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(e:Encounter {id: $encounter_id})
WHERE e.text IS NOT NULL AND trim(e.text) <> ''
RETURN count(e) AS found
"""


def _sample_domain(
    client: PatientGraphClient,
    domain: str,
    config: dict[str, Any],
    oversample: int = 3,
) -> list[dict[str, Any]]:
    """Query encounters for one domain, returning up to target * oversample rows."""
    limit = config["target"] * oversample
    rows = client.run(
        _Q_DOMAIN_ENCOUNTERS,
        keywords=config["keywords"],
        domain=domain,
        limit=limit,
    )
    return [
        {
            "patient_id": str(r["patient_id"]),
            "encounter_id": str(r["encounter_id"]),
            "date": r["date"],
            "sample_concepts": list(r["sample_concepts"] or []),
            "domain": domain,
        }
        for r in (rows or [])
    ]


def _deduplicate(encounters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate encounter IDs, keeping first occurrence."""
    seen: set[str] = set()
    result = []
    for enc in encounters:
        eid = enc["encounter_id"]
        if eid not in seen:
            seen.add(eid)
            result.append(enc)
    return result


def _select_stratified(
    client: PatientGraphClient,
    domains: dict[str, dict[str, Any]],
    total_target: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    """Sample encounters per domain and trim to per-domain targets."""
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_encounter_ids: set[str] = set()

    for domain, config in domains.items():
        logger.info("Sampling domain: %s (target=%d)", domain, config["target"])
        candidates = _sample_domain(client, domain, config)

        for enc in candidates:
            if len(selected[domain]) >= config["target"]:
                break
            if enc["encounter_id"] in all_encounter_ids:
                continue
            selected[domain].append(enc)
            all_encounter_ids.add(enc["encounter_id"])

        got = len(selected[domain])
        if got < config["target"]:
            logger.warning(
                "Domain %s: only %d/%d encounters found",
                domain,
                got,
                config["target"],
            )
        else:
            logger.info("Domain %s: selected %d encounters", domain, got)

    total = sum(len(v) for v in selected.values())
    logger.info("Total selected: %d / %d target", total, total_target)
    return dict(selected)


def _build_output(
    selected: dict[str, list[dict[str, Any]]],
    domains: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the golden test set manifest."""
    total = sum(len(v) for v in selected.values())
    safety_critical_domains = [d for d, c in domains.items() if c["safety_critical"]]
    safety_critical_counts = {
        d: len(selected.get(d, [])) for d in safety_critical_domains
    }

    return {
        "metadata": {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "purpose": "auditor_validation",
            "total_encounters": total,
            "domains": list(selected.keys()),
            "safety_critical_domains": safety_critical_domains,
            "safety_critical_counts": safety_critical_counts,
            "instructions": (
                "A clinician must review each encounter and complete the "
                "ground_truth section for each encounter_id before running "
                "validate_auditor.py. See validate_auditor.py --help."
            ),
        },
        "encounters_by_domain": {
            domain: [
                {
                    "patient_id": enc["patient_id"],
                    "encounter_id": enc["encounter_id"],
                    "date": enc["date"],
                    "sample_concepts": enc["sample_concepts"],
                    "domain": domain,
                }
                for enc in encs
            ]
            for domain, encs in selected.items()
        },
        "ground_truth_template": {
            "description": (
                "Fill in this template after clinician review. "
                "For each encounter, list the SNOMED concept IDs that SHOULD "
                "be coded (present codes) and any that SHOULD NOT be coded "
                "(absent / overcoded concepts)."
            ),
            "encounters": {
                enc["encounter_id"]: {
                    "clinician_reviewed_by": "",
                    "clinician_reviewed_date": "",
                    "should_be_coded": [],
                    "should_not_be_coded": [],
                    "notes": "",
                }
                for encs in selected.values()
                for enc in encs
            },
        },
    }


def _validate_safety_critical_coverage(
    selected: dict[str, list[dict[str, Any]]],
    domains: dict[str, dict[str, Any]],
    min_per_critical: int = 10,
) -> bool:
    """Warn if any safety-critical domain is under-represented."""
    ok = True
    for domain, config in domains.items():
        if not config["safety_critical"]:
            continue
        count = len(selected.get(domain, []))
        if count < min_per_critical:
            logger.warning(
                "SAFETY WARNING: domain '%s' has only %d encounters "
                "(minimum %d recommended for meaningful recall measurement)",
                domain,
                count,
                min_per_critical,
            )
            ok = False
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select 100-encounter golden test set for auditor validation"
    )
    parser.add_argument(
        "--output",
        default="scripts/golden_test_set.json",
        help="Output JSON file path (default: scripts/golden_test_set.json)",
    )
    parser.add_argument(
        "--encounters-per-domain",
        type=int,
        default=None,
        help="Override per-domain target (default: use DOMAINS config)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print query plan without writing output",
    )
    args = parser.parse_args()

    domains = DOMAINS.copy()
    if args.encounters_per_domain:
        for domain in domains:
            domains[domain]["target"] = args.encounters_per_domain

    total_target = sum(c["target"] for c in domains.values())
    logger.info(
        "Selecting golden test set: %d encounters across %d domains",
        total_target,
        len(domains),
    )

    if args.dry_run:
        logger.info("DRY RUN -- domain targets:")
        for domain, config in domains.items():
            flag = " [SAFETY-CRITICAL]" if config["safety_critical"] else ""
            logger.info("  %s: %d%s", domain, config["target"], flag)
        return

    client = PatientGraphClient()
    selected = _select_stratified(client, domains, total_target)

    safety_ok = _validate_safety_critical_coverage(selected, domains)
    if not safety_ok:
        logger.warning(
            "Safety-critical domains under-represented. "
            "Auditor recall measurement for these domains will have wide confidence intervals."
        )

    output = _build_output(selected, domains)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    logger.info("Golden test set written to: %s", out_path)
    logger.info(
        "NEXT STEP: Send this file to the clinician for ground truth labelling. "
        "See ground_truth_template section."
    )


if __name__ == "__main__":
    main()
