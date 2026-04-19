"""VT-LEO-AI-514 TC-014..TC-019: call_background partition + map + reduce.

Verifies the new ``call_background`` flow:
  - Single-partition path is byte-for-byte identical to the legacy
    single-call flow (TC-014).
  - Multi-partition path runs MAP per partition and REDUCE once,
    returning the merged markdown when all parts succeed (TC-015).
  - When REDUCE fails, the call falls back to deterministic stitching
    with clear "Part i of N" subheadings and a notice (TC-016).
  - Per-part failures are contained: the surviving parts still land
    and the failed part is rendered as a placeholder, with a
    structured background_part_failed error (TC-017).
  - too_many_parts produces the friendly "pick fewer records" error
    and never invokes the LLM (TC-018).
  - progress_cb is called with phase=map per part and phase=reduce
    when REDUCE runs (TC-019).

See DI-LEO-AI-513 / DI-LEO-AI-516 / DI-LEO-AI-517.
"""

from __future__ import annotations

import asyncio
from typing import Any

from libs.sbar import prompt_calls
from libs.sbar.source_resolver import ResolvedSource


def _sources(n: int, text_len: int) -> list[ResolvedSource]:
    return [
        ResolvedSource(
            source_label="Encounter",
            source_id=f"enc-{i}",
            text="x" * text_len,
            codes=[],
            metadata={},
        )
        for i in range(n)
    ]


def _prompt_fetcher(name: str) -> str:
    return f"SYSTEM:{name}"


def test_single_partition_returns_no_split_notice_and_no_reduce() -> None:
    """TC-014: the legacy under-budget path stays unchanged."""
    sources = _sources(2, text_len=200)
    calls: list[str] = []

    async def _invoker(system, user, **_kw):
        calls.append(system)
        return {"background_markdown": "single-part-md"}

    result = asyncio.run(
        prompt_calls.call_background(
            sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
        )
    )

    assert result["markdown"] == "single-part-md"
    assert result["error"] is None
    assert result["notice"] is None
    assert len(calls) == 1
    assert calls[0] == "SYSTEM:sbar_background"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["status"] == "completed"


def test_multi_partition_runs_map_then_reduce_when_all_parts_succeed() -> None:
    """TC-015: N MAP calls + 1 REDUCE call, merged markdown returned."""
    sources = _sources(12, text_len=4000)
    seen_systems: list[str] = []

    async def _invoker(system, user, **_kw):
        seen_systems.append(system)
        if "sbar_background_reduce" in system:
            return {
                "background_markdown": "MERGED",
                "citations": [],
                "missing": [],
                "conflicts": [],
            }
        return {"background_markdown": f"part-md-{len(seen_systems)}"}

    # Tight budget forces multi-part.
    import os

    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "8000"
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        del os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"]

    assert result["error"] is None
    assert result["markdown"] == "MERGED"
    assert result["notice"] and "summarised them in" in result["notice"]
    # MAP calls + 1 REDUCE.
    map_calls = [s for s in seen_systems if s == "SYSTEM:sbar_background"]
    reduce_calls = [s for s in seen_systems if s == "SYSTEM:sbar_background_reduce"]
    assert len(map_calls) >= 2
    assert len(reduce_calls) == 1
    assert all(p["status"] == "completed" for p in result["parts"])


def test_reduce_failure_falls_back_to_deterministic_stitch_with_notice() -> None:
    """TC-016: REDUCE fails -> stitch each part under a Part i of N header."""
    sources = _sources(12, text_len=4000)
    map_count = {"n": 0}

    async def _invoker(system, user, **_kw):
        if "sbar_background_reduce" in system:
            return {"error": "boom"}
        map_count["n"] += 1
        return {"background_markdown": f"bullet-list-{map_count['n']}"}

    import os

    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "8000"
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        del os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"]

    assert result["error_code"] == "reduce_failed"
    assert "side by side" in (result["notice"] or "")
    md = result["markdown"]
    # Deterministic stitch headers.
    assert "### Part 1 of" in md
    assert f"### Part {len(result['parts'])} of {len(result['parts'])}" in md
    # Every per-part bullet list shows up.
    for i in range(1, map_count["n"] + 1):
        assert f"bullet-list-{i}" in md


def test_per_part_failure_is_contained_and_surfaced_as_part_failed() -> None:
    """TC-017: one MAP fails -> stitch + background_part_failed."""
    sources = _sources(12, text_len=4000)
    seq = {"n": 0}

    async def _invoker(system, user, **_kw):
        if "sbar_background_reduce" in system:
            # Should never be called when there is a per-part
            # failure; assert this by raising.
            raise AssertionError("reduce ran despite per-part failure")
        seq["n"] += 1
        if seq["n"] == 2:
            return {"error": "Input is too long for requested model"}
        return {"background_markdown": f"bullet-{seq['n']}"}

    import os

    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "8000"
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        del os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"]

    assert result["error_code"] == "background_part_failed"
    md = result["markdown"]
    assert "### Part 2 of" in md
    assert "did not finish" in md
    # Surviving parts still landed.
    statuses = [p["status"] for p in result["parts"]]
    assert "failed" in statuses
    assert "completed" in statuses


def test_too_many_parts_returns_friendly_error_and_does_not_invoke_llm() -> None:
    """TC-018: refusal -> too_many_parts code, no LLM invocation."""
    sources = _sources(50, text_len=4000)
    invoked = {"n": 0}

    async def _invoker(system, user, **_kw):
        invoked["n"] += 1
        return {"background_markdown": "should-never-be-called"}

    import os

    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "2500"
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        del os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"]

    assert invoked["n"] == 0
    assert result["markdown"] == ""
    assert result["error_code"] == "too_many_parts"
    assert "8 parts" in (result["error"] or "")
    assert "ValidationException" not in (result["error"] or "")


def test_progress_cb_is_called_per_part_and_for_reduce() -> None:
    """TC-019: progress_cb gets a map event per part + reduce events."""
    sources = _sources(12, text_len=4000)
    events: list[dict[str, Any]] = []

    async def _invoker(system, user, **_kw):
        if "sbar_background_reduce" in system:
            return {"background_markdown": "MERGED"}
        return {"background_markdown": "bullets"}

    def _cb(ev: dict[str, Any]) -> None:
        events.append(ev)

    import os

    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "8000"
    try:
        asyncio.run(
            prompt_calls.call_background(
                sources,
                [],
                invoker=_invoker,
                prompt_fetcher=_prompt_fetcher,
                progress_cb=_cb,
            )
        )
    finally:
        del os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"]

    map_started = [
        e for e in events if e["phase"] == "map" and e["status"] == "started"
    ]
    map_completed = [
        e for e in events if e["phase"] == "map" and e["status"] == "completed"
    ]
    reduce_events = [e for e in events if e["phase"] == "reduce"]
    assert len(map_started) >= 2
    assert len(map_started) == len(map_completed)
    # Each map event must carry the part index/total.
    for e in map_started:
        assert e["part_index"] >= 1
        assert e["part_total"] >= 2
    assert any(e["status"] == "started" for e in reduce_events)
    assert any(e["status"] == "completed" for e in reduce_events)
