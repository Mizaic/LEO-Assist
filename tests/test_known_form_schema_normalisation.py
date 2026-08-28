"""Do not re-normalise taught-form chunks before LLM extraction."""

from __future__ import annotations

import json
from pathlib import Path

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.form_schema_store import has_taught_form_schema
from libs.pipeline.windowed_llm_extraction import normalise_chunks_for_llm

SHERWOOD_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form_schema"
    / "sherwood_gynae_2ww_chunks_deid.json"
)


def _section_c_chunk_text() -> str:
    payload = json.loads(SHERWOOD_FIXTURE.read_text(encoding="utf-8"))
    for chunk in payload["chunks"]:
        if "Section C" in chunk.get("text", ""):
            return str(chunk["text"])
    raise AssertionError("Section C chunk missing from Sherwood fixture")


def test_has_taught_form_schema_needs_match_and_fingerprint() -> None:
    """Both resolved keys must agree, as form_schema_state_fields writes them."""
    bound = {
        "form_schema_match": "org_service",
        "form_schema_fingerprint": "sfh-gynae-2ww-v1",
    }
    assert has_taught_form_schema(bound) is True
    assert has_taught_form_schema({"form_schema_match": "org_service"}) is False
    assert (
        has_taught_form_schema({"form_schema_fingerprint": "sfh-gynae-2ww-v1"}) is False
    )
    assert has_taught_form_schema({"form_schema_match": "none"}) is False
    assert has_taught_form_schema({}) is False


def test_taught_form_skips_second_generic_normalisation() -> None:
    chunk = SentenceChunk("c6", _section_c_chunk_text(), 0, 928)

    truncated = normalise_chunks_for_llm([chunk], skip=False)[0].text.lower()
    assert "vaginal discharge" not in truncated
    assert "polyp noted" not in truncated

    preserved = normalise_chunks_for_llm([chunk], skip=True)[0].text.lower()
    assert "vaginal discharge" in preserved
    assert "polyp noted" in preserved
