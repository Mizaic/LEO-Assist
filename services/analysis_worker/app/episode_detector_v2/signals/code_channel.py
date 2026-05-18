"""Code-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F

REAL implementation for breast (uses BREAST_SNOMED_* sets in
``site_keys``). For non-breast sites the extractor emits no signals --
this is the day-one stub behaviour confirmed in the plan.
"""

from __future__ import annotations

from collections.abc import Iterable
import re

from .._rulebook_adapter import (
    anchor_confirmed_snomed,
    anchor_suspected_snomed,
    cross_site_guard_for,
)
from ..site_keys import (
    BREAST_SNOMED_BENIGN_CLOSURE,
    BREAST_SNOMED_CONFIRMED,
    BREAST_SNOMED_SUSPECTED,
    SITE_BREAST,
    SITE_HEAD_NECK,
    site_for_referral_concept,
    site_intent_for_suspected_concept,
)
from ..types import Signal, TimelineEvent


def _breast_rulebook_benign_closure() -> frozenset[str]:
    """Benign-closure SNOMEDs for breast from the champion rulebook,
    with the Python constant as fallback. Keeps the ruled_out path
    behaviourally identical to v0 when no rulebook is installed.
    """
    try:
        from libs.episode_detector.loader import current_bundle

        rb = current_bundle().get(SITE_BREAST)
        if rb is not None:
            return frozenset(rb.signals.code_channel.benign_closure_snomed)
    except Exception:
        pass
    return BREAST_SNOMED_BENIGN_CLOSURE


def _classify_breast(concept_id: str) -> tuple[str, str, float] | None:
    """Return (site_key, intent, confidence) or None if not a breast code."""
    cid = concept_id.strip()
    if not cid:
        return None
    # cross_site_guard takes priority -- a code the rulebook says must
    # not count for breast (e.g. a urinary-only confirmed code that
    # collided in the legacy set) is skipped here too.
    if cid in cross_site_guard_for(SITE_BREAST):
        return None
    rulebook_confirmed = anchor_confirmed_snomed(SITE_BREAST)
    rulebook_suspected = anchor_suspected_snomed(SITE_BREAST)
    if cid in rulebook_confirmed or cid in BREAST_SNOMED_CONFIRMED:
        return SITE_BREAST, "confirmed", 0.95
    if cid in rulebook_suspected or cid in BREAST_SNOMED_SUSPECTED:
        return SITE_BREAST, "suspected", 0.80
    if cid in _breast_rulebook_benign_closure():
        return SITE_BREAST, "ruled_out", 0.70
    return None


def _classify_other_sites(concept_id: str) -> tuple[str, str, float] | None:
    """Return (site_key, intent, confidence) from the cross-site registry.

    The site lookup (``site_intent_for_suspected_concept``) is already
    rulebook-first and enforces ``cross_site_guard``; this wrapper
    only picks a confidence appropriate to the classified intent.
    """
    match = site_intent_for_suspected_concept(concept_id)
    if match is None:
        return None
    site_key, intent = match
    confidence = 0.85 if intent == "confirmed" else 0.70
    return site_key, intent, confidence


def _classify(concept_id: str) -> tuple[str, str, float] | None:
    """Breast-first then cross-site lookup -- breast wins on collision
    so the breast confidence calibration is preserved.
    """
    return _classify_breast(concept_id) or _classify_other_sites(concept_id)


def _classify_contextual_metastasis(
    event: TimelineEvent, code: dict
) -> tuple[str, str, float] | None:
    concept_id = str(code.get("concept_id") or "").strip()
    if concept_id != "94392001":
        return None
    haystack = " ".join(
        [
            event.text_snippet or "",
            str(code.get("evidence") or ""),
            str(code.get("display_name") or ""),
        ]
    ).lower()
    if "axillary" not in haystack:
        return None
    return SITE_BREAST, "confirmed", 0.85


def _classify_contextual_breast_diagnosis(
    event: TimelineEvent, code: dict
) -> tuple[str, str, float] | None:
    haystack = " ".join(
        [
            event.text_snippet or "",
            str(code.get("evidence") or ""),
            str(code.get("display_name") or ""),
        ]
    ).lower()
    if "infiltrating duct carcinoma" not in haystack:
        return None
    return SITE_BREAST, "confirmed", 0.90


def _evidence_site_override(code: dict) -> tuple[str, str, float] | None:
    """Use local evidence text when it contradicts a generic/wrong code.

    The deterministic 2WW coder can occasionally attach a breast-suspected
    situation because the phrase "has breast cancer" appears in the same
    sentence as a different active referral. In that case the referral target
    in the evidence text is more reliable than the coded concept.
    """

    evidence = " ".join(
        str(code.get(key) or "")
        for key in ("evidence", "evidence_sentence")
    ).lower()
    if not evidence:
        return None
    if re.search(
        r"\b(?:refer(?:ral)?\s+re\s+neck|2\s*ww\s+neck|neck\s+2\s*ww|"
        r"head\s+and\s+neck)\b",
        evidence,
    ):
        return SITE_HEAD_NECK, "suspected", 0.85
    return None


