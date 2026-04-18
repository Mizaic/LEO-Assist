"""VT-LEO-AI-180: SBARRequestPayload contract validation.

Verifies DI-LEO-AI-186 acceptance criteria:
- Patient id is required
- Each artefact must carry an id (or text for fixed_text)
- Background source types are restricted to the allowed enum
- Round-trip via ``to_pipeline_message`` preserves the contract shape
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.sbar.events import (
    BackgroundSourceType,
    SBARArtifactRef,
    SBARBackgroundSourceRef,
    SBARRequestPayload,
    SBARSituationInput,
    SituationArtifactType,
)


def _minimal_payload() -> SBARRequestPayload:
    return SBARRequestPayload(
        run_id="run-1",
        situation=SBARSituationInput(patient_id="p-1"),
    )


def test_minimal_payload_validates() -> None:
    p = _minimal_payload()
    assert p.event_type == "sbar_requested"
    assert p.situation.patient_id == "p-1"
    assert p.background == []
    assert p.guideline_ids == []


def test_referral_artefact_requires_id() -> None:
    with pytest.raises(ValidationError):
        SBARArtifactRef(type=SituationArtifactType.referral_request)


def test_fixed_text_artefact_requires_text() -> None:
    with pytest.raises(ValidationError):
        SBARArtifactRef(type=SituationArtifactType.fixed_text)


def test_fixed_text_artefact_accepts_text_only() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.fixed_text,
        text="NCDA",
    )
    assert art.text == "NCDA"
    assert art.id is None


def test_background_source_types_are_restricted() -> None:
    valid = SBARBackgroundSourceRef(
        type=BackgroundSourceType.encounter, id="e-1"
    )
    assert valid.type is BackgroundSourceType.encounter
    with pytest.raises(ValidationError):
        SBARBackgroundSourceRef(type="WrongType", id="x")  # type: ignore[arg-type]


def test_to_pipeline_message_preserves_contract() -> None:
    p = SBARRequestPayload(
        run_id="run-9",
        situation=SBARSituationInput(
            patient_id="p-99",
            artifacts=[
                SBARArtifactRef(
                    type=SituationArtifactType.referral_request,
                    id="rr-1",
                ),
                SBARArtifactRef(
                    type=SituationArtifactType.fixed_text,
                    text="NCDA",
                ),
            ],
        ),
        background=[
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.encounter, id="enc-1"
            ),
            SBARBackgroundSourceRef(
                type=BackgroundSourceType.chunk, id="ch-1"
            ),
        ],
        guideline_ids=["G-LUNG"],
        encounter_id="enc-2",
    )
    msg = p.to_pipeline_message()
    assert msg["event_type"] == "sbar_requested"
    assert msg["patient_id"] == "p-99"
    assert msg["encounter_id"] == "enc-2"
    ctx = msg["context"]
    assert ctx["run_id"] == "run-9"
    assert ctx["situation"]["patient_id"] == "p-99"
    assert len(ctx["situation"]["artifacts"]) == 2
    assert {a["type"] for a in ctx["situation"]["artifacts"]} == {
        "ReferralRequest", "FixedText",
    }
    assert {b["type"] for b in ctx["background"]} == {"Encounter", "Chunk"}
    assert ctx["guideline_ids"] == ["G-LUNG"]
