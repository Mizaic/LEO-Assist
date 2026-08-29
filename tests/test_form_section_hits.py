"""Form-native completeness: section hits through to quality_check.

Atlas trace:
  DI: DI-50BE367C
  DO: DO-85BBD932
  VT: VT-8426C84D
  Risk: R-0883B521
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.completeness.logic_groups import resolve_kind
from libs.completeness.schema import normalise_completeness_groups
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
)
from libs.pipeline.form_section_hits import collect_section_hits

_SECTION_A = FormSection(
    section_id="section_a_cancer_type",
    section_type="checkbox_single",
    label="Section A: cancer type suspected",
    start_pattern=r"(?i)section\s+a:",
    items=[
        FormSchemaItem(
            pattern="Cervix",
            entity_text="Cervical cancer suspected",
        ),
        FormSchemaItem(
            pattern="Ovary",
            entity_text="Ovarian cancer suspected",
        ),
    ],
)

_SECTION_B = FormSection(
    section_id="section_b_symptoms",
    section_type="checkbox_yesno",
    label="Section B: signs and symptoms",
    start_pattern=r"(?i)section\s+b:",
    items=[
        FormSchemaItem(
            pattern=r"B1\.",
            entity_text="Lesion suspicious of cancer of cervix",
        ),
        FormSchemaItem(
            pattern=r"B2\.",
            entity_text="Lesion suspicious of cancer of vulva",
        ),
    ],
)


def _schema() -> FormSchema:
    return FormSchema(
        schema_id="hits-1",
        fingerprint="hits",
        form_name="Hits test form",
        sections=[_SECTION_A, _SECTION_B],
        created_by="test",
    )


def _letter() -> str:
    return (
        "Section A: cancer type suspected\n"
        "Cervix [X] Ovary [ ]\n"
        "Section B: signs and symptoms\n"
        "B1. [X] Yes [ ] No\n"
        "B2. [ ] Yes [X] No\n"
    )


def test_collect_section_hits_emits_checked_and_unchecked_boxes() -> None:
    hits = collect_section_hits(_schema(), [_letter()])
    by_key = {(h["section_id"], h["item_pattern"]): h for h in hits}
    cervix = by_key[("section_a_cancer_type", "Cervix")]
    assert cervix["entity_text"] == "Cervical cancer suspected"
    assert cervix["checked"] is True
    ovary = by_key[("section_a_cancer_type", "Ovary")]
    assert ovary["checked"] is False
    assert by_key[("section_b_symptoms", r"B1\.")]["checked"] is True
    assert by_key[("section_b_symptoms", r"B2\.")]["checked"] is False


def test_chunk_state_carries_section_hits() -> None:
    from libs.pipeline.document_chunk_loader import build_document_chunk_state
    from libs.pipeline.form_schema_store import form_schema_state_fields

    rows = [
        {
            "chunk_id": "chunk-0",
            "text": _letter(),
            "ordinal": 0,
            "char_start": None,
            "char_end": None,
        }
    ]
    fields = form_schema_state_fields("exact_hash", "hits", "Hits test form")
    with patch(
        "libs.pipeline.document_chunk_loader._resolve_chunk_schema",
        return_value=(_schema(), fields),
    ):
        state = build_document_chunk_state(rows)
    hits = state.get("section_hits") or []
    assert any(
        h["section_id"] == "section_a_cancer_type"
        and h["item_pattern"] == "Cervix"
        and h["checked"] is True
        for h in hits
    )


def test_quality_check_matches_ticked_box_without_snomed(monkeypatch) -> None:
    from libs.pipeline_graph.subgraphs import quality_check

    class _EmptyGlobalReport:
        def to_dict(self) -> dict:
            return {"total_checked": 0, "compliant_count": 0, "issues": []}

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(
        quality_check,
        "_load_completeness_schema",
        lambda domain, subdomain: [
            {
                "name": "cancer_type_required",
                "kind": "required_section",
                "required": True,
                "min_count": 1,
                "members": [{"section_id": "section_a_cancer_type"}],
            }
        ],
    )
    result = quality_check.run_quality_checks(
        {
            "patient_id": "p1",
            "completeness_domain": "svc_gynae",
            "completeness_subdomain": "minimum_dataset",
            "entities": [],
            "episodes": [{}],
            "section_hits": [
                {
                    "section_id": "section_a_cancer_type",
                    "item_pattern": "Cervix",
                    "entity_text": "Cervical cancer suspected",
                    "checked": True,
                }
            ],
        }
    )
    completeness = result["completeness_result"]
    assert completeness["complete"] is True
    assert completeness["matched_groups"][0]["name"] == "cancer_type_required"


def test_normalise_keeps_section_id_and_item_pattern() -> None:
    rows = normalise_completeness_groups(
        [
            {
                "name": "symptom_criterion_required",
                "kind": "at_least_one",
                "min_count": 1,
                "members": [
                    {"section_id": "section_b_symptoms", "item_pattern": "B1."},
                    {"section_id": "section_b_symptoms", "item_pattern": "B2."},
                ],
            }
        ]
    )
    members = rows[0]["members"]
    assert members[0]["section_id"] == "section_b_symptoms"
    assert members[0]["item_pattern"] == "B1."
    assert members[1]["item_pattern"] == "B2."


def test_evaluator_matches_member_by_section_id_and_item_pattern() -> None:
    schema = [
        {
            "name": "symptom_criterion_required",
            "kind": "at_least_one",
            "required": True,
            "min_count": 1,
            "members": [
                {
                    "name": "B1",
                    "section_id": "section_b_symptoms",
                    "item_pattern": r"B1\.",
                },
                {
                    "name": "B2",
                    "section_id": "section_b_symptoms",
                    "item_pattern": r"B2\.",
                },
            ],
        }
    ]
    hits = [
        {
            "section_id": "section_b_symptoms",
            "item_pattern": r"B1\.",
            "entity_text": "Lesion suspicious of cancer of cervix",
            "checked": True,
        },
        {
            "section_id": "section_b_symptoms",
            "item_pattern": r"B2\.",
            "entity_text": "Lesion suspicious of cancer of vulva",
            "checked": False,
        },
    ]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    assert result["complete"] is True
    assert "B1" in result["matched_groups"][0]["matched_member_names"]


def test_kind_aliases_resolve_and_honour_min_count() -> None:
    assert resolve_kind({"kind": "at_least_one"}) == "one_of"
    assert resolve_kind({"kind": "required_section"}) == "n_of"
    assert resolve_kind({"kind": "recommended_section"}) == "optional"
    schema = [
        {
            "name": "symptoms",
            "kind": "at_least_one",
            "min_count": 1,
            "members": [
                {"name": "B1", "section_id": "B", "item_pattern": "B1."},
                {"name": "B2", "section_id": "B", "item_pattern": "B2."},
            ],
        }
    ]
    one = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=[
            {
                "section_id": "B",
                "item_pattern": "B1.",
                "entity_text": "B1",
                "checked": True,
            }
        ],
    )
    assert one["complete"] is True


def test_empty_leaf_is_not_assessable_and_degrades_required_group() -> None:
    schema = [{"name": "Empty required", "required": True, "concept_ids": []}]
    result = evaluate_completeness_groups(
        schema,
        present_concept_ids=set(),
        present_semantic_tags=set(),
    )
    assert result["complete"] is False
    assert result["degraded"] is True
    row = result["missing_groups"][0]
    assert row["outcome"] == "not_assessable"
    assert row["matched"] is False


def test_chunk_load_payload_keeps_section_hits() -> None:
    from libs.pipeline_graph.subgraphs.extraction import _chunk_load_payload

    hits = [
        {
            "section_id": "section_a_2ww_symptoms",
            "item_pattern": "A1.",
            "entity_text": "Newly presenting discrete hard breast lump",
            "checked": True,
        }
    ]
    payload = _chunk_load_payload(
        {
            "encounter_text": "Section A",
            "sentences": [{"sentence_id": "c1", "text": "Section A"}],
            "form_schema_match": "org_service",
            "form_schema_fingerprint": "sfh-breast-2ww-v1",
            "form_schema_label": "Breast Unit",
            "section_hits": hits,
        },
        [],
    )
    assert payload["section_hits"] == hits


def test_free_text_examination_emits_hit_and_matches_group() -> None:
    exam = FormSection(
        section_id="section_b_examination",
        section_type="free_text",
        label="Section B: Examination",
        start_pattern=r"(?i)section\s+b",
        items=[
            FormSchemaItem(
                pattern="Affected side",
                entity_text="Breast examination findings",
            )
        ],
    )
    schema = FormSchema(
        schema_id="breast-exam",
        fingerprint="exam",
        form_name="Breast exam",
        sections=[exam],
        created_by="test",
    )
    letter = (
        "Section B: Examination\n"
        "Affected side: left. 1cm hard lump, mildly tender.\n"
    )
    hits = collect_section_hits(schema, [letter])
    assert any(
        h["section_id"] == "section_b_examination" and h["checked"] is True
        for h in hits
    )
    result = evaluate_completeness_groups(
        [
            {
                "name": "examination_present",
                "kind": "recommended_section",
                "required": False,
                "min_count": 1,
                "members": [{"section_id": "section_b_examination"}],
            }
        ],
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    assert result["complete"] is True
    assert result["matched_groups"][0]["name"] == "examination_present"


def test_breast_ticked_a1_matches_two_ww_group() -> None:
    import sys
    from pathlib import Path

    from libs.pipeline.form_schema_request import (
        build_sections_from_request,
        normalize_sections_for_request,
    )

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from seed_sfh_breast_2ww_template import (  # noqa: E402
        build_completeness_groups,
        build_payload,
    )

    payload = build_payload()
    sections = build_sections_from_request(
        normalize_sections_for_request(payload["sections"])
    )
    schema = FormSchema(
        schema_id="breast-2ww",
        fingerprint="sfh-breast-2ww-v1",
        form_name=payload["form_name"],
        sections=sections,
        created_by="test",
    )
    letter = (
        "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
        "| A1. Newly presenting discrete hard lump | Yes [X] |\n"
        "| Section B: Examination |\n"
        "| Affected side left. 1cm hard lump, mildly tender. |\n"
    )
    hits = collect_section_hits(schema, [letter])
    result = evaluate_completeness_groups(
        build_completeness_groups(),
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    names = {row["name"] for row in result["matched_groups"]}
    assert "two_ww_criterion_required" in names
    assert "examination_present" in names
    assert result["complete"] is True
    assert result["degraded"] is False


def test_gynae_ticked_cervix_and_b1_satisfies_completeness_groups() -> None:
    """Ticked Section A (cancer type) and Section B (symptom) both satisfy their groups.

    This is the regression test for the item_pattern mismatch between the
    FormSchema section items and the completeness group members. The hit stores
    the FormSchemaItem.pattern verbatim; the group member item_pattern must use
    the same string so _hit_belongs matches by exact comparison.

    DI: DI-50BE367C  DO: DO-85BBD932
    """
    import json
    import sys
    from pathlib import Path

    from libs.pipeline.form_schema_request import (
        build_sections_from_request,
        normalize_sections_for_request,
    )

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from seed_sfh_gynae_2ww_template import (  # noqa: E402
        build_completeness_groups,
    )

    fixture = (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"
    )
    payload = json.loads(fixture.read_text())
    sections = build_sections_from_request(
        normalize_sections_for_request(payload["sections"])
    )
    schema = FormSchema(
        schema_id="gynae-2ww",
        fingerprint="sfh-gynae-2ww-v1",
        form_name=payload["form_name"],
        sections=sections,
        created_by="test",
    )
    letter = (
        "Section A: Gynaecological Cancer type suspected\n"
        "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
        "Section B: Signs/symptoms for 14-day rule criteria\n"
        "B1. Lesion suspicious of cancer of cervix or vagina on speculum examination"
        " | Yes [X] No [ ]\n"
    )
    hits = collect_section_hits(schema, [letter])
    result = evaluate_completeness_groups(
        build_completeness_groups(),
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=hits,
    )
    names = {row["name"] for row in result["matched_groups"]}
    assert "cancer_type_required" in names, (
        f"Section A tick must satisfy cancer_type_required; matched={names}"
    )
    assert "symptom_criterion_required" in names, (
        "Section B B1 tick must satisfy symptom_criterion_required -- "
        "check that item_pattern in the fixture matches the completeness group member"
    )
    assert result["complete"] is True
    assert result["degraded"] is False


def test_rebind_carries_completeness_groups() -> None:
    from libs.pipeline.form_schema_store import (
        FormSchemaWrite,
        rebind_form_schema_ids,
        reset_schema_cache,
    )

    reset_schema_cache()
    existing = FormSchema(
        schema_id="sid",
        fingerprint="fp-rebind",
        form_name="Test",
        sections=[_SECTION_A],
        created_by="old",
        organization_id="old-org",
        service_id="old-svc",
    )
    groups = [
        {
            "name": "cancer_type_required",
            "kind": "required_section",
            "members": [{"section_id": "section_a_cancer_type"}],
        }
    ]
    write = FormSchemaWrite(
        fingerprint="fp-rebind",
        form_name="Test",
        sections=[],
        created_by="seed",
        organization_id="RK5",
        service_id="7980224",
        completeness_groups=groups,
    )
    with patch(
        "libs.pipeline.form_schema_store.load_form_schema",
        return_value=existing,
    ):
        with patch("libs.pipeline.form_schema_store.save_form_schema") as mock_save:
            action = rebind_form_schema_ids(MagicMock(), write)
    assert action == "updated"
    saved = mock_save.call_args.args[1]
    assert saved.completeness_groups == groups
    assert saved.organization_id == "RK5"
