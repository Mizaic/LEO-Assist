"""Attachment chunks across a thread need unique labels and real ids.

The short ``s0, s1, ...`` sentence label exists so the extractor can echo it
back reliably. In the communication thread loader the chunk sentences are
built one message at a time, so the counter restarts and two unrelated
attachments both arrive as ``s0``. Two things then break:

1. The loader deduplicates on ``sentence_id``, so the second message's
   attachment looks like a repeat of the first and is dropped. Clinical text
   disappears with no warning.
2. The label is not the identity of any node, so the :DOCUMENTS write has
   nothing to match and the facts do not persist.

Atlas trace:
  DI: DI-16CE412B, DI-B7A69F26  (fail-closed boundary)
  DO: DO-728930A1
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.communication_thread_loader import (
    build_communication_thread_state,
)

_CHUNK_A = "aaaa1111bbbb2222cccc3333dddd4444"
_CHUNK_B = "eeee5555ffff6666aaaa7777bbbb8888"


def _thread_with_two_attachments() -> list[dict[str, Any]]:
    return [
        {
            "communication_id": "c1",
            "note": "Please advise on this patient.",
            "category": "REQUESTER",
            "sent_datetime": "2026-01-01T09:00:00",
            "attachment_chunks": [
                {
                    "chunk_id": _CHUNK_A,
                    "text": "Haemoglobin 118 g/L, ferritin 8 ug/L.",
                    "ordinal": 0,
                }
            ],
        },
        {
            "communication_id": "c2",
            "note": "Adding the scan report.",
            "category": "REQUESTER",
            "sent_datetime": "2026-01-02T09:00:00",
            "attachment_chunks": [
                {
                    "chunk_id": _CHUNK_B,
                    "text": "Ultrasound shows a 12 mm endometrial polyp.",
                    "ordinal": 0,
                }
            ],
        },
    ]


def _state() -> dict[str, Any]:
    return build_communication_thread_state(
        communication_request_id="cr1",
        thread_rows=_thread_with_two_attachments(),
        cr_attachment_rows=[],
        agr_response_text=None,
    )


def test_both_attachments_survive_the_thread() -> None:
    """Neither attachment may be dropped as a false duplicate."""
    texts = " ".join(str(s.get("text") or "") for s in _state()["sentences"])
    assert "ferritin 8 ug/L" in texts
    assert "endometrial polyp" in texts, (
        "the second message's attachment was dropped as a duplicate because "
        "both chunks were labelled s0"
    )


def test_chunk_labels_are_unique_across_the_thread() -> None:
    ids = [s["sentence_id"] for s in _state()["sentences"]]
    assert len(ids) == len(set(ids)), f"duplicate sentence ids: {ids}"


def test_every_chunk_label_maps_back_to_its_real_chunk_id() -> None:
    """Without this the :DOCUMENTS write matches nothing."""
    state = _state()
    reverse = state.get("chunk_id_by_sentence_id") or {}
    chunk_labels = [
        s["sentence_id"]
        for s in state["sentences"]
        if s.get("persist_source_label") == "Chunk"
    ]
    assert chunk_labels, "expected attachment chunk sentences"
    assert sorted(reverse.get(label, "") for label in chunk_labels) == sorted(
        [_CHUNK_A, _CHUNK_B]
    )


def test_communication_notes_keep_their_own_ids() -> None:
    """Comms notes are matched by their own id and must not be relabelled."""
    ids = [
        s["sentence_id"]
        for s in _state()["sentences"]
        if s.get("persist_source_label") == "Communication"
    ]
    assert "c1" in ids
    assert "c2" in ids


def test_a_genuine_repeat_of_the_same_chunk_is_still_deduplicated() -> None:
    """The same attachment on two messages should appear once."""
    rows = _thread_with_two_attachments()
    rows[1]["attachment_chunks"] = list(rows[0]["attachment_chunks"])
    state = build_communication_thread_state(
        communication_request_id="cr1",
        thread_rows=rows,
        cr_attachment_rows=[],
        agr_response_text=None,
    )
    reverse = state.get("chunk_id_by_sentence_id") or {}
    assert list(reverse.values()).count(_CHUNK_A) == 1
