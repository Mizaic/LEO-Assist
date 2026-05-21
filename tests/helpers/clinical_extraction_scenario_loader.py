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


def _greedy_phrase_match(
    expected_list: list[dict[str, str]],
    extracted_list: list[dict[str, str]],
    rules: dict[str, bool],
) -> tuple[int, list[dict[str, str]], list[dict[str, str]]]:
    """Return (tp_count, matched_extracted, missed_expected)."""
    containment = bool(rules.get("containment_match"))

    # Store normalized text but keep original dict
    expected_parsed = [
        {
            "orig": e,
            "norm": normalise_phrase(e.get("text", ""), rules),
            "tag": e.get("semantic_tag", "finding"),
        }
        for e in expected_list
    ]
    extracted_parsed = [
        {
            "orig": x,
            "norm": normalise_phrase(x.get("text", ""), rules),
            "tag": x.get("semantic_tag", "finding"),
        }
        for x in extracted_list
    ]

    matched_expected: set[int] = set()
    matched_extracted: set[int] = set()
    for e_idx, exp in enumerate(expected_parsed):
        if not exp["norm"]:
            continue
        best_x_idx: int | None = None
        best_len = -1
        for x_idx, ext in enumerate(extracted_parsed):
            if x_idx in matched_extracted or not ext["norm"]:
                continue
            if not _tags_compatible(exp["tag"], ext["tag"]):
                continue
            if _phrase_matches(exp["norm"], ext["norm"], containment_match=containment):
                if len(exp["norm"]) > best_len:
                    best_len = len(exp["norm"])
                    best_x_idx = x_idx
        if best_x_idx is not None:
            matched_expected.add(e_idx)
            matched_extracted.add(best_x_idx)
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
    case: dict[str, Any], extracted_entities: list[dict[str, str]]
) -> float:
    observables = case.get("expected_observables")
    if not isinstance(observables, list) or not observables:
        return 1.0
    targets: list[dict[str, str]] = []
    for row in observables:
        if not isinstance(row, dict):
            continue
        name = str(row.get("display_name") or row.get("test_name") or "").strip()
        if name:
            targets.append({"text": name, "semantic_tag": "observable_entity"})
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


def score_case(
    case: dict[str, Any],
    extracted_entities: list[dict[str, str]],
    rules: dict[str, bool],
) -> dict[str, Any]:
    """Score one case against extracted entities (text + semantic_tag)."""
    expected = list(case.get("expected_strings", []))
    # Ensure they are dicts (in case some weren't migrated)
    expected_dicts = [
        e if isinstance(e, dict) else {"text": e, "semantic_tag": "finding"}
        for e in expected
    ]

    tp, extra, missed = _greedy_phrase_match(expected_dicts, extracted_entities, rules)
    precision = _metric(tp, tp + len(extra))
    recall = _metric(tp, len(expected_dicts))
    return {
        "case_id": case["case_id"],
        "true_positive": tp,
        "false_positive": len(extra),
        "false_negative": len(missed),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "missed_strings": [m.get("text", "") for m in missed],
        "extra_strings": [x.get("text", "") for x in extra],
        "missed_strings_raw": missed,
        "extra_strings_raw": extra,
        "observable_recall": _observable_recall(case, extracted_entities),
    }


def score_extraction_cases(
    cases: list[dict[str, Any]],
    extracted_by_case: dict[str, list[dict[str, str]]],
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
