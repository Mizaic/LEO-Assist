from __future__ import annotations

from libs.pipeline.post_processing import run_post_processing


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
