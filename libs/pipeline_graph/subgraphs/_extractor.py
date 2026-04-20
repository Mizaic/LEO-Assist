"""Thin adapter that provides an ExtractorProvider for the extraction subgraph.

Atlas trace:
  DO: DO-0289F3A5
  Also implements: DO-83EBEE2C, DO-94EAC337
  DI: DI-48AD06E5, DI-A0C90595, DI-B954388C, DI-F298AE65
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0289F3A5")

Prompt assembly
---------------
The final system prompt is assembled from three parts stored in Neo4j:

1. ``systemPrompt``   - instructions only (scope, rules, assertions, surface-form)
2. ``outputSchema``   - machine-readable JSON schema rendered as a "## Output Format"
3. ``fewShotExamples`` — example library; filtered by ``model_scope`` and appended as
                          a "## Examples" block

This separation allows each part to be managed independently in the Admin UI
and keeps the no-code pipeline builder aware of the exact output shape.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from libs.ner.extractor_contract import ExtractionItem
from libs.ner.span_resolver import SpanResolver
from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline.extraction_response_parse import parse_extraction_terms_response
from libs.prompts.few_shot_selector import FewShotSelector

_VALID_ASSERTIONS_EXTRACT = {
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

_DEFAULT_EXTRACT_CONFIDENCE = 0.75


def _normalise_assertion(raw: Any) -> str:
    if not raw:
        return "present"
    value = str(raw).strip().lower()
    return value if value in _VALID_ASSERTIONS_EXTRACT else "present"


def _normalise_confidence(raw: Any) -> float:
    if raw is None:
        return _DEFAULT_EXTRACT_CONFIDENCE
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_EXTRACT_CONFIDENCE
    return max(0.0, min(1.0, value))


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
        ex for ex in examples if ex.get("model_scope", "any") in ("any", provider)
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


def _filter_examples_for_provider(examples: list[dict], provider: str) -> list[dict]:
    return [ex for ex in examples if ex.get("model_scope", "any") in ("any", provider)]


def _split_core_dynamic(examples: list[dict]) -> tuple[list[dict], list[dict]]:
    core_examples = [ex for ex in examples if bool(ex.get("core", False))]
    dynamic_examples = [ex for ex in examples if not bool(ex.get("core", False))]
    return core_examples, dynamic_examples


def _build_relevant_examples_block(examples: list[dict]) -> str:
    if not examples:
        return ""
    lines = ["## Relevant examples", ""]
    for ex in examples:
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
        max_few_shot: int = 20,
        provider: str | None = None,
        prompt_name: str = "extraction",
        prompt_version: int = 1,
    ) -> None:
        self._tier = tier
        self._provider = provider or _active_provider()
        self._prompt_name = prompt_name
        self._prompt_version = prompt_version
        try:
            parsed_max = int(max_few_shot or 20)
        except (TypeError, ValueError):
            parsed_max = 20
        self._max_few_shot = max(1, parsed_max)
        applicable_examples = _filter_examples_for_provider(
            few_shot_examples or [], self._provider
        )
        core_examples, dynamic_pool = _split_core_dynamic(applicable_examples)
        max_core = min(len(core_examples), self._max_few_shot)
        self._core_examples = core_examples[:max_core]
        self._dynamic_budget = max(0, self._max_few_shot - len(self._core_examples))
        self._few_shot_selector = FewShotSelector(dynamic_pool=dynamic_pool)
        self._few_shot_selector.warm()
        from libs.prompts.registry import compose_prompt_with_annotation_guidelines

        composed_prompt = compose_prompt_with_annotation_guidelines(
            self._prompt_name, system_prompt
        )

        # Assemble static system prompt from instructions/schema/core examples.
        self._system_prompt = assemble_system_prompt(
            instructions=composed_prompt,
            output_schema_json=output_schema_json,
            few_shot_examples=self._core_examples,
            provider=self._provider,
        )
        self._prompt_hash = hashlib.sha256(
            self._system_prompt.encode("utf-8")
        ).hexdigest()

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

    def extract_batch_with_usage(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> tuple[list[ExtractionItem], dict]:
        """Run extraction and return (items, llm_token_dict).

        ``llm_token_dict`` has keys: input_tokens, output_tokens, cached_tokens,
        cost_usd.
        It is written into subgraph state so WorkflowEngine can aggregate it.
        """
        items, usage = self._run_llm(encounter_text, sentences)
        return items, usage

    def _run_llm(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> tuple[list[ExtractionItem], dict]:
        """Core LLM call. Returns (items, usage_dict)."""
        if not sentences:
            logger.warning("LLM extractor received 0 sentences; skipping LLM call")
            return [], {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": 0.0,
                "prompt_name": self._prompt_name,
                "prompt_version": self._prompt_version,
                "prompt_hash": self._prompt_hash,
                "provider": self._provider,
                "model_tier": self._tier,
                "few_shot_example_ids": [],
                "empty_sentence_input": True,
            }
        from libs.llm_client.factory import create_llm

        llm = create_llm(tier=self._tier)
        sentence_block = "\n".join(f"[{s.sentence_id}] {s.text}" for s in sentences)
        dynamic_examples: list[dict] = []
        if self._dynamic_budget > 0:
            query_text = f"{encounter_text}\n\n{sentence_block}".strip()
            dynamic_examples = self._few_shot_selector.select(
                query_text=query_text, k=self._dynamic_budget
            )
        relevant_examples_block = _build_relevant_examples_block(dynamic_examples)

        user_parts: list[str] = []
        if relevant_examples_block:
            user_parts.append(relevant_examples_block)
        user_msg = (
            f"Encounter text:\n{encounter_text}\n\n"
            f"Sentences to process:\n{sentence_block}"
        )
        user_parts.append(user_msg)
        final_user_msg = "\n\n".join(user_parts)
        resp = llm.converse(
            system=self._system_prompt,
            messages=[{"role": "user", "content": final_user_msg}],
            max_tokens=4096,
            temperature=0.0,
            agent_task="v3_pipeline_extractor",
        )

        # Build usage dict — cost_usd resolved from Neo4j ModelConfig if available
        cost_usd = 0.0
        try:
            from libs.llm_client.factory import _active_provider

            provider_key = f"{_active_provider()}:{self._tier}"
            from libs.cypher.model_config_queries import GET_MODEL_CONFIG
            from libs.neo4j_client.client import KnowledgeGraphClient

            kg = KnowledgeGraphClient()
            try:
                with kg.session() as s:
                    mc = s.run(GET_MODEL_CONFIG, key=provider_key).single()
                if mc:
                    billable = max(0, resp.input_tokens - resp.cached_input_tokens)
                    cost_usd = round(
                        billable * float(mc["costPer1mInput"] or 0) / 1_000_000
                        + resp.cached_input_tokens
                        * float(mc["costPer1mCachedInput"] or 0)
                        / 1_000_000
                        + resp.output_tokens
                        * float(mc["costPer1mOutput"] or 0)
                        / 1_000_000,
                        6,
                    )
            finally:
                kg.close()
        except Exception:
            logger.debug("Cost calculation failed (non-fatal)", exc_info=True)

        usage = {
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cached_tokens": resp.cached_input_tokens,
            "cost_usd": cost_usd,
            "prompt_name": self._prompt_name,
            "prompt_version": self._prompt_version,
            "prompt_hash": self._prompt_hash,
            "provider": self._provider,
            "model_tier": self._tier,
            "few_shot_example_ids": [
                _example_id(ex)
                for ex in (self._core_examples + dynamic_examples)
                if isinstance(ex, dict)
            ],
        }

        raw = (resp.text or "").strip()
        data, parse_source = parse_extraction_terms_response(raw)
        if parse_source == "failed":
            logger.warning("LLM returned invalid JSON: %s", raw[:200])
            return [], usage
        if parse_source == "prose_empty":
            usage["llm_parse_note"] = "prose_empty"

        terms = data.get("terms", [])
        items: list[ExtractionItem] = []
        resolver = SpanResolver(encounter_text=encounter_text, sentences=sentences)

        for t in terms:
            text_val = t.get("text", "")
            span_start, span_end = resolver.resolve(
                text_val, sentence_id=str(t.get("sentence_id") or "") or None
            )
            items.append(
                ExtractionItem(
                    sentence_id=t.get("sentence_id", ""),
                    text=text_val,
                    span_start=span_start,
                    span_end=span_end,
                    semantic_tag=t.get("semantic_tag", "finding"),
                    # DI-LEO-AI-103: LLM extractor MUST NOT assign assertion;
                    # all entities start at "present" and the post-processing
                    # ConText + scope guard layers are the sole authority.
                    assertion="present",
                    confidence=_normalise_confidence(t.get("confidence")),
                    normalized=t.get("lookup_term", text_val),
                    numeric_value=t.get("value") or "",
                    unit=t.get("unit") or "",
                    reference_range=t.get("reference_range") or "",
                    source="llm",
                    model_name=self.model_name,
                    model_version=self.model_version,
                )
            )
        return items, usage

    def extract_batch(
        self,
        encounter_text: str,
        sentences: list[SentenceChunk],
    ) -> list[ExtractionItem]:
        items, _ = self._run_llm(encounter_text, sentences)
        return items


def build_extractor(
    system_prompt: str | None = None,
    tier: str = "small",
    output_schema_json: str | None = None,
    few_shot_examples: list[dict] | None = None,
    max_few_shot: int = 20,
    provider: str | None = None,
    prompt_name: str = "extraction",
    prompt_version: int = 1,
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
        max_few_shot=max_few_shot,
        provider=provider,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
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
