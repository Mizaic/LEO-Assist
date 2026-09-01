"""Coarse org-service bind must not score 2WW completeness on the wrong letter.

Breast Clinic service 117038 has a taught Kings Mill 2WW form and a
service completeness domain. A cover letter on that service must not be
marked incomplete for missing Section A ticks. Unscored is not incomplete.

Atlas trace:
  DI: DI-26546721
  DI: DI-50BE367C
  DO: DO-020C7B5C
  VT: VT-6D49BB73
  UN: UN-3B25A20E
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.pipeline.document_chunk_loader import _rewrite_and_cover
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

_MATCHING_2WW = (
    "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
    "| A1. Newly presenting discrete hard lump | Yes [X] |\n"
    "| Section B: Examination findings |\n"
)


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


def _quality(monkeypatch, extra: dict, letter_match: str) -> dict:
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(quality_check, "_load_isa_expansion", lambda required_ids: {})
    monkeypatch.setattr(
        quality_check,
        "_load_completeness_schema",
        lambda domain, subdomain: list(_breast_schema().completeness_groups),
    )
    return quality_check.run_quality_checks(
        {
            "patient_id": "p-117038",
            "completeness_domain": "svc_117038",
            "completeness_subdomain": "minimum_dataset",
            "form_schema_match": letter_match,
            "form_schema_fingerprint": "sfh-breast-2ww-v1",
            "form_layout_matched": extra.get("form_layout_matched"),
            "entities": [],
            "episodes": [{}],
            "section_hits": extra.get("section_hits") or [],
            "completeness_groups": extra.get("completeness_groups") or [],
        }
    )


def test_non_matching_layout_on_service_117038_is_not_configured(monkeypatch) -> None:
    """A cover letter on service 117038 must not get configured 2WW completeness."""
    _texts, extra = _rewrite_and_cover(_breast_schema(), [_COVER_LETTER])
    result = _quality(monkeypatch, extra, "org_service")
    completeness = result.get("completeness_result") or {}

    assert extra.get("form_layout_matched") is False
    assert not extra.get("completeness_groups")
    assert completeness.get("configured") is not True
    assert not any(
        issue.get("issue_type") == "minimum_dataset_incomplete"
        for issue in result.get("quality_issues") or []
    )


def test_matching_2ww_layout_on_service_117038_stays_configured(monkeypatch) -> None:
    """A true Kings Mill 2WW letter on 117038 must still be scored."""
    _texts, extra = _rewrite_and_cover(_breast_schema(), [_MATCHING_2WW])
    result = _quality(monkeypatch, extra, "org_service")
    completeness = result.get("completeness_result") or {}

    assert extra.get("form_layout_matched") is True
    assert extra.get("completeness_groups")
    assert completeness.get("configured") is True
