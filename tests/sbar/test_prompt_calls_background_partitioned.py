"""VT-LEO-AI-520 TC-001..TC-007: call_background partition + map + stitch.

Verifies the new ``call_background`` flow:

  - Single-partition path is byte-for-byte identical to the legacy
    single-call flow: no part heading, no notice (TC-001).
  - Multi-partition path runs MAP per partition and stitches the
    partials deterministically into one Background, with one
    ``### Part i of N -- records {a}-{b}`` heading per part. Source
    record ids are exposed via the structured ``parts`` field
    (``part["source_ids"]``), NOT embedded as inline HTML comments
    inside the rendered markdown body (TC-002).
  - Per-part failures are contained: surviving parts still land,
    the failed part renders as a placeholder pointing the reviewer
    at the errors panel, and the call returns
    ``error_code="background_part_failed"`` (TC-003).
  - There is NEVER a second LLM call to "merge" partials. The
    invoker count must equal the partition count exactly (TC-004).
  - too_many_parts produces the friendly "pick fewer records"
    error and never invokes the LLM (TC-005).
  - progress_cb is called with phase="map" once per partition,
    once at start and once at end. There is no reduce phase
    (TC-006).

See DI-LEO-AI-522 / DO-LEO-AI-521 / R-LEO-AI-510.
"""

from __future__ import annotations

import asyncio
import os
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


def _force_multi_part_env() -> None:
    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "8000"


def _clear_multi_part_env() -> None:
    os.environ.pop("SBAR_BACKGROUND_MAX_INPUT_TOKENS", None)


def test_single_partition_returns_no_part_heading_and_no_notice() -> None:
    """TC-001: legacy under-budget path is unchanged (no headings, no notice)."""
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
    assert "### Part" not in result["markdown"]
    assert len(calls) == 1
    assert calls[0] == "SYSTEM:sbar_background"
    assert len(result["parts"]) == 1
    assert result["parts"][0]["status"] == "completed"


def test_multi_partition_stitches_deterministically_with_part_headings() -> None:
    """TC-002: N MAP calls, deterministic stitch, one heading per part."""
    sources = _sources(12, text_len=4000)
    seen_systems: list[str] = []

    async def _invoker(system, user, **_kw):
        seen_systems.append(system)
        idx = len(seen_systems)
        return {"background_markdown": f"part-md-{idx}"}

    _force_multi_part_env()
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        _clear_multi_part_env()

    assert result["error"] is None
    md = result["markdown"]
    n = len(result["parts"])
    assert n >= 2
    # All MAP calls used the standard background prompt -- no second
    # "reduce" prompt fetched or invoked.
    assert all(s == "SYSTEM:sbar_background" for s in seen_systems)
    # One heading per part, in order, with records {a}-{b} or
    # "record N" formatting.
    assert "### Part 1 of" in md
    assert f"### Part {n} of {n}" in md
    # Every per-part body lands under its heading.
    for i in range(1, n + 1):
        assert f"part-md-{i}" in md
    # Source-record IDs MUST live on the structured ``parts`` field,
    # not as inline HTML comments inside the rendered markdown.
    # Markdown renderers (Tiptap with html=false) treat raw HTML
    # comments as visible plain text, leaking record UUIDs into the
    # user-facing view.
    assert "<!-- sources" not in md
    assert all("enc-" not in line for line in md.splitlines())
    flat_source_ids = {
        sid for p in result["parts"] for sid in (p.get("source_ids") or [])
    }
    assert len(flat_source_ids) >= 1
    assert "summarised them in" in (result["notice"] or "")


def test_list_payload_is_read_as_background_markdown() -> None:
    """Live Azure reply can be a JSON list. That must still become Background."""
    sources = _sources(2, text_len=200)

    async def _invoker(system, user, **_kw):
        return [{"background_markdown": "- Postmenopausal bleeding. [2026-06-23]"}]

    result = asyncio.run(
        prompt_calls.call_background(
            sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
        )
    )

    assert result.get("error") is None
    assert "Postmenopausal bleeding" in (result["markdown"] or "")


def test_non_object_payload_does_not_crash_call_background() -> None:
    """A bare string reply must not raise; the section fails closed."""
    sources = _sources(2, text_len=200)

    async def _invoker(system, user, **_kw):
        return "not a json object"

    result = asyncio.run(
        prompt_calls.call_background(
            sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
        )
    )

    assert result["markdown"] == ""
    assert result["error_code"] in {"invalid_json", "missing_section"}
    assert "Background" in (result["error"] or "")