def _is_backdated_or_review_restatement(
    event: TimelineEvent,
    code: dict,
    *,
    site_key: str,
    intent: str,
) -> bool:
    if site_key != SITE_BREAST or intent != "confirmed":
        return False
    text = (event.text_snippet or "").lower()
    flags = str(event.raw.get("encounter_flags") or "").lower()
    source = str(code.get("source") or "").lower()
    evidence = str(code.get("evidence") or "").lower()
    is_problem_list_source = source in {
        "major_text_cancer_backfill",
        "deterministic_cancer_diagnosis_coder",
    } or evidence.startswith("major:")
    if (
        is_problem_list_source
        and "back-dated and entered on:" in flags
        and not _has_same_encounter_diagnostic_context(text, evidence)
    ):
        return True
    if is_problem_list_source and "cancer care review" in text:
        return True
    if is_problem_list_source and _is_historical_breast_diagnosis_reference(
        text, evidence
    ):
        return True
    return False


def _is_historical_breast_diagnosis_reference(text: str, evidence: str) -> bool:
    haystack = f"{text} {evidence}"
    return bool(
        re.search(
            r"\b(?:diagnosed|diagnosis)\s+with\s+(?:ca\s+)?breast\s+"
            r"(?:cancer|ca)\b.{0,80}\b(?:ago|previous|past|history)\b",
            haystack,
        )
        or re.search(
            r"\b(?:ago|previous|past|history)\b.{0,80}"
            r"\b(?:diagnosed|diagnosis)\s+with\s+(?:ca\s+)?breast\s+"
            r"(?:cancer|ca)\b",
            haystack,
        )
        or re.search(
            r"\bstopped smoking\s+\d+\s+years?\s+ago\s+when diagnosed with "
            r"breast cancer\b",
            haystack,
        )
    )


def _has_same_encounter_diagnostic_context(text: str, evidence: str) -> bool:
    haystack = f"{text} {evidence}"
    return any(
        phrase in haystack
        for phrase in (
            "ultrasound guided biopsy",
            "biopsy of sentinel lymph node",
            "metastasis to lymph node",
            "axillary lymph node",
            "axillary lymph nodes",
            "histology",
            "pathology",
        )
    )


def _role_from_assertion(assertion: str | None) -> str:
    norm = (assertion or "").lower()
    if "fam" in norm:
        return "family_history"
    if "hist" in norm:
        return "history"
    if "neg" in norm:
        return "outcome"
    return "diagnosis"


def extract_code_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """Emit one Signal per coded entity that maps to a known site.

    The function is deterministic and side-effect free. It is the
    silent-drop fail-safe for stub sites: even though they have no
    candidate generator yet, the code-channel signal makes the
    encounter visible to the coverage check.
    """
    out: list[Signal] = []
    for event in events:
        for code in event.coded_entities:
            concept_id = str(code.get("concept_id") or "")
            evidence_override = _evidence_site_override(code)
            if evidence_override is not None:
                site_key, intent, confidence = evidence_override
                out.append(
                    Signal(
                        channel="code",
                        encounter_id=event.encounter_id,
                        site_key=site_key,
                        role="referral",
                        intent=intent,
                        confidence=confidence,
                        citation=(
                            f"Evidence-routed SNOMED {concept_id} "
                            f"({code.get('display_name') or 'unknown term'})"
                        ),
                    )
                )
                continue
            referral_site = site_for_referral_concept(concept_id)
            if referral_site is not None:
                out.append(
                    Signal(
                        channel="code",
                        encounter_id=event.encounter_id,
                        site_key=referral_site,
                        role="referral",
                        intent="suspected",
                        confidence=0.90,
                        citation=(
                            f"SNOMED {concept_id} "
                            f"({code.get('display_name') or 'unknown term'})"
                        ),
                    )
                )
                continue
            classification = _classify(concept_id)
            if classification is None:
                classification = _classify_contextual_metastasis(event, code)
            if classification is None:
                classification = _classify_contextual_breast_diagnosis(event, code)
            if classification is None:
                continue
            site_key, intent, confidence = classification
            if _is_backdated_or_review_restatement(
                event, code, site_key=site_key, intent=intent
            ):
                continue
            assertion = code.get("assertion")
            if (
                isinstance(assertion, str)
                and assertion.lower() in {"negated", "ruled_out", "negative"}
            ):
                intent = "ruled_out"
                confidence = max(confidence, 0.85)
            out.append(
                Signal(
                    channel="code",
                    encounter_id=event.encounter_id,
                    site_key=site_key,
                    role=_role_from_assertion(code.get("role") or assertion),
                    intent=intent,
                    confidence=confidence,
                    citation=(
                        f"SNOMED {concept_id} "
                        f"({code.get('display_name') or 'unknown term'})"
                    ),
                )
            )
    return out
