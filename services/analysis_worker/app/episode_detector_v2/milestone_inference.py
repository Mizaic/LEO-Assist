"""Infer UI-supported milestone links for v2 detector episodes.

The v2 detector resolves episode membership, but the reviewer UI needs
typed ``IS_PART_OF`` relationships. This module turns the resolved
episode plus its source timeline into curation-ready milestone links.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .types import ResolvedEpisode, TimelineEvent

PATHWAY_MILESTONE_TYPES = frozenset(
    {
        "first_presentation",
        "referral",
        "first_seen",
        "outcome_letter",
        "diagnosis_confirmed",
        "treatment_started",
        "treatment_completed",
        "benign_closure",
        "care_obstruction",
    }
)

CONTEXT_MILESTONE_TYPES = frozenset(
    {
        "related_gp_visit",
        "primary_care_investigations",
        "referral_admin",
        "referral_sent",
        "related_specialist_visit",
        "specialist_diagnostics",
        "related_correspondence",
        "treatment_planned",
        "treatment_monitoring",
        "treatment_toxicity",
    }
)

SUPPORTED_MILESTONE_TYPES = PATHWAY_MILESTONE_TYPES | CONTEXT_MILESTONE_TYPES

_ORDER = {
    "first_presentation": 0,
    "referral": 1,
    "referral_sent": 2,
    "first_seen": 3,
    "specialist_diagnostics": 4,
    "outcome_letter": 5,
    "diagnosis_confirmed": 6,
    "treatment_started": 7,
    "treatment_completed": 8,
    "benign_closure": 9,
    "care_obstruction": 10,
    "related_gp_visit": 11,
    "primary_care_investigations": 12,
    "referral_admin": 13,
    "related_specialist_visit": 14,
    "related_correspondence": 15,
    "treatment_planned": 16,
    "treatment_monitoring": 17,
    "treatment_toxicity": 18,
}


@dataclass(frozen=True)
class MilestoneLink:
    encounter_id: str
    milestone_type: str
    evidence_quote: str
    confidence: float = 0.80
    treatment_type: str | None = None


def infer_milestone_links(
    episode: ResolvedEpisode,
    timeline: list[TimelineEvent],
) -> list[MilestoneLink]:
    """Infer supported milestone links for an episode.

    Multiple links may be returned for a single encounter when the
    encounter genuinely fills multiple slots, e.g. referral +
    first_presentation or diagnosis_confirmed + specialist_diagnostics.
    """
    event_by_id = {event.encounter_id: event for event in timeline}
    links: list[MilestoneLink] = []
    for enc_id in episode.encounter_ids:
        event = event_by_id.get(enc_id)
        if event is None:
            continue
        event_links = _links_for_event(event, episode.site_key)
        if not event_links:
            event_links = [_link(event, "related_correspondence")]
        links.extend(event_links)
    return _dedupe_and_sort(links, event_by_id)


def infer_contextual_encounter_ids(
    *,
    site_key: str,
    candidate_encounter_ids: list[str],
    timeline: list[TimelineEvent],
) -> list[str]:
    """Return strong site-context encounters from a candidate window.

    Some clinically important events are generic SNOMEDs, e.g. metastatic
    malignant neoplasm to lymph node. They should join an existing breast
    cancer episode when the text makes the breast-pathway context clear,
    but they should not seed a separate site episode.
    """
    if site_key != "breast":
        return []
    event_by_id = {event.encounter_id: event for event in timeline}
    out: list[str] = []
    for enc_id in candidate_encounter_ids:
        event = event_by_id.get(enc_id)
        if event is None:
            continue
        haystack = " ".join([_normalised_text(event), *_concept_names(event)])
        if _is_strong_breast_context(haystack):
            out.append(enc_id)
    return out


def infer_walkback_encounter_ids(
    *,
    site_key: str,
    anchor_event_id: str,
    generator: str = "",
    intent: str = "",
    timeline: list[TimelineEvent],
    lookback_days: int = 90,
) -> list[str]:
    """Walk back from diagnosis to related uncoded precursor events."""
    if site_key != "breast" or generator != "diagnosis_anchored":
        return []
    if intent != "confirmed":
        return []
    event_by_id = {event.encounter_id: event for event in timeline}
    anchor = event_by_id.get(anchor_event_id)
    if anchor is None:
        return []
    anchor_haystack = " ".join([_normalised_text(anchor), *_concept_names(anchor)])
    if not _is_breast_primary_diagnosis(anchor_haystack):
        return []
    candidates: list[TimelineEvent] = []
    has_metastatic_bridge = False
    has_symptom_context = False
    anchor_date = anchor.occurred_on
    for event in timeline:
        days_before = (anchor_date - event.occurred_on).days
        if days_before < 0 or days_before > lookback_days:
            continue
        haystack = " ".join([_normalised_text(event), *_concept_names(event)])
        if _is_metastatic_diagnosis(haystack):
            has_metastatic_bridge = True
            candidates.append(event)
        elif _is_walkback_symptom_or_escalation(haystack):
            has_symptom_context = True
            candidates.append(event)
        elif event.encounter_id == anchor_event_id:
            candidates.append(event)
    if not has_metastatic_bridge or not has_symptom_context:
        return []
    out: list[str] = []
    for event in candidates:
        if event.encounter_id != anchor_event_id:
            out.append(event.encounter_id)
    return out


def infer_benign_presentation_encounter_ids(
    *,
    site_key: str,
    candidate_encounter_ids: list[str],
    intent: str,
    boundary_end: date | None,
    timeline: list[TimelineEvent],
) -> list[str]:
    """Return early presentation encounters for benign breast pathways."""
    if site_key != "breast" or intent != "ruled_out" or boundary_end is None:
        return []
    event_by_id = {event.encounter_id: event for event in timeline}
    out: list[str] = []
    for enc_id in candidate_encounter_ids:
        event = event_by_id.get(enc_id)
        if event is None or event.occurred_on > boundary_end:
            continue
        text = _normalised_text(event)
        haystack = " ".join([text, *_concept_names(event)])
        if _is_first_presentation(haystack, text):
            out.append(enc_id)
    return out


def prune_duplicate_same_day_referral_encounter_ids(
    *,
    site_key: str,
    candidate_encounter_ids: list[str],
    timeline: Sequence[TimelineEvent],
) -> list[str]:
    event_by_id = {event.encounter_id: event for event in timeline}
    links: list[MilestoneLink] = []
    for enc_id in candidate_encounter_ids:
        event = event_by_id.get(enc_id)
        if event is None:
            continue
        links.extend(_links_for_event(event, site_key))

    filtered_links = _drop_duplicate_same_day_referral_sent(links, event_by_id)
    referral_sent_before = {
        link.encounter_id for link in links if link.milestone_type == "referral_sent"
    }
    referral_sent_after = {
        link.encounter_id
        for link in filtered_links
        if link.milestone_type == "referral_sent"
    }
    dropped_referral_sent = referral_sent_before - referral_sent_after
    filtered_milestones_by_encounter: dict[str, set[str]] = {}
    for link in filtered_links:
        filtered_milestones_by_encounter.setdefault(link.encounter_id, set()).add(
            link.milestone_type
        )

    return [
        enc_id
        for enc_id in candidate_encounter_ids
        if enc_id not in dropped_referral_sent
        or filtered_milestones_by_encounter.get(enc_id)
    ]


def add_same_day_referral_sent_encounter_ids(
    *,
    site_key: str,
    candidate_encounter_ids: list[str],
    timeline: Sequence[TimelineEvent],
) -> list[str]:
    if site_key != "breast":
        return candidate_encounter_ids
    event_by_id = {event.encounter_id: event for event in timeline}
    dates = {
        event_by_id[enc_id].occurred_on
        for enc_id in candidate_encounter_ids
        if enc_id in event_by_id
    }
    out = list(candidate_encounter_ids)
    seen = set(out)
    for event in timeline:
        if event.occurred_on not in dates or event.encounter_id in seen:
            continue
        haystack = " ".join([_normalised_text(event), *_concept_names(event)])
        if _is_referral_sent(haystack):
            out.append(event.encounter_id)
            seen.add(event.encounter_id)
    return out


def prune_weak_breast_context_encounter_ids(
    *,
    site_key: str,
    candidate_encounter_ids: list[str],
    timeline: Sequence[TimelineEvent],
) -> list[str]:
    if site_key != "breast":
        return candidate_encounter_ids
    event_by_id = {event.encounter_id: event for event in timeline}
    return [
        enc_id
        for enc_id in candidate_encounter_ids
        if not _is_weak_breast_context(event_by_id.get(enc_id))
    ]


def _links_for_event(event: TimelineEvent, site_key: str) -> list[MilestoneLink]:
    text = _normalised_text(event)
    concepts = _concept_names(event)
    haystack = " ".join([text, *concepts])
    links: list[MilestoneLink] = []

    if _is_first_presentation(haystack, text, site_key) or _is_metastatic_presentation(
        haystack
    ):
        links.append(_link(event, "first_presentation"))
    if _is_referral_sent(haystack):
        links.append(_link(event, "referral_sent"))
    if _is_referral_decision(haystack):
        links.append(_link(event, "referral"))
    if _is_referral_admin(haystack):
        links.append(_link(event, "referral_admin"))
    if _is_first_seen(haystack):
        links.append(_link(event, "first_seen"))
    if _is_specialist_diagnostics(haystack):
        links.append(_link(event, "specialist_diagnostics"))
    if _is_outcome_letter(haystack):
        links.append(_link(event, "outcome_letter"))
    if _is_benign_closure(haystack, site_key):
        links.append(_link(event, "benign_closure"))
    if _is_confirmed_diagnosis(haystack) or _is_metastatic_diagnosis(haystack):
        links.append(_link(event, "diagnosis_confirmed"))
    if _is_treatment_started(haystack, text):
        links.append(_link(event, "treatment_started"))
    if _is_treatment_completed(haystack):
        links.append(_link(event, "treatment_completed"))
    if _is_treatment_planned(haystack):
        links.append(_link(event, "treatment_planned"))
    if _is_treatment_monitoring(haystack):
        links.append(_link(event, "treatment_monitoring"))
    if _is_treatment_toxicity(haystack):
        links.append(_link(event, "treatment_toxicity"))
    if _is_care_obstruction(haystack):
        links.append(_link(event, "care_obstruction"))
    if _is_primary_care_investigation(haystack):
        links.append(_link(event, "primary_care_investigations"))
    if _is_related_gp_visit(haystack):
        links.append(_link(event, "related_gp_visit"))
    if _is_related_specialist_visit(haystack):
        links.append(_link(event, "related_specialist_visit"))

    return links


def _is_strong_breast_context(haystack: str) -> bool:
    if any(
        phrase in haystack
        for phrase in (
            "advice on foreign travel",
            "mmr booster",
            "hormone replacement therapy review",
            "hrt questionnaire",
            "menopausal symptoms",
            "worried about breast cancer",
            "risk of breast cancer",
            "history of breast cyst",
            "family history of breast cancer: no",
            "breast screening up to date",
            "vaccination",
            "vaccine",
        )
    ):
        return False
    return any(
        phrase in haystack
        for phrase in (
            "malignant tumour of breast",
            "malignant neoplasm of breast",
            "invasive carcinoma of breast",
            "infiltrating duct carcinoma of breast",
            "ductal carcinoma in situ",
            "metastasis to lymph node",
            "axillary lymph",
            "breast clinic",
            "breast surgeon",
            "wide local excision of breast",
            "mastectomy",
            "infiltrating duct carcinoma",
            "[m]ductal, lobular and medullary neoplasms",
            "fast track referral for suspected breast cancer",
            "patient awaiting opd appt.: yes 2ww breast",
            "2ww breast female prism",
            "chemotherapy",
            "awaits discussion about chemo",
            "starts chemo",
            "pre chemo",
            "pre-chemo",
        )
    )


def _is_weak_breast_context(event: TimelineEvent | None) -> bool:
    if event is None:
        return False
    haystack = " ".join([_normalised_text(event), *_concept_names(event)])
    return any(
        phrase in haystack
        for phrase in (
            "problem: sore throat",
            "problem: hypertension",
            "problem: depressed mood",
            "prism hernia",
            "referral to gastroenterology service",
            "6-8 week postnatal maternity check",
            "postnatal examination normal",
            "just delivered baby",
            "depo contraception",
            "right shoulder pain",
            "unable to latch on to breast for feeding",
            "does not breast feed",
            "previous breast surgery with right-sided surgical clips",
            "no sign disease recurrence",
            "shingrix vaccination",
            "lymphoedema clinic",
        )
    )


def _is_breast_walkback_context(haystack: str) -> bool:
    if _is_strong_breast_context(haystack):
        return True
    return any(
        phrase in haystack
        for phrase in (
            "metastasis to bone of unknown primary",
            "metastatic malignant neoplasm to bone",
            "unknown primary",
            "hypercalcaemia",
            "metastatic spinal cord compression",
            "spinal cord compression",
            "mri of spine",
            "right lower back pain",
            "lower back pain",
            "flank pain",
            "acute abdomen",
            "urgent ed",
            "urgent care centre",
        )
    )


def _is_breast_primary_diagnosis(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "malignant tumour of breast",
            "malignant neoplasm of breast",
            "invasive carcinoma of breast",
            "infiltrating duct carcinoma of breast",
            "ductal carcinoma in situ",
            "infiltrating duct carcinoma",
        )
    )


def _is_walkback_symptom_or_escalation(haystack: str) -> bool:
    return _is_metastatic_presentation(haystack) or any(
        phrase in haystack
        for phrase in (
            "right flank pain",
            "radiating to ruq",
            "acute abdomen",
            "ed admission",
            "urgent care centre",
        )
    )


def _normalised_text(event: TimelineEvent) -> str:
    return " ".join((event.text_snippet or "").lower().split())


def _concept_names(event: TimelineEvent) -> list[str]:
    names: list[str] = []
    for code in event.coded_entities:
        name = str(code.get("display_name") or "").lower()
        if name:
            names.append(name)
    return names


def _link(event: TimelineEvent, milestone_type: str) -> MilestoneLink:
    return MilestoneLink(
        encounter_id=event.encounter_id,
        milestone_type=milestone_type,
        evidence_quote=_quote(event),
        confidence=0.85 if milestone_type in PATHWAY_MILESTONE_TYPES else 0.75,
        treatment_type=_treatment_type(event, milestone_type),
    )


def _quote(event: TimelineEvent) -> str:
    return " ".join((event.text_snippet or "").split())[:240]


def _is_first_presentation(haystack: str, text: str, site_key: str = "breast") -> bool:
    if site_key == "head_neck":
        return _is_head_neck_first_presentation(haystack, text)
    if "chaperone" in haystack and "breast examination" in haystack:
        return True
    has_breast_lump = (
        "breast lump" in haystack
        or "lump in breast" in haystack
        or "lump in the breast" in haystack
        or "lump of breast" in haystack
    )
    return has_breast_lump and (
        "history:" in text or "examination:" in text or "diagnosis:" in text
    )


def _is_head_neck_first_presentation(haystack: str, text: str) -> bool:
    if any(
        phrase in haystack
        for phrase in (
            "re lump on neck",
            "review following derm",
            "appt so rescheduled",
            "appointment so rescheduled",
        )
    ):
        return False
    has_neck_lump = any(
        phrase in haystack
        for phrase in (
            "lump on back of neck",
            "neck lump",
            "lump on neck",
            "lump in neck",
            "neck mass",
        )
    )
    return has_neck_lump and (
        "history:" in text or "examination:" in text or "diagnosis:" in text
    )


def _is_metastatic_presentation(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "right lower back pain",
            "lower back pain",
            "flank pain",
            "acute abdomen",
        )
    )


def _is_referral_sent(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "choice and booking enhanced services administration",
            "patient awaiting opd appt",
            "updated: waiting for information",
            "fast track referral for suspected breast cancer",
            "fast track referral for suspected head and neck cancer",
            "fast track referral for suspected breast cancer updated",
        )
    )


def _is_referral_decision(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "plan: 2ww breast referral",
            "2ww breast referral",
            "referred on 2ww",
            "refer on 2ww",
        )
    )


def _is_referral_admin(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "questionnaire started",
            "pathway accessed",
            "prism pathway & referral",
            "outbound referral",
            "first outpatient appointment date",
            "date of first outpatient appointment",
        )
    )


def _is_first_seen(haystack: str) -> bool:
    return (
        "seen in fast track suspected breast cancer clinic" in haystack
        or "seen in fast track suspected head and neck cancer clinic" in haystack
        or "seen in 2ww clinic" in haystack
    )


def _is_specialist_diagnostics(haystack: str) -> bool:
    if any(
        phrase in haystack
        for phrase in (
            "first outpatient appointment date",
            "date of first outpatient appointment",
            "awaiting needle biopsy",
        )
    ):
        return False
    return any(
        phrase in haystack
        for phrase in (
            "biopsy",
            "mammogram",
            "us scan of breast",
            "ultrasound",
            "core needle",
            "sentinel lymph node",
        )
    )


def _is_outcome_letter(haystack: str) -> bool:
    if any(
        phrase in haystack
        for phrase in (
            "medication reconciliation",
            "repeat medication check",
            "drug review",
            "new repeat medication",
        )
    ):
        return False
    if "breast to woodbrook" in haystack and not any(
        phrase in haystack
        for phrase in (
            "outcome",
            "diagnos",
            "malignant",
            "carcinoma",
            "surgery",
            "treatment",
            "oncology",
        )
    ):
        return False
    return any(
        phrase in haystack
        for phrase in (
            "breast surgeon to",
            "clinic letter",
            "outcome letter",
        )
    )


def _is_confirmed_diagnosis(haystack: str) -> bool:
    if "cancer care review" in haystack:
        return False
    suspected_only = "suspected breast cancer" in haystack and "major:" not in haystack
    if suspected_only:
        return False
    return any(
        phrase in haystack
        for phrase in (
            "diagnosed with ca breast",
            "malignant tumour of breast",
            "malignant neoplasm of breast (disorder)",
            "invasive carcinoma of breast",
            "infiltrating duct carcinoma of breast",
            "ductal carcinoma in situ",
            "metastasis to lymph node",
            "macrometastasis",
        )
    )


def _is_benign_closure(haystack: str, site_key: str = "breast") -> bool:
    if site_key == "head_neck":
        return any(
            phrase in haystack
            for phrase in (
                "minor: occipital lymph node",
                "occipital lymph node",
            )
        )
    if any(
        phrase in haystack
        for phrase in (
            "mammogram normal 1 year ago",
            "mammogram normal one year ago",
            "mammogram normal last year",
        )
    ):
        return False
    if "lipoma of breast" in haystack or "cyst of breast" in haystack:
        return True
    has_breast_investigation = any(
        phrase in haystack
        for phrase in (
            "us scan of breast",
            "ultrasound scan of breast",
            "mammogram",
            "breast ultrasound",
            "breast clinic",
        )
    )
    has_benign_result = any(
        phrase in haystack
        for phrase in (
            " - normal",
            " normal",
            "no malignancy",
            "no abnormality",
            "benign",
            "negative",
        )
    )
    return has_breast_investigation and has_benign_result


def _is_metastatic_diagnosis(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "metastasis to bone of unknown primary",
            "metastatic malignant neoplasm to bone",
            "metastatic spinal cord compression",
            "spinal cord compression",
        )
    )


def _is_treatment_started(haystack: str, text: str) -> bool:
    if "starts chemo" in haystack or "awaits discussion about chemo" in haystack:
        return False
    if "currently undergoing chemotherapy" in haystack:
        return False
    if (
        "lymphoedema clinic" in haystack
        or "following treatment for breast cancer" in haystack
    ):
        return False
    return any(
        phrase in haystack
        for phrase in (
            "major: chemotherapy",
            "chemo started",
            "started chemo",
            "pt commenced on letrozole",
            "commenced on letrozole",
            "wide local excision",
            "mastectomy",
            "radiotherapy",
        )
    ) or ("chemotherapy" in haystack and "major:" in text)


def _is_treatment_completed(haystack: str) -> bool:
    return "treatment completed" in haystack or "completed chemotherapy" in haystack


def _is_treatment_planned(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "starts chemo",
            "awaits discussion about chemo",
            "planned chemotherapy",
            "chemo planned",
        )
    )


def _is_treatment_monitoring(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "pre chemo",
            "pre-chemo",
            "last scheduled chemo",
            "urgent bloods",
        )
    )


def _is_treatment_toxicity(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "chemotherapy side effects",
            "currently undergoing chemotherapy",
            "fatigue and other side effects",
            "effects of chemo",
            "last time she had chemo",
            "advised by chemo suite",
            "hot flushes since starting letrazole",
            "medication induced menopausal hot flushing",
            "medication induced menopausal hot flushes",
        )
    )


def _is_care_obstruction(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "taxi failed",
            "failed to collect",
            "appt so rescheduled",
            "appointment so rescheduled",
            "unable to attend",
            "did not attend",
        )
    )


def _is_primary_care_investigation(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "pre chemo",
            "blood sample taken",
            "phlebotomy",
            "blood test",
            "blood taken",
        )
    )


def _is_related_gp_visit(haystack: str) -> bool:
    if _is_treatment_planned(haystack):
        return False
    if _is_treatment_toxicity(haystack) and not any(
        phrase in haystack
        for phrase in (
            "history:",
            "diagnosis:",
            "cancer care review",
            "complaining of hot flushes",
        )
    ):
        return False
    has_fit_note = "fit note" in haystack or "med3" in haystack
    if has_fit_note and not _has_breast_cancer_followup_context(haystack):
        return False
    return any(
        phrase in haystack
        for phrase in (
            "starts chemo",
            "awaits discussion about chemo",
            "currently undergoing chemotherapy",
            "chemotherapy side effects",
            "problem: generalised anxiety disorder",
            "fit note",
            "med3",
            "planned review",
            "reviewed other issues",
            "ongoing support offered",
            "cancer care review",
            "general catch up",
            "complaining of hot flushes",
        )
    )


def _has_breast_cancer_followup_context(haystack: str) -> bool:
    return any(
        phrase in haystack
        for phrase in (
            "breast cancer",
            "breast ca",
            "known breast ca",
            "breast surgery",
            "post breast surgery",
            "mastectomy",
            "radiotherapy",
            "chemotherapy",
            "oncology",
        )
    )


def _is_related_specialist_visit(haystack: str) -> bool:
    return (
        "seen in 2ww clinic" in haystack and "summary care record" in haystack
    ) or "lymphoedema clinic" in haystack


def _treatment_type(event: TimelineEvent, milestone_type: str) -> str | None:
    if not milestone_type.startswith("treatment_"):
        return None
    haystack = " ".join([_normalised_text(event), *_concept_names(event)])
    if "chemo" in haystack or "chemotherapy" in haystack:
        return "chemotherapy"
    if any(
        phrase in haystack
        for phrase in (
            "wide local excision",
            "mastectomy",
            "sentinel lymph",
            "axillary lymph node",
            "block dissection",
        )
    ):
        return "surgery"
    if "radiotherapy" in haystack:
        return "radiotherapy"
    if "letrozole" in haystack:
        return "endocrine_therapy"
    return "other"


def _dedupe_and_sort(
    links: list[MilestoneLink],
    event_by_id: dict[str, TimelineEvent],
) -> list[MilestoneLink]:
    seen: set[tuple[str, str]] = set()
    out: list[MilestoneLink] = []
    for link in links:
        key = (link.encounter_id, link.milestone_type)
        if key in seen or link.milestone_type not in SUPPORTED_MILESTONE_TYPES:
            continue
        seen.add(key)
        out.append(link)
    out = _drop_duplicate_same_day_referral_sent(out, event_by_id)
    return sorted(
        out,
        key=lambda link: (
            event_by_id[link.encounter_id].occurred_on,
            link.encounter_id,
            _ORDER.get(link.milestone_type, 99),
        ),
    )


def _drop_duplicate_same_day_referral_sent(
    links: list[MilestoneLink],
    event_by_id: dict[str, TimelineEvent],
) -> list[MilestoneLink]:
    by_date: dict[date, list[MilestoneLink]] = {}
    milestones_by_encounter: dict[str, set[str]] = {}
    for link in links:
        event = event_by_id.get(link.encounter_id)
        if event is None:
            continue
        milestones_by_encounter.setdefault(link.encounter_id, set()).add(
            link.milestone_type
        )
        if link.milestone_type == "referral_sent":
            by_date.setdefault(event.occurred_on, []).append(link)

    drop: set[tuple[str, str]] = set()
    for same_day_links in by_date.values():
        if len(same_day_links) <= 1:
            continue
        preferred = _preferred_referral_sent_link(
            same_day_links,
            milestones_by_encounter,
            event_by_id,
        )
        for link in same_day_links:
            if link.encounter_id != preferred.encounter_id:
                drop.add((link.encounter_id, link.milestone_type))
    if not drop:
        return links
    return [
        link
        for link in links
        if (link.encounter_id, link.milestone_type) not in drop
    ]


def _preferred_referral_sent_link(
    links: list[MilestoneLink],
    milestones_by_encounter: dict[str, set[str]],
    event_by_id: dict[str, TimelineEvent],
) -> MilestoneLink:
    return min(
        links,
        key=lambda link: (
            "referral_admin" not in milestones_by_encounter.get(
                link.encounter_id, set()
            ),
            event_by_id[link.encounter_id].occurred_on,
            link.encounter_id,
        ),
    )
