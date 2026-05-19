"""Load and score clinical extraction scenario fixtures."""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

_FIXTURE_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "fixtures"
    / "clinical_extraction_scenarios"
)
_TERMINAL_PUNCTUATION = ".,;:"


def fixture_dir() -> pathlib.Path:
    """Return the clinical extraction scenario fixture directory."""
    return _FIXTURE_DIR


def load_expected_strings() -> dict[str, Any]:
    """Return the expected-string fixture document."""
    path = _FIXTURE_DIR / "expected_strings.json"
    return json.loads(path.read_text(encoding="utf-8"))


def iter_cases() -> list[dict[str, Any]]:
    """Return clinical extraction scenario case rows."""
    return load_expected_strings()["cases"]


def normalise_phrase(value: str, rules: dict[str, bool]) -> str:
    """Apply only explicitly enabled raw-surface matching rules."""
    phrase = value.casefold() if rules.get("casefold") else value
    if rules.get("trim"):
        phrase = phrase.strip()
    if rules.get("collapse_whitespace"):
        phrase = re.sub(r"\s+", " ", phrase)
    if rules.get("strip_terminal_punctuation"):
        phrase = phrase.rstrip(_TERMINAL_PUNCTUATION)
    return phrase


def _normalised_set(values: list[str], rules: dict[str, bool]) -> set[str]:
    return {normalise_phrase(value, rules) for value in values}


def _metric(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _f1(precision: float, recall: float) -> float:
    denominator = precision + recall
    return 2 * precision * recall / denominator if denominator else 0.0


def score_case(
    case: dict[str, Any], extracted_strings: list[str], rules: dict[str, bool]
) -> dict[str, Any]:
    """Score one case against raw extracted ``terms[].text`` strings."""
    expected = _normalised_set(case["expected_strings"], rules)
    extracted = _normalised_set(extracted_strings, rules)
    true_positive = expected & extracted
    extra = extracted - expected
    missed = expected - extracted
    precision = _metric(len(true_positive), len(extracted))
    recall = _metric(len(true_positive), len(expected))
    return {
        "case_id": case["case_id"],
        "true_positive": len(true_positive),
        "false_positive": len(extra),
        "false_negative": len(missed),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "missed_strings": sorted(missed),
        "extra_strings": sorted(extra),
    }


def score_extraction_cases(
    cases: list[dict[str, Any]],
    extracted_by_case: dict[str, list[str]],
    rules: dict[str, bool],
) -> dict[str, Any]:
    """Score all cases and return aggregate phrase-level metrics."""
    by_case = [
        score_case(case, extracted_by_case.get(case["case_id"], []), rules)
        for case in cases
    ]
    tp = sum(row["true_positive"] for row in by_case)
    fp = sum(row["false_positive"] for row in by_case)
    fn = sum(row["false_negative"] for row in by_case)
    precision = _metric(tp, tp + fp)
    recall = _metric(tp, tp + fn)
    return {
        "overall": {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
        },
        "by_case": by_case,
    }
