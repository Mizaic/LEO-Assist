"""LLM-backed term extraction in 5-sentence batches for V3."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.services.v3.bedrock_retry import converse_with_retry
from app.services.v3.llm_usage import LLMUsage
from app.services.v3.sentence_splitter import SentenceChunk
from libs.prompts.registry import get_prompt

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Raised when LLM extraction fails and no fallback is permitted."""


_VALID_ASSERTIONS = frozenset(
    {"present", "absent", "possible", "historical", "hypothetical", "family"}
)

_ASSERTION_TO_CONTEXT: dict[str, dict[str, object]] = {
    "present": {
        "negated": False, "uncertain": False, "historical": False,
        "subject": "patient", "temporality": "present",
    },
    "absent": {
        "negated": True, "uncertain": False, "historical": False,
        "subject": "patient", "temporality": "present",
    },
    "possible": {
        "negated": False, "uncertain": True, "historical": False,
        "subject": "patient", "temporality": "hypothetical",
    },
    "historical": {
        "negated": False, "uncertain": False, "historical": True,
        "subject": "patient", "temporality": "past",
    },
    "hypothetical": {
        "negated": False, "uncertain": False, "historical": False,
        "subject": "patient", "temporality": "hypothetical",
    },
    "family": {
        "negated": False, "uncertain": False, "historical": False,
        "subject": "family", "temporality": "unknown",
    },
}

_SYSTEM_PROMPT = get_prompt("extraction", version=1)


@dataclass(frozen=True)
class ExtractedTerm:
    sentence_id: str
    text: str
    lookup_term: str
    semantic_tag: str
    assertion: str
    context: dict[str, Any]
    modifiers: dict[str, Any]


def _extract_bedrock_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(parts).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def assertion_to_context(assertion: str) -> dict[str, object]:
    """Map a unified assertion label to the legacy context dict."""
    return dict(_ASSERTION_TO_CONTEXT.get(assertion, _ASSERTION_TO_CONTEXT["present"]))


class LLMExtractor:
    def __init__(self, *, model_id: str, region: str | None = None) -> None:
        self.model_id = model_id
        self.region = region
        self._client = self._init_client(region)

    @staticmethod
    def _init_client(region: str | None):
        try:
            import boto3  # pylint: disable=import-outside-toplevel
        except Exception:  # pragma: no cover
            return None
        try:
            return boto3.client("bedrock-runtime", region_name=region)
        except Exception:  # pragma: no cover
            return None

    @property
    def enabled(self) -> bool:
        return bool(self._client and self.model_id and self.model_id != "unconfigured")

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> tuple[list[ExtractedTerm], LLMUsage]:
        if not sentences:
            return [], LLMUsage.zero()
        if not self.enabled:
            raise ExtractionError(
                "LLM extractor is not enabled (model_id=%s)" % self.model_id
            )

        sids = [s.sentence_id for s in sentences]
        logger.info("Sending %d sentences to LLM (%s)", len(sentences), sids)
        user_prompt = self._build_user_prompt(encounter_text, sentences)
        try:
            response = converse_with_retry(
                self._client,
                model_id=self.model_id,
                system=[{"text": _SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
            )
        except Exception as exc:
            raise ExtractionError("LLM converse() call failed: %s" % exc) from exc

        batch_usage = LLMUsage.from_bedrock_response(response)
        logger.info(
            "LLM response received - %d in / %d out tokens (cached=%d), stop=%s",
            batch_usage.input_tokens,
            batch_usage.output_tokens,
            batch_usage.cached_input_tokens,
            response.get("stopReason", "?"),
        )
        raw_text = _extract_bedrock_text(response)
        parsed = _parse_json_object(raw_text)
        if not parsed:
            raise ExtractionError(
                "LLM returned unparseable response for sentences %s: %s"
                % (sids, raw_text[:200])
            )
        terms = self._parse_terms(parsed, sentences)
        logger.info("Parsed %d terms from LLM response", len(terms))
        return terms, batch_usage

    @staticmethod
    def _build_user_prompt(
        encounter_text: str, sentences: list[SentenceChunk],
    ) -> str:
        sentence_payload = [
            {"sentence_id": s.sentence_id, "text": s.text}
            for s in sentences
        ]
        return (
            "Extract clinical entities from the sentence subset below.\n"
            "The encounter text provides clinical context only - "
            "extract from the sentences.\n\n"
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentences:\n{json.dumps(sentence_payload, ensure_ascii=False)}"
        )

    def _parse_terms(
        self,
        payload: dict[str, Any],
        sentences: list[SentenceChunk],
    ) -> list[ExtractedTerm]:
        valid_ids = {s.sentence_id for s in sentences}
        raw_terms = payload.get("terms", [])
        out: list[ExtractedTerm] = []
        dropped = 0
        for row in raw_terms:
            if not isinstance(row, dict):
                dropped += 1
                continue
            sid = str(row.get("sentence_id", "")).strip()
            text = str(row.get("text", "")).strip()
            if not sid or sid not in valid_ids or not text:
                dropped += 1
                continue

            lookup_term = str(row.get("lookup_term", text)).strip() or text
            semantic_tag = str(row.get("semantic_tag", "finding")).strip() or "finding"
            assertion = str(row.get("assertion", "present")).strip().lower()
            if assertion not in _VALID_ASSERTIONS:
                logger.warning(
                    "Invalid assertion %r for text=%r - defaulting to 'present'",
                    assertion, text,
                )
                assertion = "present"

            context = assertion_to_context(assertion)
            out.append(
                ExtractedTerm(
                    sentence_id=sid,
                    text=text,
                    lookup_term=lookup_term,
                    semantic_tag=semantic_tag,
                    assertion=assertion,
                    context=context,
                    modifiers={},
                )
            )
        if dropped:
            logger.warning("Dropped %d/%d rows from LLM response (bad sid or empty text)", dropped, len(raw_terms))
        return out

