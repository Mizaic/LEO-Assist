"""FormSchema organisation/service binding and service completeness domain.

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-C34A2990 (extended by form-to-service completeness slice)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.cypher.form_schema_queries import UPSERT_FORM_SCHEMA
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    _record_to_schema,
    normalize_sections_for_request,
    save_form_schema,
)


def _section() -> FormSection:
    return FormSection(
        section_id="A",
        section_type="checkbox_single",
        label="Cancer type",
        start_pattern="Section A",
        items=[],
    )


def test_record_to_schema_reads_organization_and_service_ids():
    schema = _record_to_schema(
        {
            "schema_id": "s1",
            "fingerprint": "fp-1",
            "form_name": "SFH Gynae",
            "sections_json": "[]",
            "created_by": "teacher@example.com",
            "organization_id": "org-sfh",
            "service_id": "svc-gynae",
        }
    )
    assert schema.organization_id == "org-sfh"
    assert schema.service_id == "svc-gynae"


def test_upsert_merges_org_and_service_edges_without_creating_nodes():
    """Save links FormSchema to existing Organization/Service for Bloom."""
    assert "USED_BY_ORG" in UPSERT_FORM_SCHEMA
    assert "USED_BY_SERVICE" in UPSERT_FORM_SCHEMA
    assert "SCHEMA_FOR" in UPSERT_FORM_SCHEMA
    assert "MERGE (org:Organization" not in UPSERT_FORM_SCHEMA
    assert "MERGE (svc:Service" not in UPSERT_FORM_SCHEMA
    assert "CREATE (org:Organization" not in UPSERT_FORM_SCHEMA
    assert "CREATE (svc:Service" not in UPSERT_FORM_SCHEMA
    assert "org.ods_code" in UPSERT_FORM_SCHEMA
    assert "svc.ers_service_id" in UPSERT_FORM_SCHEMA


def test_save_form_schema_persists_org_and_service_ids():
    client = MagicMock()
    client.run.return_value = []
    write = FormSchemaWrite(
        fingerprint="fp-1",
        form_name="SFH Gynae",
        sections=[_section()],
        created_by="teacher@example.com",
        organization_id="org-sfh",
        service_id="svc-gynae",
    )
    saved = save_form_schema(client, write)
    assert saved.organization_id == "org-sfh"
    assert saved.service_id == "svc-gynae"
    kwargs = client.run.call_args_list[0].kwargs
    assert kwargs["organization_id"] == "org-sfh"
    assert kwargs["service_id"] == "svc-gynae"


def test_save_form_schema_ensures_service_completeness_domain():
    client = MagicMock()
    client.run.return_value = []
    groups = [
        {
            "name": "Section A",
            "kind": "mandatory",
            "concept_ids": [100],
            "semantic_categories": [],
        },
        {
            "name": "Referral criteria",
            "kind": "one_of",
            "members": [
                {"name": "B1", "concept_ids": [111], "semantic_categories": []},
                {"name": "B2", "concept_ids": [222], "semantic_categories": []},
            ],
        },
    ]
    write = FormSchemaWrite(
        fingerprint="fp-1",
        form_name="SFH Gynae",
        sections=[_section()],
        created_by="teacher@example.com",
        organization_id="org-sfh",
        service_id="svc-gynae",
        completeness_groups=groups,
    )
    save_form_schema(client, write)
    cypher_blobs = " ".join(str(call.args[0]) for call in client.run.call_args_list)
    assert "AuditDomain" in cypher_blobs
    assert "completeness_schema" in cypher_blobs
    assert "completeness_domain" in cypher_blobs


def test_save_form_schema_allows_optional_only_completeness_groups():
    client = MagicMock()
    client.run.return_value = [
        {"domain_id": "svc_svc-gynae", "subdomain": "minimum_dataset"}
    ]
    groups = [
        {
            "name": "Optional note",
            "kind": "optional",
            "required": False,
            "semantic_categories": [],
            "concept_ids": [],
        }
    ]
    write = FormSchemaWrite(
        fingerprint="fp-optional",
        form_name="SFH Gynae",
        sections=[_section()],
        created_by="teacher@example.com",
        organization_id="org-sfh",
        service_id="svc-gynae",
        completeness_groups=groups,
    )
    saved = save_form_schema(client, write)
    assert saved.fingerprint == "fp-optional"


def test_form_schema_dataclass_holds_scope_ids():
    schema = FormSchema(
        schema_id="s1",
        fingerprint="fp-1",
        form_name="SFH Gynae",
        sections=[],
        created_by="teacher",
        organization_id="org-sfh",
        service_id="svc-gynae",
    )
    assert schema.organization_id == "org-sfh"
    assert schema.service_id == "svc-gynae"


def test_normalize_sections_fills_start_pattern_and_drops_blank_items():
    raw = [
        {
            "section_id": "S1",
            "section_type": "checkbox_single",
            "label": "Section A",
            "start_pattern": "",
            "items": [
                {"pattern": "Cervix", "entity_text": "Cervical cancer"},
                {"pattern": "", "entity_text": "skip me"},
            ],
        }
    ]
    rows = normalize_sections_for_request(raw)
    assert len(rows) == 1
    assert rows[0]["start_pattern"] == "Section A"
    assert len(rows[0]["items"]) == 1


def test_normalize_ordered_tests_keeps_analytes_without_entity_text():
    """Blood batteries use pattern + analytes; entity_text is optional in UI."""
    raw = [
        {
            "section_id": "S1",
            "section_type": "ordered_tests",
            "label": "Blood Tests",
            "start_pattern": "Blood Tests",
            "items": [
                {
                    "pattern": "FBC",
                    "entity_text": "",
                    "procedure_snomed": "26604007",
                    "procedure_display": "Full blood count",
                    "analytes": [
                        {
                            "label": "Hb",
                            "snomed_code": "1022280009",
                            "display": "Haemoglobin",
                        }
                    ],
                },
                {"pattern": "", "entity_text": "", "analytes": []},
            ],
        }
    ]
    rows = normalize_sections_for_request(raw)
    assert len(rows) == 1
    assert len(rows[0]["items"]) == 1
    item = rows[0]["items"][0]
    assert item["pattern"] == "FBC"
    assert item["entity_text"] == "Full blood count"
    assert len(item["analytes"]) == 1
