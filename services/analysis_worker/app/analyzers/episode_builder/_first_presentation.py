"""First-presentation inference from anchors and encounter text."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

from . import _config as cfg
from . import _cypher as cypher
from ._types import _parse_date

logger = logging.getLogger(__name__)

# -- Semantic tag sets -------------------------------------------------------
_PLACE_SEMANTIC_TAGS: frozenset[str] = frozenset(
    {"environment", "place", "physical_object"}
)
_NON_COMPLAINT_SEMANTIC_TAGS: frozenset[str] = frozenset(
    {"procedure", "qualifier value", "record artifact", "event", "observable entity"}
)

# -- Regex patterns ----------------------------------------------------------
_NON_COMPLAINT_NAME_RE = re.compile(
    r"\b("
    r"seen in|seen by|consultation|appointment|outpatient|"
    r"screening|programme|program|clinic|service|"
    r"general practitioner surgery|primary care establishment|"
    r"accident and emergency|emergency department"
    r")\b",
    re.IGNORECASE,
)
_CODE_LIKE_NAME_RE = re.compile(r"^[0-9,\s]+$")
_INVESTIGATION_NAME_RE = re.compile(
    r"\b("
    r"test|scan|ct|mri|ultrasound|xray|x-ray|biopsy|histology|"
    r"colonoscopy|gastroscopy|endoscopy|psa|cea|ca125|investigation|imaging"
    r")\b",
    re.IGNORECASE,
)
_SYMPTOM_TEXT_RE = re.compile(
    r"\b("
    r"pain|bleed|bleeding|lump|mass|weight loss|fatigue|tired|"
    r"haematuria|hematuria|dysphagia|night sweat|cough|bowel|"
    r"headache|nausea|vomit|skin lesion|mole|hoarseness|jaundice"
    r")\b",
    re.IGNORECASE,
)
_INVESTIGATION_TEXT_RE = re.compile(
    r"\b("
    r"test|scan|ct|mri|ultrasound|xray|x-ray|biopsy|histology|"
    r"colonoscopy|gastroscopy|endoscopy|psa|cea|ca125|investigation|imaging"
    r")\b",
    re.IGNORECASE,
)


# -- Anchor classifier helpers ----------------------------------------------


def _anchor_is_present(anchor: dict[str, Any]) -> bool:
    return str(anchor.get("assertion") or "present").strip().lower() in ("", "present")


def _anchor_tag(anchor: dict[str, Any]) -> str:
    return str(anchor.get("semantic_tag") or "").strip().lower().replace("_", " ")


def _anchor_is_place(anchor: dict[str, Any]) -> bool:
    return _anchor_tag(anchor) in _PLACE_SEMANTIC_TAGS


def _anchor_is_complaint(anchor: dict[str, Any]) -> bool:
    if not _anchor_is_present(anchor):
        return False
    name = str(anchor.get("concept_name") or "").strip()
    if not name or _CODE_LIKE_NAME_RE.fullmatch(name):
        return False
    tag = _anchor_tag(anchor)
    if tag in _PLACE_SEMANTIC_TAGS or tag in _NON_COMPLAINT_SEMANTIC_TAGS:
        return False
    if _NON_COMPLAINT_NAME_RE.search(name):
        return False
    return True


def _anchor_is_investigation(anchor: dict[str, Any]) -> bool:
    if not _anchor_is_present(anchor):
        return False
    tag = _anchor_tag(anchor)
    name = str(anchor.get("concept_name") or "").strip()
    if not name or _CODE_LIKE_NAME_RE.fullmatch(name):
        return False
    if tag == "procedure":
        return bool(_INVESTIGATION_NAME_RE.search(name))
    return False


def _anchor_in_pre_referral_window(
    anchor: dict[str, Any],
    ref_date: date,
    window_start: date,
) -> bool:
    """True if the anchor date is within [window_start, ref_date) exclusive."""
    raw = str(anchor.get("encounter_date") or "")
    if not raw:
        return False
    try:
        anchor_date = date.fromisoformat(raw[:10])
    except ValueError:
        return False
    return window_start <= anchor_date < ref_date


# -- Main first-presentation functions ---------------------------------------


def _first_presentation_from_anchors(
    anchors: AnchorResult,
    ref_date: date | None,
    referral_dates: list[date] | None = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (fp_date, complaint, place, aligned_referral_date)."""
    if not anchors.first_presentation_anchors or ref_date is None:
        return None, None, None, None

    window_start = ref_date - timedelta(days=cfg.FIRST_PRESENTATION_LOOKBACK_DAYS)
    qualifying = [
        a
        for a in anchors.first_presentation_anchors
        if _anchor_in_pre_referral_window(a, ref_date, window_start)
    ]
    if not qualifying:
        return None, None, None, None

    complaint_candidates = [a for a in qualifying if _anchor_is_complaint(a)]
    if not complaint_candidates:
        return None, None, None, None

    candidate_days = sorted(
        {
            date.fromisoformat(str(a.get("encounter_date") or "")[:10])
            for a in complaint_candidates
            if str(a.get("encounter_date") or "")
        }
    )
    ref_days = sorted(set(referral_dates or [ref_date]))

    selected_fp_day: date | None = None
    selected_ref_day: date | None = None
    for day in candidate_days:
        valid_refs = [
            rd
            for rd in ref_days
            if 0 <= (rd - day).days <= cfg.MAX_DAYS_PRESENTATION_TO_REFERRAL
        ]
        if valid_refs:
            selected_fp_day = day
            selected_ref_day = min(valid_refs)
            break

    if selected_fp_day is None:
        return None, None, None, None

    earliest_date = selected_fp_day.isoformat()
    at_earliest = [
        a
        for a in qualifying
        if str(a.get("encounter_date") or "").startswith(earliest_date)
    ]

    complaint_parts: list[str] = []
    place_parts: list[str] = []
    for a in at_earliest:
        if not _anchor_is_present(a):
            continue
        name = str(a.get("concept_name") or "").strip()
        if not name:
            continue
        if _anchor_is_place(a):
            place_parts.append(name)
        elif _anchor_is_complaint(a):
            complaint_parts.append(name)

    place_str = place_parts[0] if place_parts else None
    complaint_str = ", ".join(dict.fromkeys(complaint_parts)) or None
    if not complaint_str:
        return None, None, None, None
    aligned_ref = selected_ref_day.isoformat() if selected_ref_day else None
    return earliest_date, complaint_str, place_str, aligned_ref


