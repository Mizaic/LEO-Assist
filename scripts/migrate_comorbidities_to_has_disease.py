"""Migrate legacy comorbidity DOCUMENTS relationships to direct Patient→Disease links.

Background
----------
The NER pipeline originally coded comorbidities as SNOMED Situation codes
(e.g. "History of hypertension" 161501007) attached via:
    (Patient)-[:HAS_ENCOUNTER]->(Encounter)-[:DOCUMENTS {domain:'comorbidities'}]->(Situation)

The audit query now also supports a cleaner path:
    (Patient)-[:HAS_DISEASE {domain:'comorbidities'}]->(Disease)

This script creates those HAS_DISEASE relationships for any patient that has a
comorbidity DOCUMENTS relationship, mapping the situation/clinical-finding code
to the canonical disorder code using SITUATION_TO_DISORDER below.

The original DOCUMENTS relationships are left untouched so the pipeline remains
fully reversible.

Usage
-----
    python scripts/migrate_comorbidities_to_has_disease.py           # dry-run
    python scripts/migrate_comorbidities_to_has_disease.py --apply   # commit changes
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, Optional, Tuple

# ── Mapping table ─────────────────────────────────────────────────────────────
# situation/clinical_finding conceptId (str) → (disorder conceptId, benchmark_key)
# Disorder conceptId may be None when no canonical disorder exists yet.
SITUATION_TO_DISORDER: Dict[str, Tuple[Optional[str], str]] = {
    "161501007": ("38341003",  "comorbidity_hypertension_pct"),    # Hx hypertension → HTN
    "266995000": ("49601007",  "comorbidity_cvd_pct"),             # Hx CVD
    "267004000": ("928000",    "comorbidity_arthritis_pct"),       # Hx musculoskeletal → MSK
    "161445009": ("73211009",  "comorbidity_diabetes_pct"),        # Hx diabetes → DM
    "270473001": ("13645005",  "comorbidity_copd_pct"),            # Hx COPD → COPD
    "161523006": ("13645005",  "comorbidity_copd_pct"),            # Hx resp disease → COPD
    "308064009": ("62914000",  "comorbidity_cvd_pct"),             # Hx cerebrovascular → CVD
    "266987004": (None,        "comorbidity_previous_cancer_pct"), # Hx malignancy (no disorder)
    "74627003":  ("73211009",  "comorbidity_diabetes_pct"),        # DM complication → DM
    "161505005": ("49601007",  "comorbidity_cvd_pct"),             # Hx heart failure → CVD
    "473109007": ("49601007",  "comorbidity_cvd_pct"),             # Hx PVD → CVD
    "399211009": ("49601007",  "comorbidity_cvd_pct"),             # Hx MI → CVD
    "275540007": ("62914000",  "comorbidity_cvd_pct"),             # Hx brain disorder → CVD
    "472961001": ("928000",    "comorbidity_arthritis_pct"),       # Hx connective tissue → MSK
}

# Disorder codes that are already in the domain (map to themselves)
SELF_DISORDER_BENCHMARK: Dict[str, str] = {
    "38341003":  "comorbidity_hypertension_pct",
    "49601007":  "comorbidity_cvd_pct",
    "73211009":  "comorbidity_diabetes_pct",
    "13645005":  "comorbidity_copd_pct",
    "928000":    "comorbidity_arthritis_pct",
    "62914000":  "comorbidity_cvd_pct",
    "74732009":  "comorbidity_mental_health_pct",
    "3723001":   "comorbidity_arthritis_pct",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _get_client():
    """Import and connect to the patient graph."""
    # Add repo root to path so local libs are importable when run as a script.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from libs.neo4j_client.client import PatientGraphClient  # type: ignore

    return PatientGraphClient()


def run(apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    logger.info("=== Comorbidity migration — %s ===", mode)

    client = _get_client()
    try:
        _run_migration(client, apply=apply)
    finally:
        client.close()


def _run_migration(client, *, apply: bool) -> None:  # noqa: ANN001
    # ── 1. Fetch all comorbidity DOCUMENTS rows ────────────────────────────
    logger.info("Fetching comorbidity DOCUMENTS relationships…")
    rows = client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc)-[r:DOCUMENTS]->(node) "
        "WHERE r.domain = 'comorbidities' "
        "RETURN p.id AS patient_id, enc.date AS enc_date, "
        "       node.conceptId AS concept_id, node.name AS concept_name, "
        "       labels(node) AS node_labels"
    )

    if not rows:
        logger.info("No comorbidity DOCUMENTS relationships found — nothing to migrate.")
        return

    logger.info("Found %d comorbidity DOCUMENTS rows", len(rows))

    # ── 2. Build work list ─────────────────────────────────────────────────
    to_create: list[dict] = []
    skipped_no_mapping = 0

    for row in rows:
        cid_raw = row.get("concept_id")
        cid_str = str(cid_raw) if cid_raw is not None else ""
        patient_id = row.get("patient_id")
        enc_date = row.get("enc_date")

        if not cid_str or not patient_id:
            skipped_no_mapping += 1
            continue

        # Check self-mapping (concept already IS a disorder code in the domain)
        if cid_str in SELF_DISORDER_BENCHMARK:
            disorder_id = cid_str
            bm_key = SELF_DISORDER_BENCHMARK[cid_str]
        elif cid_str in SITUATION_TO_DISORDER:
            disorder_id_opt, bm_key = SITUATION_TO_DISORDER[cid_str]
            if disorder_id_opt is None:
                # No disorder equivalent — create a self-link with just the bm_key
                disorder_id = cid_str
            else:
                disorder_id = disorder_id_opt
        else:
            skipped_no_mapping += 1
            continue

        # Obtain a human-readable name for the disorder node
        concept_name = row.get("concept_name") or f"SNOMED:{disorder_id}"

        to_create.append({
            "patient_id": patient_id,
            "disorder_id": disorder_id,
            "concept_name": concept_name,
            "enc_date": enc_date,
            "bm_key": bm_key,
        })

    logger.info(
        "Work list: %d relationships to create, %d skipped (no mapping)",
        len(to_create),
        skipped_no_mapping,
    )

    if not to_create:
        logger.info("Nothing to do.")
        return

    if not apply:
        logger.info("[DRY-RUN] Showing first 10 planned operations:")
        for item in to_create[:10]:
            logger.info(
                "  Patient %-36s  concept %-10s  disorder %-10s  bm_key %s  date %s",
                item["patient_id"],
                item.get("disorder_id"),
                item["disorder_id"],
                item["bm_key"],
                item["enc_date"] or "NULL",
            )
        if len(to_create) > 10:
            logger.info("  … and %d more", len(to_create) - 10)
        logger.info("[DRY-RUN] Re-run with --apply to commit changes.")
        return

    # ── 3. Apply: MERGE Disease nodes + HAS_DISEASE relationships ─────────
    created = 0
    errors = 0

    for item in to_create:
        try:
            client.run(
                # MERGE the Disease node (safe to run multiple times)
                "MERGE (d:Disease {conceptId: $did}) "
                "  ON CREATE SET d.name = $dname, d.semanticTag = 'disorder', "
                "                d.source = 'migration_v1' "
                # MERGE the relationship keyed on {domain + conceptId} to prevent duplicates
                "WITH d "
                "MATCH (p:Patient {id: $pid}) "
                "MERGE (p)-[rel:HAS_DISEASE {domain: 'comorbidities', conceptId: $did}]->(d) "
                "  ON CREATE SET rel.encounter_date = $enc_date, "
                "                rel.source = 'migration_v1', "
                "                rel.benchmark_key = $bm_key "
                "  ON MATCH  SET rel.encounter_date = CASE "
                "                    WHEN rel.encounter_date IS NULL THEN $enc_date "
                "                    ELSE rel.encounter_date END, "
                "                rel.benchmark_key = $bm_key",
                did=item["disorder_id"],
                dname=item["concept_name"],
                pid=item["patient_id"],
                enc_date=item["enc_date"],
                bm_key=item["bm_key"],
            )
            created += 1
        except Exception as exc:
            logger.warning("Failed for patient %s: %s", item["patient_id"], exc)
            errors += 1

    logger.info(
        "Migration complete: %d HAS_DISEASE relationships created/updated, %d errors",
        created,
        errors,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Commit changes to Neo4j (default is dry-run only)",
    )
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
