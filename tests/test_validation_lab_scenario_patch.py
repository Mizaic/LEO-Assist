"""Tests for ScenarioPatch / ScenarioVariant verification.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _base_patch(**overrides):
    data = {
        "title": "Fragility fracture age branch",
        "patientName": "Pat Example",
        "patientAge": "68",
        "patientSex": "female",
        "caseType": "referral",
        "pmh": [
            {
                "category": "condition",
                "conceptId": "123",
                "term": "Osteoporosis",
            }
        ],
        "observations": [{"observableId": "100", "value": 412.0, "unit": "u/mL"}],
        "referralText": "Referral text",
        "equity": {
            "ethnicityConceptId": "976631000000101",
            "ethnicityTerm": "White British",
            "performanceStatusGrade": 1,
            "comorbidityBand": "low",
            "core20Decile": 2,
            "plusGroup": "none",
        },
    }
    data.update(overrides)
    return data


def test_valid_patch_accepts() -> None:
    from libs.validation_lab.scenario_patch import ScenarioPatch

    patch = ScenarioPatch.model_validate(_base_patch())
    assert patch.patientAge == "68"
    assert patch.observations and patch.observations[0].observableId == "100"


def test_unknown_equity_ethnicity_stripped() -> None:
    from libs.validation_lab.scenario_patch import verify_patch

    raw = _base_patch()
    raw["equity"]["ethnicityConceptId"] = "999999999"
    cleaned = verify_patch(raw, seen_concepts={"123": {}}, seen_observables={"100"})
    assert "ethnicityConceptId" not in (cleaned.get("equity") or {})
    assert cleaned.get("patientAge") == "68"


def test_unverified_observation_dropped() -> None:
    from libs.validation_lab.scenario_patch import verify_patch

    raw = _base_patch()
    cleaned = verify_patch(raw, seen_concepts={"123": {}}, seen_observables=set())
    assert cleaned.get("observations") == []


def test_empty_pmh_concept_id_dropped() -> None:
    from libs.validation_lab.scenario_patch import verify_patch

    raw = _base_patch(pmh=[{"category": "condition", "conceptId": "", "term": "x"}])
    cleaned = verify_patch(raw, seen_concepts={}, seen_observables={"100"})
    assert cleaned.get("pmh") == []


def test_case_type_ag_rejected() -> None:
    from libs.validation_lab.scenario_patch import ScenarioPatch

    with pytest.raises(ValidationError):
        ScenarioPatch.model_validate(_base_patch(caseType="ag"))


def test_normalise_variants_caps_positive_and_sets_recommended() -> None:
    from libs.validation_lab.scenario_patch import normalise_variants

    variants = [
        {
            "variantId": f"v{i}",
            "label": f"V{i}",
            "rationale": "r",
            "recommended": False,
            "triggerConceptIds": [],
            "isControl": False,
            "expectedTrigger": True,
        }
        for i in range(6)
    ]
    out = normalise_variants(variants, rule_evaluated=False)
    assert len(out) == 5
    assert sum(1 for v in out if v["recommended"]) == 1
    assert out[0]["recommended"] is True
    assert all(v["expectedTrigger"] is None for v in out)


def test_normalise_variants_keeps_one_control() -> None:
    from libs.validation_lab.scenario_patch import normalise_variants

    variants = [
        {
            "variantId": "p1",
            "label": "P",
            "rationale": "r",
            "recommended": True,
            "triggerConceptIds": [],
            "isControl": False,
            "expectedTrigger": None,
        },
        {
            "variantId": "c1",
            "label": "C1",
            "rationale": "r",
            "recommended": True,
            "triggerConceptIds": [],
            "isControl": True,
            "expectedTrigger": None,
        },
        {
            "variantId": "c2",
            "label": "C2",
            "rationale": "r",
            "recommended": False,
            "triggerConceptIds": [],
            "isControl": True,
            "expectedTrigger": None,
        },
    ]
    out = normalise_variants(variants, rule_evaluated=False)
    controls = [v for v in out if v["isControl"]]
    assert len(controls) == 1
    assert controls[0]["recommended"] is False


def test_normalise_variants_caps_three_per_target_rec() -> None:
    from libs.validation_lab.scenario_patch import normalise_variants

    variants = [
        {
            "variantId": f"v{i}",
            "targetRecId": f"rec-{i % 3}",
            "label": f"V{i}",
            "rationale": "r",
            "recommended": False,
            "triggerConceptIds": [],
            "isControl": False,
            "expectedTrigger": None,
        }
        for i in range(12)
    ]
    out = normalise_variants(variants, rule_evaluated=False)
    positives = [v for v in out if not v["isControl"]]
    assert len(positives) == 9
    for rec_id in ("rec-0", "rec-1", "rec-2"):
        group = [v for v in positives if v["targetRecId"] == rec_id]
        assert len(group) == 3
        assert sum(1 for v in group if v["recommended"]) == 1


def test_coerce_snake_case_variants_get_stable_ids_and_labels() -> None:
    from libs.validation_lab.scenario_patch import normalise_variants

    out = normalise_variants(
        [
            {
                "variant_id": "",
                "patient_age": 68,
                "patient_sex": "female",
                "is_control": False,
                "recommended": False,
                "referral_text": "Dear colleague...",
            },
            {
                "name": "Control under 45",
                "is_control": True,
                "patient_age": 30,
            },
        ],
        rule_evaluated=False,
    )
    assert out[0]["variantId"] == "variant-1"
    assert out[0]["title"].startswith("Dear colleague")
    assert out[0]["summary"].startswith("Dear colleague")
    assert "female" in out[0]["tags"]
    assert out[0]["patientAge"] == "68"
    assert out[0]["rationale"]
    assert out[1]["isControl"] is True
    assert out[1]["label"] == "Control under 45"
    assert out[1]["recommended"] is False


def test_coerce_rejects_placeholder_title_and_keeps_catalog_fields() -> None:
    from libs.validation_lab.scenario_patch import coerce_variant_wire

    out = coerce_variant_wire(
        {
            "title": "Variant 3",
            "label": "Variant 3",
            "summary": "Age 68 with raised CA125 in Core20 decile 2.",
            "tags": ["CA125", "2WW", "Core20"],
            "rationale": "Should fire CA125 threshold.",
            "equity": {"core20Decile": 2, "plusGroup": "none"},
        },
        index=2,
    )
    assert out["title"] == "Age 68 with raised CA125 in Core20 decile 2."
    assert out["summary"].startswith("Age 68")
    assert "CA125" in out["tags"]
    assert "Core20-2" in out["tags"]
