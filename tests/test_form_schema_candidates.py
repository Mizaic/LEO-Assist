"""Candidate taught forms for recognition: one organisation plus national.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Tenant isolation: another organisation's forms are never candidates.
Fail closed: a graph error raises FormSchemaLookupError, never [].
"""

from __future__ import annotations

from pathlib import Path

import pytest

from libs.cypher.form_schema_queries import LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG
from libs.form_recognition.schema_files import load_schema_file
from libs.pipeline.form_schema_candidates import load_candidate_schemas
from libs.pipeline.form_schema_store import (
    FormSchemaLookupError,
    _schema_to_sections_json,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "form_schema"


def _row(path: Path, fingerprint: str, organization_id: str) -> dict:
    schema = load_schema_file(path, fingerprint=fingerprint)
    return {
        "schema_id": fingerprint,
        "fingerprint": fingerprint,
        "form_name": schema.form_name,
        "status": "active",
        "sections_json": _schema_to_sections_json(schema),
        "organization_id": organization_id,
    }


class _FakeClient:
    def __init__(self, rows=None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **params):
        self.calls.append((query, params))
        if self.error is not None:
            raise self.error
        return self.rows


def test_query_is_scoped_to_active_forms_of_one_organisation_or_national() -> None:
    query = " ".join(LIST_ACTIVE_FORM_SCHEMAS_FOR_ORG.split())
    assert "s.status = 'active'" in query
    assert "s.organization_id = $organization_id" in query
    assert "coalesce(s.organization_id, '') = ''" in query
    for word in ("MERGE", "CREATE", "SET ", "DELETE"):
        assert word not in query


def test_loader_passes_the_organisation_and_parses_every_row() -> None:
    client = _FakeClient(
        rows=[
            _row(FIXTURES / "sfh_gynae_2ww_template.json", "sfh-gynae-2ww-v1", "RK5"),
            _row(
                FIXTURES / "nhs_ers_clinical_information.json",
                "nhs-ers-clinical-information-v1",
                "",
            ),
        ]
    )
    schemas = load_candidate_schemas(client, "RK5")
    assert client.calls[0][1] == {"organization_id": "RK5"}
    assert [s.fingerprint for s in schemas] == [
        "sfh-gynae-2ww-v1",
        "nhs-ers-clinical-information-v1",
    ]
    assert all(s.sections for s in schemas)


def test_unknown_organisation_still_asks_for_national_forms_only() -> None:
    client = _FakeClient(rows=[])
    assert load_candidate_schemas(client, "  ") == []
    assert client.calls[0][1] == {"organization_id": ""}


def test_graph_error_raises_lookup_error_not_an_empty_list() -> None:
    client = _FakeClient(error=RuntimeError("connection refused"))
    with pytest.raises(FormSchemaLookupError):
        load_candidate_schemas(client, "RK5")


def test_unreadable_stored_form_is_left_out_so_its_documents_pause() -> None:
    good = _row(FIXTURES / "sfh_gynae_2ww_template.json", "sfh-gynae-2ww-v1", "RK5")
    bad = dict(good, fingerprint="broken", sections_json="{not json")
    schemas = load_candidate_schemas(_FakeClient(rows=[bad, good]), "RK5")
    assert [s.fingerprint for s in schemas] == ["sfh-gynae-2ww-v1"]
