"""Tests for the file-backed GPT-5 prompt evaluation harness.

Atlas trace: DI-7B978C0C / DO-FA8FCECF / VT-06157CF6 / VAL-541EE980.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import evaluate_gpt5_prompts as harness


class FakeLLM:
    """Small in-memory replacement for the sanctioned LLM client."""

    def __init__(self, text: str = '["rectal bleeding"]') -> None:
        self.model_id = "gpt-5-mini-test"
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            text=self.text,
            input_tokens=100,
            output_tokens=20,
            cached_input_tokens=40,
            reasoning_tokens=5,
        )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fixture(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "case-1",
        "family": "extraction",
        "system": "Return a JSON list of phrases.",
        "user": "Synthetic referral with rectal bleeding.",
        "expected": ["rectal bleeding"],
        "schema": {"type": "array", "items": {"type": "string"}},
        "example_ids": ["example-2"],
        "safety_critical": True,
    }
    row.update(overrides)
    return row


def _config(name: str = "baseline") -> dict[str, Any]:
    return {
        "name": name,
        "provider": "azure",
        "tier": "small",
        "model_id": "gpt-5-mini-test",
        "reasoning_effort": "high",
        "verbosity": "low",
        "use_reasoning": True,
        "max_tokens": 200,
        "example_ids": ["example-1"],
    }


def _result(
    fixture_id: str = "case-1",
    *,
    family: str = "extraction",
    score: float = 1.0,
    safety_critical: bool = False,
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "family": family,
        "exact_match": score == 1.0,
        "schema_valid": True,
        "custom_evaluator": {
            "name": "phrase_f1",
            "score": score,
            "passed": score >= 0.95,
            "true_positive": 1 if score else 0,
            "false_positive": 0,
            "false_negative": 0 if score else 1,
        },
        "malformed_output": False,
        "error": None,
        "safety_critical": safety_critical,
        "estimated_cost_usd": 0.01,
        "latency_ms": 10,
    }


def test_live_run_uses_sanctioned_client_and_records_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeLLM()
    create_calls: list[dict[str, Any]] = []

    def fake_create_llm(**kwargs: Any) -> FakeLLM:
        create_calls.append(kwargs)
        return fake

    monkeypatch.setattr(harness, "create_llm", fake_create_llm)
    row = harness.run_live([_fixture()], _config())[0]

    assert create_calls == [
        {
            "provider": "azure",
            "tier": "small",
            "use_reasoning": True,
            "azure_reasoning_effort": "high",
            "model_id": "gpt-5-mini-test",
        }
    ]
    assert fake.calls[0]["structured_schema"]["type"] == "array"
    assert fake.calls[0]["verbosity"] == "low"
    assert fake.calls[0]["agent_task"] == "gpt5_prompt_evaluation"
    assert row["model_deployment"] == "gpt-5-mini-test"
    assert row["example_ids"] == ["example-1", "example-2"]
    assert row["prompt_hash"] and len(row["prompt_hash"]) == 64
    assert row["exact_match"] is True
    assert row["schema_valid"] is True
    assert row["custom_evaluator"]["score"] == 1.0
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 20
    assert row["cached_tokens"] == 40
    assert row["reasoning_tokens"] == 5
    assert row["estimated_cost_usd"] > 0
    assert "rectal bleeding" not in json.dumps(row)


@pytest.mark.parametrize(
    ("field", "value", "label"),
    [
        ("user", "NHS number 943 476 5919", "NHS number"),
        ("user", "Contact jane@example.test", "email"),
        ("user", "Call 07123 456789", "phone"),
        ("user", "DOB: 1970-01-02", "date of birth"),
    ],
)
def test_load_fixtures_rejects_obvious_identifiers(
    tmp_path: Path, field: str, value: str, label: str
) -> None:
    path = tmp_path / "fixtures.jsonl"
    _write_jsonl(path, [_fixture(**{field: value})])

    with pytest.raises(ValueError, match=label):
        harness.load_fixtures(path)


def test_load_fixtures_accepts_json_schema_alias(tmp_path: Path) -> None:
    path = tmp_path / "fixtures.jsonl"
    fixture = _fixture()
    fixture["json_schema"] = fixture.pop("schema")
    _write_jsonl(path, [fixture])

    loaded = harness.load_fixtures(path)

    assert loaded[0]["id"] == "case-1"
    assert loaded[0]["json_schema"]["type"] == "array"


def test_malformed_and_schema_results_are_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_schema = FakeLLM(text='{"unexpected": true}')
    monkeypatch.setattr(harness, "create_llm", lambda **_kwargs: invalid_schema)
    schema_row = harness.run_live([_fixture()], _config())[0]

    malformed = FakeLLM(text="not json")
    monkeypatch.setattr(harness, "create_llm", lambda **_kwargs: malformed)
    malformed_row = harness.run_live([_fixture()], _config())[0]

    assert schema_row["schema_valid"] is False
    assert schema_row["malformed_output"] is False
    assert malformed_row["schema_valid"] is False
    assert malformed_row["malformed_output"] is True


def test_summary_fails_below_phrase_threshold_and_on_safety_regression() -> None:
    baseline = [_result(safety_critical=True), _result("case-2")]
    candidate = [
        _result(safety_critical=True, score=0.0),
        _result("case-2", score=1.0),
    ]

    summary = harness.build_summary(baseline, candidate)

    assert summary["overall"]["candidate"]["malformed_output_rate"] == 0.0
    assert summary["families"]["extraction"]["candidate"]["phrase_f1"] < 0.95
    assert summary["gate"]["passed"] is False
    assert summary["gate"]["safety_critical_regressions"] == ["case-1"]


def test_summary_passes_for_matching_candidate() -> None:
    baseline = [_result(safety_critical=True)]
    candidate = [_result(safety_critical=True)]

    summary = harness.build_summary(baseline, candidate)

    assert summary["gate"]["passed"] is True
    assert summary["atlas_trace"] == harness.ATLAS_TRACE
    assert summary["families"]["extraction"]["candidate"]["phrase_f1"] == 1.0


def test_offline_main_compares_files_without_llm_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    summary_path = tmp_path / "summary.json"
    _write_jsonl(baseline_path, [_result()])
    _write_jsonl(candidate_path, [_result()])
    monkeypatch.setattr(
        harness,
        "create_llm",
        lambda **_kwargs: pytest.fail("offline mode made an external call"),
    )

    exit_code = harness.main(
        [
            "--baseline-results",
            str(baseline_path),
            "--candidate-results",
            str(candidate_path),
            "--summary",
            str(summary_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(summary_path.read_text(encoding="utf-8"))["gate"]["passed"]


def test_live_mode_requires_explicit_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_path = tmp_path / "baseline.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    _write_jsonl(baseline_path, [_result()])
    _write_jsonl(candidate_path, [_result()])
    monkeypatch.setattr(
        harness,
        "create_llm",
        lambda **_kwargs: pytest.fail("comparison mode made an external call"),
    )

    exit_code = harness.main(
        [
            "--fixtures",
            str(tmp_path / "unused.jsonl"),
            "--baseline-results",
            str(baseline_path),
            "--candidate-results",
            str(candidate_path),
            "--summary",
            str(tmp_path / "summary.json"),
        ]
    )

    assert exit_code == 0


def test_checked_in_fixtures_cover_required_prompt_families() -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "gpt5_prompt_eval"

    fixtures = harness.load_fixtures(fixture_dir / "fixtures.jsonl")
    mini = harness.load_config(fixture_dir / "gpt-5-mini.json")
    large = harness.load_config(fixture_dir / "gpt-5.4.json")

    assert {item["family"] for item in fixtures} == {
        "analytics",
        "coding",
        "disorder",
        "episode",
        "extraction",
        "sbar",
    }
    assert all(item.get("schema") for item in fixtures)
    assert mini["model_id"] == "gpt-5-mini"
    assert large["model_id"] == "gpt-5.4"
