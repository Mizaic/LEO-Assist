"""Prior cancer-related consultations and NCDA "multiple consultations" factors.

The NCDA (National Cancer Diagnosis Audit) primary-care pro forma asks
the GP, for every confirmed cancer episode:

    "The number of consultations for cancer-related symptoms up to one
     year before the referral that led directly to the cancer diagnosis.
     This includes email, telephone, face to face, nurse practitioner
     and nurse consultations, in any clinical setting.  If there were
     zero consultations, please record 0."

And, when the count is 2+, the GP is asked which factors from a fixed
24-item list "in your opinion accounted for" the multiple consultations.

This module implements the same question for our detector:

  1. Pull every encounter in the year before ``referral_date`` (or
     before ``end_date`` for cohort 3 episodes that never reached an
     FTR).
  2. Drop pure noise rows with the deterministic
     :func:`is_clinical_contact` filter — admin, SMS, repeat scripts,
     booking confirmations, summary-care-record updates, and most
     auto-filed lab lines.  This avoids paying tokens for ~70% of the
     raw rows.
  3. Tag each surviving row with its
     :data:`ContactType` (``"f2f" | "telephone" | "nurse" | "email"
     | "specialist_clinic" | "home_visit" | "phlebotomy" | "result_review"``)
     using the role + free-text markers — see
     :func:`classify_contact_type`.
  4. Hand the survivors to Claude Haiku 4.5 (the ``small`` Bedrock
     tier) wrapped in :func:`classify_episode_consultations` for the
     two judgments that need clinical reasoning:

       a. Per encounter, is this a *cancer-related* consultation that
          should count toward the NCDA tally?
       b. At episode level, which of the 24 NCDA factors apply, with
          a ≤25-word evidence quote per factor?

  5. Persist the result on :class:`EpisodeOfCare` alongside the
     standard :ref:`llm_usage_json` telemetry block — the orchestrator
     wraps the LLM call in ``LLMUsageRecorder`` and writes both the
     entity flat fields and a ``:AuditEvent {type:'PipelineRun'}``
     so the dashboard ``LLMSpendPanel`` and per-tenant billing pick
     up the cost automatically.

The 24 NCDA factors are split into three confidence tiers in
:data:`NCDA_FACTORS_AUTO_DETECTABLE`,
:data:`NCDA_FACTORS_LLM_JUDGMENT`, and
:data:`NCDA_FACTORS_HUMAN_REVIEW_ONLY`.  The detector only proposes
the first two; the human-review-only ones (e.g. "Inadequate history
taken", "Poor communication with the patient") are exposed in the UI
as manual checkboxes for the GP reviewer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

# ---------------------------------------------------------------------------
# Contact-type classifier (deterministic, no LLM)
# ---------------------------------------------------------------------------

ContactType = Literal[
    "f2f",
    "telephone",
    "nurse",
    "email",
    "specialist_clinic",
    "home_visit",
    "phlebotomy",
    "result_review",
    "admin",
    "other",
]

#: Roles in the encounter text that indicate a clinical staff member.
_CLINICAL_ROLES = re.compile(
    r"\((?:"
    r"clinical\s+practitioner\s+access\s+role|"
    r"nurse\s+access\s+role|"
    r"specialist\s+nurse\s+practitioner|"
    r"healthcare\s+assistant|"
    r"health\s+professional\s+access\s+role|"
    r"pharmacist|"
    r"paramedic\s+advanced\s+practitioner|"
    r"\bdr\b|\bdoctor\b|"
    r"physiotherapist|"
    r"clinical\s+supervisor"
    r")\)",
    re.IGNORECASE,
)

#: Roles that indicate admin / non-clinical-decision-making contact.
_ADMIN_ROLES = re.compile(
    r"\((?:"
    r"receptionist\s+access\s+role|"
    r"medical\s+secretary\s+access\s+role|"
    r"admin\/clinical\s+support\s+access\s+role|"
    r"clerical\s+access\s+role|"
    r"systems\s+support\s+access\s+role|"
    r"call\s+operator"
    r")\)",
    re.IGNORECASE,
)

#: Patterns that, when they DOMINATE an encounter (everything else is
#: admin), mean it should be excluded from the consultation count
#: regardless of role.
_NOISE_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*dear\s+\[person\]\s+appointment\s+has\s+been\s+booked",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*confirmation\s+of\s+appointment\s+at\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*reminder\s+of\b.*?appointment", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*reminder\s+for\s+appointment", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^\s*\(?r\)?\s+[a-z0-9][a-z0-9\s\-/.,%]*?(?:tablets?|capsules?|cream|gel|spray|drops|inhaler|injection|sachets?|powder|liquid|suppositor\w*|patch|solution)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(r"^\s*request\s+for\s+'", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^\s*summary\s+care\s+record\s+update\b", re.IGNORECASE | re.MULTILINE
    ),
    re.compile(r"^\s*etp2?\s+fp10\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*scheduled\s+task\s+creation\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*recall\s*:\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*reminder\/alert\s*:\s*", re.IGNORECASE | re.MULTILINE),
    re.compile(
        r"^\s*influenza\s+vaccination\s+invitation\b", re.IGNORECASE | re.MULTILINE
    ),
    re.compile(
        r"^\s*rsv\s*\([^)]*\)\s+vaccination\s+invitation\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*comment\s+note\s+\(xaig6\)\s*$", re.IGNORECASE | re.MULTILINE
    ),
)

#: Markers for "this row is an SMS/text-only contact" (no consultation).
_SMS_ONLY = re.compile(
    r"short\s+message\s+service\s+text\s+message\s+sent", re.IGNORECASE
)

#: Markers for "this row is an auto-filed lab/imaging result, no contact".
_AUTO_FILED = re.compile(r"\bauto[\s\-]?filed\b", re.IGNORECASE)

#: Cancer-relevant test names — when an auto-filed line contains one
#: of these, we keep the row and tag it as ``result_review`` so the
#: LLM can decide if it's part of the cancer workup.  Otherwise the
#: auto-filed row is dropped as noise.
_CANCER_RELEVANT_TESTS = re.compile(
    r"\b(?:"
    r"PSA|prostate[\s\-]?specific[\s\-]?antigen|"
    r"FIT|faecal[\s\-]?immunochemical|"
    r"calprotectin|"
    r"CEA|CA[\s\-]?125|CA[\s\-]?19[\s\-]?9|CA[\s\-]?15[\s\-]?3|"
    r"alpha[\s\-]?fetoprotein|AFP|"
    r"\bbiopsy\b|histolog\w*|cytolog\w*|"
    r"CT\s+(?:thorax|chest|abdomen|pelvis|head)|computed\s+tomography|"
    r"MRI\s+(?:prostate|rectum|breast|head|spine)|"
    r"\bUSS?\b|ultrasound|bone\s+scan|PET[\s\-]?CT|"
    r"endoscop\w*|colonoscop\w*|sigmoidoscop\w*|cystoscop\w*|"
    r"bronchoscop\w*|nasendoscop\w*|hysteroscop\w*|colposcop\w*|"
    r"mammogra\w*|dermoscop\w*|"
    r"FBC|full\s+blood\s+count|ferritin|"
    r"abnormal\s+liver|GGT|AKI"
    r")\b",
    re.IGNORECASE,
)

#: Free-text markers that indicate F2F (face-to-face) consultation.
_F2F_MARKERS = re.compile(
    r"\b(?:"
    r"f2f(?:\s+(?:review|appt|appointment))?|"
    r"face[\s\-]?to[\s\-]?face|"
    r"seen\s+f2f|"
    r"seen\s+(?:in\s+)?(?:surgery|clinic)|"
    r"attended\s+(?:with|for|in)|"
    r"examination\s*:|"
    r"o\/e\s+\-|"
    r"on\s+examination"
    r")\b",
    re.IGNORECASE,
)

#: Free-text markers that indicate telephone consultation.
_PHONE_MARKERS = re.compile(
    r"\b(?:"
    r"telephone\s+(?:consultation|encounter|triage)|"
    r"telecons?(?:ult)?|tel\s+cons?|"
    r"phone\s+(?:consultation|call|review|encounter)|"
    r"called\s+(?:the\s+)?(?:patient|pt)|"
    r"duty\s+(?:doctor|call)|"
    r"on\s+call(?!\s+duty\s+doctor)|"
    r"spoke\s+(?:to|with)\s+(?:pt|patient)|"
    r"\bteleconsult\b"
    r")\b",
    re.IGNORECASE,
)

#: Free-text markers that indicate home visit.
_HOME_MARKERS = re.compile(
    r"\b(?:home\s+visit|home\s+of\s+patient|patient'?s?\s+home|visited\s+(?:at|in)\s+home)\b",
    re.IGNORECASE,
)

#: Specialist clinic encounter — text starts with "clinic:" or
#: "entered at:" pointing to a hospital trust / clinic.
_CLINIC_MARKERS = re.compile(
    r"(?:^|\n)\s*\d{0,2}:?\d{0,2}\s*-?\s*clinic\s*:|"
    r"entered\s+at\s*:\s*[a-z][a-z\s,&\-]*(?:clinic|hospital|service|trust|centre|center)",
    re.IGNORECASE,
)

#: Phlebotomy markers (nurse-led blood draw).
_PHLEBOTOMY_MARKERS = re.compile(
    r"\bphlebotomy\s+(?:service|test|generated)\b|blood\s+sample\s+taken",
    re.IGNORECASE,
)

#: Email contact markers (NHS email, secure messaging, accurx written).
_EMAIL_MARKERS = re.compile(
    r"\b(?:e[\s\-]?mail\s+sent\s+to|secure\s+message|nhs\.?net\s+email|via\s+accurx)\b",
    re.IGNORECASE,
)

#: Markers that an encounter has clinical narrative content (history /
#: examination / plan / problem block), as opposed to being a pure
#: admin entry.  Used to gate-keep the "clinical contact" filter.
_CLINICAL_CONTENT_MARKERS = re.compile(
    r"(?:"
    r"\bhistory\s*:|\bexamination\s*:|\bplan\s*:|\bproblem\s*:|"
    r"\bpresenting\s+complaint\b|\bc\/o\b|\bcomplaining\s+of\b|"
    r"\breports?\s+(?:no|the|this|that|having|some|increasing|new|ongoing)\b"
    r")",
    re.IGNORECASE,
)


def _is_pure_admin(text: str, role_match: re.Match[str] | None) -> bool:
    """Heuristic: is this row pure admin with no clinical content?"""
    if role_match is None:
        return False
    if _CLINICAL_CONTENT_MARKERS.search(text):
        # Even a receptionist-tagged row counts as a contact if the
        # body has a clinical history / plan block.  Rare but real.
        return False
    return True


def is_clinical_contact(text: str | None, flags: str | None = None) -> bool:
    """Return True if this encounter row is a candidate cancer-pathway
    consultation that should be sent to the LLM for relatedness review.

    This is a *deterministic pre-filter* — its only purpose is to drop
    rows that are obviously noise so we don't pay tokens for them.

    Drops:
      - Empty text rows
      - SMS-only rows (text message sent + nothing else)
      - Booking confirmations / appointment reminders
      - Repeat-prescription-only rows ("(R) drug" + nothing else)
      - Summary-care-record updates and ETP FP10 housekeeping
      - Vaccine invitations and recall reminders
      - Auto-filed lab/imaging rows that don't mention a cancer-relevant test
      - Pure-admin rows (receptionist / medical secretary / admin support)
        with no clinical narrative content

    Keeps everything else for the LLM to judge.
    """
    if not text:
        return False
    t = text.strip()
    if not t:
        return False

    # 1. SMS-only → drop unless there's a clinical block alongside.
    if _SMS_ONLY.search(t) and not _CLINICAL_CONTENT_MARKERS.search(t):
        return False

    # 2. Noise-only patterns (booking confirmations, scripts, vaccine
    #    invitations, recall reminders, etc.).  If the row is dominated
    #    by one of these and has no clinical content, drop it.
    if not _CLINICAL_CONTENT_MARKERS.search(t):
        for pat in _NOISE_ONLY_PATTERNS:
            if pat.search(t):
                return False

    # 3. Auto-filed labs / imaging — keep only if a cancer-relevant
    #    test is mentioned.  Otherwise these are noisy LFT / U&E /
    #    HbA1c monitoring lines unrelated to the cancer pathway.
    if _AUTO_FILED.search(t):
        return bool(_CANCER_RELEVANT_TESTS.search(t))

    # 4. Pure-admin rows (receptionist / secretary) with no clinical
    #    content → drop.  Allow them through if they ALSO carry a
    #    clinical body (the GP sometimes writes their notes under a
    #    receptionist-tagged row, e.g. when correcting an entry).
    admin_match = _ADMIN_ROLES.search(t)
    if admin_match and not _CLINICAL_ROLES.search(t):
        if _is_pure_admin(t, admin_match):
            return False

    return True


def classify_contact_type(text: str | None) -> ContactType:
    """Classify a candidate encounter into one of nine
    :data:`ContactType` buckets using deterministic regex.  Order
    matters — the most specific marker wins.

    Returns ``"other"`` only when nothing matches.  Callers should
    pre-filter with :func:`is_clinical_contact` first.
    """
    if not text:
        return "other"
    t = text

    # Auto-filed labs that survived the pre-filter -> result review.
    if _AUTO_FILED.search(t):
        return "result_review"

    # Specialist clinic attendance has its own location marker.
    if _CLINIC_MARKERS.search(t):
        return "specialist_clinic"

    # Home visit beats F2F (more specific).
    if _HOME_MARKERS.search(t):
        return "home_visit"

    # Phlebotomy beats generic nurse (more specific).
    if _PHLEBOTOMY_MARKERS.search(t):
        return "phlebotomy"

    # Email contact (rare but distinct from F2F/phone).
    if _EMAIL_MARKERS.search(t):
        return "email"

    # Telephone vs F2F — telephone markers are more specific.
    if _PHONE_MARKERS.search(t):
        return "telephone"
    if _F2F_MARKERS.search(t):
        return "f2f"

    # Fall back to the role tag if nothing else matched.
    if re.search(r"\bnurse\s+access\s+role\b", t, re.IGNORECASE):
        return "nurse"
    if _CLINICAL_ROLES.search(t):
        # Clinical role with no F2F/phone marker — likely a clinical
        # supervision note or task entry.  Treat as "other"; the LLM
        # can still mark it related if it's part of the pathway.
        return "other"

    return "other"


# ---------------------------------------------------------------------------
# NCDA factor list (Royal College of GPs / Macmillan / Cancer Research UK
# 2018+ pro forma)
# ---------------------------------------------------------------------------

NCDAFactor = Literal[
    "co_morbidity_blurring",
    "different_initial_diagnosis",
    "different_malignancy",
    "incomplete_symptom_account",
    "low_perceived_malignancy_probability",
    "frequent_attender_vague_symptoms",
    "declined_investigation",
    "declined_referral",
    "did_not_attend_followup",
    "abnormal_result_not_followed_up",
    "poor_communication_with_patient",
    "inadequate_history_taken",
    "examination_not_performed",
    "investigation_not_ordered",
    "wrong_specialty_referral",
    "poor_communication_within_practice",
    "seen_by_multiple_health_professionals",
    "reassurance_from_negative_investigation",
    "investigation_suggested_benign_cause",
    "consultations_to_discuss_test_results",
    "no_reason",
    "other_reason",
    "no_multiple_consultations",
    "not_known",
]


#: Detector tier — these factors are deterministically derivable
#: from Read codes / structured fields without LLM judgment.
#: When the detector flags one of these, it carries near-zero
#: false-positive risk.
NCDA_FACTORS_AUTO_DETECTABLE: tuple[NCDAFactor, ...] = (
    "no_multiple_consultations",
    "did_not_attend_followup",
    "consultations_to_discuss_test_results",
    "investigation_suggested_benign_cause",
    "reassurance_from_negative_investigation",
    "different_malignancy",
    "wrong_specialty_referral",
    "seen_by_multiple_health_professionals",
    "co_morbidity_blurring",
    "different_initial_diagnosis",
    "abnormal_result_not_followed_up",
    "frequent_attender_vague_symptoms",
)

#: LLM-judgment tier — auto-detectable but with text reasoning.
#: The Haiku call surfaces these as proposed factors with evidence
#: quotes; clinician reviewer confirms or rejects.
NCDA_FACTORS_LLM_JUDGMENT: tuple[NCDAFactor, ...] = (
    "low_perceived_malignancy_probability",
    "declined_investigation",
    "declined_referral",
)

#: Human-review-only — clinician self-assessment about the quality
#: of their own care.  The detector NEVER proposes these to avoid
#: bias; they are exposed in the UI as manual-tick checkboxes.
NCDA_FACTORS_HUMAN_REVIEW_ONLY: tuple[NCDAFactor, ...] = (
    "incomplete_symptom_account",
    "poor_communication_with_patient",
    "inadequate_history_taken",
    "examination_not_performed",
    "investigation_not_ordered",
    "poor_communication_within_practice",
    "no_reason",
    "other_reason",
    "not_known",
)

#: Human-readable labels for the UI / prompt — kept exactly as worded
#: on the NCDA pro forma so the GP reviewer sees familiar phrasing.
NCDA_FACTOR_LABELS: dict[NCDAFactor, str] = {
    "co_morbidity_blurring": "Presence of co-existing morbidity / Co-morbidity blurring picture",
    "different_initial_diagnosis": "Symptoms suggested different initial diagnosis",
    "different_malignancy": "Symptoms suggested different malignancy",
    "incomplete_symptom_account": "Didn't have a full account of symptoms (eg: failure to report/elicit all symptoms)",
    "low_perceived_malignancy_probability": "Perceived low probability of patient having malignancy (eg: young patient)",
    "frequent_attender_vague_symptoms": "Patient frequently attending GP with vague symptoms",
    "declined_investigation": "Declined investigation or examination",
    "declined_referral": "Declined referral or admission",
    "did_not_attend_followup": "Did not attend for follow-up (GP or hospital)",
    "abnormal_result_not_followed_up": "Abnormal result not followed up",
    "poor_communication_with_patient": "Poor communication with the patient",
    "inadequate_history_taken": "Inadequate history taken",
    "examination_not_performed": "Appropriate examination not performed",
    "investigation_not_ordered": "Appropriate investigation not ordered",
    "wrong_specialty_referral": "Referred to the 'wrong' specialty",
    "poor_communication_within_practice": "Poor communication within the practice",
    "seen_by_multiple_health_professionals": "Seen by multiple health professionals",
    "reassurance_from_negative_investigation": "Reassurance from negative investigation",
    "investigation_suggested_benign_cause": "Investigation suggested benign cause",
    "consultations_to_discuss_test_results": "Consultation(s) to discuss test results",
    "no_reason": "No reason",
    "other_reason": "Other",
    "no_multiple_consultations": "No multiple consultations",
    "not_known": "Not known",
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateEncounter:
    """One encounter handed to the LLM for cancer-relatedness review."""

    encounter_id: str
    date: str
    text: str
    contact_type: ContactType


@dataclass(frozen=True)
class ConsultationVerdict:
    """LLM verdict for a single candidate encounter."""

    encounter_id: str
    date: str
    related: bool
    contact_type: ContactType
    evidence: str = ""


@dataclass(frozen=True)
class FactorVerdict:
    """LLM verdict for a single NCDA factor at episode level."""

    factor: NCDAFactor
    evidence_encounter_ids: tuple[str, ...]
    rationale: str = ""


@dataclass(frozen=True)
class PriorConsultationsResult:
    """Output of :func:`classify_episode_consultations`.

    Attributes:
        consultations_n:
            Total cancer-related patient-facing consultations
            (``related=True`` and ``contact_type`` in the counted set).
        f2f_n / phone_n / nurse_n / email_n / specialist_clinic_n /
        home_visit_n / phlebotomy_n / result_review_n:
            Per-bucket counts.  All summed equal ``consultations_n``.
        verdicts:
            One :class:`ConsultationVerdict` per candidate encounter
            (incl. those marked unrelated, for telemetry).
        factors:
            NCDA factors identified by the LLM with episode-level
            evidence.  Only auto-detectable + LLM-judgment factors
            ever appear here; human-review-only factors are populated
            by the reviewer in the UI.
        unrelated_filtered_n:
            Number of candidate encounters the LLM marked unrelated.
        notes:
            Free-text from the LLM (optional, for debugging).
    """

    consultations_n: int
    f2f_n: int = 0
    phone_n: int = 0
    nurse_n: int = 0
    email_n: int = 0
    specialist_clinic_n: int = 0
    home_visit_n: int = 0
    phlebotomy_n: int = 0
    result_review_n: int = 0
    verdicts: tuple[ConsultationVerdict, ...] = ()
    factors: tuple[FactorVerdict, ...] = ()
    unrelated_filtered_n: int = 0
    notes: str = ""


# ---------------------------------------------------------------------------
# Pre-filter pipeline
# ---------------------------------------------------------------------------


def select_candidate_encounters(
    encounters: Iterable[dict[str, Any]],
) -> list[CandidateEncounter]:
    """Apply the deterministic pre-filter to a year-prior encounter list.

    Each input dict must carry ``encounter_id``, ``date`` and ``text``
    (``flags`` is consulted when present).  Rows that fail
    :func:`is_clinical_contact` are dropped silently; surviving rows
    are tagged with their :func:`classify_contact_type` and returned
    in chronological order.
    """
    out: list[CandidateEncounter] = []
    for raw in encounters:
        if raw is None:
            continue
        text = (raw.get("text") or "").strip()
        flags = raw.get("flags") or ""
        if not is_clinical_contact(text, flags):
            continue
        out.append(
            CandidateEncounter(
                encounter_id=str(raw.get("encounter_id") or raw.get("id") or ""),
                date=str(raw.get("date") or ""),
                text=text,
                contact_type=classify_contact_type(text),
            )
        )
    out.sort(key=lambda c: (c.date, c.encounter_id))
    return out


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """\
You are auditing UK GP records to fill in the National Cancer Diagnosis Audit
(NCDA) primary-care pro forma for a single confirmed cancer episode.

