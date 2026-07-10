from __future__ import annotations

import pytest

from app.routers.training_synthetic_data import (
    _has_absent_evidence,
    _is_invalid_observable_assertion,
    _is_mismatched_semantic_sentence,
    _is_speculative_or_educational,
)


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (
            "If symptoms worsen, AMY may rise above 500 U/L warranting further review.",
            True,
        ),
        (
            "AST could be elevated, possibly around 90 U/L, given the clinical picture.",
            True,
        ),
        ("An abnormal ABPI could suggest significant arterial stenosis.", True),
        ("AMY was 145 U/L, trending down from peak of 780 U/L.", False),
        ("AST recorded at 27 U/L, which is within the reference range.", False),
        ("ALT returned at 1200 U/L, significantly above upper limit of normal.", False),
    ],
)
def test_speculative_detector(sentence: str, expected: bool) -> None:
    assert _is_speculative_or_educational(sentence) is expected


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("No evidence of cauda equina syndrome on this scan.", True),
        ("Patient denies chest pain today.", True),
        ("Cauda equina syndrome documented on admission.", False),
    ],
)
def test_absent_evidence_detector(sentence: str, expected: bool) -> None:
    assert _has_absent_evidence(sentence) is expected


@pytest.mark.parametrize(
    ("semantic_tag", "assertion", "expected"),
    [
        ("observable_entity", "planned", True),
        ("observable_entity", "present", False),
        ("procedure", "planned", False),
        ("finding", "planned", False),
    ],
)
def test_invalid_observable_assertion(
    semantic_tag: str,
    assertion: str,
    expected: bool,
) -> None:
    assert _is_invalid_observable_assertion(semantic_tag, assertion) is expected


@pytest.mark.parametrize(
    ("semantic_tag", "sentence", "expected"),
    [
        ("disorder", "Alb to be rechecked next week.", True),
        ("finding", "Urgent referral arranged to colorectal clinic.", True),
        ("procedure", "Urgent referral arranged to colorectal clinic.", False),
        ("disorder", "Cauda equina syndrome remains active today.", False),
    ],
)
def test_mismatched_semantic_sentence(
    semantic_tag: str,
    sentence: str,
    expected: bool,
) -> None:
    assert _is_mismatched_semantic_sentence(semantic_tag, sentence) is expected
