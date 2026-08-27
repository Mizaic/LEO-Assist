"""Record pipeline-rejected phrases into the Phrase mappings inbox.

Atlas trace:
  DI: DI-D90542E5
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-D90542E5")
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")


def normalise_phrase(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def _sentence_for(entity: dict[str, Any], sentences: list[dict[str, Any]]) -> str:
    sid = str(entity.get("__sentence_id") or "")
    for row in sentences:
        if str(row.get("sentence_id") or "") == sid:
            return str(row.get("text") or "")
    return str(entity.get("sentence_text") or "")


def sanitize_sample_sentence(sentence: str) -> str:
    """De-identify phrase sample text before it is stored or shown."""
    if not sentence:
        return ""
    try:
        from libs.utils.deidentify import deidentify_text

        return deidentify_text(sentence, ner=True)
    except Exception:
        logger.debug("Uncoded phrase de-identify failed", exc_info=True)
        return sentence


def _deidentify_sample(sentence: str, span: str) -> str:
    if not sentence:
        return span
    return sanitize_sample_sentence(sentence)


def extractor_source(entity: dict[str, Any]) -> str:
    raw = str(entity.get("__source") or entity.get("source") or "").strip().lower()
    if raw in {"ner", "ner_lab_fallback"}:
        return "model"
    if raw in {"llm", "model"}:
        return raw
    return ""


def unresolved_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for ent in entities:
        if bool(ent.get("_relation_suppressed")):
            continue
        if not ent.get("concept_id") or ent.get("terminology_unresolved"):
            out.append(ent)
    return out


def record_uncoded_phrases(
    entities: list[dict[str, Any]],
    sentences: list[dict[str, Any]] | None = None,
    *,
    run: Callable[..., Any] | None = None,
) -> int:
    """MERGE UncodedPhrase rows for persist-skipped entities. Returns writes."""
    rows = unresolved_entities(entities)
    if not rows:
        return 0
    from libs.cypher.uncoded_phrase_queries import UPSERT_UNCODED_PHRASE

    runner = run
    client = None
    if runner is None:
        from libs.neo4j_client.client import KnowledgeGraphClient

        client = KnowledgeGraphClient()
        runner = client.run
    written = 0
    try:
        for ent in rows:
            key = normalise_phrase(str(ent.get("text") or ""))
            if not key:
                continue
            span = str(ent.get("text") or "")
            sample = _deidentify_sample(_sentence_for(ent, sentences or []), span)
            runner(
                UPSERT_UNCODED_PHRASE,
                phrase_key=key,
                normalized=key,
                extracted_tag=str(ent.get("semantic_tag") or ent.get("label") or ""),
                last_score=float(ent.get("score") or 0.0),
                last_best_term=str(ent.get("rejected_term") or ent.get("term") or ""),
                last_best_concept=str(
                    ent.get("rejected_concept_id") or ent.get("concept_id") or ""
                ),
                last_best_tag=str(
                    ent.get("rejected_tag")
                    or ent.get("semantic_tag")
                    or ent.get("label")
                    or ""
                ),
                sample_span=span,
                sample_sentence=sample,
                last_extractor=extractor_source(ent),
            )
            written += 1
    except Exception:
        logger.warning("Failed to record uncoded phrases", exc_info=True)
        return written
    finally:
        if client is not None:
            client.close()
    return written
