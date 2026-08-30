"""Missing-FIT list filter for ICB teams.

Atlas: DI-55CCC312
"""

from __future__ import annotations

from libs.guidelines.missing_fit_list import in_missing_fit_list


def test_required_missing_is_on_the_list() -> None:
    assert in_missing_fit_list(
        [
            {
                "investigation_policy": "required",
                "investigation_status": "missing",
            }
        ]
    )


def test_required_with_fit_result_is_off_the_list() -> None:
    assert not in_missing_fit_list(
        [
            {
                "investigation_policy": "required",
                "investigation_status": "offered_or_resulted",
            }
        ]
    )


def test_mass_bypass_not_required_is_off_the_list() -> None:
    assert not in_missing_fit_list(
        [
            {
                "investigation_policy": "not_required",
                "investigation_status": "exempt",
            }
        ]
    )


def test_required_and_mass_together_are_off_the_list() -> None:
    assert not in_missing_fit_list(
        [
            {
                "investigation_policy": "required",
                "investigation_status": "missing",
            },
            {
                "investigation_policy": "not_required",
                "investigation_status": "exempt",
            },
        ]
    )
