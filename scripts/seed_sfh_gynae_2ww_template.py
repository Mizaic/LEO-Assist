# EXCEPTION: file exceeds 500 because it declares the full SFH Gynae 2WW
# template sections. Bind ids are not in this file; they live in the fixture.

"""Seed the SFH Gynaecology 2WW form schema template.

Sends a PUT to /form-schemas/sfh-gynae-2ww-v1 with the fully-populated
template for the Sherwood Forest Hospitals Gynaecology Urgent Suspected
Cancer pathway. Prints the API response.

Usage:
    python scripts/seed_sfh_gynae_2ww_template.py [--api-url http://host:port]

Atlas trace: DI-5C9CA57B, DI-26546721
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FINGERPRINT = "sfh-gynae-2ww-v1"
FIXTURE_PATH = Path(__file__).parent.parent / (
    "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"
)


def _analyte(label: str, snomed_code: str, display: str) -> dict:
    return {"label": label, "snomed_code": snomed_code, "display": display}


def _item(
    pattern: str,
    entity_text: str = "",
    semantic_tag: str = "finding",
    assertion: str = "present",
    procedure_snomed: str = "",
    procedure_display: str = "",
    analytes: list | None = None,
    value_placeholder: str = "",
) -> dict:
    return {
        "pattern": pattern,
        "entity_text": entity_text or pattern,
        "semantic_tag": semantic_tag,
        "assertion": assertion,
        "procedure_snomed": procedure_snomed,
        "procedure_display": procedure_display,
        "analytes": analytes or [],
        "value_placeholder": value_placeholder,
    }


def _section(
    section_id: str,
    section_type: str,
    label: str,
    start_pattern: str,
    items: list,
    semantic_tags: list | None = None,
) -> dict:
    return {
        "section_id": section_id,
        "section_type": section_type,
        "label": label,
        "start_pattern": start_pattern,
        "items": items,
        "semantic_tags": semantic_tags or [],
    }


def _blood_battery(
    label: str,
    procedure_snomed: str,
    procedure_display: str,
    analytes: list,
) -> dict:
    return _item(
        pattern=label,
        entity_text=procedure_display,
        semantic_tag="procedure",
        assertion="present",
        procedure_snomed=procedure_snomed,
        procedure_display=procedure_display,
        analytes=analytes,
    )


def build_section_a() -> dict:
    """Section A -- cancer type suspected."""
    return _section(
        section_id="section_a_cancer_type",
        section_type="checkbox_multi",
        label="Section A: Gynaecological Cancer type suspected",
        start_pattern="Section A",
        items=[
            _item("Ovary", "Suspected ovarian cancer", "disorder"),
            _item("Cervix", "Suspected cervical cancer", "disorder"),
            _item("Endometrium", "Suspected endometrial cancer", "disorder"),
            _item("Vagina", "Suspected vaginal cancer", "disorder"),
            _item("Vulva", "Suspected vulval cancer", "disorder"),
        ],
        semantic_tags=["394586005"],
    )


def build_section_b() -> dict:
    """Section B -- signs and symptoms 14-day rule.

    Item patterns use the short prefix only (e.g. "B1.") so that the hit's
    item_pattern matches the completeness group member's item_pattern exactly.
    The full description goes in entity_text, not in pattern.
    """
    return _section(
        section_id="section_b_symptoms",
        section_type="checkbox_yesno",
        label="Section B: Signs/symptoms for 14-day rule criteria",
        start_pattern="Section B",
        items=[
            _item(
                "B1.",
                "Lesion suspicious of cervical or vaginal cancer on speculum",
            ),
            _item(
                "B2.",
                "vulval mass",
            ),
            _item(
                "B3.",
                "Palpable pelvic mass (not fibroids)",
            ),
            _item(
                "B4.",
                "Suspicious pelvic mass on ultrasound",
            ),
            _item(
                "B5.",
                "Postmenopausal bleeding in woman aged over 55 not on HRT",
            ),
            _item(
                "B6.",
                "Postcoital bleeding persisting more than 4 weeks, age over 35",
            ),
            _item(
                "B7.",
                (
                    "Unexpected or prolonged bleeding persisting more than "
                    "4 weeks after stopping HRT"
                ),
            ),
            _item(
                "B8.",
                "Bleeding persisting after 6 months of continuous combined HRT",
            ),
            _item(
                "B9.",
                "Suspicion of ovarian cancer with raised CA125, postmenopausal",
            ),
        ],
        semantic_tags=["394586005"],
    )


def build_primary_care_pathway() -> dict:
    """Primary care pathway decision block (PMB pathway)."""
    return _section(
        section_id="primary_care_pathway",
        section_type="checkbox_yesno",
        label="Primary Care Pathway (PMB pathway -- if all ticked no USC referral)",
        start_pattern="For post menopausal bleeding",
        items=[
            _item(
                "New presentation with PMB",
                "New first-episode postmenopausal bleeding",
            ),
            _item(
                "Patient is not taking tamoxifen and BMI less than 40",
                "Not on tamoxifen and BMI below 40",
            ),
            _item(
                "Clinical examination including cervix looks normal",
                "Normal clinical examination including cervix",
            ),
            _item(
                "On TV USS the endometrial thickness <4mm and regular",
                "Endometrial thickness less than 4mm on transvaginal ultrasound",
            ),
        ],
    )


def build_patient_awareness() -> dict:
    """Patient awareness block."""
    return _section(
        section_id="patient_awareness",
        section_type="checkbox_yesno",
        label="Patient Awareness",
        start_pattern="Does the patient know",
        items=[
            _item(
                "Patient knows or suspects the risk of cancer",
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
            _item(
                "Has the patient been told of the suspicion of cancer",
                "Patient told of cancer suspicion",
            ),
            _item(
                "holidays planned in the next 3 weeks",
                "Holiday plans in the next 3 weeks",
            ),
        ],
    )


def build_section_c() -> dict:
    """Section C -- further clinical details."""
    return _section(
        section_id="section_c_clinical_details",
        section_type="free_text",
        label="Section C: Further Clinical details",
        start_pattern="Section C",
        items=[
            _item("BMI", "Body mass index", "observable entity"),
            _item("Co-morbidities", "Co-morbidities", "finding"),
            _item(
                "Cognitive Impairment",
                "Cognitive impairment",
                "finding",
            ),
            _item(
                "Clinical narrative",
                "Clinical narrative and examination findings",
                "finding",
                value_placeholder="Free text clinical details",
            ),
        ],
    )


def _fbc_battery() -> dict:
    return _blood_battery(
        "FBC",
        "26604007",
        "Complete blood count",
        [
            _analyte("Hb", "1022431000000105", "Haemoglobin estimation"),
            _analyte("WCC", "1110441000000100", "White blood cell count in blood"),
            _analyte("Plts", "1022651000000100", "Platelet count"),
            _analyte("MCV", "1022491000000106", "Mean corpuscular volume"),
            _analyte("Neut", "1022551000000104", "Neutrophil count"),
        ],
    )


def _ue_battery() -> dict:
    return _blood_battery(
        "UE",
        "252167001",
        "Measurement of urea and electrolytes",
        [
            _analyte("Na", "1000661000000107", "Serum sodium level"),
            _analyte("K", "1000651000000109", "Serum potassium level"),
            _analyte("Urea", "1000951000000103", "Serum urea level"),
            _analyte("Creat", "1000731000000107", "Serum creatinine level"),
            _analyte(
                "eGFR", "1011481000000105", "Estimated glomerular filtration rate"
            ),
        ],
    )


def _lft_battery() -> dict:
    return _blood_battery(
        "LFT",
        "26958001",
        "Hepatic function panel",
        [
            _analyte("ALT", "1018251000000107", "Serum alanine aminotransferase level"),
            _analyte(
                "Alk Phos", "1000621000000104", "Serum alkaline phosphatase level"
            ),
            _analyte("Bili", "997591000000109", "Serum total bilirubin level"),
            _analyte("Alb", "1000821000000103", "Serum albumin level"),
            _analyte(
                "GGT", "1000861000000106", "Serum gamma-glutamyl transferase level"
            ),
        ],
    )


def _bone_battery() -> dict:
    return _blood_battery(
        "Bone",
        "167036008",
        "Bone profile",
        [
            _analyte("Ca", "1000691000000101", "Serum calcium level"),
            _analyte("Ca cor", "", "Corrected serum calcium level"),
            _analyte(
                "Ca adj", "935051000000108", "Serum adjusted calcium concentration"
            ),
            _analyte("Phos", "1000701000000101", "Serum inorganic phosphate level"),
        ],
    )


def _remaining_batteries() -> list:
    return [
        _blood_battery(
            "CRP",
            "135842001",
            "Serum C reactive protein level",
            [_analyte("CRP", "1001371000000100", "Serum C reactive protein level")],
        ),
        _blood_battery(
            "TFTs",
            "35650009",
            "Thyroid panel",
            [
                _analyte(
                    "TSH", "1022791000000101", "Serum thyroid stimulating hormone level"
                ),
                _analyte("Free T4", "1030801000000101", "Free thyroxine level"),
            ],
        ),
        _blood_battery(
            "Iron",
            "",
            "Iron studies",
            [
                _analyte("Ferritin", "993381000000106", "Serum ferritin level"),
                _analyte(
                    "Iron Saturation", "991831000000103", "Transferrin saturation index"
                ),
                _analyte(
                    "TIBC", "1015451000000101", "Serum total iron binding capacity"
                ),
            ],
        ),
        _blood_battery(
            "Vitamins",
            "395144002",
            "B12/folate level",
            [
                _analyte("B12", "993391000000108", "Serum vitamin B12 level"),
                _analyte("Folate", "993411000000108", "Serum folate level"),
            ],
        ),
        _blood_battery(
            "Lipids",
            "16254007",
            "Lipid panel",
            [
                _analyte("Chol", "1005671000000105", "Serum cholesterol level"),
                _analyte(
                    "LDL",
                    "1022191000000100",
                    "Serum low density lipoprotein cholesterol level",
                ),
                _analyte(
                    "HDL",
                    "1005681000000107",
                    "Serum high density lipoprotein cholesterol level",
                ),
                _analyte(
                    "Chol:HDL ratio",
                    "1015681000000109",
                    "Serum cholesterol/high density lipoprotein ratio",
                ),
                _analyte("Tri", "1005691000000109", "Serum triglycerides level"),
            ],
        ),
        _blood_battery(
            "Random Glucose",
            "271061004",
            "Random blood glucose measurement",
            [
                _analyte(
                    "Random glucose", "1089381000000101", "Random blood glucose level"
                )
            ],
        ),
        _blood_battery(
            "Fasting Glucose",
            "271062006",
            "Fasting blood glucose measurement",
            [
                _analyte(
                    "Fasting glucose", "997681000000108", "Fasting blood glucose level"
                )
            ],
        ),
        _blood_battery(
            "HbA1c",
            "43396009",
            "Hemoglobin A1c measurement",
            [_analyte("HbA1c", "1003671000000109", "Haemoglobin A1c level")],
        ),
        _blood_battery(
            "CA 125",
            "909121000000107",
            "Measurement of cancer antigen 125 in serum specimen",
            [_analyte("CA 125", "1000461000000109", "Serum cancer antigen 125 level")],
        ),
    ]


def build_section_d() -> dict:
    """Section D -- investigations performed (blood panel)."""
    items = [_fbc_battery(), _ue_battery(), _lft_battery(), _bone_battery()]
    items.extend(_remaining_batteries())
    return _section(
        section_id="section_d_investigations",
        section_type="ordered_tests",
        label="Section D: Investigations performed",
        start_pattern="Section D",
        items=items,
    )


def build_points_to_remember_noise() -> dict:
    """Guidance that must never become a patient fact."""
    return _section(
        section_id="points_to_remember",
        section_type="template_noise",
        label="Points to remember",
        start_pattern="Points to remember",
        items=[],
    )


def build_ecog_status() -> dict:
    """Compact 0 [X] row, or long box-before-score ECOG 0-4."""
    return _section(
        section_id="ecog_status",
        section_type="scale",
        label="ECOG performance status",
        start_pattern="ECOG",
        items=[
            _item("0 [", "ECOG 0 fully active"),
            _item("1 [", "ECOG 1 restricted in strenuous activity"),
            _item("2 [", "ECOG 2 ambulatory and capable of selfcare"),
            _item("3 [", "ECOG 3 limited selfcare"),
            _item("4 [", "ECOG 4 completely disabled"),
            _item("Fully active", "ECOG 0 fully active"),
            _item(
                "Restricted in physically strenuous",
                "ECOG 1 restricted in strenuous activity",
            ),
            _item(
                "Ambulatory and capable of all selfcare",
                "ECOG 2 ambulatory and capable of selfcare",
            ),
            _item(
                "confined to bed or chair more than 50%",
                "ECOG 3 limited selfcare",
            ),
            _item("Totally confined to bed or chair", "ECOG 4 completely disabled"),
        ],
    )


def build_section_e() -> dict:
    """Section E -- performance status (Clinical Frailty Scale)."""
    return _section(
        section_id="section_e_performance",
        section_type="scale",
        label="Section E: Performance Status (Clinical Frailty Scale)",
        start_pattern="Section E",
        items=[
            _item("1. Very Fit", "Very fit - exercises regularly, very fit for age"),
            _item("2. Fit", "Fit - no active disease symptoms, exercises occasionally"),
            _item(
                "3. Managing well", "Managing well - medical problems well controlled"
            ),
            _item("4. Very Mild", "Very mild frailty - not fully independent"),
            _item("5. Mild", "Mild frailty - limited in some instrumental activities"),
            _item(
                "6. Moderate",
                "Moderate frailty - needs help with all outside activities",
            ),
            _item(
                "7. Severe", "Severe frailty - completely dependent for personal care"
            ),
            _item("8. Very Severe", "Very severe frailty - approaching end of life"),
            _item(
                "9. Terminally ill",
                "Terminally ill - life expectancy less than 6 months",
            ),
        ],
    )


def _coded_finding(name: str, concept_id: int) -> dict:
    return {
        "name": name,
        "kind": "optional",
        "required": False,
        "semantic_categories": [],
        "concept_ids": [concept_id],
    }


def _ng12_gynae_finding_members() -> list:
    """Coded findings that already fire NG12 1.5.12 / 1.5.13 / 1.5.14 / 1.5.17."""
    return [
        _coded_finding("Postmenopausal bleeding", 76742009),
        _coded_finding("Postcoital bleeding", 48880000),
        _coded_finding("Vaginal discharge", 271939006),
        _coded_finding("Ulceration of vulva", 68640004),
        _coded_finding("Mass of vulva", 289477004),
        _coded_finding("Swelling of vulva", 289475007),
    ]


def _cancer_type_members() -> list:
    return [{"section_id": "section_a_cancer_type"}] + _ng12_gynae_finding_members()


# Taught Section B ticks that already have a coded completeness member.
_BOX_CONCEPT_IDS = {
    "B2.": 289477004,  # Mass of vulva
    "B5.": 76742009,  # Postmenopausal bleeding
    "B6.": 48880000,  # Postcoital bleeding
}


def _symptom_members() -> list:
    boxes = []
    for index in range(1, 10):
        pattern = f"B{index}."
        row = {"section_id": "section_b_symptoms", "item_pattern": pattern}
        concept_id = _BOX_CONCEPT_IDS.get(pattern)
        if concept_id:
            row["concept_ids"] = [concept_id]
        boxes.append(row)
    return boxes + _ng12_gynae_finding_members()


def build_completeness_groups() -> list:
    return [
        {
            "name": "cancer_type_required",
            "kind": "required_section",
            "required": True,
            "min_count": 1,
            "semantic_categories": [],
            "concept_ids": [],
            "members": _cancer_type_members(),
        },
        {
            "name": "symptom_criterion_required",
            "kind": "at_least_one",
            "required": True,
            "min_count": 1,
            "semantic_categories": [],
            "concept_ids": [],
            "members": _symptom_members(),
        },
        {
            "name": "clinical_details_present",
            "kind": "recommended_section",
            "required": False,
            "min_count": 1,
            "semantic_categories": [],
            "concept_ids": [],
            "members": [{"section_id": "section_c_clinical_details"}],
        },
    ]


_SCOPE_KEYS = (
    "organization_id",
    "service_id",
    "organization_ods_code",
    "organization_name",
    "service_name",
)


def _scope_from_fixture() -> dict[str, str]:
    """Read example org/service ids from the fixture, not from code constants."""
    empty = {key: "" for key in _SCOPE_KEYS}
    if not FIXTURE_PATH.exists():
        return empty
    with open(FIXTURE_PATH, encoding="ascii") as fh:
        data = json.load(fh)
    return {key: str(data.get(key) or "") for key in _SCOPE_KEYS}


def build_payload() -> dict:
    """Load the taught template. Bind ids come from the fixture file."""
    if FIXTURE_PATH.exists():
        with open(FIXTURE_PATH, encoding="ascii") as fh:
            return json.load(fh)
    return _built_template()


def _built_template() -> dict:
    """Rebuild section payload. Overlay bind ids from the fixture if present."""
    return {
        "form_name": (
            "Sherwood Forest Hospitals NHS Foundation Trust -- "
            "Gynaecology Urgent Suspected Cancer Pathway (2WW)"
        ),
        "sections": [
            build_section_a(),
            build_section_b(),
            build_primary_care_pathway(),
            build_patient_awareness(),
            build_section_c(),
            build_section_d(),
            build_section_e(),
            build_ecog_status(),
            build_points_to_remember_noise(),
        ],
        "saved_by": "seed_sfh_gynae_2ww_template",
        "status": "active",
        **_scope_from_fixture(),
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
    url = f"{api_url}/api/v1/form-schemas/{FINGERPRINT}"
    print(f"PUT {url}")
    try:
        resp = requests.put(url, json=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        try:
            body = resp.json()
            print(json.dumps(body, indent=2, ensure_ascii=True))
        except Exception:
            print(resp.text[:500])
        if resp.status_code not in (200, 201):
            sys.exit(1)
    except requests.exceptions.ConnectionError as exc:
        print(f"Connection failed: {exc}")
        print("Is the API running at", api_url, "?")
        sys.exit(2)


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
                created_by=payload.get("saved_by") or "seed_sfh_gynae_2ww_template",
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed SFH Gynae 2WW form schema template"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL for the LEO API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help="Only write the fixture file; skip the API call",
    )
    parser.add_argument(
        "--write-graph",
        action="store_true",
        help="Write the schema to the patient graph (NEO4J_URI).",
    )
    args = parser.parse_args()

    payload = _built_template()
    save_fixture(payload)

    if args.fixture_only:
        print("Fixture-only mode: skipping API and graph write.")
    elif args.write_graph:
        write_graph(payload)
    else:
        post_to_api(args.api_url, payload)


if __name__ == "__main__":
    main()
