#!/usr/bin/env python3
"""File-backed GPT-5 baseline-versus-candidate evaluation harness.

Atlas trace: DI-7B978C0C / DO-FA8FCECF / VT-06157CF6 / VAL-541EE980.
Fixture and model response text is never written to results or logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from libs.llm_client.factory import create_llm
from libs.llm_usage import LLMCostConfig, LLMUsage

ATLAS_TRACE = {
    "design_input": "DI-7B978C0C",
    "design_output": "DO-FA8FCECF",
    "verification_test": "VT-06157CF6",
    "validation_test": "VAL-541EE980",
}
PHRASE_F1_THRESHOLD = 0.95
_REQUIRED_FIXTURE_FIELDS = frozenset({"id", "family", "system", "user", "expected"})
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE)
_NHS_RE = re.compile(r"\b\d{3}[\s-]?\d{3}[\s-]?\d{4}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+44\s?\d{9,10}|0(?:1|2|7)\d[\d\s-]{8,12})(?!\d)")
_DOB_RE = re.compile(
    r"\b(?:dob|date\s+of\s+birth|born)\s*[:=-]?\s*"
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            rows.append(row)
    return rows


def _contains_identifier(value: Any) -> str | None:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    patterns = (
        ("NHS number", _NHS_RE),
        ("email", _EMAIL_RE),
        ("phone", _PHONE_RE),
        ("date of birth", _DOB_RE),
    )
    return next((name for name, pattern in patterns if pattern.search(text)), None)


def load_fixtures(path: Path) -> list[dict[str, Any]]:
    """Load and validate de-identified evaluation fixtures."""
    fixtures = _read_jsonl(path)
    seen: set[str] = set()
    for row in fixtures:
        missing = sorted(_REQUIRED_FIXTURE_FIELDS - row.keys())
        if missing:
            raise ValueError(f"fixture is missing fields: {', '.join(missing)}")
        fixture_id = str(row["id"]).strip()
        if not fixture_id or fixture_id in seen:
            raise ValueError("fixture ids must be non-empty and unique")
        if not isinstance(row["system"], str) or not isinstance(row["user"], str):
            raise ValueError(f"fixture {fixture_id}: system and user must be strings")
        identifier = _contains_identifier(row)
        if identifier:
            raise ValueError(f"fixture {fixture_id}: possible {identifier} detected")
        if "schema" in row and "json_schema" in row:
            raise ValueError(f"fixture {fixture_id}: use only one JSON schema field")
        schema = row.get("schema", row.get("json_schema"))
        if schema is not None:
            Draft202012Validator.check_schema(schema)
        row["id"] = fixture_id
        row["family"] = str(row["family"]).strip()
        seen.add(fixture_id)
    return fixtures


def load_config(path: Path) -> dict[str, Any]:
    """Load one baseline or candidate model configuration."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: configuration must be an object")
    config = {
        "name": str(raw.get("name") or path.stem),
        "provider": str(raw.get("provider") or "azure"),
        "tier": str(raw.get("tier") or "small"),
        "model_id": raw.get("model_id"),
        "reasoning_effort": str(raw.get("reasoning_effort") or "high"),
        "verbosity": str(raw.get("verbosity") or "medium"),
        "use_reasoning": bool(raw.get("use_reasoning", True)),
        "max_tokens": int(raw.get("max_tokens", 2048)),
        "example_ids": [str(item) for item in raw.get("example_ids", [])],
    }
    if raw.get("system") is not None and raw.get("system_file") is not None:
        raise ValueError(f"{path}: use only system or system_file")
    if raw.get("system_file") is not None:
        prompt_path = path.parent / str(raw["system_file"])
        config["system"] = prompt_path.read_text(encoding="utf-8")
    elif raw.get("system") is not None:
        config["system"] = str(raw["system"])
    if config["max_tokens"] < 1:
        raise ValueError(f"{path}: max_tokens must be positive")
    return config


def _schema(fixture: dict[str, Any]) -> dict[str, Any] | None:
    return fixture.get("schema", fixture.get("json_schema"))


