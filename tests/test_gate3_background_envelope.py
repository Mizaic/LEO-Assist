"""Gate 3 A3.5 -- codes-first Background envelope."""

from __future__ import annotations

import json
import re

from libs.sbar.background_envelope import build_codes_first_user_message
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