def test_per_part_failure_is_contained_and_surfaced_as_part_failed() -> None:
    """TC-003: one MAP fails -> stitch with placeholder + part_failed."""
    sources = _sources(12, text_len=4000)
    seq = {"n": 0}

    async def _invoker(system, user, **_kw):
        seq["n"] += 1
        if seq["n"] == 2:
            return {"error": "Input is too long for requested model"}
        return {"background_markdown": f"bullet-{seq['n']}"}

    _force_multi_part_env()
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        _clear_multi_part_env()

    assert result["error_code"] == "background_part_failed"
    md = result["markdown"]
    assert "### Part 2 of" in md
    assert "could not be generated" in md
    statuses = [p["status"] for p in result["parts"]]
    assert "failed" in statuses
    assert "completed" in statuses


def test_no_reduce_call_is_ever_made() -> None:
    """TC-004: invoker is called exactly once per partition; never more."""
    sources = _sources(12, text_len=4000)
    seen_systems: list[str] = []

    async def _invoker(system, user, **_kw):
        seen_systems.append(system)
        # If the implementation ever requests the reduce prompt,
        # fail loudly.
        assert (
            system != "SYSTEM:sbar_background_reduce"
        ), "call_background must not invoke a reduce prompt"
        return {"background_markdown": "ok"}

    _force_multi_part_env()
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        _clear_multi_part_env()

    assert len(seen_systems) == len(result["parts"])
    assert all(s == "SYSTEM:sbar_background" for s in seen_systems)


def test_too_many_parts_returns_friendly_error_and_does_not_invoke_llm() -> None:
    """TC-005: refusal -> too_many_parts code, no LLM invocation."""
    sources = _sources(50, text_len=4000)
    invoked = {"n": 0}

    async def _invoker(system, user, **_kw):
        invoked["n"] += 1
        return {"background_markdown": "should-never-be-called"}

    os.environ["SBAR_BACKGROUND_MAX_INPUT_TOKENS"] = "2500"
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        _clear_multi_part_env()

    assert invoked["n"] == 0
    assert result["markdown"] == ""
    assert result["error_code"] == "too_many_parts"
    assert "8 parts" in (result["error"] or "")
    assert "ValidationException" not in (result["error"] or "")


def test_progress_cb_is_called_per_part_with_no_reduce_phase() -> None:
    """TC-006: progress_cb gets one started+completed pair per part, no reduce."""
    sources = _sources(12, text_len=4000)
    events: list[dict[str, Any]] = []

    async def _invoker(system, user, **_kw):
        return {"background_markdown": "bullets"}

    def _cb(ev: dict[str, Any]) -> None:
        events.append(ev)

    _force_multi_part_env()
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources,
                [],
                invoker=_invoker,
                prompt_fetcher=_prompt_fetcher,
                progress_cb=_cb,
            )
        )
    finally:
        _clear_multi_part_env()

    n = len(result["parts"])
    assert n >= 2
    map_started = [
        e for e in events if e["phase"] == "map" and e["status"] == "started"
    ]
    map_completed = [
        e for e in events if e["phase"] == "map" and e["status"] == "completed"
    ]
    reduce_events = [e for e in events if e["phase"] == "reduce"]
    assert len(map_started) == n
    assert len(map_completed) == n
    assert reduce_events == []
    # Each map event carries the part index/total.
    for e in map_started:
        assert e["part_index"] >= 1
        assert e["part_total"] == n


def test_stitched_markdown_includes_records_range_and_no_inline_source_ids() -> None:
    """TC-007: stitched headings show 'records {a}-{b}'; source ids are
    surfaced via the structured ``parts`` field, not as inline HTML
    comments inside the rendered markdown.
    """
    sources = _sources(12, text_len=4000)

    async def _invoker(system, user, **_kw):
        return {"background_markdown": "ok"}

    _force_multi_part_env()
    try:
        result = asyncio.run(
            prompt_calls.call_background(
                sources, [], invoker=_invoker, prompt_fetcher=_prompt_fetcher
            )
        )
    finally:
        _clear_multi_part_env()

    md = result["markdown"]
    # At least one heading must show a record range like
    # "records 1-X" since N >= 2 partitions split the 12 inputs.
    assert "records 1" in md
    # The rendered markdown MUST NOT carry the legacy
    # ``<!-- sources: ... -->`` HTML comments. Markdown renderers
    # (Tiptap with html=false) treat those as visible text, leaking
    # raw record UUIDs into the user-facing view.
    assert "<!-- sources" not in md
    for i in range(12):
        assert f"enc-{i}" not in md
    # The source ids MUST instead live on the structured ``parts``
    # field so the UI can render them in a separate disclosure.
    parts = result["parts"]
    assert isinstance(parts, list) and len(parts) >= 2
    flat_source_ids = {sid for p in parts for sid in (p.get("source_ids") or [])}
    for i in range(12):
        assert f"enc-{i}" in flat_source_ids
