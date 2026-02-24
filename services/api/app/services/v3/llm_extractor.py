"""LLM-backed term extraction in 5-sentence batches for V3."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.services.context_reconciler import reconcile_context
from app.services.v3.sentence_splitter import SentenceChunk


_TERM_FALLBACK_RE = re.compile(
    r"\b([A-Za-z][A-Za-z\-]{2,}(?:\s+[A-Za-z][A-Za-z\-]{2,}){0,3})\b"
)


@dataclass(frozen=True)
class ExtractedTerm:
    sentence_id: str
    text: str
    semantic_tag: str
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
    ) -> list[ExtractedTerm]:
        if not sentences:
            return []
        if not self.enabled:
            return self._fallback_extract(sentences)

        prompt = self._build_prompt(encounter_text, sentences)
        try:
            response = self._client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 1600, "temperature": 0.0},
            )
            parsed = _parse_json_object(_extract_bedrock_text(response))
            terms = self._parse_terms(parsed, sentences)
            return terms if terms else self._fallback_extract(sentences)
        except Exception:  # pragma: no cover - runtime provider errors
            return self._fallback_extract(sentences)

    def _build_prompt(self, encounter_text: str, sentences: list[SentenceChunk]) -> str:
        sentence_payload = [
            {
                "sentence_id": s.sentence_id,
                "start": s.start,
                "end": s.end,
                "text": s.text,
            }
            for s in sentences
        ]
        return (
            "You are a UK clinical NLP extractor.\n"
            "Given de-identified encounter text and a sentence subset, extract medical terms.\n"
            "Return strict JSON only.\n"
            "Schema:\n"
            "{\n"
            '  "terms": [\n'
            "    {\n"
            '      "sentence_id": "s0",\n'
            '      "text": "term surface form as appears in sentence",\n'
            '      "semantic_tag": "Situation|Clinical_finding|Disease|Observable_entity|Procedure|SnomedConcept|Other",\n'
            '      "context": {\n'
            '        "negated": false,\n'
            '        "uncertain": false,\n'
            '        "historical": false,\n'
            '        "temporality": "present|past|planned|hypothetical|unknown",\n'
            '        "subject": "patient|family|other"\n'
            "      },\n"
            '      "modifiers": {\n'
            '        "severity": null,\n'
            '        "laterality": null,\n'
            '        "episodicity": null,\n'
            '        "course": null,\n'
            '        "anatomical_site": null,\n'
            '        "qualifier": null,\n'
            '        "measurement": null,\n'
            '        "value": null,\n'
            '        "unit": null\n'
            "      }\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentence subset:\n{json.dumps(sentence_payload, ensure_ascii=False)}"
        )

    def _parse_terms(
        self,
        payload: dict[str, Any],
        sentences: list[SentenceChunk],
    ) -> list[ExtractedTerm]:
        valid_ids = {s.sentence_id for s in sentences}
        out: list[ExtractedTerm] = []
        for row in payload.get("terms", []):
            if not isinstance(row, dict):
                continue
            sid = str(row.get("sentence_id", "")).strip()
            text = str(row.get("text", "")).strip()
            if not sid or sid not in valid_ids or not text:
                continue
            semantic_tag = str(row.get("semantic_tag", "Other")).strip() or "Other"
            context = row.get("context", {}) if isinstance(row.get("context"), dict) else {}
            modifiers = (
                row.get("modifiers", {}) if isinstance(row.get("modifiers"), dict) else {}
            )
            out.append(
                ExtractedTerm(
                    sentence_id=sid,
                    text=text,
                    semantic_tag=semantic_tag,
                    context={
                        "negated": bool(context.get("negated", False)),
                        "uncertain": bool(context.get("uncertain", False)),
                        "historical": bool(context.get("historical", False)),
                        "temporality": str(context.get("temporality", "unknown")),
                        "subject": str(context.get("subject", "patient")),
                    },
                    modifiers=modifiers,
                )
            )
        return out

    def _fallback_extract(self, sentences: list[SentenceChunk]) -> list[ExtractedTerm]:
        out: list[ExtractedTerm] = []
        for sentence in sentences:
            ctx = reconcile_context(sentence.text)
            seen: set[str] = set()
            for m in _TERM_FALLBACK_RE.finditer(sentence.text):
                text = m.group(1).strip()
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                out.append(
                    ExtractedTerm(
                        sentence_id=sentence.sentence_id,
                        text=text,
                        semantic_tag="Other",
                        context={
                            "negated": ctx.negated,
                            "uncertain": ctx.uncertain,
                            "historical": ctx.historical,
                            "temporality": ctx.temporality,
                            "subject": ctx.subject,
                        },
                        modifiers={},
                    )
                )
        return out

