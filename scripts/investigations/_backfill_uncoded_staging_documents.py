"""Backfill :DOCUMENTS / :HAS_* for encounters where staging text exists but coding is missing.

Uses ONLY SNOMED concept IDs listed in
``configs/snomed/snomed_ncda_stage_of_diagnosis_mapping.json`` so every write is
eligible for cancer_audit / stage_of_diagnosis subdomain tagging after KG promotion::

    python scripts/ncda/promote_stage_of_diagnosis.py

Default: dry-run (prints planned links). To apply::

    python scripts/investigations/_backfill_uncoded_staging_documents.py --apply

Atlas: operational remediation. Pair with ValueSet re-seed when the mapping file changes.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from libs.keyvault.loader import load_keyvault_secrets
from libs.cypher.documents_queries import upsert_encounter_documents_link
from libs.neo4j_client.client import PatientGraphClient

load_keyvault_secrets()

MAPPING_PATH = ROOT / "configs" / "snomed" / "snomed_ncda_stage_of_diagnosis_mapping.json"
SOURCE = "staging_backfill_v1"
DOMAIN = "stage_of_diagnosis"

_STAGING_WRITE = {
    "integrated_tnm_category": "399703000",
    "breslow_depth_staging_melanoma": "106243009",
    "clark_melanoma_level_3": "21165006",
    "stage_4_qualifier": "258232002",
}

# Clinician-targeted rows: (patient_id, encounter_id, list of payload dicts)
_BACKFILL: list[tuple[str, str, list[dict[str, Any]]]] = [
    (
        "7324271383",
        "48e5022e-cf15-4382-a4dd-d083ebcc4e0b",
        [
            {
                "key": "integrated_tnm_category",
                "semantic_tag": "observable_entity",
                "name": "Integrated TNM category (observable entity)",
                "evidence": "TNM8 T stage: pT3b (at least)",
            },
            {
                "key": "breslow_depth_staging_melanoma",
                "semantic_tag": "observable_entity",
                "name": "Breslow depth staging for melanoma of skin (observable entity)",
                "evidence": "Breslow thickness: 3.7 mm (at least)",
                "numeric_value": 3.7,
                "unit": "mm",
            },
        ],
    ),
    (
        "7324271383",
        "60d51cc3-2492-4e75-8a05-47577e14414c",
        [
            {
                "key": "integrated_tnm_category",
                "semantic_tag": "observable_entity",
                "name": "Integrated TNM category (observable entity)",
                "evidence": "pT3b malignant melanoma right thigh, Breslow thickness 3.7 mm",
            },
            {
                "key": "breslow_depth_staging_melanoma",
                "semantic_tag": "observable_entity",
                "name": "Breslow depth staging for melanoma of skin (observable entity)",
                "evidence": "Breslow thickness 3.7 mm",
                "numeric_value": 3.7,
                "unit": "mm",
            },
        ],
    ),
    (
        "4200186896",
        "bff06127-b56f-4f65-81ab-b546de35d06d",
        [
            {
                "key": "integrated_tnm_category",
                "semantic_tag": "observable_entity",
                "name": "Integrated TNM category (observable entity)",
                "evidence": "TNM8 category: pT1b",
            },
            {
                "key": "breslow_depth_staging_melanoma",
                "semantic_tag": "observable_entity",
                "name": "Breslow depth staging for melanoma of skin (observable entity)",
                "evidence": "Breslow thickness: 0.8mm (rounded from 0.83 mm)",
                "numeric_value": 0.8,
                "unit": "mm",
            },
            {
                "key": "clark_melanoma_level_3",
                "semantic_tag": "clinical_finding",
                "name": "Clark melanoma level 3 (morphologic abnormality)",
                "evidence": "Clark level: III",
            },
        ],
    ),
    (
        "6261656266",
        "64a7bee5-de05-4e47-be76-b4cf318d4038",
        [
            {
                "key": "integrated_tnm_category",
                "semantic_tag": "observable_entity",
                "name": "Integrated TNM category (observable entity)",
                "evidence": "pT1 pNx",
            },
        ],
    ),
    (
        "4940120139",
        "7d8380a2-1833-4c2c-b78e-42cea780019e",
        [
            {
                "key": "stage_4_qualifier",
                "semantic_tag": "clinical_finding",
                "name": "Stage 4 (qualifier value)",
                "evidence": "Suspected stage 4. Surgical treatment not an option. Treatment will be palliative.",
            },
        ],
    ),
    (
        "4802297327",
        "6972320e-1375-49f1-9291-ef7a7f30e16c",
        [
            {
                "key": "stage_4_qualifier",
                "semantic_tag": "clinical_finding",
                "name": "Stage 4 (qualifier value)",
                "evidence": "Had stage 4 CA to mandable which has been grafted using bone and tissue from the lower leg.",
            },
        ],
    ),
    (
        "6142203497",
        "fe514809-8a02-4a9c-9717-b4b564bf05ad",
        [
            {
                "key": "stage_4_qualifier",
                "semantic_tag": "clinical_finding",
                "name": "Stage 4 (qualifier value)",
                "evidence": "Medical history of stage IV cancer.",
            },
        ],
    ),
    (
        "4926916703",
        "21480df5-3141-46dc-9f44-a85aa8e7e4e1",
        [
            {
                "key": "integrated_tnm_category",
                "semantic_tag": "observable_entity",
                "name": "Integrated TNM category (observable entity)",
                "evidence": "Squamous cell carcinoma stage T1 completely excised right occipital scalp October 2023",
            },
        ],
    ),
]


def _allowed_concept_ids() -> set[str]:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {
        str(entry["concept_id"])
        for entry in (data.get("mappings") or {}).values()
        if entry.get("concept_id") is not None
    }


def _validate_config(allowed: set[str]) -> None:
    for _pid, _eid, payloads in _BACKFILL:
        for p in payloads:
            key = p["key"]
            if key not in _STAGING_WRITE:
                raise ValueError(f"Unknown staging key {key!r}")
            expect = _STAGING_WRITE[key]
            if expect not in allowed:
                raise ValueError(
                    f"Concept {expect} for {key} not in stage_of_diagnosis mapping"
                )
    if not allowed:
        raise ValueError("Empty stage_of_diagnosis mapping")


_Q_EXISTS = """
MATCH (e:Encounter)-[r:DOCUMENTS]->(c)
WHERE toString(e.id) = $encounter_id AND toString(c.conceptId) = $concept_id
RETURN count(r) AS n
"""


def run_staging_document_backfill(*, apply: bool = False) -> None:
    """Backfill patient graph with staging ``:DOCUMENTS`` / ``:HAS_*`` edges."""
    allowed = _allowed_concept_ids()
    _validate_config(allowed)

    run_id = str(uuid.uuid4())
    client = PatientGraphClient()
    try:
        with client.session() as session:
            for patient_id, encounter_id, payloads in _BACKFILL:
                for p in payloads:
                    key = p["key"]
                    concept_id = _STAGING_WRITE[key]
                    if concept_id not in allowed:
                        raise SystemExit(
                            f"Config error: {concept_id} not in {MAPPING_PATH.name}"
                        )
                    exists = (
                        session.run(
                            _Q_EXISTS,
                            encounter_id=encounter_id,
                            concept_id=concept_id,
                        ).single()
                        or {"n": 0}
                    )
                    if (exists.get("n") or 0) > 0:
                        print(
                            f"SKIP existing patient={patient_id} enc={encounter_id} "
                            f"concept={concept_id} ({key})"
                        )
                        continue
                    line = (
                        f"WRITE patient={patient_id} enc={encounter_id} "
                        f"concept={concept_id} tag={p['semantic_tag']} evidence={p['evidence']!r}"
                    )
                    if p.get("numeric_value") is not None:
                        line += f" value={p['numeric_value']} {p.get('unit', '')}"
                    print(line)
                    if not apply:
                        continue
                    upsert_encounter_documents_link(
                        session,
                        patient_id,
                        encounter_id,
                        concept_id,
                        p["semantic_tag"],
                        p["name"],
                        p["evidence"],
                        source=SOURCE,
                        domain=DOMAIN,
                        confidence=1.0,
                        model_name="deterministic_backfill",
                        model_version="1",
                        contract_version="stage_of_diagnosis_mapping",
                        run_id=run_id,
                        numeric_value=p.get("numeric_value"),
                        unit=p.get("unit"),
                    )
    finally:
        client.close()
    if not apply:
        print(
            "\nDry-run only. Re-run with --apply or "
            "``python scripts/ncda/promote_stage_of_diagnosis.py --apply-backfill``."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill stage_of_diagnosis DOCUMENTS links for known uncoded encounters."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to Neo4j (default is dry-run).",
    )
    args = parser.parse_args()
    run_staging_document_backfill(apply=args.apply)


if __name__ == "__main__":
    main()
