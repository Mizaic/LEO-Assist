"""Thin adapter that provides an ExtractorProvider for the extraction subgraph.

Prompt assembly
---------------
The final system prompt is assembled from three parts stored in Neo4j:

1. ``systemPrompt``   — instructions only (scope, rules, assertions, surface-form rules)
2. ``outputSchema``   — machine-readable JSON schema rendered as a "## Output Format" block
3. ``fewShotExamples`` — example library; filtered by ``model_scope`` and appended as
                          a "## Examples" block

This separation allows each part to be managed independently in the Admin UI
and keeps the no-code pipeline builder aware of the exact output shape.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.ner.extractor_contract import ExtractionItem, ExtractorProvider
from libs.nlp.sentence_splitter import SentenceChunk

logger = logging.getLogger(__name__)


def _active_provider() -> str:
    """Return the active LLM provider name (``"aws"`` or ``"azure"``)."""
    import os
    return os.getenv("PIPELINE_MODEL_PROVIDER", "aws")


def _build_few_shot_block(examples: list[dict], provider: str = "aws") -> str:
    """Render a subset of the example library as a prompt section.

    Selects examples whose ``model_scope`` is ``"any"`` or matches *provider*.
    ``provider`` should be ``"aws"`` (Claude/Bedrock) or ``"azure"`` (OpenAI).
    Returns an empty string when there are no matching examples.
    """
    applicable = [
        ex for ex in examples
        if ex.get("model_scope", "any") in ("any", provider)
    ]
    if not applicable:
        return ""

    lines = ["## Examples", ""]
    for ex in applicable:
        desc = ex.get("description", "")
        cat = ex.get("category", "")
        header = f"# {cat}" + (f" — {desc}" if desc else "")
        lines.append(header)
        lines.append(f"Input:  {ex.get('input', '')}")
        lines.append(f"Output: {ex.get('output', '')}")
        lines.append("")
    return "\n".join(lines)


def assemble_system_prompt(
    instructions: str,
    output_schema_json: str | None = None,
    few_shot_examples: list[dict] | None = None,
    provider: str | None = None,
) -> str:
    """Assemble the final system prompt from its three managed parts.

    Args:
        instructions: The raw ``systemPrompt`` field from Neo4j (instructions only).
        output_schema_json: The ``outputSchema`` field (JSON string or None).
        few_shot_examples: Parsed list from the ``fewShotExamples`` field.
        provider: Active LLM provider — ``"aws"`` (Claude/Bedrock) or ``"azure"``
            (OpenAI).  Defaults to the ``PIPELINE_MODEL_PROVIDER`` environment
            variable.  Used to select provider-specific examples from the library;
            examples marked ``"any"`` are always included.

    Returns:
        The complete system prompt string to send to the LLM.
    """
    active_provider = provider or _active_provider()
    parts: list[str] = [instructions.strip()]

    # Append the output format block
    if output_schema_json:
        try:
            schema = json.loads(output_schema_json)
            from libs.prompts.extraction_output_schema import format_output_schema_block
            fmt_block = format_output_schema_block(schema)
            if fmt_block:
                parts.append(fmt_block)
        except Exception as exc:
            logger.debug("Could not render output schema block: %s", exc)

    # Append provider-filtered few-shot examples
    if few_shot_examples:
        ex_block = _build_few_shot_block(few_shot_examples, provider=active_provider)
        if ex_block:
            parts.append(ex_block)

    return "\n\n".join(parts)


class LLMExtractorAdapter:
    """LLM-backed entity extractor conforming to ExtractorProvider protocol."""

    def __init__(
        self,
        system_prompt: str,
        tier: str = "small",
        output_schema_json: str | None = None,
        few_shot_examples: list[dict] | None = None,
        provider: str | None = None,
    ) -> None:
        self._tier = tier
        self._provider = provider or _active_provider()
        # Assemble the full prompt from its three managed parts, filtering
        # examples to those that match this provider ("any" is always included).
        self._system_prompt = assemble_system_prompt(
            instructions=system_prompt,
            output_schema_json=output_schema_json,
            few_shot_examples=few_shot_examples,
            provider=self._provider,
        )

    @property
    def source(self) -> str:
        return "llm"

    @property
    def model_name(self) -> str:
        return f"llm-{self._tier}"

    @property
    def model_version(self) -> str:
        return "pipeline-v2"

    def is_available(self) -> bool:
        try:
            from libs.llm_client.factory import create_llm
            llm = create_llm(tier=self._tier)
            return llm is not None
        except Exception:
            return False

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> list[ExtractionItem]:
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=self._tier)
        sentence_block = "\n".join(
            f"[{s.sentence_id}] {s.text}" for s in sentences
        )
        user_msg = (
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentences to process:\n{sentence_block}"
        )
        resp = llm.converse(
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=4096,
            temperature=0.0,
        )
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON: %s", raw[:200])
            return []

        terms = data.get("terms", [])
        items: list[ExtractionItem] = []
        for t in terms:
            text_val = t.get("text", "")
            items.append(
                ExtractionItem(
                    sentence_id=t.get("sentence_id", ""),
                    text=text_val,
                    span_start=0,
                    span_end=len(text_val),
                    semantic_tag=t.get("semantic_tag", "finding"),
                    assertion=t.get("assertion", "present"),
                    confidence=1.0,
                    normalized=t.get("lookup_term", text_val),
                    numeric_value=t.get("value") or "",
                    unit=t.get("unit") or "",
                    reference_range=t.get("reference_range") or "",
                    source="llm",
                    model_name=self.model_name,
                    model_version=self.model_version,
                )
            )
        return items


def build_extractor(
    system_prompt: str | None = None,
    tier: str = "small",
    output_schema_json: str | None = None,
    few_shot_examples: list[dict] | None = None,
    provider: str | None = None,
) -> LLMExtractorAdapter:
    """Build an LLM extractor, assembling the full system prompt from its parts.

    If ``system_prompt`` is None, falls back to the registry (Neo4j → hardcoded).
    ``output_schema_json`` and ``few_shot_examples`` are optional; when provided
    they are rendered and appended to the instructions before sending to the LLM.

    ``provider`` controls which provider-specific examples are selected:
    ``"aws"`` (Claude/Bedrock) or ``"azure"`` (OpenAI).  Defaults to the
    ``PIPELINE_MODEL_PROVIDER`` environment variable.
    """
    if not system_prompt:
        from libs.prompts.registry import get_prompt
        system_prompt = get_prompt("extraction", version=1)
    return LLMExtractorAdapter(
        system_prompt=system_prompt,
        tier=tier,
        output_schema_json=output_schema_json,
        few_shot_examples=few_shot_examples,
        provider=provider,
    )
