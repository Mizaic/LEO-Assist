"""LLM disambiguation for multi-candidate code matches."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.v3.coding_resolver import CodingCandidate


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
    ) -> CodingCandidate | None:
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        if not self.enabled:
            return candidates[0]

        prompt = (
            "You are disambiguating SNOMED concepts for a clinical term in context.\n"
            "Return strict JSON only with keys: conceptId, confidence, reason.\n"
            'If none fit, return {"conceptId":"NONE","confidence":0.0,"reason":"..."}.\n\n'
            f"Encounter text:\n{encounter_text}\n\n"
            f"Term: {term_text}\n"
            f"Candidates: {json.dumps([c.__dict__ for c in candidates], ensure_ascii=False)}"
        )
        try:
            response = self._client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 320, "temperature": 0.0},
            )
            parsed = _parse_json_object(_extract_bedrock_text(response))
            concept_id = str(parsed.get("conceptId", "")).strip()
            if not concept_id or concept_id.upper() == "NONE":
                return candidates[0]
            for candidate in candidates:
                if candidate.snomed_concept_id == concept_id:
                    return CodingCandidate(
                        snomed_concept_id=candidate.snomed_concept_id,
                        snomed_term=candidate.snomed_term,
                        read_code=candidate.read_code,
                        score=float(parsed.get("confidence", candidate.score) or candidate.score),
                        source="llm_disambiguation",
                    )
        except Exception:  # pragma: no cover
            pass
        return candidates[0]

