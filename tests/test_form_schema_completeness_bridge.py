"""Integration test: FormSchema save -> ServiceDomain write -> evaluate.

Verifies the bridge between FormSchema completeness rules and the
ServiceDomain completeness_schema that the runtime pipeline reads.

Atlas trace:
  UN: UN-3B25A20E
  DI: DI-26546721
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.completeness.service_domain import ensure_service_completeness_domain
from libs.pipeline.form_schema_store import FormSchemaWrite, save_form_schema
from libs.pipeline.form_schema_normalizer import FormSection


def _section() -> FormSection:
    return FormSection(
        section_id="A",
        section_type="checkbox_single",
        label="Cancer type",
        start_pattern="Section A",
        items=[],
    )


def _mock_client(domain_row: dict | None = None) -> MagicMock:
    client = MagicMock()
    client.run.return_value = [domain_row] if domain_row else []
    return client


# -- Test 1: bridge writes completeness_schema to AuditDomain on save ------

def test_save_form_schema_with_groups_calls_ensure_domain():
    """save_form_schema must call ensure_service_completeness_domain when
    service_id is set and completeness_groups are provided."""
    groups = [
        {"name": "Referral section", "kind": "mandatory", "concept_ids": [100]}
    ]
    write = FormSchemaWrite(
        fingerprint="fp-bridge-test",
        form_name="SFH Gynae 2WW",
        sections=[_section()],
        created_by="test@sfh.nhs.uk",
        organization_id="org-sfh",
        service_id="svc-gynae",
        completeness_groups=groups,
    )
    client = _mock_client()

    with patch(
        "libs.pipeline.form_schema_store.ensure_service_completeness_domain"
    ) as mock_ensure:
        mock_ensure.return_value = {"domain_id": "svc_svc-gynae", "subdomain": "minimum_dataset"}
        save_form_schema(client, write)

    mock_ensure.assert_called_once_with(
        client,
        organization_id="org-sfh",
        service_id="svc-gynae",
        form_name="SFH Gynae 2WW",
        groups=groups,
        require_blocking_groups=False,
    )


def test_save_form_schema_without_service_id_skips_domain():
    """When service_id is empty, ensure_service_completeness_domain must not
    be called -- the schema is not scoped to a service."""
    write = FormSchemaWrite(
        fingerprint="fp-unscoped",
        form_name="Generic Form",
        sections=[_section()],
        created_by="test@sfh.nhs.uk",
        organization_id="",
        service_id="",
        completeness_groups=[],
    )
    client = _mock_client()
    with patch(
        "libs.pipeline.form_schema_store.ensure_service_completeness_domain"
    ) as mock_ensure:
        save_form_schema(client, write)
    mock_ensure.assert_not_called()


# -- Test 2: written schema round-trips through evaluate_completeness_groups -

def test_written_schema_evaluates_correctly_via_ensure_domain():
    """The JSON written by ensure_service_completeness_domain matches the
    shape that evaluate_completeness_groups can process."""
    groups = [
        {
            "name": "Mandatory code",
            "kind": "mandatory",
            "required": True,
            "concept_ids": [200],
            "semantic_categories": [],
            "members": [],
            "if_group": None,
            "then_group": None,
            "min_count": 1,
        }
    ]
    client = _mock_client()
    ensure_service_completeness_domain(
        client,
        organization_id="org-sfh",
        service_id="svc-gynae",
        form_name="Gynae 2WW",
        groups=groups,
    )

    # Extract the schema JSON that was written to Neo4j
    written_calls = client.run.call_args_list
    schema_kwarg = written_calls[-1].kwargs.get("schema") or written_calls[-1].args[-1]
    stored = json.loads(schema_kwarg)
    schema_groups = stored.get("groups", [])

    # Must evaluate correctly -- concept_id 200 satisfies the mandatory group
    present = evaluate_completeness_groups(
        schema_groups,
        present_concept_ids={200},
        present_semantic_tags=set(),
    )
    assert present["complete"] is True

    # Without the concept the group is missing
    absent = evaluate_completeness_groups(
        schema_groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
    )
    assert absent["complete"] is False
    assert absent["missing_groups"][0]["name"] == "Mandatory code"


def test_one_of_group_round_trips():
    """An 'one_of' completeness group written by ensure_service_completeness_domain
    evaluates correctly after JSON round-trip."""
    groups = [
        {
            "name": "Referral criteria",
            "kind": "one_of",
            "required": True,
            "concept_ids": [],
            "semantic_categories": [],
            "min_count": 1,
            "members": [
                {"name": "Route B1", "concept_ids": [111], "semantic_categories": []},
                {"name": "Route B2", "concept_ids": [222], "semantic_categories": []},
            ],
            "if_group": None,
            "then_group": None,
        }
    ]
    client = _mock_client()
    ensure_service_completeness_domain(
        client,
        organization_id="org-sfh",
        service_id="svc-gynae",
        form_name="Gynae 2WW",
        groups=groups,
    )

    written_calls = client.run.call_args_list
    schema_kwarg = written_calls[-1].kwargs.get("schema") or written_calls[-1].args[-1]
    stored = json.loads(schema_kwarg)
    schema_groups = stored.get("groups", [])

    no_match = evaluate_completeness_groups(
        schema_groups,
        present_concept_ids=set(),
        present_semantic_tags=set(),
    )
    assert no_match["complete"] is False

    b2_match = evaluate_completeness_groups(
        schema_groups,
        present_concept_ids={222},
        present_semantic_tags=set(),
    )
    assert b2_match["complete"] is True
