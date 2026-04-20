"""Auto-stamped Atlas trace.

Atlas trace:
  DO: DO-0289F3A5
  Also implements: DO-64BDC193, DO-6CD07544, DO-94EAC337
  DI: DI-48AD06E5, DI-88C8BBCD, DI-A0579B64, DI-A0C90595, DI-F298AE65
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0289F3A5")
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from libs.ner.extractor_contract import CONTRACT_VERSION, ExtractionItem
from libs.ner.span_resolver import SpanResolver
from libs.pipeline_graph.subgraphs._extractor import assemble_system_prompt
from libs.prompts.registry import get_prompt_config

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
                _DAILY_CAP,
                entity_text,
            )
            return

        try:
            client = KnowledgeGraphClient()
            with client.session() as session:
                maps_row = session.run(_MAPS_TO_EXISTS, normalized=normalized).single()
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
                        pending,
                        entity_text,
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
                entity_text,
                concept_id,
                score,
            )
        except Exception as exc:
            logger.warning(
                "Stream C: failed to create SurfaceFormTask for %r: %s",
                entity_text,
                exc,
            )


# ---------------------------------------------------------------------------
# Output-format instructions appended to the system prompt at runtime.
# The main system prompt intentionally omits this so examples can be stored
# separately in Neo4j and injected by the prompt manager.
# ---------------------------------------------------------------------------
_OUTPUT_FORMAT = """

## Output Format

Your entire assistant message must be one JSON object only (parseable by json.loads).
No markdown headings, bullet rationale, code fences, or text before or after the object.

When there are no codable entities, respond with exactly: {"terms":[]}

Full schema when entities exist:
{
  "terms": [
    {
      "sentence_id": "<id from the Sentences list>",
      "text": "<exact span as written in the sentence>",
      "lookup_term": "<standard clinical term for SNOMED lookup; preserve onset/chronicity/certainty/laterality qualifiers>",
      "semantic_tag": "<disorder|finding|procedure|substance|product|observable entity|situation|regime/therapy|staging scale>",
      "confidence": 0.92,
      "numeric_value": "<numeric value if observable entity, else empty string>",
      "unit": "<unit if observable entity, else empty string>",
      "reference_range": "<range if present, else empty string>",
      "modifiers": {}
    }
  ]
}

confidence is REQUIRED on every entity and is a self-assessment in
[0.0, 1.0]; do not hard-code 1.0 for every entity.

Never replace the JSON object with prose (for example "No codable entities").
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

_DEFAULT_CONFIDENCE = 0.75


def _parse_assertion(raw: Any) -> str:
    """Normalise an LLM-emitted assertion value.

    Unknown or empty values fall back to ``"present"``. Final assertion is
    still re-checked by the post-processing pipeline (ConText + scope guard)
    so an incorrect extractor emission is never the only signal.
    """
    if not raw:
        return "present"
    value = str(raw).strip().lower()
    return value if value in _VALID_ASSERTIONS else "present"


def _parse_confidence(raw: Any) -> float:
    """Clamp an LLM-emitted confidence into ``[0.0, 1.0]``.

    Missing / non-numeric values fall back to ``_DEFAULT_CONFIDENCE`` (0.75)
    rather than the previous hard-coded 1.0 -- we do not want to treat every
    extraction as infallibly confident.
    """
    if raw is None:
        return _DEFAULT_CONFIDENCE
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_CONFIDENCE
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


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
    span_start: int = 0
    span_end: int = 0
    confidence: float = 1.0
    context: dict[str, Any] = field(default_factory=dict)
    modifiers: dict[str, Any] = field(default_factory=dict)


