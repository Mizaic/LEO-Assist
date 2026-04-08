from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from libs.ner.extractor_contract import CONTRACT_VERSION, ExtractionItem
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stream C -- LLM auto-detected surface form creation (daily cap)
# ---------------------------------------------------------------------------

_DAILY_CAP = 20
_AUTO_SURFACE_LOCK = threading.Lock()
_auto_surface_count: int = 0
_auto_surface_date: str = ""  # ISO date string (YYYY-MM-DD)

_COUNT_PENDING_SURFACE_FORMS = """
MATCH (t:SurfaceFormTask)
WHERE t.status = 'pending'
RETURN count(t) AS n
"""

_MAPS_TO_EXISTS = """
MATCH (sf:SurfaceForm {normalized: $normalized})-[:MAPS_TO]->()
RETURN count(sf) AS n
"""


def _today_utc() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _auto_surface_count_today() -> int:
    """Return the current daily creation count, resetting at midnight UTC."""
    global _auto_surface_count, _auto_surface_date
    today = _today_utc()
    if _auto_surface_date != today:
        _auto_surface_count = 0
        _auto_surface_date = today
    return _auto_surface_count


def _increment_auto_surface() -> None:
    global _auto_surface_count, _auto_surface_date
    _auto_surface_date = _today_utc()
    _auto_surface_count += 1


def _try_create_auto_surface_form_task(
    normalized: str,
    entity_text: str,
    concept_id: str,
    concept_term: str,
    score: float,
) -> None:
    """Create a SurfaceFormTask for a high-confidence auto-detected term.

    Guards: daily cap of 20, pending backlog cap of 50, MAPS_TO already exists.
    All guards are checked inside a lock to avoid race conditions.
    """
    try:
        from libs.neo4j_client.client import KnowledgeGraphClient
        from libs.cypher.surface_form_task_queries import (
            UPSERT_SURFACE_FORM_TASK,
            make_surface_form_task_id,
        )
    except Exception as exc:
        logger.debug("Stream C: could not import Neo4j deps: %s", exc)
        return

    with _AUTO_SURFACE_LOCK:
        if _auto_surface_count_today() >= _DAILY_CAP:
            logger.debug(
                "Stream C: daily cap (%d) reached -- skipping %r",
                _DAILY_CAP, entity_text,
            )
            return

        try:
            client = KnowledgeGraphClient()
            with client.session() as session:
                maps_row = session.run(
                    _MAPS_TO_EXISTS, normalized=normalized
                ).single()
                if maps_row and maps_row["n"] > 0:
                    logger.debug(
                        "Stream C: MAPS_TO already exists for %r -- skip",
                        normalized,
                    )
                    client.close()
                    return

                pending_row = session.run(_COUNT_PENDING_SURFACE_FORMS).single()
                pending = int(pending_row["n"]) if pending_row else 0
                if pending > 50:
                    logger.info(
                        "Stream C: pending backlog %d > 50 -- skipping %r",
                        pending, entity_text,
                    )
                    client.close()
                    return

                task_id = make_surface_form_task_id(
                    candidate_id="llm_auto_detected",
                    entity_text=normalized,
                    current_concept="",
                )
                session.run(
                    UPSERT_SURFACE_FORM_TASK,
                    task_id=task_id,
                    entity_text=entity_text,
                    current_concept="",
                    current_term="",
                    suggested_concept=concept_id,
                    suggested_term=concept_term,
                    candidates_json="[]",
                    context_text="",
                    candidate_id="",
                    confidence=score,
                    source="llm_auto_detected",
                )
            client.close()
            _increment_auto_surface()
            logger.info(
                "Stream C: created SurfaceFormTask for %r -> %s (score=%.2f)",
                entity_text, concept_id, score,
            )
        except Exception as exc:
            logger.warning(
                "Stream C: failed to create SurfaceFormTask for %r: %s",
                entity_text, exc,
            )

# ---------------------------------------------------------------------------
# Output-format instructions appended to the system prompt at runtime.
# The main system prompt intentionally omits this so examples can be stored
# separately in Neo4j and injected by the prompt manager.
# ---------------------------------------------------------------------------
_OUTPUT_FORMAT = """

## Output Format

Return ONLY valid JSON — no prose before or after. Schema:
{
  "terms": [
    {
      "sentence_id": "<id from the Sentences list>",
      "text": "<exact span as written in the sentence>",
      "lookup_term": "<standard clinical term for SNOMED lookup>",
      "semantic_tag": "<disorder|finding|procedure|substance|product|observable entity|situation|regime/therapy|staging scale>",
      "assertion": "<present|absent|refuted|possible|historical|planned|hypothetical|family|declined|cancelled>",
      "numeric_value": "<numeric value if observable entity, else empty string>",
      "unit": "<unit if observable entity, else empty string>",
      "reference_range": "<range if present, else empty string>",
      "modifiers": {}
    }
  ]
}

If no codeable entities are found, return {"terms": []}.
"""

