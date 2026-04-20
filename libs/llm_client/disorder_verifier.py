"""Disorder entity verifier: LLM-judge gate for disorder false positives.

Atlas trace:
  DO: DO-19EB27A0
  Also implements: DO-68FDA1E0
  DI: DI-3197332F, DI-9D967259
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-19EB27A0")

Only called for disorder entities whose assertion is ``present`` after
ConText. Classifies whether the entity is an active confirmed diagnosis or
merely informational / historical / uncertain context within the encounter
text.

Backing implementation
----------------------
``libs.llm_client.consensus.run_consensus`` issues a single AWS Bedrock call
(with one parse-retry). An optional dual-model consensus can be enabled via
``CONSENSUS_DUAL_MODEL=true`` which dispatches parallel AWS + Azure small-tier
judges with a big-tier arbitrator on disagreement (see ``consensus.py``).

Fail-safe behaviour
-------------------
Both HITL and AUTONOMOUS now fail CLOSED on consensus failure. A failed gate
call returns ``GATE_FAILED`` (not ``ACTIVE_DIAGNOSIS``). Downstream, the tier
classifier treats ``gate_failed`` the same way as ``uncertain`` -- the entity
is routed to review, never silently auto-coded. Previously HITL defaulted to
``ACTIVE_DIAGNOSIS`` which meant a silent Bedrock failure looked identical to
a confirmed diagnosis in the review queue.
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
    "  informational   -- the entity only appears in a test name, formula name, "
    "or measurement label (e.g. 'eGFR formula (CKD-EPI)', 'HbA1c target per "
    "NICE guideline', 'CKD-EPI creatinine equation'). "
    "Do NOT use informational for referral reasons, monitoring plans, problem "
    "lists, or active management contexts -- those are active_diagnosis.\n"
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
    "5. Lab results (eGFR, creatinine, HbA1c, sodium, haemoglobin) are "
    "observations, not diagnoses. If the entity came from a lab result line, "
    "return informational. CKD-EPI is a formula name, not a diagnosis.\n"
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
    # Consensus call failed (provider error, parse error, etc). This is
    # surfaced explicitly so callers can distinguish "the model is unsure"
    # from "we never got an answer".
    GATE_FAILED = "gate_failed"


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
    """Fail-closed for both modes.

    Any verify_disorder call that cannot obtain a parseable consensus response
    returns ``gate_failed``. The tier classifier treats ``gate_failed`` the
    same as ``uncertain`` which routes the entity to review (HITL) or blocks
    auto-coding (autonomous). Previously HITL fell back to ACTIVE_DIAGNOSIS
    which silently let provider outages look like confirmed diagnoses.
    """
    del coding_mode  # retained for call-site symmetry; no longer branches
    return DisorderVerdict.GATE_FAILED.value


def verify_disorder(
    entity_text: str,
    encounter_text: str,
    *,
    coding_mode: str = "hitl",
) -> DisorderVerdict:
    """Classify a disorder entity using the LLM-judge consensus gate.

    Fails CLOSED in both modes: a consensus failure (provider error, empty
    response, unknown verdict) returns ``GATE_FAILED`` so the downstream tier
    classifier can route the entity to review instead of silently passing it
    as an active diagnosis.
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
            "-- using fail_verdict=%s (coding_mode=%s)",
            raw,
            entity_text,
            fail_v,
            coding_mode,
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
