"""Regression coverage for referral 000049823847: the referral was submitted
on the Serious Non-Specific Symptoms (NSS) pathway FORM, but is coded and
guideline-matched as a straightforward 2WW breast referral
(``ReferralRequest.clinicType == "2WW_BREAST"``, NG12 rule 1.4.1). The
Situation section previously named this as a vague, unexplained "conflicts
between 2WW and the Serious Non-Specific Symptoms pathway" -- clinically
valuable signal (wrong-pathway form used) rendered uselessly.

Covers:
1. ``clinic_type`` (the specific pathway, e.g. "2WW_BREAST") is now pulled
   onto the referral_request artefact alongside the generic ``specialty``.
2. The Situation prompt gives the model a concrete worked example of naming
   both sides of a form-vs-coded-pathway mismatch instead of a bare
   "conflicts between X and Y" clause.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from libs.prompts.sbar_situation_v1 import SBAR_SITUATION_SYSTEM_V1
from libs.sbar.events import SituationArtifactType
from libs.sbar.prompt_calls import _serialise_situation_context
from libs.sbar.source_resolver import _REFERRAL_REQUEST_QUERY, _resolve_artifact


def _flatten(txt: str) -> str:
    return " ".join(txt.split())


def test_referral_request_query_selects_clinic_type():
    assert "clinic_type" in _REFERRAL_REQUEST_QUERY
    assert "rr.clinicType" in _REFERRAL_REQUEST_QUERY


def test_resolve_artifact_returns_clinic_type_for_referral_request():
    from libs.sbar.events import SBARArtifactRef

    session = MagicMock()
    session.run.return_value.single.return_value = {
        "id": "000049823847",
        "specialty": "2WW",
        "clinic_type": "2WW_BREAST",
        "priority": "TWO_WEEK_WAIT",
        "reason": "Unilateral nipple discharge prompting concern for cancer.",
        "status": "AWAITING_TRIAGE",
        "created_at": "2026-03-19",
    }

    artefact = _resolve_artifact(
        session,
        SBARArtifactRef(type=SituationArtifactType.referral_request, id="000049823847"),
    )

    assert artefact["clinic_type"] == "2WW_BREAST"
    assert artefact["specialty"] == "2WW"


def test_situation_prompt_names_both_sides_of_pathway_mismatch():
    flat = _flatten(SBAR_SITUATION_SYSTEM_V1).lower()
    assert "clinic_type" in flat
    assert "never just say" in flat or "not just label the two pathway names" in flat
    assert "serious, non-specific symptoms pathway referral request" in flat
    # The bad/vague example the model must not reproduce verbatim.
    assert (
        'bad (too vague, do not write this): "the request conflicts '
        'between 2ww and the serious non-specific symptoms pathway."'
    ) in flat


def test_situation_prompt_prefers_specific_clinic_type_over_bare_specialty():
    flat = _flatten(SBAR_SITUATION_SYSTEM_V1).lower()
    assert "name the specific pathway" in flat
    assert "2ww_breast" in flat


def test_serialise_situation_context_includes_clinic_type_for_llm():
    from libs.sbar.source_resolver import ResolvedSituation

    resolved = ResolvedSituation(
        patient_id="pat-1",
        patient_summary={"gender": "female", "birth_date": "1955-04-09"},
        artifacts=[
            {
                "type": SituationArtifactType.referral_request.value,
                "id": "000049823847",
                "specialty": "2WW",
                "clinic_type": "2WW_BREAST",
                "priority": "TWO_WEEK_WAIT",
                "reason": "Unilateral nipple discharge prompting concern for cancer.",
            }
        ],
    )

    user_message = _serialise_situation_context(resolved)
    body = json.loads(user_message.split("```json\n", 1)[1].rsplit("\n```", 1)[0])

    artefact = body["artifacts"][0]
    assert artefact["clinic_type"] == "2WW_BREAST"
    assert artefact["specialty"] == "2WW"
