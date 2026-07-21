"""Load and score clinical extraction scenario fixtures.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Any

_DEFAULT_FIXTURE_DIR = (
    pathlib.Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "clinical_extraction_scenarios"
)
_TERMINAL_PUNCTUATION = ".,;:"


def fixture_dir() -> pathlib.Path:
    """Return the clinical extraction scenario fixture directory."""
    configured = os.getenv("CLINICAL_EXTRACTION_SCENARIO_DIR", "").strip()
    return pathlib.Path(configured) if configured else _DEFAULT_FIXTURE_DIR


def load_expected_strings() -> dict[str, Any]:
    """Return the expected-string fixture document."""
    path = fixture_dir() / "expected_strings.json"
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


_MIN_CONTAINMENT_LEN = 3
_CLINICAL_FINDING_FAMILY = frozenset(
    {
        "finding",
        "disorder",
        "situation",
        "morphologic_abnormality",
    }
)


def _tags_compatible(expected_tag: str, extracted_tag: str) -> bool:
    if not expected_tag or not extracted_tag:
        return True
    if expected_tag == extracted_tag:
        return True
    return (
        expected_tag in _CLINICAL_FINDING_FAMILY
        and extracted_tag in _CLINICAL_FINDING_FAMILY
    )


def _phrase_matches(
    expected_norm: str, extracted_norm: str, *, containment_match: bool
) -> bool:
    if expected_norm == extracted_norm:
        return True
    if not containment_match:
        return False
    if len(expected_norm) >= _MIN_CONTAINMENT_LEN and expected_norm in extracted_norm:
        return True
    if len(extracted_norm) >= _MIN_CONTAINMENT_LEN and extracted_norm in expected_norm:
        return True
    return False


def _entity_text(entity: dict[str, str] | str) -> str:
    return entity.get("text", "") if isinstance(entity, dict) else str(entity)


def _entity_tag(entity: dict[str, str] | str) -> str:
    return entity.get("semantic_tag", "finding") if isinstance(entity, dict) else ""


def _greedy_phrase_match(
    expected_list: list[dict[str, str]],
    extracted_list: list[dict[str, str] | str],
    rules: dict[str, bool],
) -> tuple[int, list[dict[str, str] | str], list[dict[str, str]]]:
    """Return (tp_count, matched_extracted, missed_expected)."""
    containment = bool(rules.get("containment_match"))

    expected_parsed = [
        {
            "orig": expected,
            "norm": normalise_phrase(expected.get("text", ""), rules),
            "tag": expected.get("semantic_tag", "finding"),
        }
        for expected in expected_list
    ]
    extracted_parsed = [
        {
            "orig": extracted,
            "norm": normalise_phrase(_entity_text(extracted), rules),
            "tag": _entity_tag(extracted),
        }
        for extracted in extracted_list
    ]

    matched_expected: set[int] = set()
    matched_extracted: set[int] = set()
    for expected_idx, expected in enumerate(expected_parsed):
        if not expected["norm"]:
            continue
        best_extracted_idx: int | None = None
        best_len = -1
        for extracted_idx, extracted in enumerate(extracted_parsed):
            if extracted_idx in matched_extracted or not extracted["norm"]:
                continue
            if not _tags_compatible(expected["tag"], extracted["tag"]):
                continue
            if not _phrase_matches(
                expected["norm"],
                extracted["norm"],
                containment_match=containment,
            ):
                continue
            if len(expected["norm"]) > best_len:
                best_len = len(expected["norm"])
                best_extracted_idx = extracted_idx
        if best_extracted_idx is not None:
            matched_expected.add(expected_idx)
            matched_extracted.add(best_extracted_idx)
    missed = [
        expected_list[i] for i in range(len(expected_list)) if i not in matched_expected
    ]
    extra = [
        extracted_list[i]
        for i in range(len(extracted_list))
        if i not in matched_extracted
    ]
    return len(matched_expected), extra, missed


def _observable_recall(
    case: dict[str, Any], extracted_entities: list[dict[str, str] | str]
) -> float:
    observables = case.get("expected_observables")
    if not isinstance(observables, list) or not observables:
        return 1.0
    targets = _observable_targets(observables)
    if not targets:
        return 1.0
    rules = {
        "casefold": True,
        "trim": True,
        "collapse_whitespace": True,
        "strip_terminal_punctuation": True,
        "containment_match": True,
    }
    _, _, missed = _greedy_phrase_match(targets, extracted_entities, rules)
    return _metric(len(targets) - len(missed), len(targets))


def _observable_targets(observables: list[Any]) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for row in observables:
        if not isinstance(row, dict):
            continue
        name = str(row.get("display_name") or row.get("test_name") or "").strip()
        if name:
            targets.append({"text": name, "semantic_tag": "observable_entity"})
    return targets


def score_case(
    case: dict[str, Any],
    extracted_entities: list[dict[str, str] | str],
    rules: dict[str, bool],
) -> dict[str, Any]:
    """Score one case against extracted entities by text and semantic tag."""
    expected = list(case.get("expected_strings", []))
    expected_dicts = [
        row if isinstance(row, dict) else {"text": row, "semantic_tag": "finding"}
        for row in expected
    ]

    true_positive, extra, missed = _greedy_phrase_match(
        expected_dicts,
        extracted_entities,
        rules,
    )
    precision = _metric(true_positive, true_positive + len(extra))
    recall = _metric(true_positive, len(expected_dicts))
    return {
        "case_id": case["case_id"],
        "true_positive": true_positive,
        "false_positive": len(extra),
        "false_negative": len(missed),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "missed_strings": [row.get("text", "") for row in missed],
        "extra_strings": [_entity_text(row) for row in extra],
        "missed_strings_raw": missed,
        "extra_strings_raw": extra,
        "observable_recall": _observable_recall(case, extracted_entities),
    }


def score_extraction_cases(
    cases: list[dict[str, Any]],
    extracted_by_case: dict[str, list[dict[str, str] | str]],
    rules: dict[str, bool],
) -> dict[str, Any]:
    """Score all cases and return aggregate phrase-level metrics."""
    by_case = [
        score_case(case, extracted_by_case.get(case["case_id"], []), rules)
        for case in cases
    ]
    true_positive = sum(row["true_positive"] for row in by_case)
    false_positive = sum(row["false_positive"] for row in by_case)
    false_negative = sum(row["false_negative"] for row in by_case)
    precision = _metric(true_positive, true_positive + false_positive)
    recall = _metric(true_positive, true_positive + false_negative)
    return {
        "overall": {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        },
        "by_case": by_case,
    }