class LLMExtractor:
    source = "llm"

    def __init__(self, model_id: str = "llm-unconfigured") -> None:
        self.model_id = model_id or "llm-unconfigured"
        self.model_version = "1.0"
        self.prompt_name = "extraction"
        self.prompt_version = 1
        self.prompt_hash = ""
        self.selected_few_shot_ids: list[str] = []
        self._system_prompt = ""
        self._load_prompt_bundle()
        self.client = self._init_client()
        configured = self.model_id not in {"unconfigured", "llm-unconfigured"}
        self.enabled = bool(self.client) and configured
        self.model_name = self.client.model_id if self.client else self.model_id

    def _load_prompt_bundle(self) -> None:
        """Load extraction prompt/schema/examples from Neo4j PromptConfig."""
        try:
            cfg = get_prompt_config(self.prompt_name, version=self.prompt_version)
        except Exception:
            logger.exception(
                "LLMExtractor could not load prompt config %s v%s",
                self.prompt_name,
                self.prompt_version,
            )
            self._system_prompt = ""
            self.prompt_hash = ""
            self.selected_few_shot_ids = []
            return

        few_shots = cfg.get("fewShotExamples") or []
        if not isinstance(few_shots, list):
            few_shots = []
        self.selected_few_shot_ids = [
            _example_id(ex) for ex in few_shots if isinstance(ex, dict)
        ]
        self._system_prompt = assemble_system_prompt(
            instructions=str(cfg.get("systemPrompt") or ""),
            output_schema_json=cfg.get("outputSchema"),
            few_shot_examples=few_shots,
        )
        if not cfg.get("outputSchema"):
            self._system_prompt = f"{self._system_prompt}\n\n{_OUTPUT_FORMAT}"
        self.prompt_hash = hashlib.sha256(
            self._system_prompt.encode("utf-8")
        ).hexdigest()

    def _init_client(self):
        """Return a wired LLMClient or None if Bedrock is not configured."""
        try:
            from libs.llm_client.factory import create_llm

            return create_llm(
                provider=None,  # reads PIPELINE_MODEL_PROVIDER env, defaults "aws"
                tier="small",  # Haiku for extraction — fast, low cost, structured task
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
        if not self.enabled or not sentences or not self._system_prompt:
            return []
        user_msg = self._build_user_prompt(encounter_text, sentences)
        try:
            resp = self.client.converse(
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=2048,
                temperature=0.0,
                agent_task="coding_worker_llm_extractor",
            )
            payload = self._parse_json(resp.text)
        except Exception as exc:
            logger.error("LLMExtractor.extract_batch failed: %s", exc)
            return []
        terms = self._parse_terms(payload, sentences, encounter_text)
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
        from libs.pipeline.extraction_response_parse import (
            parse_extraction_terms_response,
        )

        data, _src = parse_extraction_terms_response(raw)
        return data

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        """Extract raw text payload from bedrock/openai-like responses."""
        try:
            content = response.get("output", {}).get("message", {}).get("content", [])
            if not content:
                return ""
            first = content[0]
            if isinstance(first, dict):
                return str(first.get("text") or "")
        except Exception:
            return ""
        return ""

    @staticmethod
    def _build_user_prompt(encounter_text: str, sentences: list) -> str:
        parts = [f"ENCOUNTER TEXT:\n{encounter_text}\n\nSENTENCES TO EXTRACT FROM:"]
        for sentence in sentences:
            sid = getattr(sentence, "sentence_id", "s0")
            text = getattr(sentence, "text", "")
            parts.append(f"[{sid}] {text}")
        return "\n".join(parts)

    def _parse_terms(
        self,
        payload: dict[str, Any],
        sentences: list,
        encounter_text: str = "",
    ) -> list[ExtractedTerm]:
        terms = payload.get("terms") or []
        if not isinstance(terms, list):
            return []
        valid_sentence_ids = {
            getattr(sentence, "sentence_id", "") for sentence in sentences
        }
        resolver = SpanResolver(encounter_text=encounter_text, sentences=sentences)
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
            # DI-LEO-AI-103: LLM extractor MUST NOT assign assertion. All
            # entities are initialised to "present" so that ConText and the
            # post-processing scope guards are the sole authority for
            # non-present assertions.
            assertion = "present"
            dedup_key = (text.lower(), str(term.get("semantic_tag") or ""), assertion)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            context = dict(
                _ASSERTION_TO_CONTEXT.get(assertion, _ASSERTION_TO_CONTEXT["present"])
            )
            span_start, span_end = resolver.resolve(
                text, sentence_id=sentence_id or None
            )
            confidence = _parse_confidence(term.get("confidence"))
            results.append(
                ExtractedTerm(
                    sentence_id=sentence_id or "s0",
                    text=text,
                    lookup_term=str(term.get("lookup_term") or text),
                    semantic_tag=str(term.get("semantic_tag") or "finding"),
                    assertion=assertion,
                    span_start=span_start,
                    span_end=span_end,
                    confidence=confidence,
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
                    confidence=confidence,
                    resolver=resolver,
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
        confidence: float,
        resolver: SpanResolver,
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
            span_start, span_end = resolver.resolve(comp, sentence_id=sentence_id)
            out.append(
                ExtractedTerm(
                    sentence_id=sentence_id,
                    text=comp,
                    lookup_term=comp,
                    semantic_tag="observable entity",
                    assertion=assertion,
                    span_start=span_start,
                    span_end=span_end,
                    confidence=confidence,
                    context=dict(
                        _ASSERTION_TO_CONTEXT.get(
                            assertion, _ASSERTION_TO_CONTEXT["present"]
                        )
                    ),
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


def extracted_term_to_item(
    term: ExtractedTerm, *, source: str, model_name: str, model_version: str
) -> ExtractionItem:
    span_start = int(term.span_start or 0)
    span_end = int(term.span_end or 0)
    if span_end <= span_start:
        span_end = span_start + max(len(term.text), 1)
    return ExtractionItem(
        sentence_id=term.sentence_id,
        text=term.text,
        span_start=span_start,
        span_end=span_end,
        semantic_tag=term.semantic_tag,
        assertion=term.assertion,
        confidence=float(term.confidence),
        normalized=term.lookup_term,
        source_meta={"context": term.context, "modifiers": term.modifiers},
        source=source,
        model_name=model_name,
        model_version=model_version,
        contract_version=CONTRACT_VERSION,
    )


def _example_id(example: dict[str, Any]) -> str:
    explicit = str(example.get("id") or "").strip()
    if explicit:
        return explicit
    seed = "|".join(
        [
            str(example.get("category") or ""),
            str(example.get("description") or ""),
            str(example.get("input") or ""),
        ]
    )
    if not seed:
        return ""
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
