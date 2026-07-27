"""LLM helper: expand a vague clinical phrase into candidate term strings.

Atlas trace:
  DI: DI-42246DA7
  DO: DO-F8C56339
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")

Used by the guidance-rule authoring "Ask LEO for ideas" flow. The model
returns plain-English finding/symptom/test names only -- never SNOMED
concept IDs. The UI grounds each ticked term via /api/terminology/search
so codes always come from the terminology index, not the LLM.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from libs.llm_client.factory import create_llm
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    redact_for_log,
    sanitise_for_prompt,
)

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_MAX_TERMS = 20
_MIN_TERM_LEN = 2
_MAX_TERM_LEN = 80

_SYSTEM = INJECTION_GUARD + (
    "You help UK primary-care clinicians turn a vague guideline phrase "
    "into a short list of specific clinical terms they can look up in "
    "SNOMED CT.\n\n"
    "The phrase is usually something like 'symptoms of lung cancer' or "
    "'skin changes suggestive of breast cancer'.\n\n"
    "RULES:\n"
    "1. Return ONLY plain-English clinical terms (findings, symptoms, "
    "signs, or common blood-test names). Never invent SNOMED IDs.\n"
    "2. Prefer terms a GP note would use. Keep each term short "
    "(a few words).\n"
    "3. Do not repeat the original vague phrase itself.\n"
    "4. Do not include advice, procedures to offer, or referral wording.\n"
    "5. Return between 4 and 15 terms when the phrase is clinical; "
    "return an empty list if the phrase is not a clinical topic.\n"
    "6. Reply with JSON only: "
    '{"terms": ["term one", "term two"], "reason": "one short sentence"}\n'
)


@dataclass
class TopicExpansionResult:
    """Plain-English terms suggested for a vague clinical phrase."""

    terms: list[str] = field(default_factory=list)
    reason: str = ""
    model_id: str = ""


def _parse_json(text: str) -> dict:
    text = cap_llm_response(text, max_chars=4000)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalise_terms(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        term = " ".join(item.strip().split())
        if len(term) < _MIN_TERM_LEN or len(term) > _MAX_TERM_LEN:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= _MAX_TERMS:
            break
    return out


def expand_topic_terms(
    *,
    phrase: str,
    tier: str = "small",
) -> TopicExpansionResult:
    """Ask an LLM for plain-English clinical terms matching ``phrase``.

    Never returns SNOMED IDs. On LLM failure returns an empty term list
    with a short reason the UI can show.
    """
    cleaned = sanitise_for_prompt(phrase, max_chars=400).strip()
    if len(cleaned) < _MIN_TERM_LEN:
        return TopicExpansionResult(reason="Phrase was empty.")

    user_msg = json.dumps({"phrase": cleaned})
    resolved_tier = tier if tier in ("small", "big", "max") else "small"
    try:
        client = create_llm(provider="aws", tier=resolved_tier)
        response = client.converse(
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.0,
            max_tokens=600,
            agent_task="topic_expansion",
        )
    except Exception:
        logger.warning(
            "topic_expansion failed for %s",
            redact_for_log(phrase),
            exc_info=True,
        )
        return TopicExpansionResult(
            reason="LEO could not suggest terms right now.",
        )

    parsed = _parse_json(response.text)
    terms = _normalise_terms(parsed.get("terms"))
    reason = str(parsed.get("reason", "")).strip()[:300]
    return TopicExpansionResult(
        terms=terms,
        reason=reason,
        model_id=getattr(response, "model_id", "") or "",
    )
