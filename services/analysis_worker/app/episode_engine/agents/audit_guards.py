"""Always-keep guards for the Episode Engine Audit Relevance Filter.

Pure function. No LLM. No I/O.

The Audit Relevance Filter (DI-LEO-AI-524) reduces the milestone-extractor
input from "every encounter in the candidate window" to "encounters that
look pathway-relevant". Most of that is done by a cheap Haiku triage call,
but a small set of encounters MUST be kept regardless of any LLM decision:

  1. Cancer-coded SNOMED edges in the knowledge graph -- the structured
     data already says this encounter belongs to the pathway.
  2. Anchor encounters tagged by the segmenter for this window in any
     anchor role (referral, first_seen, diagnosis_confirmed,
     treatment_started, treatment_completed, benign_closure,
     first_presentation, place_of_first_presentation, outcome_letter).
     The segmenter has already classified these as pathway-relevant; the
     LLM triage SHALL NOT be allowed to drop them.
  3. Encounters already flagged by the deterministic safety-netting or
     disruption hint detectors.

Guard decisions are FINAL. The LLM cannot override them. See R-LEO-AI-512
for why this matters: a free-text-only safety-netting note that the
deterministic hint detector misses still has to be picked up by the LLM,
but a structured cancer-coded encounter must never be lost to a wrong LLM
"drop" decision.

The guards return plain English reason strings (reading age 9-11) so the
EoC audit trace can be reviewed by a clinician without developer help.
"""

from __future__ import annotations

from typing import Iterable, Mapping


# Plain-English reason strings. Reading age 9-11. No clinical jargon.
_REASON_CANCER_CODED = "Cancer-coded by SNOMED in the patient record"
_REASON_HINT_FLAGGED = "Safety-netting or delay hint matched in the text"
_REASON_ANCHOR_PREFIX = "Segmenter anchor: "

# Anchor roles the segmenter can tag on an encounter for a window.
# Any tag in this set guarantees the encounter is kept.
_ANCHOR_ROLES: frozenset[str] = frozenset(
    {
        "referral",
        "first_seen",
        "diagnosis_confirmed",
        "treatment_started",
        "treatment_completed",
        "benign_closure",
        "first_presentation",
        "place_of_first_presentation",
        "outcome_letter",
    }
)


def apply_guards(
    encounters: Iterable[Mapping[str, object]],
    segmenter_anchors: Mapping[str, Iterable[str]] | None,
    cancer_coded_encounter_ids: Iterable[str] | None,
    hint_flagged_encounter_ids: Iterable[str] | None,
) -> dict[str, str]:
    """Return ``{encounter_id: guard_reason}`` for every guard-kept encounter.

    Inputs are kept loose so the caller can hand in dicts straight from
    Neo4j rows or Pydantic ``model_dump`` payloads. The function never
    raises on a missing field; it simply does not add a guard for an
    encounter it cannot identify.

    ``segmenter_anchors`` maps ``encounter_id -> list of anchor role
    tags`` for this window. Any tag listed in ``_ANCHOR_ROLES`` triggers
    a guard with reason "Segmenter anchor: <role>".
    """

    cancer_set = {str(e) for e in (cancer_coded_encounter_ids or []) if e}
    hint_set = {str(e) for e in (hint_flagged_encounter_ids or []) if e}
    anchors = {
        str(eid): list(tags or [])
        for eid, tags in (segmenter_anchors or {}).items()
        if eid
    }
    in_window = {str((e or {}).get("encounter_id") or "") for e in encounters}
    in_window.discard("")

    reasons: dict[str, str] = {}
    for eid in sorted(in_window):
        anchor = _first_anchor_role(anchors.get(eid, []))
        if anchor is not None:
            reasons[eid] = _REASON_ANCHOR_PREFIX + anchor
            continue
        if eid in cancer_set:
            reasons[eid] = _REASON_CANCER_CODED
            continue
        if eid in hint_set:
            reasons[eid] = _REASON_HINT_FLAGGED
    return reasons


def _first_anchor_role(tags: Iterable[str]) -> str | None:
    """Return the first anchor role in ``tags`` or None."""
    for tag in tags:
        if tag in _ANCHOR_ROLES:
            return tag
    return None