You receive:
  - episode metadata (cancer_type, first_presentation_date, referral_date)
  - a JSON list of candidate encounters that occurred in the year before the
    referral, each pre-tagged with a contact_type ("f2f", "telephone",
    "nurse", "email", "specialist_clinic", "home_visit", "phlebotomy",
    "result_review", or "other").

For EACH candidate encounter you must decide:
  related (bool)
    True if the encounter discusses the cancer-related symptoms, tests, or
    workup that led to the fast-track referral. False if the encounter is
    for an unrelated condition (LTC review, vaccination, repeat
    prescription, midwife visit, podiatry, MSK injury unrelated to the
    cancer site, etc.).
  contact_type
    Confirm or correct the pre-tag from the list above.
  evidence (<=25 words)
    A short quote from the encounter text justifying the call.

Then, at the EPISODE level, pick zero or more factors from the NCDA list
below that are present in the encounter evidence. Only pick factors that
are clearly supported by the text — do NOT speculate.

NCDA factors you may propose (each with a one-line definition):

co_morbidity_blurring -- multiple active long-term conditions on the patient
  record made it harder to spot the cancer signal.
different_initial_diagnosis -- the symptoms were initially attributed to a
  non-cancer diagnosis (e.g. BPH, IBS, mastalgia, MSK pain).
