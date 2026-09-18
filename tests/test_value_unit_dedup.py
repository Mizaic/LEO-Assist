"""A unit that has been read into an observable is not a fact of its own.

Referral 000482029135 coded 54 facts, and nine of them were units of
measure: "Kilounit/liter", "Micromole/liter", "Beats/minute". The CA 125
observable already carried unit "ku/L", so "Kilounit/liter" was the same
information written twice -- once where a reader can use it, once as a
standalone claim about the patient.

Layer 5 reads the "6 ku/L" span to fill the observable, then leaves the
span in the list, so it goes on to be resolved and coded. Nothing is lost
by dropping it: the unit is on the observable.

Rule: .cursor/rules/architecture-first.mdc -- fix the layer that owns
value-unit linking rather than filtering qualifier codes further down.
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.post_processing import (
    link_observable_value_units,
    run_post_processing_with_trace,
)


def _ca125_row() -> list[dict[str, Any]]:
    """The real shape from the CA 125 table row on that referral."""
    return [
        {
            "label": "observable_entity",
            "text": "CA 125",
            "start": 0,
            "end": 6,
            "value": None,
            "unit": None,
        },
        {
            "label": "qualifier_value",
            "text": "6 ku/L",
            "start": 9,
            "end": 15,
        },
    ]


def test_the_observable_still_gets_its_value_and_unit() -> None:
    entities = _ca125_row()
    link_observable_value_units(entities)
    assert entities[0]["value"] == "6"
    assert entities[0]["unit"] == "ku/L"


def test_the_unit_it_read_is_not_coded_as_a_second_fact() -> None:
    entities = _ca125_row()
    link_observable_value_units(entities)
    assert entities[1].get("__suppress__") is True


def test_a_unit_nobody_read_is_left_alone() -> None:
    """Suppression follows absorption. An orphan span keeps its chance."""
    entities = [
        {
            "label": "qualifier_value",
            "text": "6 ku/L",
            "start": 9,
            "end": 15,
        },
    ]
    link_observable_value_units(entities)
    assert entities[0].get("__suppress__") is not True


def test_a_span_saying_what_the_observable_already_says_is_dropped() -> None:
    """The live case. An earlier layer fills the observable from raw text, so
    linking skips it, and the bare span is left to be coded on its own."""
    entities = _ca125_row()
    entities[0]["value"] = "6"
    entities[0]["unit"] = "ku/L"
    link_observable_value_units(entities)
    assert entities[1].get("__suppress__") is True


def test_a_different_reading_nearby_is_kept() -> None:
    """Only a span that repeats the observable goes. A second, different
    reading is new information and must survive."""
    entities = _ca125_row()
    entities[0]["value"] = "6"
    entities[0]["unit"] = "ku/L"
    entities[1]["text"] = "38 ku/L"
    link_observable_value_units(entities)
    assert entities[1].get("__suppress__") is not True


def test_the_whole_pipeline_does_not_record_the_unit_as_a_fact() -> None:
    """End to end, because layer 5 is where the drop has to happen: the only
    other layer that acts on the flag is the optional disorder gate."""
    entities = [
        {
            "text": "CA 125",
            "label": "observable_entity",
            "start": 17,
            "end": 23,
            "assertion": "present",
            "value": None,
            "unit": None,
        },
        {
            "text": "6 ku/L",
            "label": "qualifier_value",
            "start": 26,
            "end": 32,
            "assertion": "present",
        },
    ]
    kept, _trace = run_post_processing_with_trace(
        "Bloods this week: CA 125 6 ku/L (normal range).",
        entities,
        enable_disorder_gate=False,
    )
    labels = [str(e.get("label")) for e in kept]
    assert "qualifier_value" not in labels
    obs = [e for e in kept if e.get("label") == "observable_entity"]
    assert len(obs) == 1
    assert obs[0].get("unit") == "ku/L"


def test_a_word_result_stays_a_fact_in_its_own_right() -> None:
    """Pass 2 reads words, not units. "Positive" can carry clinical meaning
    on its own, so absorbing it as a value must not delete it."""
    entities = [
        {
            "label": "observable_entity",
            "text": "FIT",
            "start": 0,
            "end": 3,
            "value": None,
        },
        {"label": "finding", "text": "positive", "start": 6, "end": 14},
    ]
    link_observable_value_units(entities)
    assert entities[1].get("__suppress__") is not True
