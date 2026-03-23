from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from libs.ner.extractor_contract import CONTRACT_VERSION, ExtractionItem

_VALID_ASSERTIONS = {
    "present",
    "absent",
    "refuted",
    "possible",
    "historical",
    "hypothetical",
    "family",
    "declined",
    "cancelled",
}


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
        self.model_name = self.model_id
        self.model_version = "1.0"
        self.client = self._init_client()
        self.enabled = bool(self.client) and self.model_id != "unconfigured"

    def _init_client(self):
        return None

    def is_available(self) -> bool:
        return bool(self.enabled)

    def extract_batch(self, encounter_text: str, sentences: list) -> list[ExtractionItem]:
        if not self.enabled or not sentences:
            return []
        prompt = self._build_user_prompt(encounter_text, sentences)
        _ = prompt
        return []

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return {}
            return {}

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        content = (((response or {}).get("output") or {}).get("message") or {}).get("content") or []
        if not content:
            return ""
        first = content[0] or {}
        return str(first.get("text") or "")

    @staticmethod
    def _build_user_prompt(encounter_text: str, sentences: list) -> str:
        parts = [f"Encounter:\n{encounter_text}", "Sentences:"]
        for sentence in sentences:
            parts.append(f"- {getattr(sentence, 'sentence_id', '')}: {getattr(sentence, 'text', '')}")
        return "\n".join(parts)

    def _parse_terms(self, payload: dict[str, Any], sentences: list) -> list[ExtractedTerm]:
        terms = payload.get("terms") or []
        if not isinstance(terms, list):
            return []
        valid_sentence_ids = {getattr(sentence, "sentence_id", "") for sentence in sentences}
        results: list[ExtractedTerm] = []
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
            results.append(
                ExtractedTerm(
                    sentence_id=sentence_id or "s0",
                    text=text,
                    lookup_term=str(term.get("lookup_term") or text),
                    semantic_tag=str(term.get("semantic_tag") or "finding"),
                    assertion=assertion,
                    context={"negated": assertion in {"absent", "refuted"}},
                    modifiers=dict(term.get("modifiers") or {}),
                )
            )
        return results


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
