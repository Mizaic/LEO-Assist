import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "services" / "api"))

from app.services.test_patient_scaffolder import ScaffoldError  # noqa: E402
from app.services.test_patient_scaffolder import _assert_triggers_in_text  # noqa: E402
from app.services.test_patient_scaffolder import _validate_encounters  # noqa: E402
from app.services.test_patient_scaffolder import load_rule_for_scaffold  # noqa: E402


class FakeClient:
    def run(self, _query: str, **_params: object) -> list[dict]:
        return [
            {
                "rule_id": "rule-1",
                "rule_name": "Saved rule",
                "logic_json": json.dumps(
                    {
                        "kind": "CONCEPT",
                        "criterion": {
                            "snomed_concept_id": "old",
                            "preferred_term": "Old trigger",
                        },
                    }
                ),
                "demographic_constraints": [],
            }
        ]


def test_trigger_validation_accepts_uk_spelling_variants() -> None:
    encounters = [
        {
            "text": (
                "Blood tests show iron deficiency anaemia. "
                "The patient needs guideline review."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "87522002",
            "preferred_term": "Iron deficiency anemia (disorder)",
        }
    ]

    _assert_triggers_in_text(encounters, triggers)


def test_trigger_validation_accepts_diarrhoea_for_diarrhea_trigger() -> None:
    encounters = [
        {
            "text": (
                "3 week history of loose stools and diarrhoea. "
                "No rectal bleeding. Plan FIT test."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "62315008",
            "preferred_term": "Diarrhea (finding)",
        }
    ]

    _assert_triggers_in_text(encounters, triggers)


def test_trigger_validation_accepts_haematuria_for_hematuria_trigger() -> None:
    encounters = [
        {
            "text": (
                "68yo male. Painless visible haematuria for 3 weeks. "
                "No dysuria. MSU sent."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "34436003",
            "preferred_term": "Hematuria (finding)",
        }
    ]

    _assert_triggers_in_text(encounters, triggers)


def test_trigger_validation_accepts_weight_loss_for_weight_decreased() -> None:
    encounters = [
        {
            "text": (
                "58yo male. Reports unintentional weight loss over 6 weeks. "
                "No rectal bleeding. FIT kit issued today."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "262285001",
            "preferred_term": "Weight decreased (finding)",
        }
    ]

    _assert_triggers_in_text(encounters, triggers)


def test_validate_encounters_attaches_weight_code_from_weight_loss_note() -> None:
    encounters = [
        {
            "text": (
                "Patient reports losing weight over the past two months. "
                "Appetite reduced but no dysphagia."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "262285001",
            "preferred_term": "Weight decreased (finding)",
        }
    ]

    cleaned = _validate_encounters(encounters, triggers)

    assert cleaned[0]["codes"] == [
        {
            "concept_id": "262285001",
            "term": "Weight decreased (finding)",
            "assertion": "present",
        }
    ]


def test_trigger_validation_accepts_dyspnoea_for_dyspnea_trigger() -> None:
    encounters = [
        {
            "text": (
                "62yo ex smoker. 6 week history of progressive dyspnoea on "
                "exertion. No haemoptysis."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "267036007",
            "preferred_term": "Dyspnea (finding)",
        }
    ]

    _assert_triggers_in_text(encounters, triggers)


def test_trigger_validation_accepts_breathlessness_for_dyspnea_trigger() -> None:
    encounters = [
        {
            "text": (
                "Patient reports increasing breathlessness when climbing stairs. "
                "CXR arranged."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "267036007",
            "preferred_term": "Dyspnea (finding)",
        }
    ]

    _assert_triggers_in_text(encounters, triggers)


def test_validate_encounters_attaches_codes_to_matching_notes() -> None:
    encounters = [
        {
            "text": (
                "Patient reports tiredness. Bloods requested today. "
                "Review planned once results return."
            )
        },
        {
            "text": (
                "Blood tests show iron deficiency anaemia. "
                "FIT testing discussed and kit provided."
            )
        },
    ]
    triggers = [
        {
            "concept_id": "87522002",
            "preferred_term": "Iron deficiency anemia (disorder)",
        }
    ]

    cleaned = _validate_encounters(encounters, triggers)

    assert cleaned[0]["codes"] == []
    assert cleaned[1]["codes"] == [
        {
            "concept_id": "87522002",
            "term": "Iron deficiency anemia (disorder)",
            "assertion": "present",
        }
    ]


def test_validate_encounters_rejects_indirect_trigger_mentions() -> None:
    encounters = [
        {
            "text": (
                "Patient has blood tests consistent with low iron stores. "
                "Plan is to investigate possible bowel cause."
            )
        }
    ]
    triggers = [
        {
            "concept_id": "87522002",
            "preferred_term": "Iron deficiency anemia (disorder)",
        }
    ]

    with pytest.raises(ScaffoldError, match="did not mention every trigger"):
        _validate_encounters(encounters, triggers)


def test_load_rule_for_scaffold_uses_unsaved_draft_logic_tree() -> None:
    draft_rule = {
        "name": "Draft rule",
        "logic_tree": {
            "kind": "AND",
            "children": [
                {
                    "kind": "CONCEPT",
                    "criterion": {
                        "snomed_concept_id": "new",
                        "preferred_term": "New trigger",
                    },
                },
                {
                    "kind": "DEMOGRAPHIC",
                    "field": "age",
                    "operator": "<",
                    "value": 50,
                    "unit": "years",
                },
            ],
        },
    }

    row = load_rule_for_scaffold(FakeClient(), rule_id="rule-1", draft_rule=draft_rule)

    assert row["rule_name"] == "Draft rule"
    assert [trigger["concept_id"] for trigger in row["triggers"]] == ["new"]
    assert row["demographic_constraints"] == [
        {"field": "age", "operator": "<", "value": 50, "unit": "years"}
    ]
