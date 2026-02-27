"""LLM disambiguation for multi-candidate code matches."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.v3.bedrock_retry import converse_with_retry
from app.services.v3.coding_resolver import CodingCandidate
from app.services.v3.llm_usage import LLMUsage
from libs.prompts.registry import get_prompt

logger = logging.getLogger(__name__)


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
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


class CodingDisambiguator:
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

    def choose_best(
        self,
        *,
        encounter_text: str,
        term_text: str,
        candidates: list[CodingCandidate],
    ) -> tuple[CodingCandidate | None, LLMUsage]:
        no_usage = LLMUsage.zero()
        if not candidates:
            return None, no_usage
        if len(candidates) == 1:
            return candidates[0], no_usage
        if not self.enabled:
            return candidates[0], no_usage

        system_text = get_prompt("disambiguation", version=1)
        prompt = (
            f"{system_text}\n\n"
            f"Encounter text:\n{encounter_text}\n\n"
            f"Term: {term_text}\n"
            f"Candidates: {json.dumps([c.__dict__ for c in candidates], ensure_ascii=False)}"
        )
        try:
            response = converse_with_retry(
                self._client,
                model_id=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 320, "temperature": 0.0},
            )
            call_usage = LLMUsage.from_bedrock_response(response)
            logger.info(
                "Disambiguator response - %d in / %d out tokens",
                call_usage.input_tokens, call_usage.output_tokens,
            )
            parsed = _parse_json_object(_extract_bedrock_text(response))
            concept_id = str(parsed.get("conceptId", "")).strip()
            if not concept_id or concept_id.upper() == "NONE":
                return candidates[0], call_usage
            for candidate in candidates:
                if candidate.snomed_concept_id == concept_id:
                    return CodingCandidate(
                        snomed_concept_id=candidate.snomed_concept_id,
                        snomed_term=candidate.snomed_term,
                        read_code=candidate.read_code,
                        score=float(parsed.get("confidence", candidate.score) or candidate.score),
                        source="llm_disambiguation",
                    ), call_usage
        except Exception:  # pragma: no cover
            logger.warning("Disambiguator call failed for term=%r", term_text, exc_info=True)
        return candidates[0], no_usage

