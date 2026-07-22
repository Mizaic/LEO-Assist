"""Full source-record text threading through the Background disclosure.

Pins the fix for the SBAR widget "source records" dialog only ever
showing a 200-char preview (e.g. "Chunk: 5b6f45bbe4...7f8a0e -- Dear
Colleague,") instead of the record text a reviewer actually needs to
check the AI-generated Background against source. ``full_text`` is
threaded end to end:

  PartitionDescriptor.full_text (background_partitioner.py)
    -> _sources_from_part()["full_text"] (prompt_calls.py)
    -> persisted on :Assessment.background_parts
    -> _normalise_source_ref()["fullText"] (sdk_auth.py, camelCase)

This file covers the middle hop (prompt_calls._sources_from_part /
_build_part_summary). The two ends are covered by
tests/sbar/test_background_partitioner.py and tests/test_sdk_auth.py.

Atlas trace:
  DI: DI-85C95E53, DI-A898556B
  Risk mitigated: R-4965BCD2
"""

from __future__ import annotations

from libs.sbar.background_partitioner import PartitionDescriptor
from libs.sbar.prompt_calls import _build_part_summary, _sources_from_part


def _part(descriptors: list) -> dict:
    return {
        "part_index": 1,
        "part_total": 1,
        "record_count": len(descriptors),
        "record_range": (1, len(descriptors)),
        "descriptors": descriptors,
        "source_ids": [d.source_id if hasattr(d, "source_id") else d["source_id"] for d in descriptors],
    }


def test_sources_from_part_carries_full_text_from_descriptor_objects() -> None:
    """PartitionDescriptor is a dataclass -- attribute-access branch."""
    descriptor = PartitionDescriptor(
        source_id="chunk-1",
        source_label="Chunk",
        slice_index=1,
        slice_total=1,
        char_count=42,
        preview="Dear Colleague,",
        full_text="Dear Colleague,\n\nFull letter text here.",
    )
    sources = _sources_from_part(_part([descriptor]))
    assert len(sources) == 1
    assert sources[0]["id"] == "chunk-1"
    assert sources[0]["preview"] == "Dear Colleague,"
    assert sources[0]["full_text"] == "Dear Colleague,\n\nFull letter text here."


def test_sources_from_part_carries_full_text_from_dict_descriptors() -> None:
    """Descriptors round-tripped through JSON arrive as plain dicts."""
    descriptor = {
        "source_id": "enc-1",
        "source_label": "Encounter",
        "preview": "Progressive jaundice.",
        "full_text": "Progressive jaundice for six weeks, weight loss.",
    }
    sources = _sources_from_part(_part([descriptor]))
    assert sources[0]["full_text"] == (
        "Progressive jaundice for six weeks, weight loss."
    )


def test_sources_from_part_defaults_full_text_to_empty_string() -> None:
    """Legacy descriptors without full_text must not raise KeyError."""
    descriptor = PartitionDescriptor(
        source_id="enc-legacy",
        source_label="Encounter",
        slice_index=1,
        slice_total=1,
        char_count=10,
        preview="Legacy preview.",
    )
    sources = _sources_from_part(_part([descriptor]))
    assert sources[0]["full_text"] == ""
    assert sources[0]["preview"] == "Legacy preview."


def test_sources_from_part_bare_source_ids_fallback_has_empty_full_text() -> None:
    """The no-descriptors fallback path (bare source_ids) is still valid."""
    sources = _sources_from_part({"source_ids": ["enc-9"], "descriptors": []})
    assert sources == [
        {
            "id": "enc-9",
            "type": "Record",
            "label": "enc-9",
            "preview": "",
            "full_text": "",
        }
    ]


def test_build_part_summary_includes_full_text_in_persisted_sources() -> None:
    """The persisted :Assessment.background_parts payload carries it too."""
    descriptor = PartitionDescriptor(
        source_id="chunk-2",
        source_label="Chunk",
        slice_index=1,
        slice_total=1,
        char_count=20,
        preview="Short preview",
        full_text="Short preview but much longer full text for the reviewer.",
    )
    part = {
        "part_index": 1,
        "part_total": 1,
        "record_count": 1,
        "record_range": (1, 1),
        "source_ids": ["chunk-2"],
        "descriptors": [descriptor],
    }
    summary = _build_part_summary(part)
    assert summary["sources"][0]["full_text"] == (
        "Short preview but much longer full text for the reviewer."
    )
