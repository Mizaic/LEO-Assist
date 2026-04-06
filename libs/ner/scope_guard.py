"""Defence-in-depth guard: enforce intended-use boundaries at extraction time.

Clinical safety rules that prevent the pipeline from operating beyond its
intended purpose as a retrospective clinical-coding tool:

1. **Safety-netting suppression** -- entities extracted from safety-netting or
   contingency text (e.g. "if develops chest pain, call 999") are SUPPRESSED
   (removed from the entity list entirely). Safety-netting is patient advice,
   not a clinical event. It should never appear in the coding or review queue.
   ``reclassify_assertion`` returns the sentinel ``"suppressed"`` and the
   post-processing layer removes those entities before downstream steps.

2. **Treatment recommendation reclassification** -- entities whose sentence
   context contains advisory/recommendation language (e.g. "consider starting",
   "recommend referral", "advise lifestyle changes") are reclassified from
   "present" to "hypothetical". The entity IS real but conditional; it is kept
   in the review queue for a human to decide.

3. **Diagnosis from symptom guard** -- entities tagged as disorder whose
   sentence contains hedged diagnostic language ("consistent with", "in
   keeping with", "suggestive of") without an explicit diagnosis statement
   are reclassified to "possible".

These guards run AFTER LLM extraction and the lab-value guard, but BEFORE
context detection (MedSpaCy ConText). ConText may further tighten assertions
(e.g. from "present" to "absent"), which is always safe.

Distinction between suppression and hypothetical:
  - Safety netting   = patient instructions ("call 999 if...") -- no entity
  - Hypothetical     = conditional clinical plan ("start X if no improvement")
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety-netting / contingency text detection
# ---------------------------------------------------------------------------

_SAFETY_NETTING_RE = re.compile(
    r"\b("
    r"if\s+(?:you\s+)?(?:develop|experience|notice|get|have|feel|become|worsen)"
    r"|worsening\s+(?:advice|instructions?|plan)"
    r"|seek\s+(?:urgent|immediate|emergency|medical)\s+(?:help|review|attention|care|advice)"
    r"|attend\s+(?:a[&\s]*e|emergency|casualty|urgent\s+care)"
    r"|call\s+(?:999|111|ambulance|GP|doctor|nhs|out[\s-]+of[\s-]+hours)"
    r"|go\s+(?:straight\s+)?to\s+(?:a[&\s]*e|hospital|emergency)"
    r"|red\s+flag"
    r"|safety[\s-]*netting"
    r"|return\s+(?:immediately|urgently|sooner)\s+if"
    r"|(?:come|go)\s+back\s+(?:if|should)"
    r"|(?:ring|phone|contact)\s+(?:us|the\s+surgery|your\s+(?:gp|doctor))\s+if"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Treatment recommendation / advisory language
# ---------------------------------------------------------------------------

_RECOMMENDATION_RE = re.compile(
    r"\b(?:"
    r"consider\s+(?:starting|commencing|initiating|prescribing|referring|adding|trying|giving|using)"
    r"|recommend(?:ed|ing|s)?\s+(?:start\w*|commenc\w*|initiat\w*|prescrib\w*|referr\w*|add\w*|try\w*|giv\w*|us\w*|review\w*)"
    r"|advis(?:e[ds]?|ing)\s+(?:to\s+)?(?:start|commenc|initiat|try|take|use|consider|stop|avoid)\w*"
    r"|suggest(?:ed|s|ing)?\s+(?:start\w*|commenc\w*|initiat\w*|prescrib\w*|referr\w*|try\w*|giv\w*|us\w*)"
    r"|(?:should|could|may|might)\s+(?:be\s+)?(?:started\s+on|commenced\s+on|initiated\s+on|referred)"
    r"|(?:plan|intention|aim)\s+to\s+(?:start|commenc|initiat|prescrib|refer|try|give|review)\w*"
    r"|would\s+(?:benefit\s+from|recommend|suggest|advise)"
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Hedged / interpretive diagnostic language
# ---------------------------------------------------------------------------

_HEDGED_DIAGNOSIS_RE = re.compile(
    r"\b("
    r"consistent\s+with"
    r"|in\s+keeping\s+with"
    r"|suggestive\s+of"
    r"|may\s+(?:represent|indicate|suggest|be)"
    r"|could\s+(?:represent|indicate|suggest|be)"
    r"|(?:likely|probably|possibly|potentially)\s+(?:represents?|indicates?|suggests?|due\s+to)"
    r"|picture\s+(?:is\s+)?(?:in\s+keeping|consistent|suggestive)"
    r"|raises?\s+(?:the\s+)?(?:possibility|suspicion|concern)\s+(?:of|for|that)"
    r"|cannot\s+(?:exclude|rule\s*out)"
    r"|differential\s+(?:includes?|diagnosis)"
    r")\b",
    re.IGNORECASE,
)

_CONFIRMED_DIAGNOSIS_RE = re.compile(
    r"\b("
    r"diagnos[ei]s|diagnos(?:ed|ing)|dx[:\s]"
    r"|has\s+(?:been\s+)?diagnosed"
    r"|confirmed?\b"
    r"|established\b"
    r"|known\s+(?:to\s+have|case\s+of|\w+)"
    r"|suffers?\s+from"
    r"|(?:patient|pt)\s+has\s+\w+"
    r"|on\s+treatment\s+for"
    r"|managed\s+for"
    r"|being\s+treated\s+for"
    r"|presents?\s+with"
    r"|problem\s+list"
    r"|active\s+problem"
    r"|impression[:\s]"
    r"|assessment[:\s]"
    r")\b",
    re.IGNORECASE,
)


def is_safety_netting_sentence(sentence_text: str) -> bool:
    """Return True if the sentence is safety-netting / contingency advice."""
    return bool(_SAFETY_NETTING_RE.search(sentence_text))


def has_recommendation_language(sentence_text: str) -> bool:
    """Return True if the sentence contains treatment recommendation phrasing."""
    return bool(_RECOMMENDATION_RE.search(sentence_text))


def has_hedged_diagnosis(sentence_text: str) -> bool:
    """Return True if the sentence uses interpretive diagnostic language
    without a confirmed diagnosis statement."""
    if not _HEDGED_DIAGNOSIS_RE.search(sentence_text):
        return False
    if _CONFIRMED_DIAGNOSIS_RE.search(sentence_text):
        return False
    return True


SUPPRESSED = "suppressed"


def reclassify_assertion(
    *,
    entity_semantic_tag: str,
    entity_assertion: str,
    sentence_text: str,
    entity_text: str = "",
) -> str | None:
    """Return a corrected assertion if scope-guard rules apply, else None.

    Returns:
        ``SUPPRESSED`` (``"suppressed"``) if the entity originates from a
        safety-netting sentence and should be REMOVED from the entity list
        entirely -- caller must filter it out, it must not reach Neo4j.
        ``"hypothetical"`` if the entity is a conditional clinical plan
        (recommendation language) that should be kept for human review.
        ``"possible"`` if hedged diagnostic language applies.
        ``None`` if no scope-guard rule fires.
    """
    if entity_assertion not in ("present", ""):
        return None

    label = f"{entity_text!r} [{entity_semantic_tag}]" if entity_text else entity_semantic_tag

    if is_safety_netting_sentence(sentence_text):
        logger.info(
            "scope_guard: %s -> SUPPRESSED (safety-netting, not a clinical entity) | sent: %.120s",
            label,
            sentence_text,
        )
        return SUPPRESSED

    if has_recommendation_language(sentence_text):
        logger.info(
            "scope_guard: %s -> 'hypothetical' (conditional clinical plan) | sent: %.120s",
            label,
            sentence_text,
        )
        return "hypothetical"

    tag = (entity_semantic_tag or "").lower().replace("_", " ")
    if tag == "disorder" and has_hedged_diagnosis(sentence_text):
        logger.info(
            "scope_guard: %s -> 'possible' (hedged diagnosis) | sent: %.120s",
            label,
            sentence_text,
        )
        return "possible"

    return None
