"""Finding and disorder dates use the shared observation-date helper.

Atlas: DI-0BB36B4D
"""

from __future__ import annotations

from libs.pipeline.observation_date import assign_finding_observed_at


def test_one_date_on_finding_line_is_stored() -> None:
    text = "Fracture of humerus 12 Mar 2019 after a fall."
    entities = [
        {
            "text": "Fracture of humerus",
            "label": "disorder",
            "start": 0,
            "end": 19,
        }
    ]
    out = assign_finding_observed_at(text, entities)
    assert out[0]["observed_at"] == "2019-03-12"


def test_two_dates_on_finding_line_are_not_guessed() -> None:
    text = "Fracture of humerus 12 Mar 2019, reviewed 04 Jan 2024."
    entities = [
        {
            "text": "Fracture of humerus",
            "label": "disorder",
            "start": 0,
            "end": 19,
        }
    ]
    out = assign_finding_observed_at(text, entities)
    assert "observed_at" not in out[0]


def test_existing_observed_at_is_not_overwritten() -> None:
    text = "Fracture of humerus 12 Mar 2019 after a fall."
    entities = [
        {
            "text": "Fracture of humerus",
            "label": "disorder",
            "start": 0,
            "end": 19,
            "observed_at": "2018-01-01",
        }
    ]
    out = assign_finding_observed_at(text, entities)
    assert out[0]["observed_at"] == "2018-01-01"
