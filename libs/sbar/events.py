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
        Primary care      - clinic_appointment_prep, annual_ltc_review,
                            structured_medication_review,
                            mdt_discussion, ncda, two_week_wait,
                            frailty_pcsp, learning_disability_ahc
        Secondary care    - hospital_admission, discharge_summary,
                            ooh_handover, outpatient_new_clinic,
                            outpatient_followup_clinic, mdt_specialty,
                            pre_op_assessment, procedure_note,
                            ward_round_progress, ed_handover,
                            comprehensive_geriatric_assessment,
                            tertiary_referral, specialty_letter_to_gp,
                            chemotherapy_consent, palliative_care_mdt
        Statutory /
        social            - care_home_review, advance_care_planning,
                            safeguarding_case, continuing_healthcare,
                            death_summary, insurance_dvla_report,
                            subject_access_request, best_interests_dols,
                            mental_health_tribunal
        Quality
        assurance         - significant_event_review, peer_review_cbd

    Display labels live in the matching SUMMARISATION_CONTEXT_LABELS
    dict so the enum stays purely a contract.

    Per-context framing snippets live in
    SUMMARISATION_CONTEXT_PROMPTS and are also seeded into Neo4j as
    `sbar_situation_context_<value>` :PromptConfig nodes so that
    platform admins can refine the wording at runtime via
    /admin/knowledge?tab=ai-instructions (see DI-LEO-AI-507).
    """

    # Primary care (8)
    clinic_appointment_prep = "clinic_appointment_prep"
    annual_ltc_review = "annual_ltc_review"
    structured_medication_review = "structured_medication_review"
    mdt_discussion = "mdt_discussion"
    ncda = "ncda"
    two_week_wait = "two_week_wait"
    frailty_pcsp = "frailty_pcsp"
    learning_disability_ahc = "learning_disability_ahc"
    # Secondary care (15)
    hospital_admission = "hospital_admission"
    discharge_summary = "discharge_summary"
    ooh_handover = "ooh_handover"
    outpatient_new_clinic = "outpatient_new_clinic"
    outpatient_followup_clinic = "outpatient_followup_clinic"
    mdt_specialty = "mdt_specialty"
    pre_op_assessment = "pre_op_assessment"
    procedure_note = "procedure_note"
    ward_round_progress = "ward_round_progress"
    ed_handover = "ed_handover"
    comprehensive_geriatric_assessment = "comprehensive_geriatric_assessment"
    tertiary_referral = "tertiary_referral"
    specialty_letter_to_gp = "specialty_letter_to_gp"
    chemotherapy_consent = "chemotherapy_consent"
    palliative_care_mdt = "palliative_care_mdt"
    # Statutory and social (9)
    care_home_review = "care_home_review"
    advance_care_planning = "advance_care_planning"
    safeguarding_case = "safeguarding_case"
    continuing_healthcare = "continuing_healthcare"
    death_summary = "death_summary"
    insurance_dvla_report = "insurance_dvla_report"
    subject_access_request = "subject_access_request"
    best_interests_dols = "best_interests_dols"
    mental_health_tribunal = "mental_health_tribunal"
    # Quality assurance (2)
    significant_event_review = "significant_event_review"
    peer_review_cbd = "peer_review_cbd"


# Display-group label per context value. The same group strings drive
# both the SummarisationContextSelect dropdown groups and the
# `[<Group>] ...` description prefix on the seeded :PromptConfig nodes
# (DI-LEO-AI-507) so the AI Instructions list groups them by clinical
# setting.
SUMMARISATION_CONTEXT_GROUPS: dict[SummarisationContext, str] = {
    # Primary care
    SummarisationContext.clinic_appointment_prep: "Primary care",
    SummarisationContext.annual_ltc_review: "Primary care",
    SummarisationContext.structured_medication_review: "Primary care",
    SummarisationContext.mdt_discussion: "Primary care",
    SummarisationContext.ncda: "Primary care",
    SummarisationContext.two_week_wait: "Primary care",
    SummarisationContext.frailty_pcsp: "Primary care",
    SummarisationContext.learning_disability_ahc: "Primary care",
    # Secondary care
    SummarisationContext.hospital_admission: "Secondary care",
    SummarisationContext.discharge_summary: "Secondary care",
    SummarisationContext.ooh_handover: "Secondary care",
    SummarisationContext.outpatient_new_clinic: "Secondary care",
    SummarisationContext.outpatient_followup_clinic: "Secondary care",
    SummarisationContext.mdt_specialty: "Secondary care",
    SummarisationContext.pre_op_assessment: "Secondary care",
    SummarisationContext.procedure_note: "Secondary care",
    SummarisationContext.ward_round_progress: "Secondary care",
    SummarisationContext.ed_handover: "Secondary care",
    SummarisationContext.comprehensive_geriatric_assessment: "Secondary care",
    SummarisationContext.tertiary_referral: "Secondary care",
    SummarisationContext.specialty_letter_to_gp: "Secondary care",
    SummarisationContext.chemotherapy_consent: "Secondary care",
    SummarisationContext.palliative_care_mdt: "Secondary care",
    # Statutory and social
    SummarisationContext.care_home_review: "Statutory and social",
    SummarisationContext.advance_care_planning: "Statutory and social",
    SummarisationContext.safeguarding_case: "Statutory and social",
    SummarisationContext.continuing_healthcare: "Statutory and social",
    SummarisationContext.death_summary: "Statutory and social",
    SummarisationContext.insurance_dvla_report: "Statutory and social",
    SummarisationContext.subject_access_request: "Statutory and social",
    SummarisationContext.best_interests_dols: "Statutory and social",
    SummarisationContext.mental_health_tribunal: "Statutory and social",
    # Quality assurance
    SummarisationContext.significant_event_review: "Quality assurance",
    SummarisationContext.peer_review_cbd: "Quality assurance",
}


# Friendly display labels (UK English, sentence case where natural).
SUMMARISATION_CONTEXT_LABELS: dict[SummarisationContext, str] = {
    # Primary care
    SummarisationContext.clinic_appointment_prep: "Clinic appointment prep",
    SummarisationContext.annual_ltc_review: "Long-term condition annual review",
    SummarisationContext.structured_medication_review: (
        "Structured medication review (SMR)"
    ),
    SummarisationContext.mdt_discussion: "MDT prep (primary care)",
    SummarisationContext.ncda: "National Cancer Diagnosis Audit (NCDA)",
    SummarisationContext.two_week_wait: ("Suspected cancer (2WW / Faster Diagnosis)"),
    SummarisationContext.frailty_pcsp: (
        "Frailty / personalised care and support plan (PCSP)"
    ),
    SummarisationContext.learning_disability_ahc: (
        "Learning disability annual health check"
    ),
    # Secondary care
    SummarisationContext.hospital_admission: "Hospital admission summary",
    SummarisationContext.discharge_summary: "Hospital discharge summary",
    SummarisationContext.ooh_handover: "Out-of-hours handover",
    SummarisationContext.outpatient_new_clinic: "Outpatient new clinic letter",
    SummarisationContext.outpatient_followup_clinic: (
        "Outpatient follow-up clinic letter"
    ),
    SummarisationContext.mdt_specialty: ("Specialty MDT (cancer / surgical / neuro)"),
    SummarisationContext.pre_op_assessment: "Pre-operative assessment",
    SummarisationContext.procedure_note: "Operation / procedure note summary",
    SummarisationContext.ward_round_progress: ("Ward round / inpatient progress note"),
    SummarisationContext.ed_handover: ("Emergency Department triage / handover"),
    SummarisationContext.comprehensive_geriatric_assessment: (
        "Comprehensive Geriatric Assessment (CGA)"
    ),
    SummarisationContext.tertiary_referral: "Tertiary referral letter",
    SummarisationContext.specialty_letter_to_gp: ("Specialty clinic letter back to GP"),
    SummarisationContext.chemotherapy_consent: ("Chemotherapy / SACT consent"),
    SummarisationContext.palliative_care_mdt: (
        "Palliative care MDT / hospice referral"
    ),
    # Statutory and social
    SummarisationContext.care_home_review: "Care home / housebound review",
    SummarisationContext.advance_care_planning: (
        "Advance care planning / ReSPECT / TEP"
    ),
    SummarisationContext.safeguarding_case: "Safeguarding case conference",
    SummarisationContext.continuing_healthcare: "Continuing healthcare (CHC)",
    SummarisationContext.death_summary: "Death summary / coroner request",
    SummarisationContext.insurance_dvla_report: (
        "Insurance / DVLA / occupational report"
    ),
    SummarisationContext.subject_access_request: "Subject access request (SAR)",
    SummarisationContext.best_interests_dols: ("Best Interests / DoLS meeting"),
    SummarisationContext.mental_health_tribunal: ("Mental Health Act tribunal report"),
    # Quality assurance
    SummarisationContext.significant_event_review: ("Significant event review (SEA)"),
    SummarisationContext.peer_review_cbd: ("Peer review / Case-based discussion (CBD)"),
}


# Per-context prompt fragments injected into the Situation stage of the
# SBAR orchestrator. Each snippet describes what the LLM should
# emphasise for that context. Kept short so the orchestrator can
# concatenate without bloating the prompt.
SUMMARISATION_CONTEXT_PROMPTS: dict[SummarisationContext, str] = {
    # Primary care
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
        "Frame the Situation as a concise primary-care MDT case "
        "presentation: diagnosis, current management, decision the team "
        "must make, and any GP follow-up actions."
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
    SummarisationContext.frailty_pcsp: (
        "Frame the Situation around a frailty / personalised care and "
        "support plan: goals, support network, anticipated needs."
    ),
    SummarisationContext.learning_disability_ahc: (
        "Frame the Situation around an LD annual health check: "
        "communication needs, reasonable adjustments, health actions."
    ),
    # Secondary care
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
    SummarisationContext.outpatient_new_clinic: (
        "Frame the Situation as a new specialist clinic letter: the "
        "referral question, key history, and what the specialist needs "
        "to address today."
    ),
    SummarisationContext.outpatient_followup_clinic: (
        "Frame the Situation as a follow-up specialist clinic letter: "
        "progress since the last visit, response to treatment, and "
        "what to do next."
    ),
    SummarisationContext.mdt_specialty: (
        "Frame the Situation as a specialty MDT case (cancer, surgical, "
        "or neuro): diagnosis, stage or severity, performance status, "
        "and the team decision needed."
    ),
    SummarisationContext.pre_op_assessment: (
        "Frame the Situation as a pre-operative assessment: planned "
        "procedure, anaesthetic risk, optimisation tasks, and red flags "
        "before theatre."
    ),
    SummarisationContext.procedure_note: (
        "Frame the Situation as a procedure or operation summary: "
        "indication, what was done, findings, complications, and "
        "recovery plan."
    ),
    SummarisationContext.ward_round_progress: (
        "Frame the Situation as a ward round progress note: current "
        "problems, response to treatment overnight, jobs for today, "
        "and discharge planning."
    ),
    SummarisationContext.ed_handover: (
        "Frame the Situation as an Emergency Department handover: "
        "presenting complaint, working diagnosis, what has been done "
        "in ED, and what the admitting team must do next."
    ),
    SummarisationContext.comprehensive_geriatric_assessment: (
        "Frame the Situation as a Comprehensive Geriatric Assessment: "
        "medical, functional, social, and psychological needs of an "
        "older patient."
    ),
    SummarisationContext.tertiary_referral: (
        "Frame the Situation as a tertiary referral letter: the "
        "specialist question, why local services cannot manage, and "
        "the urgency."
    ),
    SummarisationContext.specialty_letter_to_gp: (
        "Frame the Situation as a specialty letter back to the GP: "
        "outcome of the clinic visit, plan, medication changes, and "
        "what the GP needs to do."
    ),
    SummarisationContext.chemotherapy_consent: (
        "Frame the Situation for a chemotherapy or SACT consent "
        "discussion: cancer diagnosis, intent (cure or control), "
        "regimen, key risks, and what success looks like."
    ),
    SummarisationContext.palliative_care_mdt: (
        "Frame the Situation as a palliative care MDT or hospice "
        "referral: prognosis, current symptoms, advance care plan, "
        "and the support needed at home or hospice."
    ),
    # Statutory and social
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
    SummarisationContext.best_interests_dols: (
        "Frame the Situation for a Best Interests or DoLS meeting: "
        "the decision needed, the patient's capacity, their wishes if "
        "known, and the least restrictive option."
    ),
    SummarisationContext.mental_health_tribunal: (
        "Frame the Situation as a Mental Health Act tribunal report: "
        "presenting illness, current risk, response to treatment, and "
        "the case for or against continued detention."
    ),
    # Quality assurance
    SummarisationContext.significant_event_review: (
        "Frame the Situation as a significant event review: what "
        "happened, what could have been done differently, learning."
    ),
    SummarisationContext.peer_review_cbd: (
        "Frame the Situation for a peer review / case-based discussion: "
        "presenting problem, decisions made, learning points."
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
            raise ValueError(f"{self.type.value} artefacts require a Neo4j node id")
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
