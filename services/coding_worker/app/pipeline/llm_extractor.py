"""LLM-backed clinical term extraction.

Adapted from PCA services/api/app/services/v3/llm_extractor.py.
Uses libs/llm-client cache and fallback for resilience.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_VALID_ASSERTIONS = frozenset(
    {"present", "absent", "possible", "historical", "hypothetical", "family"}
)

_ASSERTION_TO_CONTEXT: dict[str, dict[str, object]] = {
    "present": {"negated": False, "uncertain": False, "historical": False, "subject": "patient", "temporality": "present"},
    "absent": {"negated": True, "uncertain": False, "historical": False, "subject": "patient", "temporality": "present"},
    "possible": {"negated": False, "uncertain": True, "historical": False, "subject": "patient", "temporality": "hypothetical"},
    "historical": {"negated": False, "uncertain": False, "historical": True, "subject": "patient", "temporality": "past"},
    "hypothetical": {"negated": False, "uncertain": False, "historical": False, "subject": "patient", "temporality": "hypothetical"},
    "family": {"negated": False, "uncertain": False, "historical": False, "subject": "family", "temporality": "unknown"},
}


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedTerm:
    sentence_id: str
    text: str
    lookup_term: str
    semantic_tag: str
    assertion: str
    context: dict[str, Any]
    modifiers: dict[str, Any]


class LLMExtractor:
    """Extracts clinical terms from encounter text using Bedrock LLM."""

    SYSTEM_PROMPT = (
        "You are a UK primary care clinical entity extractor. "
        "Extract SNOMED CT-codable clinical entities from de-identified GP text. "
        "Return ONLY valid JSON: {\"terms\": [{\"sentence_id\", \"text\", \"lookup_term\", "
        "\"semantic_tag\", \"assertion\"}]}. Return {\"terms\": []} for no entities."
    )

    def __init__(self, *, model_id: str, region: str | None = None) -> None:
        self.model_id = model_id
        self.region = region
        self._client = self._init_client(region)

    @staticmethod
    def _init_client(region: str | None):
        try:
            import boto3
            return boto3.client("bedrock-runtime", region_name=region)
        except Exception:
            return None

    @property
    def enabled(self) -> bool:
        return bool(self._client and self.model_id and self.model_id != "unconfigured")

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list,
    ) -> list[ExtractedTerm]:
        if not sentences or not self.enabled:
            return []

        user_prompt = self._build_user_prompt(encounter_text, sentences)
        try:
            response = self._client.converse(
                modelId=self.model_id,
                system=[{"text": self.SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.0},
            )
        except Exception as exc:
            raise ExtractionError(f"LLM call failed: {exc}") from exc

        raw_text = self._extract_text(response)
        parsed = self._parse_json(raw_text)
        return self._parse_terms(parsed, sentences)

    @staticmethod
    def _build_user_prompt(encounter_text: str, sentences: list) -> str:
        payload = [{"sentence_id": s.sentence_id, "text": s.text} for s in sentences]
        return (
            f"Extract clinical entities from sentences below.\n\n"
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentences:\n{json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        content = response.get("output", {}).get("message", {}).get("content", [])
        parts = [item["text"] for item in (content or []) if isinstance(item, dict) and "text" in item]
        return "\n".join(parts).strip()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {}

    def _parse_terms(self, payload: dict[str, Any], sentences: list) -> list[ExtractedTerm]:
        valid_ids = {s.sentence_id for s in sentences}
        out: list[ExtractedTerm] = []
        for row in payload.get("terms", []):
            if not isinstance(row, dict):
                continue
            sid = str(row.get("sentence_id", "")).strip()
            text = str(row.get("text", "")).strip()
            if not sid or sid not in valid_ids or not text:
                continue
            assertion = str(row.get("assertion", "present")).strip().lower()
            if assertion not in _VALID_ASSERTIONS:
                assertion = "present"
            out.append(ExtractedTerm(
                sentence_id=sid,
                text=text,
                lookup_term=str(row.get("lookup_term", text)).strip() or text,
                semantic_tag=str(row.get("semantic_tag", "finding")).strip(),
                assertion=assertion,
                context=dict(_ASSERTION_TO_CONTEXT.get(assertion, _ASSERTION_TO_CONTEXT["present"])),
                modifiers={},
            ))
        return out
