"""Gate 3 A3.5 -- codes-first Background envelope."""

from __future__ import annotations

import json
import re

from libs.sbar.background_envelope import (
    build_codes_first_user_message,
    serialise_code,
    serialise_completeness_for_context,
)
from libs.sbar.source_resolver import ResolvedCode, ResolvedSource
from libs.sbar.uncoded_coverage import CoverageReport, SalvageSentence


def test_coded_chunk_omits_full_prose() -> None:
    sources = [
        ResolvedSource(
            source_label="Chunk",
            source_id="chunk-a",
            text="A" * 5000,
            codes=[
                ResolvedCode(
                    concept_id="123",
                    term="Weight loss",
                    chunk_id="chunk-a",
                    source_label="Chunk",
                    source_id="chunk-a",
                )
            ],
        )
    ]
    msg = build_codes_first_user_message(sources, sources[0].codes)
    match = re.search(r"```json\n(?P<body>.*)\n```", msg, re.DOTALL)
    assert match
    body = json.loads(match.group("body"))
    assert body["sources"][0]["has_codes"] is True
    assert "text" not in body["sources"][0]


def test_includes_salvage_sentences_and_accounting() -> None:
    coverage = CoverageReport(
        total_sentences=4,
        covered_sentences=2,
        uncovered_sentences=2,
        salvage_sentences=[
            SalvageSentence(
                chunk_id="chunk-a",
                sentence_index=1,
                text="Progressive dysphagia for 6 weeks.",
                reason="uncoded_qualifier",
            )
        ],
    )
    msg = build_codes_first_user_message([], [], coverage)
    body = json.loads(
        re.search(r"```json\n(?P<body>.*)\n```", msg, re.DOTALL).group("body")
    )
    assert body["salvage_sentences"][0]["text"].startswith("Progressive")
    assert body["source_accounting"]["salvage_sentences"] == 1


def test_includes_structured_completeness_missing_groups() -> None:
    completeness = {
        "configured": True,
        "complete": False,
        "domain": "cancer_referrals",
        "subdomain": "upper_gi",
        "missing_groups": [
            {"name": "Examination findings", "required": True},
        ],
        "matched_groups": [
            {"name": "Presenting symptom", "required": True},
        ],
    }
    msg = build_codes_first_user_message([], [], completeness_result=completeness)
    body = json.loads(
        re.search(r"```json\n(?P<body>.*)\n```", msg, re.DOTALL).group("body")
    )
    assert body["completeness"]["missing_groups"][0]["name"] == "Examination findings"


def test_serialise_code_omits_duplicate_evidence_copies() -> None:
    code = ResolvedCode(
        concept_id="123",
        term="Weight loss",
        evidence="x" * 1000,
        evidence_sentence="x" * 1000,
        source_label="Chunk",
        source_id="chunk-a",
    )
    payload = serialise_code(code)
    assert payload["patient_wording"] == "x" * 1000
    assert "evidence" not in payload
    assert "evidence_sentence" not in payload


def test_serialise_code_keeps_distinct_evidence_span() -> None:
    code = ResolvedCode(
        concept_id="123",
        term="Weight loss",
        evidence="weight loss",
        evidence_sentence="Reports weight loss for 3 weeks.",
        source_label="Chunk",
        source_id="chunk-a",
    )
    payload = serialise_code(code)
    assert payload["patient_wording"] == "Reports weight loss for 3 weeks."
    assert payload["evidence"] == "weight loss"
    assert "evidence_sentence" not in payload


def test_omits_completeness_when_no_missing_groups() -> None:
    completeness = {
        "configured": True,
        "complete": True,
        "missing_groups": [],
        "matched_groups": [{"name": "Presenting symptom", "required": True}],
    }
    slim = serialise_completeness_for_context(completeness)
    assert slim is None
