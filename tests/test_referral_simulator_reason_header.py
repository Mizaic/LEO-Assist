"""Slice D: reason-header fixture contract at the harness boundary."""

from __future__ import annotations

from libs.pipeline_graph.subgraphs.referral_reason import _REASON_PATTERNS
from libs.referral_simulator.message import build_referral_received_message
from libs.referral_simulator.scaffold import split_into_chunks

_REASON_HEADER = "The reason for referral is progressive jaundice and weight loss."
_NO_REASON_BODY = (
    "Patient presents with progressive jaundice.\n\n" "LFTs show a cholestatic pattern."
)


def _markdown_with_reason_header() -> str:
    return (
        f"{_REASON_HEADER}\n\n"
        "Patient presents with progressive jaundice.\n\n"
        "LFTs show a cholestatic pattern."
    )


def test_happy_reason_header_chunks_and_handoff_complete():
    """Markdown with eRS header yields chunks + handoff so referral_reason can run."""
    text = _markdown_with_reason_header()
    chunks = split_into_chunks(text, "rr-1:leo-referral-bundle")
    joined = " ".join(c["text"] for c in chunks).lower()
    assert any(pattern in joined for pattern in _REASON_PATTERNS)

    body = build_referral_received_message(
        patient_id="p-1",
        encounter_id="enc-1",
        referral_id="rr-1",
        document_reference_id="rr-1:leo-referral-bundle",
        chunk_ids=[c["id"] for c in chunks],
        run_id="run-1",
    )
    assert body["referral_id"] == "rr-1"
    assert body["chunk_ids"]
    assert body["text_segmentation_mode"] == "document_chunks"
    # Handoff is complete -- missing header is a content issue, not this case.
    assert not (not body.get("referral_id") or not body.get("chunk_ids"))


def test_unhappy_no_reason_header_still_valid_referral_handoff():
    """Without a reason header, scaffold/message remain valid production shape.

    referral_reason may skip for content (no header match), which must not be
    confused with missing referral_id / chunk_ids.
    """
    chunks = split_into_chunks(_NO_REASON_BODY, "rr-2:leo-referral-bundle")
    joined = " ".join(c["text"] for c in chunks).lower()
    assert not any(pattern in joined for pattern in _REASON_PATTERNS)

    body = build_referral_received_message(
        patient_id="p-2",
        encounter_id="enc-2",
        referral_id="rr-2",
        document_reference_id="rr-2:leo-referral-bundle",
        chunk_ids=[c["id"] for c in chunks],
        run_id="run-2",
    )
    assert body["referral_id"] == "rr-2"
    assert len(body["chunk_ids"]) >= 1
    assert body["source_node_type"] == "ReferralRequest"
    # Content may cause referral_reason to skip after header search; handoff OK.
    content_skip_ok = True
    handoff_missing = not body.get("referral_id") or not body.get("chunk_ids")
    assert content_skip_ok and not handoff_missing
