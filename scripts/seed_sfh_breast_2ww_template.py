# EXCEPTION: file exceeds 300 because it declares the full SFH Breast 2WW
# template sections. Bind ids live in the fixture.

"""Seed the SFH Kings Mill Breast Unit 2WW form schema.

Usage:
    python scripts/seed_sfh_breast_2ww_template.py [--api-url http://host:port]
    python scripts/seed_sfh_breast_2ww_template.py --fixture-only
    python scripts/seed_sfh_breast_2ww_template.py --write-graph

--write-graph also stores completeness_groups on the FormSchema node
so a later dry-run can assess Section A and examination without a
stale empty AuditDomain schema.

Atlas trace: DI-5C9CA57B, DI-26546721, DI-50BE367C
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_sfh_gynae_2ww_template import (  # noqa: E402
    _analyte,
    _bone_battery,
    _fbc_battery,
    _item,
    _lft_battery,
    _remaining_batteries,
    _section,
    _ue_battery,
)

FINGERPRINT = "sfh-breast-2ww-v1"
FIXTURE_PATH = ROOT / "tests/fixtures/form_schema/sfh_breast_2ww_template.json"

_SCOPE = {
    "organization_id": "RK5",
    "service_id": "117038",
    "organization_ods_code": "RK5",
    "organization_name": "Sherwood Forest Hospitals NHS Foundation Trust",
    "service_name": "Breast Clinic - Kings Mill Hospital - SFHFT - RK5",
}


def build_section_a() -> dict:
    """Section A -- 2WW breast cancer symptoms."""
    return _section(
        section_id="section_a_2ww_symptoms",
        section_type="checkbox_multi",
        label=(
            "Section A: Symptoms / Signs suggesting possible breast cancer "
            "so meeting criteria for 2 Week Wait referral"
        ),
        start_pattern="Section A",
        items=[
            _item(
                "A1.",
                "Newly presenting discrete hard lump",
            ),
            _item(
                "A2.",
                "discrete lump that persists post period",
            ),
            _item(
                "A.2",
                "discrete lump that persists post period",
            ),
            _item("A3.", "Nipple ulceration"),
            _item("A4.", "Unilateral blood stained nipple discharge"),
            _item("A5.", "Skin nodule of breast"),
            _item("A6.", "Distortion of breast"),
            _item("A7.", "Skin tethering of breast"),
            _item("A8.", "Nipple eczema"),
            _item("A9.", "Recent nipple retraction"),
            _item("A10.", "Possible breast cancer recurrence"),
        ],
        semantic_tags=["finding"],
    )


def build_section_b() -> dict:
    """Section B -- examination narrative."""
    return _section(
        section_id="section_b_examination",
        section_type="free_text",
        label="Section B: Examination",
        start_pattern="Section B",
        items=[
            _item(
                "Affected side",
                "Breast examination findings",
                "finding",
                value_placeholder="Free text examination",
            ),
        ],
    )


def build_section_c() -> dict:
    """Section C -- other relevant information."""
    return _section(
        section_id="section_c_other",
        section_type="free_text",
        label="Section C: Other information that you consider relevant",
        start_pattern="Section C",
        items=[
            _item(
                "High risk family history",
                "Family history relevant to breast referral",
                "finding",
            ),
        ],
    )


def build_investigations() -> dict:
    """Mandatory blood table -- same batteries as the gynae form, no CA125."""
    skip = {"CA 125", "Random Glucose", "Fasting Glucose"}
    extras = [item for item in _remaining_batteries() if item["pattern"] not in skip]
    extras.append(
        _item(
            "Glucose",
            "Blood glucose measurement",
            "procedure",
            procedure_snomed="271061004",
            procedure_display="Random blood glucose measurement",
            analytes=[
                _analyte("Glucose", "1089381000000101", "Random blood glucose level"),
                _analyte("Fasting", "997681000000108", "Fasting blood glucose level"),
            ],
        )
    )
    extras.append(
        _item(
            "HbA1c",
            "Hemoglobin A1c measurement",
            "procedure",
            procedure_snomed="43396009",
            procedure_display="Hemoglobin A1c measurement",
            analytes=[_analyte("HbA1c", "1003671000000109", "Haemoglobin A1c level")],
        )
    )
    items = [_fbc_battery(), _ue_battery(), _lft_battery(), _bone_battery()]
    items.extend(extras)
    return _section(
        section_id="section_d_investigations",
        section_type="ordered_tests",
        label="Section D: Investigations performed",
        start_pattern="Section D: Investigations",
        items=items,
    )


def build_awareness() -> dict:
    """Patient knows / urgent referral / holidays."""
    return _section(
        section_id="patient_awareness",
        section_type="checkbox_yesno",
        label="Does the patient know?",
        start_pattern="Does the patient know",
        items=[
            _item(
                "knows or suspects the risk of cancer",
                "Patient is aware of possible cancer",
            ),
            _item(
                "referred on an urgent basis",
                "Patient aware of urgent referral",
            ),
            _item(
                "holiday plans in the next 2 months",
                "Holiday plans in the next 2 months",
            ),
        ],
    )


def build_ecog() -> dict:
    """Long ECOG row with the box before the score."""
    return _section(
        section_id="performance_status",
        section_type="scale",
        label="Performance status",
        start_pattern=r"(?i)^\s*\|\s*Performance status\s*\|",
        items=[
            _item("Fully active", "ECOG 0 fully active without restriction"),
            _item(
                "Restricted in physically strenuous",
                "ECOG 1 restricted in strenuous activity",
            ),
            _item(
                "Ambulatory and capable of all selfcare",
                "ECOG 2 ambulatory but unable to work",
            ),
            _item(
                "confined to bed or chair more than 50%",
                "ECOG 3 limited selfcare",
            ),
            _item("Totally confined to bed or chair", "ECOG 4 completely disabled"),
        ],
    )


def build_symptomatic() -> dict:
    """Urgent / symptomatic route -- not the 2WW criteria."""
    return _section(
        section_id="section_d_symptomatic",
        section_type="checkbox_multi",
        label="Section D: Symptoms/signs for urgent or symptomatic referral",
        start_pattern="Section D: Symptoms",
        items=[
            _item("Breast abscess", "Breast abscess"),
            _item("Asymmetric nodularity", "Asymmetric breast nodularity"),
            _item("Recurrent cyst", "Recurrent breast cyst"),
            _item("Breast lump < 30", "Breast lump under 30 years"),
            _item("Intractable breast pain", "Intractable breast pain"),
            _item(
                "Asymmetrical nodularity or thickening",
                "Asymmetrical nodularity persisting after menstruation",
            ),
            _item("fails to respond to antibiotics", "Breast infection not settling"),
            _item("unilateral eczematous skin", "Unilateral nipple or areola eczema"),
            _item(
                "Unilateral, spontaneous nipple discharge",
                "Unilateral spontaneous nipple discharge",
            ),
        ],
    )


def build_mastalgia_noise() -> dict:
    """Guidance that must never become a patient fact."""
    return _section(
        section_id="mastalgia_guidance",
        section_type="template_noise",
        label="Mastalgia managed in primary care",
        start_pattern="PATIENTS WITH MASTALGIA",
        items=[],
    )


def build_details() -> dict:
    """GP narrative."""
    return _section(
        section_id="details_narrative",
        section_type="free_text",
        label="Details",
        start_pattern="Please include duration and site",
        items=[
            _item(
                "Dear",
                "Referral narrative",
                "finding",
                value_placeholder="Free text clinical details",
            ),
        ],
    )


def build_admin() -> dict:
    """Form chrome and patient/practice boxes."""
    return _section(
        section_id="admin_header",
        section_type="admin",
        label="Breast Unit Referral Form header",
        start_pattern="Breast Unit Referral Form",
        items=[],
    )


def _section_a_members() -> list:
    boxes = [
        {"section_id": "section_a_2ww_symptoms", "item_pattern": pattern}
        for pattern in (
            "A1.",
            "A2.",
            "A.2",
            "A3.",
            "A4.",
            "A5.",
            "A6.",
            "A7.",
            "A8.",
            "A9.",
            "A10.",
        )
    ]
    boxes.append(
        {
            "name": "Breast lump",
            "kind": "optional",
            "required": False,
            "semantic_categories": [],
            "concept_ids": [89164003],
        }
    )
    return boxes


def build_completeness_groups() -> list:
    return [
        {
            "name": "two_ww_criterion_required",
            "kind": "at_least_one",
            "required": True,
            "min_count": 1,
            "semantic_categories": [],
            "concept_ids": [],
            "members": _section_a_members(),
        },
        {
            "name": "examination_present",
            "kind": "recommended_section",
            "required": False,
            "min_count": 1,
            "semantic_categories": [],
            "concept_ids": [],
            "members": [{"section_id": "section_b_examination"}],
        },
    ]


def build_payload() -> dict:
    """Taught Breast Unit 2WW template bound to RK5 service 117038."""
    return {
        "form_name": (
            "Sherwood Forest Hospitals NHS Foundation Trust -- "
            "Kings Mill and Newark Hospital Breast Unit Referral Form (2WW)"
        ),
        "sections": [
            build_admin(),
            build_section_a(),
            build_section_b(),
            build_section_c(),
            build_investigations(),
            build_awareness(),
            build_ecog(),
            build_symptomatic(),
            build_mastalgia_noise(),
            build_details(),
        ],
        "saved_by": "seed_sfh_breast_2ww_template",
        "status": "active",
        **_SCOPE,
        "completeness_groups": build_completeness_groups(),
    }


def save_fixture(payload: dict) -> None:
    """Write the payload to the fixture file."""
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE_PATH, "w", encoding="ascii") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)
    print(f"Fixture saved: {FIXTURE_PATH}")


def post_to_api(api_url: str, payload: dict) -> None:
    """PUT the payload to the form schema API."""
    import requests

    url = f"{api_url}/api/v1/form-schemas/{FINGERPRINT}"
    print(f"PUT {url}")
    resp = requests.put(url, json=payload, timeout=30)
    print(f"Status: {resp.status_code}")
    print(resp.text[:500])
    if resp.status_code not in (200, 201):
        sys.exit(1)


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
                created_by=payload.get("saved_by") or "seed_sfh_breast_2ww_template",
                schema_id=FINGERPRINT,
                status=payload.get("status") or "active",
                organization_id=payload["organization_id"],
                service_id=payload["service_id"],
                organization_name=payload["organization_name"],
                service_name=payload["service_name"],
                organization_ods_code=payload["organization_ods_code"],
                completeness_groups=payload.get("completeness_groups") or [],
            ),
        )
        print(
            f"saved         : {saved.fingerprint} org={saved.organization_id} "
            f"service={saved.service_id} "
            f"groups={len(saved.completeness_groups)}"
        )
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--fixture-only", action="store_true")
    parser.add_argument(
        "--write-graph",
        action="store_true",
        help="Write the schema to the patient graph (NEO4J_URI).",
    )
    args = parser.parse_args()
    payload = build_payload()
    save_fixture(payload)
    if args.fixture_only:
        print("Fixture-only mode: skipping API and graph write.")
        return 0
    if args.write_graph:
        write_graph(payload)
        return 0
    post_to_api(args.api_url, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
