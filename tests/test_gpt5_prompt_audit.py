"""Tests for GPT-5 prompt inventory and deterministic cookbook checks.

Atlas trace: DI-7B978C0C / DO-FA8FCECF.
No test imports service modules or calls Neo4j or an external language model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.audit_gpt5_prompts import (
    audit_prompt,
    build_inventory,
    discover_prompt_sources,
    write_json_report,
)

PROMPT_TEXT = (
    "You are a clinical reviewer. Return a JSON object with fields "
    '{"decision": "accept"}. Keep every decision grounded in the record.'
)


def _make_tree(root: Path, service_source: str = "") -> None:
    """Create only the search roots needed by isolated AST tests."""
    for relative in ("libs/prompts", "libs/llm_client", "services", "scripts"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "services" / "inline.py").write_text(service_source, encoding="utf-8")


def _seed(**overrides: object) -> dict[str, object]:
    """Return one minimal seeded PromptConfig row."""
    seed: dict[str, object] = {
        "name": "review",
        "version": 1,
        "system_prompt": PROMPT_TEXT,
        "output_schema": json.dumps(
            {
                "type": "object",
                "properties": {"decision": {"type": "string"}},
            }
        ),
        "few_shot_examples": [{"input": "Case A", "output": '{"decision": "accept"}'}],
    }
    seed.update(overrides)
    return seed


def test_inventory_includes_every_seed_and_matches_ast_source(tmp_path: Path) -> None:
    """Seed rows retain identity and resolve to the matching source constant."""
    _make_tree(tmp_path)
    prompt_file = tmp_path / "libs" / "prompts" / "review_v1.py"
    prompt_file.write_text(
        f"REVIEW_SYSTEM_PROMPT = {PROMPT_TEXT!r}\n",
        encoding="utf-8",
    )

    report = build_inventory(tmp_path, [_seed(), _seed(name="review_alias")])
    seeded = [entry for entry in report["entries"] if entry["seeded_identity"]]

    assert len(seeded) == 2
    assert report["summary"]["seeded_count"] == 2
    assert {entry["seeded_identity"]["name"] for entry in seeded} == {
        "review",
        "review_alias",
    }
    assert all(entry["source_path"] == "libs/prompts/review_v1.py" for entry in seeded)
    assert all(entry["symbol"] == "REVIEW_SYSTEM_PROMPT" for entry in seeded)


def test_inventory_emits_required_fields_and_prompt_hash(tmp_path: Path) -> None:
    """JSON entries expose the complete stable audit contract."""
    _make_tree(tmp_path)

    report = build_inventory(tmp_path, [_seed()])
    entry = report["entries"][0]

    assert set(entry) == {
        "source_path",
        "symbol",
        "category",
        "consumer",
        "model_tier",
        "seed_status",
        "seeded_identity",
        "sha256",
        "output_schema_present",
        "few_shot_count",
        "issues",
    }
    assert entry["sha256"] == hashlib.sha256(PROMPT_TEXT.encode()).hexdigest()
    assert entry["output_schema_present"] is True
    assert entry["few_shot_count"] == 1


def test_ast_discovery_does_not_import_service_modules(tmp_path: Path) -> None:
    """AST discovery reads an inline prompt despite import-time failure code."""
    source = (
        "raise RuntimeError('must not execute')\n"
        "CLINICAL_SYSTEM_PROMPT = (\n"
        "    'You are a clinical coding reviewer. Review patient evidence and '\n"
        "    'return a cautious decision for a clinician to check before use.'\n"
        ")\n"
    )
    _make_tree(tmp_path, source)

    found = discover_prompt_sources(tmp_path)

    assert [(item.source_path, item.symbol) for item in found] == [
        ("services/inline.py", "CLINICAL_SYSTEM_PROMPT")
    ]


def test_conservative_cookbook_checks_report_explicit_issues() -> None:
    """Explicit contradictions, stale wording, duplicates and ASCII are checked."""
    non_ascii = chr(946)
    text = (
        "You are a clinical reviewer using Claude on Amazon Bedrock. "
        "Return only JSON. Do not return JSON. "
        f"Review patient {non_ascii} evidence carefully."
    )
    duplicate = {"input": "same", "output": "{}"}

    issues = audit_prompt(
        text,
        None,
        [duplicate, duplicate],
        inline=True,
        guarded=False,
    )

    assert "contradictory_imperatives" in issues
    assert "unclear_json_output_contract" in issues
    assert "duplicate_few_shots" in issues
    assert "stale_claude_bedrock_wording" in issues
    assert "likely_missing_injection_guard" in issues
    assert "non_ascii" in issues


def test_json_few_shots_are_checked_against_output_contract() -> None:
    """Invalid JSON and wrong top-level JSON types identify their examples."""
    schema = {"type": "object"}
    examples = [
        {"input": "A", "output": "not-json"},
        {"input": "B", "output": "[]"},
        {"input": "C", "output": "{}"},
    ]

    issues = audit_prompt("Return a JSON object.", schema, examples)

    assert "few_shot_output_not_json:0" in issues
    assert "few_shot_json_type_mismatch:1" in issues
    assert "few_shot_json_type_mismatch:2" not in issues
    untyped = audit_prompt("Return only JSON.", None, examples[:1])
    assert "few_shot_output_not_json:0" in untyped


def test_injection_guard_check_is_limited_to_likely_inline_system_prompts() -> None:
    """Canonical prompts and guarded inline prompts avoid the heuristic issue."""
    text = "You are a clinical reviewer for patient referral evidence." * 2

    canonical = audit_prompt(text, None, [], inline=False, guarded=False)
    guarded = audit_prompt(text, None, [], inline=True, guarded=True)

    assert "likely_missing_injection_guard" not in canonical
    assert "likely_missing_injection_guard" not in guarded


def test_json_writer_is_deterministic_and_ascii(tmp_path: Path) -> None:
    """Optional JSON output escapes non-ASCII and preserves report content."""
    report = {
        "entries": [{"symbol": "PROMPT", "issues": ["non_ascii"]}],
        "summary": {"entry_count": 1},
    }
    output = tmp_path / "audit.json"

    write_json_report(report, output)
    raw = output.read_text(encoding="utf-8")

    assert raw.isascii()
    assert json.loads(raw) == report