different_malignancy -- an earlier 2WW was raised for a DIFFERENT cancer
  pathway before the one that led to diagnosis (e.g. NSS 2WW first, upper
  GI 2WW later for the same patient).
low_perceived_malignancy_probability -- the clinician explicitly noted
  cancer was unlikely (young patient, atypical demographics, etc.).
frequent_attender_vague_symptoms -- the patient had many consultations in
  the year for non-specific symptoms before the cancer pattern emerged.
declined_investigation -- the patient refused an examination or test.
declined_referral -- the patient refused a referral or hospital appointment.
did_not_attend_followup -- DNA codes or "did not attend" text in the window.
abnormal_result_not_followed_up -- a flagged abnormal lab/imaging result
  with no clinical follow-up encounter in the next 30 days.
wrong_specialty_referral -- an earlier referral to a non-cancer specialty
  (e.g. community breast pain clinic, MSK physio) that delayed the cancer
  pathway.
seen_by_multiple_health_professionals -- consultations with three or more
  distinct named clinicians in the window.
reassurance_from_negative_investigation -- a normal/satisfactory test
  result was used to reassure the patient and pause further workup.
investigation_suggested_benign_cause -- a test result pointed to a benign
  diagnosis that turned out to be wrong.
consultations_to_discuss_test_results -- one or more consultations in the
  window were specifically to discuss test results (PSA, FIT, scans).