def _prompt_hash(system: str, user: str, schema: Any) -> str:
    payload = json.dumps(
        {"system": system, "user": user, "schema": schema},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_json(text: str) -> tuple[Any, bool]:
    try:
        return json.loads(text), True
    except (json.JSONDecodeError, TypeError):
        return None, False


def _normalise_phrase(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _extract_phrases(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_normalise_phrase(value)] if value.strip() else []
    if isinstance(value, list):
        return [phrase for item in value for phrase in _extract_phrases(item)]
    if not isinstance(value, dict):
        return []
    if isinstance(value.get("text"), str):
        return _extract_phrases(value["text"])
    for key in ("terms", "phrases", "expected_strings", "entities", "items"):
        if key in value:
            return _extract_phrases(value[key])
    return []


def _phrase_f1(expected: Any, actual: Any) -> dict[str, Any]:
    expected_counts = Counter(_extract_phrases(expected))
    actual_counts = Counter(_extract_phrases(actual))
    true_positive = sum((expected_counts & actual_counts).values())
    false_positive = sum((actual_counts - expected_counts).values())
    false_negative = sum((expected_counts - actual_counts).values())
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = true_positive / precision_denominator if precision_denominator else 1.0
    recall = true_positive / recall_denominator if recall_denominator else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "name": "phrase_f1",
        "score": round(f1, 6),
        "passed": f1 >= PHRASE_F1_THRESHOLD,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def _evaluate(fixture: dict[str, Any], text: str) -> dict[str, Any]:
    expected = fixture["expected"]
    schema = _schema(fixture)
    parsed, parsed_ok = _parse_json(text)
    structured = schema is not None or isinstance(expected, (dict, list))
    actual = parsed if parsed_ok and structured else text.strip()
    exact = actual == expected if structured else str(expected).strip() == actual
    schema_valid: bool | None = None
    if schema is not None:
        schema_valid = parsed_ok and Draft202012Validator(schema).is_valid(parsed)
    evaluator = str(fixture.get("evaluator") or "").strip()
    custom = None
    if evaluator == "phrase_f1" or fixture["family"] == "extraction":
        custom = _phrase_f1(expected, parsed if parsed_ok else None)
    return {
        "exact_match": exact,
        "schema_valid": schema_valid,
        "custom_evaluator": custom,
        "malformed_output": bool(structured and not parsed_ok),
    }


def _estimated_cost(config: dict[str, Any], response: Any) -> float:
    usage = LLMUsage(
        input_tokens=max(0, int(getattr(response, "input_tokens", 0) or 0)),
        output_tokens=max(0, int(getattr(response, "output_tokens", 0) or 0)),
        cached_input_tokens=max(
            0, int(getattr(response, "cached_input_tokens", 0) or 0)
        ),
        reasoning_tokens=max(0, int(getattr(response, "reasoning_tokens", 0) or 0)),
        llm_calls=1,
        input_excludes_cache=config["provider"] in {"aws", "bedrock"},
    )
    rates = LLMCostConfig.for_provider_tier(config["provider"], config["tier"])
    return round(usage.cost_usd(rates), 6)


def _create_client(config: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {
        "provider": config["provider"],
        "tier": config["tier"],
        "use_reasoning": config["use_reasoning"],
        "azure_reasoning_effort": config["reasoning_effort"],
    }
    if config["model_id"]:
        kwargs["model_id"] = str(config["model_id"])
    return create_llm(**kwargs)


def _result_row(
    fixture: dict[str, Any], config: dict[str, Any], client: Any
) -> dict[str, Any]:
    system = str(config.get("system", fixture["system"]))
    example_ids = sorted(
        set(config["example_ids"])
        | {str(item) for item in fixture.get("example_ids", [])}
    )
    started = time.monotonic()
    try:
        response = client.converse(
            system=system,
            messages=[{"role": "user", "content": fixture["user"]}],
            max_tokens=config["max_tokens"],
            temperature=0.0,
            json_mode=_schema(fixture) is not None,
            structured_schema=_schema(fixture),
            verbosity=config["verbosity"],
            agent_task="gpt5_prompt_evaluation",
            patient_id="",
        )
        evaluation = _evaluate(fixture, str(response.text or ""))
        error = None
    except Exception as exc:
        response = None
        evaluation = {
            "exact_match": False,
            "schema_valid": False if _schema(fixture) is not None else None,
            "custom_evaluator": (
                _phrase_f1(fixture["expected"], None)
                if fixture["family"] == "extraction"
                else None
            ),
            "malformed_output": True,
        }
        error = f"{type(exc).__name__}: LLM call failed"
    latency_ms = int((time.monotonic() - started) * 1000)
    context = {
        "fixture": fixture,
        "config": config,
        "client": client,
        "system": system,
        "example_ids": example_ids,
    }
    return _build_result_metadata(context, response, evaluation, error, latency_ms)


def _build_result_metadata(
    context: dict[str, Any],
    response: Any,
    evaluation: dict[str, Any],
    error: str | None,
    latency_ms: int,
) -> dict[str, Any]:
    fixture = context["fixture"]
    config = context["config"]
    client = context["client"]

    def token(name: str) -> int:
        return max(0, int(getattr(response, name, 0) or 0))

    return {
        "fixture_id": fixture["id"],
        "family": fixture["family"],
        "configuration": config["name"],
        "model_deployment": str(getattr(client, "model_id", config["model_id"]) or ""),
        "reasoning_effort": config["reasoning_effort"],
        "verbosity": config["verbosity"],
        "prompt_hash": _prompt_hash(
            context["system"], fixture["user"], _schema(fixture)
        ),
        "example_ids": context["example_ids"],
        "safety_critical": bool(fixture.get("safety_critical", False)),
        **evaluation,
        "input_tokens": token("input_tokens"),
        "output_tokens": token("output_tokens"),
        "cached_tokens": token("cached_input_tokens"),
        "reasoning_tokens": token("reasoning_tokens"),
        "estimated_cost_usd": _estimated_cost(config, response) if response else 0.0,
        "latency_ms": latency_ms,
        "error": error,
    }


def run_live(
    fixtures: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Run one configuration through the sanctioned synchronous LLM path."""
    client = _create_client(config)
    return [_result_row(fixture, config, client) for fixture in fixtures]


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    temporary.replace(path)


def _primary_score(row: dict[str, Any]) -> float:
    custom = row.get("custom_evaluator")
    if isinstance(custom, dict) and custom.get("score") is not None:
        return float(custom["score"])
    if row.get("schema_valid") is not None:
        return float(bool(row["schema_valid"]))
    return float(bool(row.get("exact_match")))


def _is_regression(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if old.get("exact_match") and not new.get("exact_match"):
        return True
    if old.get("schema_valid") is True and new.get("schema_valid") is not True:
        return True
    if not old.get("malformed_output") and new.get("malformed_output"):
        return True
    if old.get("error") is None and new.get("error") is not None:
        return True
    return _primary_score(new) < _primary_score(old)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    schemas = [row for row in rows if row.get("schema_valid") is not None]
    customs = [
        row["custom_evaluator"]
        for row in rows
        if isinstance(row.get("custom_evaluator"), dict)
    ]
    counts = {
        key: sum(int(item.get(key, 0)) for item in customs)
        for key in ("true_positive", "false_positive", "false_negative")
    }
    phrase = _phrase_from_counts(counts) if customs else None
    return {
        "count": count,
        "exact_match_rate": _rate(rows, "exact_match"),
        "schema_pass_rate": _rate(schemas, "schema_valid"),
        "custom_evaluator_average": (
            round(sum(float(item["score"]) for item in customs) / len(customs), 6)
            if customs
            else None
        ),
        "phrase_f1": phrase,
        "malformed_output_rate": _rate(rows, "malformed_output"),
        "error_rate": (
            round(sum(row.get("error") is not None for row in rows) / count, 6)
            if count
            else 0.0
        ),
        "estimated_cost_usd": round(
            sum(float(row.get("estimated_cost_usd", 0.0)) for row in rows), 6
        ),
        "latency_ms": sum(int(row.get("latency_ms", 0)) for row in rows),
    }


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    return (
        round(sum(bool(row.get(key)) for row in rows) / len(rows), 6) if rows else None
    )


def _phrase_from_counts(counts: dict[str, int]) -> float:
    tp = counts["true_positive"]
    precision_denominator = tp + counts["false_positive"]
    recall_denominator = tp + counts["false_negative"]
    precision = tp / precision_denominator if precision_denominator else 1.0
    recall = tp / recall_denominator if recall_denominator else 1.0
    return round(
        2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        6,
    )


def build_summary(
    baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build family and overall comparison metrics and release gate."""
    baseline_by_id = {row["fixture_id"]: row for row in baseline}
    candidate_by_id = {row["fixture_id"]: row for row in candidate}
    if baseline_by_id.keys() != candidate_by_id.keys():
        raise ValueError("baseline and candidate fixture ids must match")
    families = sorted({str(row["family"]) for row in baseline})
    family_summary = {
        family: {
            "baseline": _metrics([row for row in baseline if row["family"] == family]),
            "candidate": _metrics(
                [row for row in candidate if row["family"] == family]
            ),
        }
        for family in families
    }
    safety_regressions = sorted(
        fixture_id
        for fixture_id, old in baseline_by_id.items()
        if old.get("safety_critical")
        and _is_regression(old, candidate_by_id[fixture_id])
    )
    extraction_f1 = (
        family_summary.get("extraction", {}).get("candidate", {}).get("phrase_f1")
    )
    reasons = []
    if extraction_f1 is not None and extraction_f1 < PHRASE_F1_THRESHOLD:
        reasons.append(f"candidate extraction phrase_f1 below {PHRASE_F1_THRESHOLD}")
    if safety_regressions:
        reasons.append("one or more safety-critical fixtures regressed")
    return {
        "atlas_trace": ATLAS_TRACE,
        "overall": {"baseline": _metrics(baseline), "candidate": _metrics(candidate)},
        "families": family_summary,
        "gate": {
            "passed": not reasons,
            "reasons": reasons,
            "extraction_phrase_f1_threshold": PHRASE_F1_THRESHOLD,
            "safety_critical_regressions": safety_regressions,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Allow external LLM calls")
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--baseline-config", type=Path)
    parser.add_argument("--candidate-config", type=Path)
    parser.add_argument("--baseline-results", type=Path, required=True)
    parser.add_argument("--candidate-results", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run live evaluation only when opted in, otherwise compare result files."""
    args = _parser().parse_args(argv)
    try:
        if args.live:
            required = (args.fixtures, args.baseline_config, args.candidate_config)
            if any(path is None for path in required):
                raise ValueError(
                    "--live requires fixtures and both configuration files"
                )
            fixtures = load_fixtures(args.fixtures)
            baseline = run_live(fixtures, load_config(args.baseline_config))
            candidate = run_live(fixtures, load_config(args.candidate_config))
            _write_jsonl(args.baseline_results, baseline)
            _write_jsonl(args.candidate_results, candidate)
        else:
            baseline = _read_jsonl(args.baseline_results)
            candidate = _read_jsonl(args.candidate_results)
        summary = build_summary(baseline, candidate)
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(summary, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    return 0 if summary["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