def _first_presentation_from_referral_context(
    patient_id: str,
    ref_date: date | None,
    anchors: AnchorResult,
    patient_client: Any,
) -> tuple[str | None, str | None, str | None]:
    """Fallback: infer first presentation from encounter context near referral."""
    if not patient_id or ref_date is None:
        return None, None, None

    start_day = ref_date - timedelta(days=cfg.FALLBACK_REASON_WINDOW_DAYS_BEFORE)
    end_day = ref_date + timedelta(days=cfg.FALLBACK_REASON_WINDOW_DAYS_AFTER)

    day_clues: dict[date, dict[str, set[str]]] = defaultdict(
        lambda: {"symptoms": set(), "investigations": set(), "places": set()}
    )

    for a in anchors.first_presentation_anchors:
        d = _parse_date(a.get("encounter_date"))
        if not d or d < start_day or d > end_day:
            continue
        name = str(a.get("concept_name") or "").strip()
        if not name:
            continue
        if _anchor_is_place(a):
            day_clues[d]["places"].add(name)
        elif _anchor_is_complaint(a):
            day_clues[d]["symptoms"].add(name)
        elif _anchor_is_investigation(a):
            day_clues[d]["investigations"].add(name)

    try:
        text_rows = (
            patient_client.run(
                cypher.REFERRAL_CONTEXT_TEXT_Q,
                patient_id=patient_id,
                start_date=start_day.isoformat(),
                end_date=end_day.isoformat(),
            )
            or []
        )
    except Exception:  # noqa: BLE001
        logger.warning("Referral context text query failed for patient %s", patient_id)
        text_rows = []

    for row in text_rows:
        d = _parse_date(row.get("encounter_date"))
        if not d:
            continue
        txt = str(row.get("text") or "")
        for m in _SYMPTOM_TEXT_RE.finditer(txt):
            day_clues[d]["symptoms"].add(m.group(0).lower())
        for m in _INVESTIGATION_TEXT_RE.finditer(txt):
            day_clues[d]["investigations"].add(m.group(0).lower())

    if not day_clues:
        return None, None, None

    return _pick_best_clue_day(day_clues, ref_date)


def _pick_best_clue_day(
    day_clues: dict[date, dict[str, set[str]]],
    ref_date: date,
) -> tuple[str | None, str | None, str | None]:
    """Select the best clue day: earliest symptom pre-referral, then
    earliest investigation, then post-referral symptom/investigation."""
    ordered_days = sorted(day_clues.keys())
    pre_or_same_days = [d for d in ordered_days if d <= ref_date]
    post_days = [d for d in ordered_days if d > ref_date]

    chosen_day, clue_kind, clue_source_day = _scan_clue_days(
        pre_or_same_days, post_days, day_clues, ref_date
    )

    if chosen_day is None or clue_kind is None or clue_source_day is None:
        return None, None, None

    complaint_parts = sorted(day_clues[clue_source_day][clue_kind])
    if not complaint_parts:
        return None, None, None
    place = sorted(day_clues[clue_source_day]["places"])
    return (
        chosen_day.isoformat(),
        ", ".join(complaint_parts),
        place[0] if place else None,
    )


def _scan_clue_days(
    pre_days: list[date],
    post_days: list[date],
    day_clues: dict[date, dict[str, set[str]]],
    ref_date: date,
) -> tuple[date | None, str | None, date | None]:
    """Return (chosen_day, clue_kind, clue_source_day)."""
    for d in pre_days:
        if day_clues[d]["symptoms"]:
            return d, "symptoms", d
    for d in pre_days:
        if day_clues[d]["investigations"]:
            return d, "investigations", d
    for d in post_days:
        if day_clues[d]["symptoms"]:
            return ref_date, "symptoms", d
    for d in post_days:
        if day_clues[d]["investigations"]:
            return ref_date, "investigations", d
    return None, None, None
