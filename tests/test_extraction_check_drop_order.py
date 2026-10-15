"""Extraction check corrections land on the fact the model named.

The model numbers facts as it was shown them. When it also drops a fact,
its corrections and relation edits must still use that numbering, and
relations must follow their targets to their new places once facts are
removed. Before this fix, a drop shifted every later correction onto the
next fact, so a present fact could be marked absent.

Atlas trace:
  DO: DO-8620A68B
"""

from __future__ import annotations

from libs.pipeline_graph.subgraphs.llm_check import _apply_extraction_check

TEXT = "noise. cough. FIT result."


def _facts() -> list[dict]:
    return [
        {"text": "noise", "label": "finding", "assertion": "present"},
        {"text": "cough", "label": "disorder", "assertion": "present"},
        {"text": "FIT result", "label": "observable entity", "assertion": "present"},
    ]


def _apply(result: dict, facts: list[dict] | None = None) -> list[dict]:
    full = {
        "drop": [],
        "correct_assertion": [],
        "correct_label": [],
        "add": [],
        **result,
    }
    state = {
        "entities": facts or _facts(),
        "llm_check_result": full,
        "encounter_text": TEXT,
    }
    return _apply_extraction_check(state)["entities"]


def _by_text(entities: list[dict]) -> dict[str, dict]:
    return {e["text"]: e for e in entities}


def test_an_assertion_correction_lands_on_the_fact_the_model_named():
    out = _by_text(
        _apply(
            {"drop": [0], "correct_assertion": [{"index": 1, "assertion": "absent"}]}
        )
    )
    assert out["cough"]["assertion"] == "absent"
    assert out["FIT result"]["assertion"] == "present"


def test_a_label_correction_lands_on_the_fact_the_model_named():
    out = _by_text(
        _apply({"drop": [0], "correct_label": [{"index": 1, "label": "finding"}]})
    )
    assert out["cough"]["label"] == "finding"
    assert out["FIT result"]["label"] == "observable entity"


def test_a_correction_for_a_dropped_fact_changes_nothing_else():
    out = _by_text(
        _apply(
            {
                "drop": [0],
                "correct_label": [{"index": 0, "label": "procedure"}],
                "correct_assertion": [{"index": 0, "assertion": "absent"}],
            }
        )
    )
    assert set(out) == {"cough", "FIT result"}
    assert out["cough"]["label"] == "disorder"
    assert out["cough"]["assertion"] == "present"


def test_a_new_relation_uses_the_models_numbering():
    out = _apply(
        {
            "drop": [0],
            "add_relation": [
                {
                    "index": 1,
                    "type": "finding_site",
                    "target_idx": 2,
                    "target_text": "x",
                }
            ],
        }
    )
    cough = _by_text(out)["cough"]
    targets = [out[r["target_idx"]]["text"] for r in cough["__relations"]]
    assert targets == ["FIT result"]


def test_an_existing_relation_follows_its_target_after_a_drop():
    facts = _facts()
    facts[2]["__relations"] = [
        {"type": "finding_site", "target_idx": 1, "target_text": "cough"}
    ]
    out = _apply({"drop": [0]}, facts)
    fit = _by_text(out)["FIT result"]
    assert [out[r["target_idx"]]["text"] for r in fit["__relations"]] == ["cough"]


def test_a_relation_to_a_dropped_fact_is_removed():
    facts = _facts()
    facts[1]["__relations"] = [
        {"type": "finding_site", "target_idx": 0, "target_text": "noise"}
    ]
    out = _apply({"drop": [0]}, facts)
    assert _by_text(out)["cough"]["__relations"] == []
