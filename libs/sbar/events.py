"""Queue contract for SBAR generation jobs.

A producer (Admin UI playground, encounter-created hook, referral writer)
publishes a ``sbar_requested`` message to the ``pipeline-jobs`` queue. The
pipeline worker dispatches the payload to ``SBAROrchestrator``.

Schema (validated with Pydantic) decouples producers from the orchestrator
and provides a single place to validate and document the contract -- see
DI-LEO-AI-186.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SituationArtifactType(str, Enum):
    """Permitted Situation input artefact node labels.

    The Situation always includes the patient. Optionally, callers may
    attach one or more record artefacts (a referral request, a procedure
    request, a fixed Patient context block, or a typed Summarisation
    Context such as 'clinic appointment prep' or 'discharge summary').
    The enum is open for extension -- add new types here and update
    ``source_resolver._resolve_artifact``.

    The legacy ``fixed_text`` member is kept for one minor version of
    backward compatibility: existing fixtures that pass
    ``type="FixedText"`` with a free-form ``text`` value will continue to
    deserialise. New producers MUST use ``summarisation_context`` and
    pass a ``context_value`` from :class:`SummarisationContext`.
    """

    referral_request = "ReferralRequest"
    procedure_request = "ProcedureRequest"
    patient_context = "PatientContext"
    summarisation_context = "SummarisationContext"
    # Deprecated: removed after one minor version. Producers must migrate
    # to summarisation_context with a SummarisationContext value.
    fixed_text = "FixedText"


class SummarisationContext(str, Enum):
    """NHS-aligned reasons a clinician asks LEO for an SBAR summary.

    Each value is a stable backend string (kept short and snake_case) so
    it can be persisted on the SBAR job, the resulting Assessment node
    and any downstream audit trail without relying on UI labels.

    Grouped (display order) into:
        Primary care  - clinic_appointment_prep, annual_ltc_review,
                        structured_medication_review, mdt_discussion,
                        ncda, two_week_wait, frailty_pcsp,
                        learning_disability_ahc
        Acute         - hospital_admission, discharge_summary,
                        ooh_handover
        Statutory /
        social        - care_home_review, advance_care_planning,
                        safeguarding_case, continuing_healthcare,
                        death_summary, insurance_dvla_report,
                        subject_access_request
        Quality
        assurance     - significant_event_review, peer_review_cbd

    Display labels live in the matching SUMMARISATION_CONTEXT_LABELS
    dict so the enum stays purely a contract.
    """

    clinic_appointment_prep = "clinic_appointment_prep"
    annual_ltc_review = "annual_ltc_review"
    structured_medication_review = "structured_medication_review"
    mdt_discussion = "mdt_discussion"
    ncda = "ncda"
    two_week_wait = "two_week_wait"
    hospital_admission = "hospital_admission"
    discharge_summary = "discharge_summary"
    ooh_handover = "ooh_handover"
    care_home_review = "care_home_review"
    advance_care_planning = "advance_care_planning"
    safeguarding_case = "safeguarding_case"
    significant_event_review = "significant_event_review"
    continuing_healthcare = "continuing_healthcare"
    death_summary = "death_summary"
    insurance_dvla_report = "insurance_dvla_report"
    subject_access_request = "subject_access_request"
    peer_review_cbd = "peer_review_cbd"
    frailty_pcsp = "frailty_pcsp"
    learning_disability_ahc = "learning_disability_ahc"


# Friendly display labels (UK English, sentence case where natural).
SUMMARISATION_CONTEXT_LABELS: dict[SummarisationContext, str] = {
    SummarisationContext.clinic_appointment_prep: "Clinic appointment prep",
    SummarisationContext.annual_ltc_review: "Long-term condition annual review",
    SummarisationContext.structured_medication_review: (
        "Structured medication review (SMR)"
    ),
    SummarisationContext.mdt_discussion: "MDT (multidisciplinary team) meeting",
    SummarisationContext.ncda: "National Cancer Diagnosis Audit (NCDA)",
    SummarisationContext.two_week_wait: (
        "Suspected cancer (2WW / Faster Diagnosis)"
    ),
    SummarisationContext.hospital_admission: "Hospital admission summary",
    SummarisationContext.discharge_summary: "Hospital discharge summary",
    SummarisationContext.ooh_handover: "Out-of-hours handover",
    SummarisationContext.care_home_review: "Care home / housebound review",
    SummarisationContext.advance_care_planning: (
        "Advance care planning / ReSPECT / TEP"
    ),
    SummarisationContext.safeguarding_case: "Safeguarding case conference",
    SummarisationContext.significant_event_review: (
        "Significant event review (SEA)"
    ),
    SummarisationContext.continuing_healthcare: "Continuing healthcare (CHC)",
    SummarisationContext.death_summary: "Death summary / coroner request",
    SummarisationContext.insurance_dvla_report: (
        "Insurance / DVLA / occupational report"
    ),
    SummarisationContext.subject_access_request: "Subject access request (SAR)",
    SummarisationContext.peer_review_cbd: (
        "Peer review / Case-based discussion (CBD)"
    ),
    SummarisationContext.frailty_pcsp: (
        "Frailty / personalised care and support plan (PCSP)"
    ),
    SummarisationContext.learning_disability_ahc: (
        "Learning disability annual health check"
    ),
}


# Per-context prompt fragments injected into the Situation stage of the
# SBAR orchestrator. Each snippet describes what the LLM should
# emphasise for that context. Kept short so the orchestrator can
# concatenate without bloating the prompt.
SUMMARISATION_CONTEXT_PROMPTS: dict[SummarisationContext, str] = {
    SummarisationContext.clinic_appointment_prep: (
        "Frame the Situation around what the clinician needs to ask or "
        "review at today's clinic appointment."
    ),
    SummarisationContext.annual_ltc_review: (
        "Frame the Situation around the patient's long-term conditions, "
        "current control, and any review actions due."
    ),
    SummarisationContext.structured_medication_review: (
        "Frame the Situation around the patient's medications: "
        "indications, problems, side effects, and review priorities."
    ),
    SummarisationContext.mdt_discussion: (
        "Frame the Situation as a concise MDT case presentation: "
        "diagnosis, current management, decision the team must make."
    ),
    SummarisationContext.ncda: (
        "Frame the Situation for a National Cancer Diagnosis Audit "
        "review: route to diagnosis, intervals, and any avoidable delay."
    ),
    SummarisationContext.two_week_wait: (
        "Frame the Situation around the suspected cancer concern, the "
        "2WW / Faster Diagnosis pathway and what the receiving team "
        "needs to action."
    ),
    SummarisationContext.hospital_admission: (
        "Frame the Situation around the reason for admission, current "
        "stability, and anything the admitting team must know now."
    ),
    SummarisationContext.discharge_summary: (
        "Frame the Situation around the discharge: diagnosis, "
        "treatment given, follow-up needed, and red flags for the GP."
    ),
    SummarisationContext.ooh_handover: (
        "Frame the Situation as an out-of-hours handover: the active "
        "concern, what has been done, what the next clinician must do."
    ),
    SummarisationContext.care_home_review: (
        "Frame the Situation around a care home / housebound review: "
        "frailty, problem list, current treatment, anticipatory needs."
    ),
    SummarisationContext.advance_care_planning: (
        "Frame the Situation around ACP / ReSPECT / TEP: prognosis, "
        "patient wishes, ceilings of treatment, escalation plan."
    ),
    SummarisationContext.safeguarding_case: (
        "Frame the Situation for a safeguarding case conference: "
        "concerns, evidence, agencies involved, immediate risk."
    ),
    SummarisationContext.significant_event_review: (
        "Frame the Situation as a significant event review: what "
        "happened, what could have been done differently, learning."
    ),
    SummarisationContext.continuing_healthcare: (
        "Frame the Situation for a Continuing Healthcare assessment: "
        "primary health needs across the four key indicators."
    ),
    SummarisationContext.death_summary: (
        "Frame the Situation as a death summary: sequence of events "
        "leading to death, contributing conditions, mode of death."
    ),
    SummarisationContext.insurance_dvla_report: (
        "Frame the Situation factually for an insurance or DVLA report: "
        "diagnoses, medications, fitness-relevant findings only."
    ),
    SummarisationContext.subject_access_request: (
        "Frame the Situation as a high-level patient-readable summary "
        "of their record. Avoid clinical jargon."
    ),
    SummarisationContext.peer_review_cbd: (
        "Frame the Situation for a peer review / case-based discussion: "
        "presenting problem, decisions made, learning points."
    ),
    SummarisationContext.frailty_pcsp: (
        "Frame the Situation around a frailty / personalised care and "
        "support plan: goals, support network, anticipated needs."
    ),
    SummarisationContext.learning_disability_ahc: (
        "Frame the Situation around an LD annual health check: "
        "communication needs, reasonable adjustments, health actions."
    ),
}


class BackgroundSourceType(str, Enum):
    """Permitted Background input source node labels."""

    encounter = "Encounter"
    document_reference = "DocumentReference"
    chunk = "Chunk"


class SBARSituationInput(BaseModel):
    """Situation inputs.

    ``patient_id`` is mandatory. ``artifacts`` is an ordered list of
    record-artefact references (zero or more). ``fixed_text`` entries
    may carry a literal ``text`` value rather than a Neo4j node id (used
    for 'NCDA' or specialty-clinic context labels).
    """

    patient_id: str = Field(..., min_length=1)
    artifacts: list["SBARArtifactRef"] = Field(default_factory=list)


class SBARArtifactRef(BaseModel):
    """One Situation artefact reference.

    The validator enforces a per-type contract:

    * ``referral_request``, ``procedure_request``, ``patient_context``
      require a Neo4j node id.
    * ``summarisation_context`` requires a ``context_value`` from
      :class:`SummarisationContext`.
    * The legacy ``fixed_text`` requires a non-empty ``text`` value.
      Producers should migrate to ``summarisation_context`` --
      ``fixed_text`` will be removed after one minor version.
    """

    type: SituationArtifactType
    id: str | None = None
    text: str | None = None
    context_value: SummarisationContext | None = None

    @model_validator(mode="after")
    def _validate_id_or_text(self) -> "SBARArtifactRef":
        if self.type is SituationArtifactType.summarisation_context:
            if self.context_value is None:
                raise ValueError(
                    "summarisation_context artefacts require a "
                    "context_value from SummarisationContext"
                )
            return self
        if self.type is SituationArtifactType.fixed_text:
            if not (self.text or "").strip():
                raise ValueError("fixed_text artefacts require non-empty text")
            return self
        if not (self.id or "").strip():
            raise ValueError(
                f"{self.type.value} artefacts require a Neo4j node id"
            )
        return self


class SBARBackgroundSourceRef(BaseModel):
    """One Background input source -- an Encounter, DocumentReference, or Chunk.

    For DocumentReferences, the orchestrator resolves child :Chunk nodes
    automatically when present (and falls back to the document text body
    otherwise).
    """

    type: BackgroundSourceType
    id: str = Field(..., min_length=1)


class SBARRequestPayload(BaseModel):
    """Body of a ``sbar_requested`` pipeline-jobs message."""

    event_type: Literal["sbar_requested"] = "sbar_requested"
    run_id: str = Field(..., min_length=1)
    requested_by: str | None = None
    tenant_id: str | None = None

    situation: SBARSituationInput
    background: list[SBARBackgroundSourceRef] = Field(default_factory=list)

    # Optional reviewer-supplied free-text concern. Framed in the
    # Situation prompt as a QSIR-aligned "what is the worry today" note
    # so the LLM can tailor its summary. Capped to 500 characters to
    # keep prompt cost bounded; UI enforces the same limit.
    concern: str | None = Field(default=None, max_length=500)

    # Optional restriction to a subset of guidelines for the Assessment
    # roaring-bitmap evaluation. Empty -> evaluate against the global scope.
    guideline_ids: list[str] = Field(default_factory=list)

    # Optional client-provided assessment id. If omitted the orchestrator
    # generates one (uuid4 hex). Useful for retries / idempotency tests.
    assessment_id: str | None = None

    # Optional encounter id used to reach back to a Patient or to attach a
    # HAS_ASSESSMENT relationship from a future/same-day encounter.
    encounter_id: str | None = None

    extra: dict[str, Any] = Field(default_factory=dict)

    def to_pipeline_message(self) -> dict[str, Any]:
        """Serialise to the dict form consumed by the workflow event handler."""
        return {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "patient_id": self.situation.patient_id,
            "encounter_id": self.encounter_id or "",
            "context": self.model_dump(mode="json"),
        }


SBARSituationInput.model_rebuild()
