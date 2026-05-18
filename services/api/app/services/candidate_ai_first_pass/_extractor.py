"""Haiku-based AI re-extraction of TrainingCandidate entities.

Atlas trace:
  DO: DO-D7005C41
  DI: DI-0FFA05BB
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D7005C41")

DI-LEO-AI-208 / DO-LEO-AI-205.

Calls Haiku 4.5 (tier='small' via libs.llm_client.factory.create_llm)
with the production EXTRACTION_SYSTEM_V1 prompt and a top-k of nearest
gold few-shot exemplars selected by BioClinicalBERT cosine similarity.

On any LLM failure the extractor falls back to the candidate's
existing entities_json so the workflow never silently zeros out an
entity list.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.prompts.few_shot_selector import FewShotSelector

from ._types import ExtractedEntity, ExtractionResult

logger = logging.getLogger(__name__)


_DEFAULT_FEW_SHOT_K = 5
_MAX_OUTPUT_TOKENS = 1500
_MAX_TEXT_CHARS = 16_000
_MAX_HINT_ENTITIES = 30


def _safe_load_entities(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [e for e in parsed if isinstance(e, dict)] if isinstance(parsed, list) else []


def _to_extracted(rows: list[dict[str, Any]]) -> list[ExtractedEntity]:
    out: list[ExtractedEntity] = []
    for r in rows:
        text = str(r.get("text") or "").strip()
        label = str(r.get("label") or r.get("semantic_tag") or "").strip()
        if not text or not label:
            continue
        assertion = str(r.get("assertion") or "present").strip().lower() or "present"
        extras = {
            k: v
            for k, v in r.items()
            if k not in {"text", "label", "assertion", "ai_first_pass"}
        }
        out.append(
            ExtractedEntity(
                text=text, label=label, assertion=assertion, extras=extras
            )
        )
    return out


def _format_few_shot_block(examples: list[dict[str, Any]]) -> str:
    """Render exemplars as a human-readable multi-shot block.

    Each example becomes:
        EXAMPLE input:
        <text>
        EXAMPLE entities (JSON):
        [...]
    """
    if not examples:
        return ""
    parts: list[str] = ["RECENT GOLD EXAMPLES (mimic this output style):"]
    for i, ex in enumerate(examples, start=1):
        text = str(ex.get("input") or "").strip()
        out = ex.get("output")
        if not text or not isinstance(out, list):
            continue
        try:
            out_str = json.dumps(out, ensure_ascii=True)[:1200]
        except (TypeError, ValueError):
            continue
        parts.append(f"\n--- EXAMPLE {i} ---")
        parts.append(f"input:\n{text[:600]}")
        parts.append(f"entities:\n{out_str}")
    return "\n".join(parts)


def _build_user_message(
    *,
    candidate_text: str,
    original_entities: list[dict[str, Any]],
    few_shot_block: str,
) -> str:
    safe_text = candidate_text[:_MAX_TEXT_CHARS]
    hint = original_entities[:_MAX_HINT_ENTITIES]
    payload = {
        "full_encounter_text": safe_text,
        "sentence_subset": safe_text,
        "previous_extractor_output_for_reference": hint,
    }
    body = json.dumps(payload, ensure_ascii=True)
    if not few_shot_block:
        return body
    return f"{few_shot_block}\n\n--- TASK ---\n{body}"


def _call_haiku(
    system: str,
    user_msg: str,
    *,
    tier: str = "small",
    patient_id: str = "",
) -> tuple[str, str]:
    """Invoke Haiku via the shared LLM factory; returns (text, model_id).

    Imported lazily so the extractor module is cheap to import in tests
    that stub out the call.
    """
    from libs.llm_client.factory import create_llm

    client = create_llm(provider="aws", tier=tier)
    response = client.converse(
        system=system,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.0,
        max_tokens=_MAX_OUTPUT_TOKENS,
        agent_task="candidate_ai_first_pass",
        patient_id=str(patient_id or ""),
    )
    return response.text or "", response.model_id


def _parse_haiku_entities(raw: str) -> list[dict[str, Any]] | None:
    """Parse Haiku's JSON output into a list[dict] or None on failure."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[-1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # Maybe Haiku wrapped it in {"entities": [...]}.
        try:
            inner = json.loads(text[text.find("{") : text.rfind("}") + 1])
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        parsed = inner
    if isinstance(parsed, dict):
        for key in ("entities", "output", "items", "result"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
        else:
            return None
    if not isinstance(parsed, list):
        return None
    return [e for e in parsed if isinstance(e, dict)]


def ai_extract_entities(
    *,
    candidate: dict[str, Any],
    selector: FewShotSelector | None,
    k: int = _DEFAULT_FEW_SHOT_K,
    tier: str = "small",
    call_llm: Any = _call_haiku,
) -> ExtractionResult:
    """Run the AI extractor for one candidate.

    Returns an ExtractionResult. On any failure path the result falls
    back to the original entities_json so downstream code never sees a
    silent empty list as "the AI said no entities".
    """
    candidate_text = str(candidate.get("text") or "").strip()
    original_entities = _safe_load_entities(candidate.get("entities_json"))

    if not candidate_text:
        return ExtractionResult(
            entities=_to_extracted(original_entities),
            fallback_used=True,
            extractor_error="empty_candidate_text",
        )

    examples: list[dict[str, Any]] = []
    if selector is not None:
        try:
            examples = selector.select(candidate_text, k)
        except Exception:  # noqa: BLE001
            logger.warning("FewShotSelector.select failed", exc_info=True)
            examples = []

    few_shot_block = _format_few_shot_block(examples)
    user_msg = _build_user_message(
        candidate_text=candidate_text,
        original_entities=original_entities,
        few_shot_block=few_shot_block,
    )

    patient_id = str(candidate.get("patient_id") or "")
    try:
        raw, _model_id = call_llm(
            EXTRACTION_SYSTEM_V1, user_msg, tier=tier, patient_id=patient_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Haiku extractor call failed for candidate=%s: %s",
            candidate.get("candidate_id"),
            exc,
        )
        return ExtractionResult(
            entities=_to_extracted(original_entities),
            fallback_used=True,
            extractor_error=f"llm_error:{type(exc).__name__}",
        )

    parsed = _parse_haiku_entities(raw)
    if parsed is None:
        return ExtractionResult(
            entities=_to_extracted(original_entities),
            fallback_used=True,
            extractor_error="parse_error",
        )

    extracted = _to_extracted(parsed)
    if not extracted:
        return ExtractionResult(
            entities=_to_extracted(original_entities),
            fallback_used=True,
            extractor_error="zero_entities_after_parse",
        )

    return ExtractionResult(entities=extracted, fallback_used=False)
