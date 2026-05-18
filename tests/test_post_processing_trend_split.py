from __future__ import annotations

from libs.pipeline.post_processing import run_post_processing


def test_now_marker_overrides_pre_marker_value_through_full_pipeline():
    # "weight loss 10kg - now 79kg": the 10kg is a delta (weight change), so
    # only the post-"now" value (79kg) should reach the observable's
    # value/unit fields after the full post-processing stack runs.
    encounter = "weight loss 10kg - now 79kg"
    entities = [
        {
            "text": encounter,
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "assertion": "present",
            "value": "10",
            "unit": "kg",
        }
    ]

    processed = run_post_processing(encounter, entities, enable_disorder_gate=False)
    observables = [e for e in processed if str(e.get("label")) == "observable_entity"]

    assert len(observables) == 1
    obs = observables[0]
    assert str(obs.get("value")) == "79"
    assert str(obs.get("unit")).lower() == "kg"
    assert obs.get("text") == "weight loss 10kg"


def test_splits_observable_into_present_and_historical_values():
    encounter = "AMY on discharge was 145 U/L, trending down from peak of 780 U/L."
    start = encounter.find("AMY")
    entities = [
        {
            "text": "AMY",
            "label": "observable_entity",
            "start": start,
            "end": start + 3,
            "assertion": "present",
        }
    ]

    processed = run_post_processing(encounter, entities, enable_disorder_gate=False)
    observables = [e for e in processed if str(e.get("label")) == "observable_entity"]

    assert len(observables) == 2
    current = next(e for e in observables if e.get("assertion") == "present")
    historical = next(e for e in observables if e.get("assertion") == "historical")

    assert str(current.get("value")) == "145"
    assert str(current.get("unit")).lower() == "u/l"
    assert str(historical.get("value")) == "780"
    assert str(historical.get("unit")).lower() == "u/l"
