"""VT-66D6DE07 -- window-local extraction context acceptance verification."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from libs.pipeline.extraction_prompt import (
    CONTEXT_MODE_FULL_DOCUMENT,
    CONTEXT_MODE_WINDOW_LOCAL,
    build_extraction_user_message,
)
from libs.pipeline.extraction_window import (
    ChunkRef,
    estimate_tokens,
    plan_extraction_windows_by_tokens,
)
from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline_graph.subgraphs.extraction import _run_windowed_llm_extraction


def test_shared_prompt_labels_for_context_modes() -> None:
    local = build_extraction_user_message(
        "alpha chunk",
        "[c1] alpha chunk",
        context_mode=CONTEXT_MODE_WINDOW_LOCAL,
    )
    full = build_extraction_user_message(
        "alpha chunk\n\nbeta chunk",
        "[c1] alpha chunk",
        context_mode=CONTEXT_MODE_FULL_DOCUMENT,
    )
    assert "Window context:" in local
    assert "beta chunk" not in local
    assert "Encounter text:" in full
    assert "beta chunk" in full


def test_token_planner_respects_budget_and_overlap() -> None:
    chunks = [
        ChunkRef(chunk_id=f"c{i}", text=("word " * 40) + f"chunk-{i}") for i in range(8)
    ]
    windows = plan_extraction_windows_by_tokens(
        chunks,
        max_window_input_tokens=500,
        window_overlap_chunks=1,
        max_chunks_per_window=10,
        overhead_tokens=50,
    )
    assert len(windows) >= 2
    for window in windows:
        if window.truncated:
            continue
        payload = "\n\n".join(c.text for c in chunks if c.chunk_id in window.chunk_ids)
        sentence_block = "\n".join(
            f"[{c.chunk_id}] {c.text}" for c in chunks if c.chunk_id in window.chunk_ids
        )
        assert estimate_tokens(payload) + estimate_tokens(sentence_block) + 50 <= 500
    # Overlap: adjacent windows share a trailing chunk when possible.
    if len(windows) >= 2:
        assert windows[0].chunk_ids[-1] in windows[1].chunk_ids


def test_oversized_chunk_is_split_across_windows_not_truncated() -> None:
    """An oversized chunk is spread over windows, keeping every character.

    This used to assert ``w.truncated`` on a lone oversized chunk, which
    let the caller cut it to half the window budget. Splitting replaced
    truncation so no clinical text is dropped.
    """
    from libs.pipeline.extraction_window import window_chunk_text

    huge = "x" * 20000
    chunks = [
        ChunkRef(chunk_id="big", text=huge),
        ChunkRef(chunk_id="small", text="tiny"),
    ]
    windows = plan_extraction_windows_by_tokens(
        chunks,
        max_window_input_tokens=400,
        window_overlap_chunks=0,
        max_chunks_per_window=10,
        overhead_tokens=10,
    )
    assert not any(w.truncated for w in windows)
    covered = {cid for w in windows for cid in w.chunk_ids}
    assert covered == {"big", "small"}

    big_windows = [w for w in windows if w.chunk_ids == ("big",)]
    assert len(big_windows) > 1, "the oversized chunk must span several windows"
    rebuilt = "".join(window_chunk_text(w, "big", huge) for w in big_windows)
    assert rebuilt == huge, "every character must reach a window"


def test_window_local_prompt_omits_off_window_chunk_body() -> None:
    chunks = [
        SentenceChunk(sentence_id="c1", text="ALPHA_UNIQUE_BODY", start=0, end=17),
        SentenceChunk(sentence_id="c2", text="BETA_UNIQUE_BODY", start=19, end=35),
    ]
    captured: list[str] = []

    def _fake_llm(context, window_chunks, state, **kwargs):
        captured.append(str(context))
        return {"entities": [], "llm_tokens": {"input_tokens": 1}}

    with patch(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction",
        side_effect=_fake_llm,
    ):
        result = _run_windowed_llm_extraction(
            "ALPHA_UNIQUE_BODY\n\nBETA_UNIQUE_BODY",
            chunks,
            {"execution_manifest": {"extraction": {}}},
            window_size=1,
            window_overlap=0,
            context_mode=CONTEXT_MODE_WINDOW_LOCAL,
            max_window_input_tokens=3500,
        )
    assert result["extraction_context_mode"] == CONTEXT_MODE_WINDOW_LOCAL
    assert result["extraction_window_count"] == 2
    assert len(captured) == 2
    assert "BETA_UNIQUE_BODY" not in captured[0]
    assert "ALPHA_UNIQUE_BODY" not in captured[1]


def test_full_document_rollback_echoes_full_text() -> None:
    chunks = [
        SentenceChunk(sentence_id="c1", text="ALPHA_UNIQUE_BODY", start=0, end=17),
        SentenceChunk(sentence_id="c2", text="BETA_UNIQUE_BODY", start=19, end=35),
    ]
    captured: list[str] = []

    def _fake_llm(context, window_chunks, state, **kwargs):
        captured.append(str(context))
        return {"entities": [], "llm_tokens": {"input_tokens": 1}}

    full = "ALPHA_UNIQUE_BODY\n\nBETA_UNIQUE_BODY"
    with patch(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction",
        side_effect=_fake_llm,
    ):
        _run_windowed_llm_extraction(
            full,
            chunks,
            {},
            window_size=1,
            window_overlap=0,
            context_mode=CONTEXT_MODE_FULL_DOCUMENT,
            max_window_input_tokens=3500,
        )
    assert all(msg == full for msg in captured)


def test_dual_path_uses_shared_prompt_builder() -> None:
    pipeline = Path("libs/pipeline_graph/subgraphs/_extractor.py").read_text(
        encoding="utf-8"
    )
    worker = Path("services/coding_worker/app/pipeline/llm_extractor.py").read_text(
        encoding="utf-8"
    )
    assert "build_extraction_user_message" in pipeline
    assert "build_extraction_user_message" in worker
    assert "json_mode=True" in pipeline
    assert "json_mode=True" in worker
    assert "extraction_max_tokens" in pipeline
    assert "extraction_max_tokens" in worker


def test_windowed_extraction_keeps_model_identity() -> None:
    chunks = [
        SentenceChunk(sentence_id="c1", text="ALPHA_UNIQUE_BODY", start=0, end=17),
    ]

    def _fake_llm(context, window_chunks, state, **kwargs):
        return {
            "entities": [{"text": "jaundice"}],
            "llm_tokens": {"input_tokens": 1},
            "extraction_model_name": "gpt-5-mini",
            "extraction_model_version": "extraction v1",
            "extraction_model_requested_version": "",
            "extraction_model_version_mismatch": False,
        }

    with patch(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction",
        side_effect=_fake_llm,
    ):
        result = _run_windowed_llm_extraction(
            "ALPHA_UNIQUE_BODY",
            chunks,
            {},
            window_size=10,
            window_overlap=0,
            context_mode=CONTEXT_MODE_WINDOW_LOCAL,
            max_window_input_tokens=3500,
        )
    assert result["extraction_model_name"] == "gpt-5-mini"
    assert result["extraction_model_version"] == "extraction v1"


def test_windowed_extraction_keeps_facts_when_later_window_fails() -> None:
    chunks = [
        SentenceChunk(sentence_id="c1", text="ALPHA_UNIQUE_BODY", start=0, end=17),
        SentenceChunk(sentence_id="c2", text="BETA_UNIQUE_BODY", start=19, end=35),
    ]
    calls = {"n": 0}

    def _fake_llm(context, window_chunks, state, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "entities": [{"text": "jaundice", "start": 0, "end": 8}],
                "llm_tokens": {"input_tokens": 1},
            }
        raise TimeoutError("Request timed out.")

    with patch(
        "libs.pipeline_graph.subgraphs.extraction._run_llm_extraction",
        side_effect=_fake_llm,
    ):
        result = _run_windowed_llm_extraction(
            "ALPHA_UNIQUE_BODY\n\nBETA_UNIQUE_BODY",
            chunks,
            {},
            window_size=1,
            window_overlap=0,
            context_mode=CONTEXT_MODE_WINDOW_LOCAL,
            max_window_input_tokens=3500,
        )
    assert [row["text"] for row in result["entities"]] == ["jaundice"]
    assert result["errors"]
    assert "Request timed out" in result["errors"][0]


def test_span_resolver_still_receives_full_document_kwarg() -> None:
    # Static contract: windowed path passes span_document_text=encounter_text.
    source = Path("libs/pipeline/windowed_llm_extraction.py").read_text(
        encoding="utf-8"
    )
    assert "span_document_text=ctx.encounter_text" in source
