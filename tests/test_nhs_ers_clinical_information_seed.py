"""Seed contract: national e-RS Clinical Information persists to the graph.

Wrapper-only referrals have no specialty org or service bind. The taught
schema must therefore keep an empty organisation and service, and still
persist every fixture section plus completeness group.

Atlas trace:
  DI: DI-50BE367C
  DO: DO-85BBD932
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from libs.pipeline.form_schema_request import (
    build_sections_from_request,
    normalize_sections_for_request,
)
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    _record_to_schema,
    save_form_schema,
)

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from seed_nhs_ers_clinical_information import (  # noqa: E402
    FINGERPRINT,
    FIXTURE_PATH,
    build_payload,
)

_EXPECTED_SECTIONS = {
    "admin_header",
    "ubrn_information",
    "patient_information",
    "attachments",
    "risk_to_others",
    "reason_for_referral",
    "expectation_of_referral",
    "medication",
    "past_medical_history",
    "allergies",
    "findings",
    "family_history",
    "social_context",
    "service_provider_activity",
}

_EXPECTED_GROUPS = {
    "reason_for_referral_required",
    "findings_or_bloods_present",
    "medication_present",
}


def test_seed_payload_matches_fixture_sections_and_groups() -> None:
    payload = build_payload()
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="ascii"))
    assert payload["fingerprint"] == FINGERPRINT == "nhs-ers-clinical-information-v1"
    assert payload["organization_id"] == ""
    assert payload["service_id"] == ""
    assert {s["section_id"] for s in payload["sections"]} == _EXPECTED_SECTIONS
    names = {g["name"] for g in payload["completeness_groups"]}
    assert _EXPECTED_GROUPS <= names
    assert payload["sections"] == fixture["sections"]
    assert payload["completeness_groups"] == fixture["completeness_groups"]


def test_seed_write_persists_sections_and_completeness_groups() -> None:
    payload = build_payload()
    sections = build_sections_from_request(
        normalize_sections_for_request(payload["sections"])
    )
    client = MagicMock()
    client.run.return_value = []
    write = FormSchemaWrite(
        fingerprint=FINGERPRINT,
        form_name=payload["form_name"],
        sections=sections,
        created_by="test",
        schema_id=FINGERPRINT,
        organization_id="",
        service_id="",
        completeness_groups=payload["completeness_groups"],
    )
    with patch(
        "libs.pipeline.form_schema_store.ensure_service_completeness_domain"
    ) as ens:
        saved = save_form_schema(client, write)
    ens.assert_not_called()
    assert saved.fingerprint == FINGERPRINT
    assert saved.organization_id == ""
    assert saved.service_id == ""
    kwargs = client.run.call_args_list[0].kwargs
    stored_groups = json.loads(kwargs["completeness_groups_json"])
    assert {g["name"] for g in stored_groups} >= _EXPECTED_GROUPS
    stored_sections = json.loads(kwargs["sections_json"])
    assert {s["section_id"] for s in stored_sections} == _EXPECTED_SECTIONS
    loaded = _record_to_schema(
        {
            "schema_id": FINGERPRINT,
            "fingerprint": FINGERPRINT,
            "form_name": payload["form_name"],
            "sections_json": kwargs["sections_json"],
            "created_by": "test",
            "completeness_groups_json": kwargs["completeness_groups_json"],
        }
    )
    assert {s.section_id for s in loaded.sections} == _EXPECTED_SECTIONS
    assert {g["name"] for g in loaded.completeness_groups} >= _EXPECTED_GROUPS
