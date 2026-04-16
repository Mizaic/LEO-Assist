"""Regression checks for label verification prompt policy text."""

from __future__ import annotations

from libs.prompts.label_verification_examples import LABEL_VERIFICATION_EXAMPLES
from libs.prompts.label_verification_v2 import LABEL_VERIFICATION_V2


def _example_by_description(description: str) -> dict:
    for example in LABEL_VERIFICATION_EXAMPLES:
        if example.get("description") == description:
            return example
    raise AssertionError(f"Missing example: {description}")


def test_prompt_preserves_procedure_semantics_across_status_contexts():
    assert "planned / pending / historical / absent / hypothetical" in (
        LABEL_VERIFICATION_V2
    )
    assert "do NOT relabel a procedure noun to situation solely because it has not happened yet" in (
        LABEL_VERIFICATION_V2
    )
    assert "2WW referral" in LABEL_VERIFICATION_V2
    assert "preserve existing gold annotation" in LABEL_VERIFICATION_V2


def test_prompt_narrows_regime_therapy_to_explicit_regimens():
    assert (
        '"chemo" / "chemotherapy" / "HRT" / "radiotherapy" in ordinary treatment context usually -> procedure'
        in LABEL_VERIFICATION_V2
    )
    assert 'use regime_therapy only when the span clearly names a regimen/course/category rather than the treatment act itself (for example "CHOP regimen")' in (
        LABEL_VERIFICATION_V2
    )


def test_examples_align_with_completed_gold_policy():
    planned_proc = _example_by_description("Planned colonoscopy keeps procedure label")
    assert '"suggested_label": "procedure"' in planned_proc["output"]
    assert "procedure_status_preserved" in planned_proc["output"]

    dual_label = _example_by_description(
        "2WW referral preserves intentional dual labels"
    )
    assert dual_label["output"].count('"suggested_label": "procedure"') == 1
    assert dual_label["output"].count('"suggested_label": "situation"') == 1
    assert "preserve_existing_multilabel" in dual_label["output"]

    regimen = _example_by_description("Named regimen stays regime_therapy")
    assert '"text": "CHOP regimen"' in regimen["input"]
    assert '"suggested_label": "regime_therapy"' in regimen["output"]


def test_examples_no_longer_teach_old_boundary_policy():
    descriptions = {example.get("description") for example in LABEL_VERIFICATION_EXAMPLES}
    assert "Chemo shorthand - regime_therapy not substance" not in descriptions
    assert "Planned procedure on waiting list - situation not procedure" not in descriptions
