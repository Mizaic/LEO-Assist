"""Disorder entity verifier: dual-model consensus gate for false positives.

Only called for disorder entities whose assertion is 'present' after ConText.
Classifies whether the entity is an active confirmed diagnosis or merely
informational/historical/uncertain context within the encounter text.

Consensus pattern:
  1. Haiku (AWS small) + GPT-5 mini (Azure small) in parallel.
  2. If they agree, use that verdict.
  3. If they disagree, Sonnet (AWS big) arbitrates.

Fail-safe behaviour depends on coding mode:
  HITL:       default to ACTIVE_DIAGNOSIS (human will review)
  AUTONOMOUS: default to UNCERTAIN (do not code without confirmation)
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum

from libs.llm_client.consensus import ConsensusResult, run_consensus
from libs.llm_client.prompt_safety import (
    INJECTION_GUARD,
    cap_llm_response,
    sanitise_for_prompt,
)

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM_PROMPT = INJECTION_GUARD + (
    "You are a UK primary care clinical coding specialist.\n\n"
    "You are given a clinical entity (a disorder or condition) extracted from a "
    "GP record encounter, along with the full encounter text.\n\n"
    "Your task: decide whether the entity represents an ACTIVE confirmed diagnosis "
    "for this patient, or whether it appears in a different context.\n\n"
    "Return exactly ONE of these verdicts:\n"
    "  active_diagnosis -- the disorder is asserted as a current confirmed finding "
    "for this patient (e.g. 'Patient has CKD stage 3', 'Dx: type 2 diabetes', "
    "'Discussed diabetes management', 'Referral: CKD stage 3 for nephrology review', "
    "'Known COPD', 'On treatment for hypertension')\n"
    "  informational   -- the entity appears ONLY in a test name, formula name, "
    "measurement label, template field name, protocol title, or eGFR calculation "
    "label (e.g. 'eGFR formula (CKD-EPI)', 'HbA1c target per NICE diabetes "
    "guideline', 'CKD-EPI creatinine equation'). "
    "Do NOT return informational for entities in referral reasons, monitoring "
    "plans, problem lists, or active management contexts — those are "
    "active_diagnosis.\n"
    "  historical      -- the entity clearly refers to a past RESOLVED condition, "
    "appearing after h/o, history of, background, or explicit past-tense "
    "resolution language. 'Discussed X' does NOT make X historical — "
    "discussion of a condition means it is actively managed.\n"
    "  refuted         -- the entity was an initial impression later overridden "
    "by investigation (e.g. 'initially suggested Barrett's oesophagus, but biopsy "
    "confirmed cancer'). The overridden impression is refuted, not informational.\n"
    "  uncertain       -- the entity is prefixed with possible, query, ?, or "
    "clinical context is insufficient to classify\n\n"
    "RULES:\n"
    "1. If the entity is ONLY in a test name or measurement label, return "
    "informational.\n"
    "2. If the entity appears in a referral reason or monitoring plan, it is "
    "active_diagnosis (the patient HAS the condition — that is why they are "
    "being referred or monitored).\n"
    "3. When in doubt between active_diagnosis and uncertain, prefer uncertain.\n"
    "4. When in doubt between informational and historical, prefer informational.\n"
    "5. A lab result (eGFR, creatinine, HbA1c, sodium, haemoglobin, etc.) is an "
    "observation, NOT a diagnosis. If the disorder entity was extracted from a lab "
    "result line, return informational. 'CKD-EPI' (Chronic Kidney Disease "
    "Epidemiology Collaboration) is a formula name — it is NOT a diagnosis.\n"
    "6. Do NOT classify a lab value as active_diagnosis. Only return "
    "active_diagnosis when the encounter text explicitly states a confirmed "
    "diagnosis for the patient.\n"
    "7. An initial impression later contradicted by investigation is refuted, "
    "not informational.\n\n"
    "Respond ONLY with a JSON object:\n"
    '{"verdict": "<one of the five verdicts>", "reason": "<one sentence>"}'
)


class DisorderVerdict(str, Enum):
    ACTIVE_DIAGNOSIS = "active_diagnosis"
    INFORMATIONAL = "informational"
    HISTORICAL = "historical"
    REFUTED = "refuted"
    UNCERTAIN = "uncertain"


def _parse_verdict(text: str) -> str:
    """Extract the verdict string from raw LLM response text."""
    text = cap_llm_response(text, max_chars=1000)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        verdict = (
            str(parsed.get("verdict", "")).strip() if isinstance(parsed, dict) else ""
        )
        return verdict if verdict in _VALID_VERDICTS else ""
    except json.JSONDecodeError:
        pass
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return ""
    try:
        parsed = json.loads(m.group(0))
        verdict = (
            str(parsed.get("verdict", "")).strip() if isinstance(parsed, dict) else ""
        )
        return verdict if verdict in _VALID_VERDICTS else ""
    except json.JSONDecodeError:
        return ""


_VALID_VERDICTS = {v.value for v in DisorderVerdict}


def _fail_verdict_for_mode(coding_mode: str) -> str:
    if coding_mode == "autonomous":
        return DisorderVerdict.UNCERTAIN.value
    return DisorderVerdict.ACTIVE_DIAGNOSIS.value


def verify_disorder(
    entity_text: str,
    encounter_text: str,
    *,
    coding_mode: str = "hitl",
) -> DisorderVerdict:
    """Classify a disorder entity using dual-model consensus.

    In HITL mode, defaults to ACTIVE_DIAGNOSIS on failure so a human sees it.
    In AUTONOMOUS mode, defaults to UNCERTAIN so the entity is not coded.
    """
    user_msg = json.dumps(
        {
            "entity_text": sanitise_for_prompt(entity_text, max_chars=200),
            "encounter_text": sanitise_for_prompt(encounter_text, max_chars=2_000),
        }
    )

    fail_v = _fail_verdict_for_mode(coding_mode)

    result: ConsensusResult = run_consensus(
        system_prompt=_SYSTEM_PROMPT,
        user_msg=user_msg,
        parse_fn=_parse_verdict,
        fail_verdict=fail_v,
        max_tokens=150,
    )

    raw = result.verdict
    if raw not in _VALID_VERDICTS:
        logger.warning(
            "DisorderVerifier consensus returned unknown verdict %r for %r "
            "-- using fail_verdict=%s",
            raw,
            entity_text,
            fail_v,
        )
        return DisorderVerdict(fail_v)

    verdict = DisorderVerdict(raw)
    logger.info(
        "DisorderVerifier entity=%r verdict=%s agreed=%s models=%s",
        entity_text,
        verdict.value,
        result.agreed,
        result.model_ids,
    )
    return verdict
