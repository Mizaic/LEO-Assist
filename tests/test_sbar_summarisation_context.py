"""VT-LEO-AI-231 / VT-LEO-AI-509 -- SummarisationContext enum, group
mapping, source-resolver Neo4j-first lookup with hardcoded fallback,
and per-call cache.

Verifies DI-LEO-AI-231 (extended) and DI-LEO-AI-507 acceptance
criteria:
  - The enum has exactly 34 stable members.
  - Every member has a friendly label, a prompt fragment, and a
    display group mapping.
  - SBARArtifactRef accepts type='summarisation_context' with a
    context_value, and rejects it without one.
  - The legacy `fixed_text` artefact type still validates for one
    minor version of backward compatibility.
  - source_resolver._resolve_artifact() returns the matching
    prompt fragment in `prompt_snippet` (Neo4j-first when a
    session is provided, hardcoded-dict fallback otherwise).
  - The Neo4j-first lookup honours admin-edited PromptConfig text.
  - The fallback path tolerates None / raising / empty sessions.
  - resolve_situation() caches per-context lookups so two artefacts
    with the same context value cause at most one PromptConfig
    query.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from libs.sbar.events import (
    SBARArtifactRef,
    SBARSituationInput,
    SituationArtifactType,
    SUMMARISATION_CONTEXT_GROUPS,
    SUMMARISATION_CONTEXT_LABELS,
    SUMMARISATION_CONTEXT_PROMPTS,
    SummarisationContext,
)
from libs.sbar.source_resolver import (
    SBAR_SITUATION_CONTEXT_PROMPT_PREFIX,
    SBAR_SITUATION_CONTEXT_PROMPT_VERSION,
    _resolve_artifact,
    _situation_context_snippet,
    resolve_situation,
)


# --- Enum + label/prompt/group parity ---------------------------------------


def test_enum_has_exactly_34_members() -> None:
    assert len(list(SummarisationContext)) == 34


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


def test_every_member_has_a_group() -> None:
    members = set(SummarisationContext)
    assert set(SUMMARISATION_CONTEXT_GROUPS.keys()) == members
    allowed = {
        "Primary care",
        "Secondary care",
        "Statutory and social",
        "Quality assurance",
    }
    assert set(SUMMARISATION_CONTEXT_GROUPS.values()).issubset(allowed)


def test_mdt_discussion_label_is_primary_care_disambiguated() -> None:
    label = SUMMARISATION_CONTEXT_LABELS[SummarisationContext.mdt_discussion]
    assert "primary care" in label.lower()


def test_secondary_care_group_includes_new_contexts() -> None:
    secondary = {
        ctx.value
        for ctx, group in SUMMARISATION_CONTEXT_GROUPS.items()
        if group == "Secondary care"
    }
    expected_new = {
        "outpatient_new_clinic",
        "outpatient_followup_clinic",
        "mdt_specialty",
        "pre_op_assessment",
        "procedure_note",
        "ward_round_progress",
        "ed_handover",
        "comprehensive_geriatric_assessment",
        "tertiary_referral",
        "specialty_letter_to_gp",
        "chemotherapy_consent",
        "palliative_care_mdt",
    }
    assert expected_new.issubset(secondary)


def test_statutory_group_includes_new_contexts() -> None:
    statutory = {
        ctx.value
        for ctx, group in SUMMARISATION_CONTEXT_GROUPS.items()
        if group == "Statutory and social"
    }
    assert {"best_interests_dols", "mental_health_tribunal"}.issubset(statutory)


# --- Source resolver: fallback path -----------------------------------------


def test_source_resolver_falls_back_to_dict_when_session_is_none() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.clinic_appointment_prep,
    )
    resolved = _resolve_artifact(session=None, ref=art)
    assert resolved is not None
    expected_prompt = SUMMARISATION_CONTEXT_PROMPTS[
        SummarisationContext.clinic_appointment_prep
    ]
    assert resolved["prompt_snippet"] == expected_prompt
    assert resolved["value"] == "clinic_appointment_prep"


# --- Source resolver: Neo4j-first lookup ------------------------------------


class _FakeRunResult:
    def __init__(self, row):
        self._row = row

    def single(self):
        return self._row


class _FakeSession:
    """Minimal stand-in for a Neo4j session.

    `responses` maps the prompt name (as passed to `session.run`) to the
    value `single()` should return. Any other call returns None.
    """

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def run(self, _query, **params):
        name = params.get("name")
        self.calls.append(name)
        return _FakeRunResult(self.responses.get(name))


def test_source_resolver_uses_neo4j_snippet_when_present() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.two_week_wait,
    )
    name = (
        f"{SBAR_SITUATION_CONTEXT_PROMPT_PREFIX}"
        f"{SummarisationContext.two_week_wait.value}"
    )
    session = _FakeSession({name: {"systemPrompt": "OVERRIDE FRAMING"}})
    resolved = _resolve_artifact(session=session, ref=art)
    assert resolved["prompt_snippet"] == "OVERRIDE FRAMING"
    assert session.calls == [name]


def test_source_resolver_falls_back_when_neo4j_returns_no_row() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.ed_handover,
    )
    session = _FakeSession({})
    resolved = _resolve_artifact(session=session, ref=art)
    expected = SUMMARISATION_CONTEXT_PROMPTS[SummarisationContext.ed_handover]
    assert resolved["prompt_snippet"] == expected


def test_source_resolver_falls_back_when_neo4j_returns_empty_string() -> None:
    art = SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.mdt_specialty,
    )
    name = (
        f"{SBAR_SITUATION_CONTEXT_PROMPT_PREFIX}"
        f"{SummarisationContext.mdt_specialty.value}"
    )
    session = _FakeSession({name: {"systemPrompt": "   "}})
    resolved = _resolve_artifact(session=session, ref=art)
    expected = SUMMARISATION_CONTEXT_PROMPTS[SummarisationContext.mdt_specialty]
    assert resolved["prompt_snippet"] == expected


def test_source_resolver_falls_back_when_session_raises() -> None:
    class _RaisingSession:
        def __init__(self):
            self.calls = 0

        def run(self, *_a, **_kw):
            self.calls += 1
            raise RuntimeError("neo4j down")

    art = SBARArtifactRef(
        type=SituationArtifactType.summarisation_context,
        context_value=SummarisationContext.palliative_care_mdt,
    )
    session = _RaisingSession()
    resolved = _resolve_artifact(session=session, ref=art)
    expected = SUMMARISATION_CONTEXT_PROMPTS[
        SummarisationContext.palliative_care_mdt
    ]
    assert resolved["prompt_snippet"] == expected
    assert resolved["prompt_snippet"] is not None
    assert session.calls == 1


def test_situation_snippet_lookup_uses_versioned_query() -> None:
    """Smoke test: confirm we pass version=1 to the GET query so the
    resolver only ever returns the snippet from the seeded major version
    of the PromptConfig (forward-compat with future versions)."""
    captured = {}

    class _CapturingSession:
        def run(self, _query, **params):
            captured.update(params)
            return _FakeRunResult({"systemPrompt": "ok"})

    snippet = _situation_context_snippet(
        _CapturingSession(),
        SummarisationContext.discharge_summary,
    )
    assert snippet == "ok"
    assert captured["version"] == SBAR_SITUATION_CONTEXT_PROMPT_VERSION
    assert captured["name"].endswith("discharge_summary")


# --- Source resolver: per-call cache ---------------------------------------


def test_resolve_situation_caches_snippet_lookups_per_call(
    monkeypatch,
) -> None:
    """Two artefacts with the same context value should issue at most
    one PromptConfig lookup against the session."""
    name = (
        f"{SBAR_SITUATION_CONTEXT_PROMPT_PREFIX}"
        f"{SummarisationContext.hospital_admission.value}"
    )
    session = _FakeSession({name: {"systemPrompt": "ADMIT FRAMING"}})

    # Stub out the Patient lookup so resolve_situation does not need a
    # real graph: the only behaviour under test is the snippet cache.
    from libs.sbar import source_resolver as sr

    monkeypatch.setattr(
        sr,
        "get_patient_context",
        lambda _s, _pid: {"patient_id": _pid},
    )

    situation = SBARSituationInput(
        patient_id="P1",
        artifacts=[
            SBARArtifactRef(
                type=SituationArtifactType.summarisation_context,
                context_value=SummarisationContext.hospital_admission,
            ),
            SBARArtifactRef(
                type=SituationArtifactType.summarisation_context,
                context_value=SummarisationContext.hospital_admission,
            ),
        ],
    )
    resolved = resolve_situation(session, situation)
    assert len(resolved.artifacts) == 2
    for art in resolved.artifacts:
        assert art["prompt_snippet"] == "ADMIT FRAMING"
    # The cache must collapse two artefacts onto a single Neo4j call.
    assert session.calls == [name]


def test_resolve_situation_cache_keys_per_distinct_context(
    monkeypatch,
) -> None:
    name_admit = (
        f"{SBAR_SITUATION_CONTEXT_PROMPT_PREFIX}"
        f"{SummarisationContext.hospital_admission.value}"
    )
    name_disch = (
        f"{SBAR_SITUATION_CONTEXT_PROMPT_PREFIX}"
        f"{SummarisationContext.discharge_summary.value}"
    )
    session = _FakeSession(
        {
            name_admit: {"systemPrompt": "ADMIT"},
            name_disch: {"systemPrompt": "DISCH"},
        }
    )

    from libs.sbar import source_resolver as sr

    monkeypatch.setattr(
        sr,
        "get_patient_context",
        lambda _s, _pid: {"patient_id": _pid},
    )

    situation = SBARSituationInput(
        patient_id="P1",
        artifacts=[
            SBARArtifactRef(
                type=SituationArtifactType.summarisation_context,
                context_value=SummarisationContext.hospital_admission,
            ),
            SBARArtifactRef(
                type=SituationArtifactType.summarisation_context,
                context_value=SummarisationContext.discharge_summary,
            ),
            SBARArtifactRef(
                type=SituationArtifactType.summarisation_context,
                context_value=SummarisationContext.hospital_admission,
            ),
        ],
    )
    resolved = resolve_situation(session, situation)
    snippets = [art["prompt_snippet"] for art in resolved.artifacts]
    assert snippets == ["ADMIT", "DISCH", "ADMIT"]
    # Two distinct contexts -> exactly two Neo4j calls.
    assert session.calls == [name_admit, name_disch]
