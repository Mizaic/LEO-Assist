"""VT-LEO-AI-231 -- SummarisationContext enum + source-resolver injection.

Verifies DI-LEO-AI-231 acceptance criteria:
  - The enum has exactly 20 stable members.
  - Every member has a friendly label and a prompt fragment.
  - SBARArtifactRef accepts type='summarisation_context' with a
    context_value, and rejects it without one.
  - The legacy `fixed_text` artefact type still validates for one
    minor version of backward compatibility.
  - source_resolver._resolve_artifact() injects the matching
    prompt fragment into the resolved artefact dict.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.sbar.events import (
    SBARArtifactRef,
    SituationArtifactType,
    SummarisationContext,
    SUMMARISATION_CONTEXT_LABELS,
    SUMMARISATION_CONTEXT_PROMPTS,
)
from libs.sbar.source_resolver import _resolve_artifact


def test_enum_has_exactly_20_members() -> None:
    assert len(list(SummarisationContext)) == 20


def test_every_member_has_a_label_and_prompt() -> None:
    members = set(SummarisationContext)
    assert set(SUMMARISATION_CONTEXT_LABELS.keys()) == members
    assert set(SUMMARISATION_CONTEXT_PROMPTS.keys()) == members
    for value, label in SUMMARISATION_CONTEXT_LABELS.items():
        assert label.strip(), f"empty label for {value.value}"
    for value, prompt in SUMMARISATION_CONTEXT_PROMPTS.items():
        assert prompt.strip(), f"empty prompt for {value.value}"


def test_summarisation_context_artefact_requires_context_value() -> None:
    SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.clinic_appointment_prep,
    )
    with pytest.raises(ValidationError):
        SBARArtifactRef(type=SituationArtifactType.summarisation_context)


def test_legacy_fixed_text_still_validates() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.fixed_text,
        text="NCDA review",
    )
    assert art.text == "NCDA review"


def test_source_resolver_injects_matching_prompt_fragment() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.clinic_appointment_prep,
    )
    resolved = _resolve_artifact(session=None, ref=art)
    assert resolved is not None
    expected_prompt = SUMMARISATION_CONTEXT_PROMPTS[
        SummarisationContext.clinic_appointment_prep
    ]
    flat = " ".join(str(v) for v in resolved.values())
    assert expected_prompt in flat
    assert SummarisationContext.clinic_appointment_prep.value in flat
