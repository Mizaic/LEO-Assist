"""A letter on a taught service must not be scored against that form's ticks.

Breast Clinic service 117038 has a taught Kings Mill 2WW form and a
service completeness domain built from that form's sections. A cover
letter on that service is not the form: it must not be marked incomplete
for missing Section A ticks. Unscored is not incomplete.

There is no organisation-and-service bind any more. Recognition decides
which form a document is (DI-E21DF9EF). Groups that can only be met by a
taught form's ticks are not assessable unless the bundle was recognised.

Atlas trace:
  DI: DI-26546721, DI-50BE367C, DI-E21DF9EF
  DO: DO-020C7B5C, DO-E458EEC5
  VT: VT-6D49BB73, VT-B13F7C48
  UN: UN-3B25A20E
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.pipeline.form_recognition_apply import recognise_texts, recognition_fields
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_schema_request import (
    build_sections_from_request,
    normalize_sections_for_request,
)

_BREAST_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "form_schema"
    / "sfh_breast_2ww_template.json"
)

_COVER_LETTER = (
    "Dear Colleague\n"
    "Please see this patient in the Breast Clinic.\n"
    "Yours sincerely\n"
    "GP Partner\n"
)

_CONCEPT_GROUP = {
    "name": "imaging_present",
    "kind": "at_least_one",
    "required": True,
    "min_count": 1,
    "semantic_categories": ["procedure"],
    "concept_ids": [],
    "members": [],
}


class _EmptyGlobalReport:
    def to_dict(self) -> dict:
        return {"total_checked": 0, "compliant_count": 0, "issues": []}


def _breast_schema() -> FormSchema:
    payload = json.loads(_BREAST_FIXTURE.read_text(encoding="utf-8"))
    return FormSchema(
        schema_id="sfh-breast-2ww-v1",
        fingerprint="sfh-breast-2ww-v1",
        form_name=payload["form_name"],
        sections=build_sections_from_request(
            normalize_sections_for_request(payload["sections"])
        ),
        created_by="test",
        organization_id="RK5",
        service_id="117038",
        completeness_groups=list(payload.get("completeness_groups") or []),
    )


def _quality(monkeypatch, fields: dict, service_groups: list[dict]) -> dict:
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(quality_check, "_load_isa_expansion", lambda required_ids: {})
    monkeypatch.setattr(
        quality_check,
        "_load_completeness_schema",
        lambda domain, subdomain: list(service_groups),
    )
    return quality_check.run_quality_checks(
        {
            "patient_id": "p-117038",
            "completeness_domain": "svc_117038",
            "completeness_subdomain": "minimum_dataset",
            "entities": [],
            "episodes": [{}],
            **fields,
        }
    )


def _letter_fields() -> dict:
    schema = _breast_schema()
    outcomes = recognise_texts([_COVER_LETTER], lambda: [schema])
    return recognition_fields([_COVER_LETTER], outcomes)


def _incomplete(result: dict) -> bool:
    return any(
        issue.get("issue_type") == "minimum_dataset_incomplete"
        for issue in result.get("quality_issues") or []
    )


def test_cover_letter_on_service_117038_is_not_scored_on_form_ticks(
    monkeypatch,
) -> None:
    fields = _letter_fields()
    groups = list(_breast_schema().completeness_groups)
    result = _quality(monkeypatch, fields, groups)
    completeness = result.get("completeness_result") or {}

    assert fields["form_schema_match"] == "not_a_form"
    assert fields["form_layout_matched"] is False
    assert not fields.get("completeness_groups")
    assert completeness.get("configured") is not True
    assert not _incomplete(result)


def test_concept_groups_still_score_a_letter(monkeypatch) -> None:
    groups = list(_breast_schema().completeness_groups) + [_CONCEPT_GROUP]
    result = _quality(monkeypatch, _letter_fields(), groups)
    completeness = result.get("completeness_result") or {}

    assert completeness.get("configured") is True
    names = [row["name"] for row in completeness.get("missing_groups") or []]
    assert names == ["imaging_present"]


def test_recognised_2ww_form_stays_configured(monkeypatch) -> None:
    """A recognised Kings Mill 2WW form is still scored on its own groups."""
    schema = _breast_schema()
    fields = {
        "form_schema_match": "recognised",
        "form_schema_fingerprint": schema.fingerprint,
        "form_layout_matched": True,
        "section_hits": [],
        "completeness_groups": list(schema.completeness_groups),
    }
    result = _quality(monkeypatch, fields, [])
    completeness = result.get("completeness_result") or {}

    assert completeness.get("configured") is True
