"""Seed the national e-RS Clinical Information taught schema.

Empty organisation and service so wrapper-only referrals can bind by
fingerprint. Does not seed a service completeness domain.

Usage:
    python scripts/seed_nhs_ers_clinical_information.py --fixture-only
    python scripts/seed_nhs_ers_clinical_information.py --write-graph

Atlas trace: DI-1A1943BB, DO-E3AF3879, DI-50BE367C
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FINGERPRINT = "nhs-ers-clinical-information-v1"
FIXTURE_PATH = ROOT / "tests/fixtures/form_schema/nhs_ers_clinical_information.json"


def build_payload() -> dict:
    """Load the taught national e-RS schema with empty org and service."""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="ascii"))
    payload["fingerprint"] = FINGERPRINT
    payload["organization_id"] = ""
    payload["service_id"] = ""
    payload["organization_name"] = ""
    payload["service_name"] = ""
    payload["organization_ods_code"] = ""
    payload["saved_by"] = "seed_nhs_ers_clinical_information"
    payload["status"] = "active"
    return payload


def write_graph(payload: dict) -> None:
    """Persist the schema on the patient graph NEO4J_URI points at."""
    from dotenv import load_dotenv

    for name in ("secrets/.env", "secrets/.env.secrets", ".env"):
        load_dotenv(ROOT / name, override=False)
    import os

    from libs.neo4j_client.client import PatientGraphClient
    from libs.pipeline.form_schema_request import (
        build_sections_from_request,
        normalize_sections_for_request,
    )
    from libs.pipeline.form_schema_store import FormSchemaWrite, save_form_schema

    sections = build_sections_from_request(
        normalize_sections_for_request(payload["sections"])
    )
    uri = os.getenv("NEO4J_URI", "") or os.getenv("NEO4J_PATIENT_URI", "")
    print(f"neo4j         : {uri}")
    if "localhost" in uri or not uri.startswith("neo4j+s://"):
        raise SystemExit(f"Refusing to write: NEO4J_URI is not production Aura ({uri})")
    client = PatientGraphClient()
    try:
        saved = save_form_schema(
            client,
            FormSchemaWrite(
                fingerprint=FINGERPRINT,
                form_name=payload["form_name"],
                sections=sections,
                created_by=payload.get("saved_by")
                or "seed_nhs_ers_clinical_information",
                schema_id=FINGERPRINT,
                status=payload.get("status") or "active",
                organization_id="",
                service_id="",
                completeness_groups=payload.get("completeness_groups") or [],
            ),
        )
        names = [g.get("name") for g in saved.completeness_groups]
        print(
            f"saved         : {saved.fingerprint} org={saved.organization_id!r} "
            f"service={saved.service_id!r} groups={names}"
        )
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-only", action="store_true")
    parser.add_argument(
        "--write-graph",
        action="store_true",
        help="Write the schema to the patient graph (NEO4J_URI).",
    )
    args = parser.parse_args()
    payload = build_payload()
    if args.fixture_only:
        print(f"Fixture-only: {FIXTURE_PATH}")
        return 0
    if args.write_graph:
        write_graph(payload)
        return 0
    parser.error("Pass --fixture-only or --write-graph")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
