"""Fix Analyzer service.

Ported from VRB clinical-ai/app/agent/subagents/fix_analyzer.py.

Takes a structured correction from HITL review and uses an LLM to determine
what fix should be applied to the knowledge layer (ValueSet, ConceptMap,
DomainRegistry) to prevent the same error in future runs.

Returns a FixProposal that can be applied, dismissed, or edited by a human.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import uuid4

from libs.llm_client.providers import invoke_with_fallback

logger = logging.getLogger(__name__)

FIX_ANALYZER_SYSTEM = """You are a clinical coding knowledge-base analyst.

Given a human correction to an AI-proposed encounter label, recommend a fix to the
knowledge layer so the AI gets it right next time.

Fix types you can recommend:
- add_synonym: Add a text synonym / designation to a FHIR ValueSet concept so the
  search engine matches this wording next time.
- add_code: Add a new SNOMED concept to a ValueSet for a domain.
- update_code: Replace an incorrect SNOMED concept with the correct one in a ValueSet.
- add_mapping: Add a mapping in a ConceptMap (source -> target).
- update_milestone_prompt: Suggest a change to the episode builder prompt (not
  auto-applicable; will be queued for a developer).
- no_fix: No knowledge-layer change is needed (e.g. the AI was correct but the user
  disagrees, or it's a one-off data issue).

OUTPUT: Return ONLY a single JSON object with these fields:
{
  "fix_type": "<one of the types above>",
  "domain": "<domain name, e.g. fast_track_referrals>",
  "resource_type": "<ValueSet | ConceptMap | null>",
  "resource_id": "<FHIR resource id if known, else null>",
  "change_description": "<plain-English description of the change>",
  "change_payload": <JSON patch object or null>,
  "confidence": <0-100>,
  "reasoning": "<why this fix is recommended>",
  "auto_applicable": <true|false>
}

Rules:
- If the correction type is "missing_synonym", the fix is almost always add_synonym.
- If the correction type is "wrong_code", the fix is usually update_code or add_code.
- If the correction type is "missing_code", the fix is usually add_code.
- If the correction type is "wrong_milestone", the fix is usually update_milestone_prompt.
- If the correction type is "wrong_encounter", the fix is usually no_fix.
- Set auto_applicable=true only for add_synonym, add_code, update_code, add_mapping.
- Set auto_applicable=false for update_milestone_prompt and no_fix.
"""


def analyze_correction(
    *,
    correction_type: str,
    correct_value: Optional[str],
    user_reason: Optional[str],
    proposal: Dict[str, Any],
    encounter_context: Optional[Dict[str, Any]] = None,
    domain_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Analyze a correction and return a FixProposal dict."""
    user_parts = [
        "## Correction",
        f"Type: {correction_type}",
    ]
    if correct_value:
        user_parts.append(f"Correct value: {correct_value}")
    if user_reason:
        user_parts.append(f"Reason: {user_reason}")

    user_parts.append("\n## Original AI Proposal")
    user_parts.append(json.dumps(proposal, indent=2, default=str))

    if encounter_context:
        user_parts.append("\n## Encounter Context")
        user_parts.append(json.dumps(encounter_context, indent=2, default=str))

    if domain_context:
        user_parts.append("\n## Current Domain / ValueSet Context")
        user_parts.append(json.dumps(domain_context, indent=2, default=str))

    user_message = "\n".join(user_parts)

    logger.info(
        "Analyzing correction: type=%s correct_value=%s", correction_type, correct_value
    )

    messages = [
        {"role": "system", "content": FIX_ANALYZER_SYSTEM},
        {"role": "user", "content": user_message},
    ]
    response = invoke_with_fallback(messages, max_tokens=2048, temperature=0.1)

    try:
        result = json.loads(
            response.content if hasattr(response, "content") else str(response)
        )
    except (json.JSONDecodeError, AttributeError):
        result = {"fix_type": "no_fix", "reasoning": "Failed to parse LLM response"}

    fix = {
        "fix_id": f"FIX_{uuid4().hex}",
        "fix_type": result.get("fix_type", "no_fix"),
        "domain": result.get("domain"),
        "resource_type": result.get("resource_type"),
        "resource_id": result.get("resource_id"),
        "change_description": result.get("change_description", ""),
        "change_payload": result.get("change_payload"),
        "confidence": result.get("confidence", 0),
        "reasoning": result.get("reasoning", ""),
        "auto_applicable": result.get("auto_applicable", False),
        "status": "pending",
    }

    logger.info(
        "Fix analysis complete: fix_type=%s confidence=%d auto_applicable=%s",
        fix["fix_type"],
        fix["confidence"],
        fix["auto_applicable"],
    )
    return fix
