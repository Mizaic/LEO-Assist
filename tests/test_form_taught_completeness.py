"""Taught FormSchema completeness groups must reach quality_check.

Live dry-run 000486035327 showed two_ww_criterion_required and
examination_present as not_assessable with empty members. Hits were
present. The graph AuditDomain still had the old vacuous groups.

Atlas trace:
  DI: DI-50BE367C
  DO: DO-85BBD932
  VT: VT-8426C84D
  Risk: R-0883B521
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_schema_store import (
    FormSchemaWrite,
    _record_to_schema,
    rebind_form_schema_ids,
    reset_schema_cache,
    save_form_schema,
)

_VACUOUS_GRAPH = [
    {
        "name": "two_ww_criterion_required",
        "kind": "mandatory",
        "required": True,
        "concept_ids": [],
        "members": [],
    },
    {
        "name": "examination_present",
        "kind": "optional",
        "required": False,
        "concept_ids": [],
        "members": [],
    },
]

_TAUGHT_GROUPS = [
    {
        "name": "two_ww_criterion_required",
        "kind": "at_least_one",
        "required": True,
        "min_count": 1,
        "members": [{"section_id": "section_a_2ww_symptoms", "item_pattern": "A1."}],
    },
    {
        "name": "examination_present",
        "kind": "recommended_section",
        "required": False,
        "min_count": 1,
        "members": [{"section_id": "section_b_examination"}],
    },
]

_HITS = [
    {
        "section_id": "section_a_2ww_symptoms",
        "item_pattern": "A1.",
        "entity_text": "Newly presenting discrete hard breast lump",
        "checked": True,
    },
    {
        "section_id": "section_b_examination",
        "item_pattern": "Affected side",
        "entity_text": "Breast examination findings",
        "checked": True,
    },
]


class _EmptyGlobalReport:
    def to_dict(self) -> dict:
        return {"total_checked": 0, "compliant_count": 0, "issues": []}


def _section() -> FormSection:
    return FormSection(
        section_id="section_a_2ww_symptoms",
        section_type="checkbox_multi",
        label="Section A",
        start_pattern="Section A",
        items=[FormSchemaItem(pattern="A1.", entity_text="Hard lump")],
    )


def test_quality_check_uses_taught_groups_when_graph_schema_is_vacuous(
    monkeypatch,
) -> None:
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(
        quality_check,
        "_load_completeness_schema",
        lambda domain, subdomain: _VACUOUS_GRAPH,
    )
    result = quality_check.run_quality_checks(
        {
            "patient_id": "p-breast",
            "completeness_domain": "svc_117038",
            "completeness_subdomain": "minimum_dataset",
            "entities": [],
            "episodes": [{}],
            "section_hits": _HITS,
            "completeness_groups": _TAUGHT_GROUPS,
        }
    )
    completeness = result["completeness_result"]
    names = {row["name"] for row in completeness["matched_groups"]}
    assert "two_ww_criterion_required" in names
    assert "examination_present" in names
    assert completeness["complete"] is True
    assert completeness["degraded"] is False


def test_chunk_load_payload_keeps_completeness_groups() -> None:
    from libs.pipeline_graph.subgraphs.extraction import _chunk_load_payload

    payload = _chunk_load_payload(
        {
            "encounter_text": "Section A",
            "sentences": [{"sentence_id": "c1", "text": "Section A"}],
            "form_schema_match": "org_service",
            "form_schema_fingerprint": "sfh-breast-2ww-v1",
            "form_schema_label": "Breast Unit",
            "section_hits": _HITS,
            "completeness_groups": _TAUGHT_GROUPS,
        },
        [],
    )
    assert payload["completeness_groups"] == _TAUGHT_GROUPS
    assert payload["section_hits"] == _HITS


def test_rewrite_and_cover_attaches_completeness_groups() -> None:
    from libs.pipeline.document_chunk_loader import _rewrite_and_cover

    schema = FormSchema(
        schema_id="breast",
        fingerprint="sfh-breast-2ww-v1",
        form_name="Breast Unit",
        sections=[_section()],
        created_by="test",
        completeness_groups=_TAUGHT_GROUPS,
    )
    _texts, extra = _rewrite_and_cover(
        schema, ["Section A\nA1. Yes [X]\nSection B\nAffected side"]
    )
    assert extra["completeness_groups"] == _TAUGHT_GROUPS
    assert extra.get("form_layout_matched") is True
    assert extra.get("section_hits")


def test_save_persists_completeness_groups_on_form_schema() -> None:
    client = MagicMock()
    client.run.return_value = []
    write = FormSchemaWrite(
        fingerprint="fp-taught-groups",
        form_name="Breast Unit",
        sections=[_section()],
        created_by="test",
        organization_id="RK5",
        service_id="117038",
        completeness_groups=_TAUGHT_GROUPS,
    )
    with patch("libs.pipeline.form_schema_store.ensure_service_completeness_domain"):
        saved = save_form_schema(client, write)
    assert saved.completeness_groups == _TAUGHT_GROUPS
    kwargs = client.run.call_args_list[0].kwargs
    stored = json.loads(kwargs["completeness_groups_json"])
    assert stored == _TAUGHT_GROUPS
    loaded = _record_to_schema(
        {
            "schema_id": "s1",
            "fingerprint": "fp-taught-groups",
            "form_name": "Breast Unit",
            "sections_json": "[]",
            "created_by": "test",
            "completeness_groups_json": kwargs["completeness_groups_json"],
        }
    )
    assert loaded.completeness_groups == _TAUGHT_GROUPS


def test_rebind_refreshes_groups_when_scope_unchanged() -> None:
    reset_schema_cache()
    existing = FormSchema(
        schema_id="sid",
        fingerprint="fp-same-scope",
        form_name="Breast Unit",
        sections=[_section()],
        created_by="old",
        organization_id="RK5",
        service_id="117038",
    )
    write = FormSchemaWrite(
        fingerprint="fp-same-scope",
        form_name="Breast Unit",
        sections=[],
        created_by="seed",
        organization_id="RK5",
        service_id="117038",
        completeness_groups=_TAUGHT_GROUPS,
    )
    with patch(
        "libs.pipeline.form_schema_store.load_form_schema",
        return_value=existing,
    ):
        with patch("libs.pipeline.form_schema_store.save_form_schema") as mock_save:
            action = rebind_form_schema_ids(MagicMock(), write)
    assert action == "updated"
    saved = mock_save.call_args.args[1]
    assert saved.completeness_groups == _TAUGHT_GROUPS


def test_extraction_subgraph_preserves_section_hits_and_groups() -> None:
    """ExtractionState must declare section_hits and completeness_groups.

    LangGraph StateGraph only returns keys declared in the TypedDict schema.
    If section_hits and completeness_groups are not in ExtractionState, they
    are silently dropped and quality_check receives empty lists, causing every
    taught-form completeness group to be reported as not_assessable.

    This is the root cause found on 2026-08-29 when all 6 breast UBRNs and
    9/11 gynae UBRNs reported not_assessable despite correct form seeding.
    """
    from libs.pipeline_graph.subgraphs.extraction import (
        ExtractionState,
        build_extraction_subgraph,
    )

    schema_annotations = ExtractionState.__annotations__
    assert "section_hits" in schema_annotations, (
        "section_hits must be declared in ExtractionState so LangGraph "
        "preserves it across the extraction subgraph"
    )
    assert "completeness_groups" in schema_annotations, (
        "completeness_groups must be declared in ExtractionState so LangGraph "
        "preserves it across the extraction subgraph"
    )

    subgraph = build_extraction_subgraph()
    result = subgraph.invoke(
        {
            "section_hits": _HITS,
            "completeness_groups": _TAUGHT_GROUPS,
            "encounter_text": "Section A",
            "sentences": [
                {
                    "sentence_id": "s0",
                    "chunk_id": "c1",
                    "text": "Section A",
                    "text_raw": "Section A",
                    "start": 0,
                    "end": 9,
                }
            ],
            "chunk_ids": ["c1"],
            "chunk_id_by_sentence_id": {"s0": "c1"},
            "text_segmentation_mode": "document_chunks",
            "errors": [],
            "warnings": [],
        }
    )
    assert (
        result.get("section_hits") == _HITS
    ), "section_hits were dropped by ExtractionState -- add the field to the TypedDict"
    assert (
        result.get("completeness_groups") == _TAUGHT_GROUPS
    ), "completeness_groups were dropped -- add the field to ExtractionState"


def _fixture_schema(filename: str, fingerprint: str) -> FormSchema:
    from pathlib import Path

    from libs.pipeline.form_schema_request import (
        build_sections_from_request,
        normalize_sections_for_request,
    )

    payload = json.loads(
        (
            Path(__file__).resolve().parent / "fixtures" / "form_schema" / filename
        ).read_text()
    )
    return FormSchema(
        schema_id=fingerprint,
        fingerprint=fingerprint,
        form_name=payload["form_name"],
        sections=build_sections_from_request(
            normalize_sections_for_request(payload["sections"])
        ),
        created_by="test",
        completeness_groups=list(payload.get("completeness_groups") or []),
    )


def _quality_from_preloaded_letter(
    schema: FormSchema, letter: str, monkeypatch
) -> dict:
    from libs.pipeline.form_schema_store import remember_schema, reset_schema_cache
    from libs.pipeline_graph.subgraphs import quality_check
    from libs.pipeline_graph.subgraphs.extraction import load_document_chunks

    reset_schema_cache()
    remember_schema(schema)
    loaded = load_document_chunks(
        {
            "sentences": [
                {
                    "sentence_id": "s0",
                    "chunk_id": "c1",
                    "text": letter,
                    "text_raw": letter,
                    "start": 0,
                    "end": len(letter),
                }
            ],
            "encounter_text": letter,
            "form_schema_fingerprint": schema.fingerprint,
            "form_schema_match": "org_service",
            "form_schema_label": schema.form_name,
            "errors": [],
            "warnings": [],
        }
    )
    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(quality_check, "_load_completeness_schema", lambda d, s: [])
    return quality_check.run_quality_checks(
        {
            "patient_id": "p-fixture",
            "completeness_domain": "svc_test",
            "completeness_subdomain": "minimum_dataset",
            "entities": [],
            "episodes": [{}],
            "section_hits": loaded.get("section_hits") or [],
            "completeness_groups": schema.completeness_groups,
        }
    )["completeness_result"]


def test_fixture_ticked_hits_satisfy_taught_completeness_groups(monkeypatch) -> None:
    """Ticked fixture boxes must score the taught completeness groups.

    Dry-run pre-loads chunk sentences, so load_document_chunks must still
    collect section_hits. quality_check then matches those hits against
    the fixture completeness_groups (real section_id / item_pattern).
    """
    gynae = _fixture_schema("sfh_gynae_2ww_template.json", "sfh-gynae-2ww-v1")
    gynae_result = _quality_from_preloaded_letter(
        gynae,
        (
            "Section A: Gynaecological Cancer type suspected\n"
            "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
        ),
        monkeypatch,
    )
    gynae_matched = {row["name"] for row in gynae_result["matched_groups"]}
    assert "cancer_type_required" in gynae_matched, gynae_result

    breast = _fixture_schema("sfh_breast_2ww_template.json", "sfh-breast-2ww-v1")
    breast_result = _quality_from_preloaded_letter(
        breast,
        (
            "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
            "| A1. Newly presenting discrete hard lump | Yes [X] |\n"
        ),
        monkeypatch,
    )
    breast_matched = {row["name"] for row in breast_result["matched_groups"]}
    assert "two_ww_criterion_required" in breast_matched, breast_result


def test_load_schema_prefers_assessable_valueset() -> None:
    from libs.pipeline_graph.subgraphs import quality_check

    vacuous = json.dumps({"groups": _VACUOUS_GRAPH})
    taught = json.dumps({"groups": _TAUGHT_GROUPS})
    patient_mock = MagicMock()
    patient_mock.run.return_value = [
        {"id": "ncda-minimum-dataset", "completeness_schema": vacuous},
        {"id": "svc_117038-minimum_dataset", "completeness_schema": taught},
    ]
    with patch(
        "libs.pipeline_graph.subgraphs.quality_check.PatientGraphClient",
        return_value=patient_mock,
    ):
        schema = quality_check._load_completeness_schema(
            "svc_117038", "minimum_dataset"
        )
    assert schema[0]["members"]
    assert schema[0]["name"] == "two_ww_criterion_required"