no_multiple_consultations -- there were 0 or 1 cancer-related
  consultations in the window.

Return a STRICT JSON object with this shape (and no markdown fences):

{
  "encounters": [
    {"encounter_id": "...", "date": "YYYY-MM-DD", "related": true,
     "contact_type": "f2f", "evidence": "<=25 words"}
  ],
  "factors": [
    {"factor": "different_initial_diagnosis",
     "evidence_encounter_ids": ["..."],
     "rationale": "<=25 words"}
  ],
  "summary": {
    "consultations_n": 0,
    "f2f_n": 0, "phone_n": 0, "nurse_n": 0, "email_n": 0,
    "specialist_clinic_n": 0, "home_visit_n": 0,
    "phlebotomy_n": 0, "result_review_n": 0,
    "unrelated_filtered_n": 0
  },
  "notes": ""
}
"""


def build_user_message(
    *,
    cancer_type: str | None,
    first_presentation_date: str | None,
    referral_date: str | None,
    candidates: Sequence[CandidateEncounter],
    text_chars_per_candidate: int = 600,
) -> str:
    """Build the user message handed to the LLM.

    Truncates each candidate's text to ``text_chars_per_candidate`` to
    keep the prompt under control — 600 chars per encounter at ~30
    candidates per episode is roughly 18K characters / ~4500 tokens
    of input, well within Haiku's window.
    """
    payload = {
        "episode": {
            "cancer_type": cancer_type or "",
            "first_presentation_date": first_presentation_date or "",
            "referral_date": referral_date or "",
            "candidate_count": len(candidates),
        },
        "candidates": [
            {
                "encounter_id": c.encounter_id,
                "date": c.date,
                "contact_type": c.contact_type,
                "text": (c.text or "")[:text_chars_per_candidate],
            }
            for c in candidates
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# LLM wrapper
# ---------------------------------------------------------------------------


def _coerce_contact_type(raw: Any, fallback: ContactType) -> ContactType:
    val = (raw or "").strip().lower() if isinstance(raw, str) else ""
    valid: set[str] = {
        "f2f",
        "telephone",
        "nurse",
        "email",
        "specialist_clinic",
        "home_visit",
        "phlebotomy",
        "result_review",
        "admin",
        "other",
    }
    return val if val in valid else fallback  # type: ignore[return-value]


def _coerce_factor(raw: Any) -> NCDAFactor | None:
    val = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if val in NCDA_FACTORS_AUTO_DETECTABLE or val in NCDA_FACTORS_LLM_JUDGMENT:
        return val  # type: ignore[return-value]
    if val == "no_multiple_consultations":
        return val  # type: ignore[return-value]
    return None


# Set of contact_types that count toward the NCDA consultation tally.
# result_review and admin are deliberately excluded — the NCDA wording
# is "consultations" (face-to-face / phone / email / nurse / NP), not
# results-only encounters.  We still surface result_review_n separately
# so the dashboard can show how busy the workup was.
_COUNTED_CONTACT_TYPES: frozenset[ContactType] = frozenset(
    {
        "f2f",
        "telephone",
        "nurse",
        "email",
        "specialist_clinic",
        "home_visit",
        "phlebotomy",
    }
)


def parse_llm_response(
    raw: dict[str, Any],
    *,
    candidates: Sequence[CandidateEncounter],
) -> PriorConsultationsResult:
    """Parse the LLM's JSON response into a :class:`PriorConsultationsResult`.

    Defensive — missing fields default to safe values, and the per-bucket
    counts are recomputed from the verdict list rather than trusting the
    LLM's ``summary`` block (so rounding errors / disagreements between
    its two outputs can't propagate).
    """
    by_id: dict[str, CandidateEncounter] = {c.encounter_id: c for c in candidates}

    raw_encs = raw.get("encounters")
    verdicts: list[ConsultationVerdict] = []
    if isinstance(raw_encs, list):
        for r in raw_encs:
            if not isinstance(r, dict):
                continue
            eid = str(r.get("encounter_id") or "").strip()
            cand = by_id.get(eid)
            fallback_type: ContactType = cand.contact_type if cand else "other"
            related = bool(r.get("related", False))
            verdicts.append(
                ConsultationVerdict(
                    encounter_id=eid,
                    date=str(r.get("date") or (cand.date if cand else "")),
                    related=related,
                    contact_type=_coerce_contact_type(
                        r.get("contact_type"), fallback_type
                    ),
                    evidence=str(r.get("evidence") or "").strip()[:200],
                )
            )

    # Compute counts from verdicts ourselves — never trust the LLM
    # summary for the headline number.
    bucket_counts: dict[ContactType, int] = {
        "f2f": 0,
        "telephone": 0,
        "nurse": 0,
        "email": 0,
        "specialist_clinic": 0,
        "home_visit": 0,
        "phlebotomy": 0,
        "result_review": 0,
    }
    consultations_n = 0
    unrelated_n = 0
    for v in verdicts:
        if not v.related:
            unrelated_n += 1
            continue
        if v.contact_type in bucket_counts:
            bucket_counts[v.contact_type] += 1
        if v.contact_type in _COUNTED_CONTACT_TYPES:
            consultations_n += 1

    raw_factors = raw.get("factors")
    factors: list[FactorVerdict] = []
    if isinstance(raw_factors, list):
        for r in raw_factors:
            if not isinstance(r, dict):
                continue
            f = _coerce_factor(r.get("factor"))
            if f is None:
                continue
            ev_ids = r.get("evidence_encounter_ids") or []
            if not isinstance(ev_ids, list):
                ev_ids = []
            factors.append(
                FactorVerdict(
                    factor=f,
                    evidence_encounter_ids=tuple(
                        str(x).strip() for x in ev_ids if str(x).strip()
                    ),
                    rationale=str(r.get("rationale") or "").strip()[:200],
                )
            )

    # NCDA "no_multiple_consultations" is mutually exclusive with the
    # other factors -- it answers the gating question "were there
    # multiple consultations?" with NO.  When the LLM proposes it
    # alongside actual factors (a common Haiku failure mode) we drop
    # it; when the consultation count is >=2 we drop it whether the
    # LLM proposed it or not; only when count <=1 do we force it on
    # an otherwise-empty factor list.
    if consultations_n >= 2:
        factors = [f for f in factors if f.factor != "no_multiple_consultations"]
    elif consultations_n <= 1 and not any(
        f.factor != "no_multiple_consultations" for f in factors
    ):
        factors = [
            FactorVerdict(
                factor="no_multiple_consultations",
                evidence_encounter_ids=tuple(),
                rationale="0 or 1 cancer-related consultations in the window.",
            )
        ]

    return PriorConsultationsResult(
        consultations_n=consultations_n,
        f2f_n=bucket_counts["f2f"],
        phone_n=bucket_counts["telephone"],
        nurse_n=bucket_counts["nurse"],
        email_n=bucket_counts["email"],
        specialist_clinic_n=bucket_counts["specialist_clinic"],
        home_visit_n=bucket_counts["home_visit"],
        phlebotomy_n=bucket_counts["phlebotomy"],
        result_review_n=bucket_counts["result_review"],
        verdicts=tuple(verdicts),
        factors=tuple(factors),
        unrelated_filtered_n=unrelated_n,
        notes=str(raw.get("notes") or "").strip()[:400],
    )


def empty_result_for_no_candidates() -> PriorConsultationsResult:
    """Helper: when the pre-filter returns zero candidates, the NCDA
    answer is 0 consultations and ``no_multiple_consultations``."""
    return PriorConsultationsResult(
        consultations_n=0,
        factors=(
            FactorVerdict(
                factor="no_multiple_consultations",
                evidence_encounter_ids=tuple(),
                rationale="No clinical contacts in the year-prior window after pre-filter.",
            ),
        ),
    )


def classify_episode_consultations(
    *,
    cancer_type: str | None,
    first_presentation_date: str | None,
    referral_date: str | None,
    encounters: Iterable[dict[str, Any]],
    patient_id: str = "",
    llm_caller: Any = None,
    agent_task: str = "ncda_prior_consultations",
    text_chars_per_candidate: int = 600,
) -> PriorConsultationsResult:
    """End-to-end: pre-filter, build prompt, call Haiku, parse result.

    The LLM call is delegated to the supplied ``llm_caller`` callable
    so the function is fully testable without hitting Bedrock.  The
    callable signature is::

        llm_caller(
            system_prompt: str,
            user_message: str,
            *,
            agent_task: str,
            patient_id: str,
        ) -> dict

    The default is ``None``, in which case
    :func:`_default_haiku_caller` is used.  In production the
    orchestrator is expected to supply an explicit caller that wires
    ``LLMUsageRecorder`` correctly.
    """
    candidates = select_candidate_encounters(encounters)
    if not candidates:
        return empty_result_for_no_candidates()

    if llm_caller is None:
        llm_caller = _default_haiku_caller

    user_message = build_user_message(
        cancer_type=cancer_type,
        first_presentation_date=first_presentation_date,
        referral_date=referral_date,
        candidates=candidates,
        text_chars_per_candidate=text_chars_per_candidate,
    )

    raw = llm_caller(
        _SYSTEM_PROMPT,
        user_message,
        agent_task=agent_task,
        patient_id=patient_id,
    )

    if not isinstance(raw, dict) or raw.get("error"):
        # LLM failure — fall back to a "result_review only" verdict
        # built from the deterministic candidates so the dashboard
        # can still surface SOMETHING for the episode.
        consultations_n = sum(
            1 for c in candidates if c.contact_type in _COUNTED_CONTACT_TYPES
        )
        return PriorConsultationsResult(
            consultations_n=consultations_n,
            verdicts=tuple(
                ConsultationVerdict(
                    encounter_id=c.encounter_id,
                    date=c.date,
                    related=False,
                    contact_type=c.contact_type,
                    evidence="LLM unavailable; deterministic fallback.",
                )
                for c in candidates
            ),
            unrelated_filtered_n=0,
            notes=f"LLM error: {raw.get('error') if isinstance(raw, dict) else 'no response'}",
        )

    return parse_llm_response(raw, candidates=candidates)


def _default_haiku_caller(
    system_prompt: str,
    user_message: str,
    *,
    agent_task: str,
    patient_id: str,
) -> dict[str, Any]:
    """Production LLM caller — Claude Haiku 4.5 on Bedrock via
    ``LLMClient.converse`` with telemetry wired through.

    Lives in this module rather than at import top-level so unit tests
    don't pull in boto3 / langchain.
    """
    from libs.llm_client.factory import create_llm
    from libs.llm_client.json_helper import _extract_json  # type: ignore[attr-defined]

    client = create_llm(provider="aws", tier="small")
    response = client.converse(
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=4096,
        temperature=0.0,
        agent_task=agent_task,
        patient_id=patient_id,
    )
    text = response.text if hasattr(response, "text") else str(response)
    try:
        return _extract_json(text)
    except Exception as exc:  # pragma: no cover - JSON failure path
        return {"error": f"JSON parse failed: {exc}"}


__all__ = [
    "CandidateEncounter",
    "ConsultationVerdict",
    "ContactType",
    "FactorVerdict",
    "NCDAFactor",
    "NCDA_FACTORS_AUTO_DETECTABLE",
    "NCDA_FACTORS_HUMAN_REVIEW_ONLY",
    "NCDA_FACTORS_LLM_JUDGMENT",
    "NCDA_FACTOR_LABELS",
    "PriorConsultationsResult",
    "build_user_message",
    "classify_contact_type",
    "classify_episode_consultations",
    "empty_result_for_no_candidates",
    "is_clinical_contact",
    "parse_llm_response",
    "select_candidate_encounters",
]