_VALID_ASSERTIONS = {
    "present",
    "absent",
    "refuted",
    "possible",
    "historical",
    "planned",
    "hypothetical",
    "family",
    "declined",
    "cancelled",
}

_ASSERTION_TO_CONTEXT: dict[str, dict[str, bool]] = {
    "present": {"negated": False, "declined": False, "cancelled": False},
    "absent": {"negated": True, "declined": False, "cancelled": False},
    "refuted": {"negated": True, "declined": False, "cancelled": False},
    "possible": {"negated": False, "declined": False, "cancelled": False},
    "historical": {"negated": False, "declined": False, "cancelled": False},
    "planned": {"negated": False, "declined": False, "cancelled": False},
    "hypothetical": {"negated": False, "declined": False, "cancelled": False},
    "family": {"negated": False, "declined": False, "cancelled": False},
    "declined": {"negated": False, "declined": True, "cancelled": False},
    "cancelled": {"negated": False, "declined": False, "cancelled": True},
}

_TNM_TRIPLET_RE = re.compile(
    r"\b(?:[cpyr]?t[0-4](?:[a-c])?)\s*(?:[cpyr]?n[0-3](?:[a-c])?)\s*(?:[cpyr]?m[0-1](?:[a-c])?)\b",
    re.IGNORECASE,
)
_TNM_COMPONENT_RE = re.compile(r"[cpyr]?[tnm][0-4](?:[a-c])?", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedTerm:
    sentence_id: str
    text: str
    lookup_term: str
    semantic_tag: str
    assertion: str
    context: dict[str, Any] = field(default_factory=dict)
    modifiers: dict[str, Any] = field(default_factory=dict)


class LLMExtractor:
    source = "llm"

    def __init__(self, model_id: str = "llm-unconfigured") -> None:
        self.model_id = model_id or "llm-unconfigured"
        self.model_version = "1.0"
        self.client = self._init_client()
        self.enabled = bool(self.client)
        self.model_name = self.client.model_id if self.client else self.model_id

    def _init_client(self):
        """Return a wired LLMClient or None if Bedrock is not configured."""
        try:
            from libs.llm_client.factory import create_llm
            return create_llm(
                provider=None,   # reads PIPELINE_MODEL_PROVIDER env, defaults "aws"
                tier="small",    # Haiku for extraction — fast, low cost, structured task
            )
        except Exception as exc:
            logger.warning("LLMExtractor: could not initialise client: %s", exc)
            return None

    def is_available(self) -> bool:
        return bool(self.enabled)

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
    ) -> list[ExtractionItem]:
        """Call the LLM and return ExtractionItems for all sentences."""
        if not self.enabled or not sentences:
            return []
        system = EXTRACTION_SYSTEM_V1 + _OUTPUT_FORMAT
        user_msg = self._build_user_prompt(encounter_text, sentences)
        try:
            resp = self.client.converse(
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=2048,
                temperature=0.0,
            )
            payload = self._parse_json(resp.text)
        except Exception as exc:
            logger.error("LLMExtractor.extract_batch failed: %s", exc)
            return []
        terms = self._parse_terms(payload, sentences)
        return [
            extracted_term_to_item(
                t,
                source=self.source,
                model_name=self.model_name,
                model_version=self.model_version,
            )
            for t in terms
        ]

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        raw = raw.strip()
        # Strip markdown fence if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            raw = "\n".join(inner).strip()
        # Find leading brace in case of preamble
        if not raw.startswith("{"):
            idx = raw.find("{")
            if idx >= 0:
                raw = raw[idx:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            end = raw.rfind("}")
            if end > 0:
                try:
                    return json.loads(raw[: end + 1])
                except json.JSONDecodeError:
                    pass
            return {}

    @staticmethod
    def _build_user_prompt(encounter_text: str, sentences: list) -> str:
        parts = [f"ENCOUNTER TEXT:\n{encounter_text}\n\nSENTENCES TO EXTRACT FROM:"]
        for sentence in sentences:
            sid = getattr(sentence, "sentence_id", "s0")
            text = getattr(sentence, "text", "")
            parts.append(f"[{sid}] {text}")
        return "\n".join(parts)

    def _parse_terms(self, payload: dict[str, Any], sentences: list) -> list[ExtractedTerm]:
        terms = payload.get("terms") or []
        if not isinstance(terms, list):
            return []
        valid_sentence_ids = {getattr(sentence, "sentence_id", "") for sentence in sentences}
        results: list[ExtractedTerm] = []
        seen: set[tuple[str, str, str]] = set()  # (text_lower, tag, assertion)
        for term in terms:
            if not isinstance(term, dict):
                continue
            sentence_id = str(term.get("sentence_id") or "")
            if valid_sentence_ids and sentence_id not in valid_sentence_ids:
                continue
            text = str(term.get("text") or "").strip()
            if not text:
                continue
            assertion = str(term.get("assertion") or "present").lower()
            if assertion not in _VALID_ASSERTIONS:
                assertion = "present"
            dedup_key = (text.lower(), str(term.get("semantic_tag") or ""), assertion)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            context = dict(_ASSERTION_TO_CONTEXT.get(assertion, _ASSERTION_TO_CONTEXT["present"]))
            results.append(
                ExtractedTerm(
                    sentence_id=sentence_id or "s0",
                    text=text,
                    lookup_term=str(term.get("lookup_term") or text),
                    semantic_tag=str(term.get("semantic_tag") or "finding"),
                    assertion=assertion,
                    context=context,
                    modifiers=dict(term.get("modifiers") or {}),
                )
            )
            # Deterministic TNM split:
            # If the model outputs a single staging-scale token like T2N1M0,
            # also emit T/N/M component entities so terminology resolution can
            # map each axis independently.
            results.extend(
                self._split_tnm_components(
                    sentence_id=sentence_id or "s0",
                    text=text,
                    semantic_tag=str(term.get("semantic_tag") or ""),
                    assertion=assertion,
                )
            )
        return results

    @staticmethod
    def _split_tnm_components(
        *,
        sentence_id: str,
        text: str,
        semantic_tag: str,
        assertion: str,
    ) -> list[ExtractedTerm]:
        tag = semantic_tag.strip().lower()
        if tag != "staging scale":
            return []
        if not _TNM_TRIPLET_RE.search(text):
            return []
        components = [m.group(0).upper() for m in _TNM_COMPONENT_RE.finditer(text)]
        if len(components) < 3:
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for comp in components:
            key = comp.lower()
            axis = key[0] if key[0] in {"t", "n", "m"} else key[1]
            if axis in seen:
                continue
            seen.add(axis)
            deduped.append(comp)
        out: list[ExtractedTerm] = []
        for comp in deduped:
            out.append(
                ExtractedTerm(
                    sentence_id=sentence_id,
                    text=comp,
                    lookup_term=comp,
                    semantic_tag="observable entity",
                    assertion=assertion,
                    context=dict(_ASSERTION_TO_CONTEXT.get(assertion, _ASSERTION_TO_CONTEXT["present"])),
                    modifiers={"derived_from_tnm_triplet": text},
                )
            )
        return out


def maybe_create_surface_form_tasks(
    items: list[ExtractionItem],
    resolved: dict[str, Any],
) -> None:
    """Stream C: queue auto-detected surface form tasks for high-confidence terms.

    Called after terminology API resolution. For each term with a resolver
    score >= 0.90 and no existing MAPS_TO relationship, create a
    SurfaceFormTask (subject to daily cap and pending backlog cap).

    Non-blocking: all Neo4j errors are logged and swallowed.
    """
    seen: set[str] = set()
    for item in items:
        lookup = item.normalized or item.text
        if not lookup:
            continue
        normalized = re.sub(r"\s+", " ", lookup.strip().lower())
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates = resolved.get(lookup) or resolved.get(item.text) or []
        if not candidates:
            continue
        best = candidates[0]
        score = float(best.get("score") or 0.0)
        if score < 0.90:
            continue
        concept_id = str(best.get("snomed_concept_id") or "").strip()
        concept_term = str(best.get("snomed_term") or lookup).strip()
        if not concept_id:
            continue
        _try_create_auto_surface_form_task(
            normalized=normalized,
            entity_text=item.text,
            concept_id=concept_id,
            concept_term=concept_term,
            score=score,
        )


def extracted_term_to_item(term: ExtractedTerm, *, source: str, model_name: str, model_version: str) -> ExtractionItem:
    return ExtractionItem(
        sentence_id=term.sentence_id,
        text=term.text,
        span_start=0,
        span_end=len(term.text),
        semantic_tag=term.semantic_tag,
        assertion=term.assertion,
        confidence=1.0,
        normalized=term.lookup_term,
        source_meta={"context": term.context, "modifiers": term.modifiers},
        source=source,
        model_name=model_name,
        model_version=model_version,
        contract_version=CONTRACT_VERSION,
    )
