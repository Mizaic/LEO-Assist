"""Facts must attach to the real :Chunk, not to the model-facing label.

The document-chunks loader labels sentences ``s0, s1, ...`` because the
extractor is primed on few-shot examples using that style. Handed the raw
32-character Neo4j chunk hash instead, the model copied the first hash onto
every fact, and every fact in an 11-chunk referral was attributed to the
document banner.

The label fixes that, but it is not the identity of anything in the graph.
The :DOCUMENTS write matches its source with

    MATCH (src:Chunk {id: $source_id})

so passing ``s0`` matches no node, the write affects zero rows, and the
writer still reports success. That is how a run claims 23 links and
persists none. ``chunk_id_by_sentence_id`` exists in pipeline state for
exactly this translation, and nothing was reading it.

Atlas trace:
  DI: DI-16CE412B, DI-B7A69F26  (fail-closed boundary)
  DO: DO-728930A1
  Risk: R-294446BF
"""

from __future__ import annotations

from typing import Any

from libs.pipeline_graph.subgraphs.persist import resolve_chunk_source_id

_CHUNK_HASH = "b689f4e037be32adc8f70163067c0063"
_OTHER_HASH = "4a8d9afbdb1e46b4caedb0aadcdbece1"


def _reverse() -> dict[str, str]:
    return {"s0": _CHUNK_HASH, "s6": _OTHER_HASH}


def test_short_label_is_translated_to_the_chunk_hash() -> None:
    """s0 must become the Neo4j chunk id the write can actually match."""
    assert resolve_chunk_source_id("s0", _reverse()) == _CHUNK_HASH
    assert resolve_chunk_source_id("s6", _reverse()) == _OTHER_HASH


def test_a_real_chunk_hash_passes_through_unchanged() -> None:
    """Paths that already carry the hash must not be disturbed."""
    assert resolve_chunk_source_id(_CHUNK_HASH, _reverse()) == _CHUNK_HASH


def test_unknown_label_is_reported_not_silently_written() -> None:
    """A label with no chunk behind it must fail closed.

    Returning it unchanged would send ``s3`` into a MATCH that finds
    nothing, and the fact would disappear with the run still green.
    """
    assert resolve_chunk_source_id("s3", _reverse()) is None


def test_empty_label_is_reported() -> None:
    assert resolve_chunk_source_id("", _reverse()) is None


def test_missing_reverse_map_passes_a_hash_through() -> None:
    """Encounter-sentence mode has no map and already uses real ids."""
    assert resolve_chunk_source_id(_CHUNK_HASH, {}) == _CHUNK_HASH


def test_missing_reverse_map_rejects_a_short_label() -> None:
    """Without a map an ``s0`` cannot be turned into anything matchable."""
    assert resolve_chunk_source_id("s0", {}) is None


# ---------------------------------------------------------------------------
# The write path must use the translation
# ---------------------------------------------------------------------------


def _payload_for(state: dict[str, Any]) -> list[dict[str, Any]]:
    from libs.pipeline_graph.subgraphs.persist import build_sentences_payload

    return build_sentences_payload(
        state,
        terms_by_sentence={"s6": [{"text": "vaginal discharge"}]},
    )


def test_payload_carries_the_chunk_hash_for_the_write() -> None:
    """What reaches documents_queries must be matchable in the graph."""
    state = {
        "sentences": [
            {"sentence_id": "s0", "text": "--- Document: referral.doc ---"},
            {"sentence_id": "s6", "text": "Section C: vaginal discharge noted"},
        ],
        "chunk_id_by_sentence_id": _reverse(),
        "text_segmentation_mode": "document_chunks",
        "encounter_text": "--- Document: referral.doc ---",
    }

    payload = _payload_for(state)
    carrying = [row for row in payload if row["terms"]]
    assert len(carrying) == 1
    assert carrying[0]["sentence_id"] == _OTHER_HASH, (
        "the write matches MATCH (src:Chunk {id: $source_id}); a short label "
        "matches nothing and the fact is silently lost"
    )


def test_payload_keeps_the_sentence_text_with_the_translated_id() -> None:
    """Translation must not cost the evidence sentence."""
    state = {
        "sentences": [
            {"sentence_id": "s6", "text": "Section C: vaginal discharge noted"},
        ],
        "chunk_id_by_sentence_id": _reverse(),
        "text_segmentation_mode": "document_chunks",
        "encounter_text": "Section C: vaginal discharge noted",
    }

    payload = _payload_for(state)
    assert payload[0]["text"] == "Section C: vaginal discharge noted"
