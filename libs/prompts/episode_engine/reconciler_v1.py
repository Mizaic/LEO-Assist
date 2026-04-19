"""Stage 5 prompt: reconcile candidate windows into final episodes.

Inputs (USER_TEMPLATE):
    patient_id        : str
    candidate_payload : JSON-encoded list of {window_id, episode_type,
                        confidence, suspected_site, window_start,
                        window_end, milestones[]}

Output: ReconcilerResult.
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.prompts.episode_engine._shared import (
    BREAST_REFERENCE_CASE,
    DISRUPTION_CATEGORY_LIST,
    EPISODE_TYPE_LIST,
    MILESTONE_TYPE_LIST,
    PRESENTATION_PLACE_LIST,
    RULES_OF_THE_ROAD,
)

VERSION = "v1"
TOOL_NAME = "submit_episodes"

SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care cancer pathway analyst. The earlier\n"
    "stages have produced one classification + milestone set per\n"
    "candidate window. Your job is to RECONCILE these into final\n"
    "episodes:\n\n"
    "  - MERGE multi-site windows that share a single confirmed primary\n"
    "    diagnosis (e.g. 2WW breast + 2WW ovarian where the histology\n"
    "    confirms breast only -> ONE breast episode, ovarian referral\n"
    "    becomes a referral milestone within it).\n"
    "  - SPLIT a window if it spans two distinct cancers years apart that\n"
    "    the segmenter incorrectly merged.\n"
    "  - DROP windows classified non_cancer or uncertain with low\n"
    "    confidence; they will not become episodes.\n"
    "  - PRESERVE windows of type 'benign' as benign episodes (no cancer\n"
    "    flag, only benign_closure milestone).\n"
    "  - PRESERVE separate cancer episodes that are years apart for the\n"
    "    same site (e.g. recurrence) -- never merge them.\n\n"
    "For each reconciled episode:\n"
    "  - episode_id is a stable string in this call ('e1', 'e2', ...);\n"
    "    the writer maps it to a deterministic graph id.\n"
    "  - episode_type from: " + EPISODE_TYPE_LIST + ".\n"
    "  - milestone type from: " + MILESTONE_TYPE_LIST + ".\n"
    "  - milestones: union of merged-window milestones, deduplicated by\n"
    "    (type, encounter_id). Keep highest-confidence on conflict.\n"
    "  - PRESERVE the milestone TYPE from the upstream extractor. Do NOT\n"
    "    re-cast first_presentation as first_seen, do NOT collapse\n"
    "    outcome_letter into diagnosis_confirmed, and do NOT drop\n"
    "    first_presentation or outcome_letter when reconciling. They are\n"
    "    distinct events on the pathway.\n"
    "  - presentation_place MUST be carried through verbatim for every\n"
    "    first_presentation milestone. Pick from:\n"
    "    " + PRESENTATION_PLACE_LIST + ".\n"
    "    Set null for every other milestone type. If an upstream\n"
    "    first_presentation is missing presentation_place, infer the\n"
    "    closest match from the encounter text rather than dropping it.\n"
    "  - merged_from: list the input window_ids you merged.\n"
    "  - confidence: overall episode confidence.\n"
    "  - needs_human_review: true if any milestone has confidence<0.6,\n"
    "    or if the merge required guesswork.\n\n"
    "Episode-level signals to PRESERVE through reconciliation\n"
    "(BOTH fields are REQUIRED in your output for every episode --\n"
    "the schema rejects payloads that omit them):\n"
    "  - safety_netting: keep the EARLIEST documented advice across\n"
    "    the merged windows. Carry recorded, evidence_quote,\n"
    "    encounter_id, date and confidence VERBATIM. If NONE of the\n"
    "    merged windows recorded safety netting, emit\n"
    "    safety_netting={recorded:false, evidence_quote:null,\n"
    "    encounter_id:null, date:null, confidence:0.9}.\n"
    "  - disruptions: take the UNION of disruption entries across\n"
    "    merged windows, deduplicated by (date, category,\n"
    "    encounter_id). Do NOT invent new disruptions. Do NOT\n"
    "    re-categorise. Categories are: " + DISRUPTION_CATEGORY_LIST + ".\n"
    "    If no merged window recorded any disruptions, emit\n"
    "    disruptions=[].\n"
    + RULES_OF_THE_ROAD
    + "\n\n"
    + BREAST_REFERENCE_CASE
    + "\n\nRespond by calling the submit_episodes tool.\n"
)


USER_TEMPLATE = (
    "Patient: {patient_id}\n"
    "\n"
    "Candidate windows from earlier stages (JSON):\n"
    "<candidates>\n"
    "{candidate_payload}\n"
    "</candidates>\n"
    "\n"
    "Reconcile into final episodes now."
)


_MILESTONE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "type",
        "date",
        "encounter_id",
        "evidence_quote",
        "confidence",
        "reasoning",
    ],
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "first_presentation",
                "referral",
                "first_seen",
                "outcome_letter",
                "diagnosis_confirmed",
                "treatment_started",
                "treatment_completed",
                "benign_closure",
            ],
        },
        "date": {"type": "string"},
        "encounter_id": {"type": "string"},
        "evidence_quote": {"type": "string"},
        "treatment_type": {
            "type": ["string", "null"],
            "enum": [
                "surgery",
                "endocrine",
                "chemotherapy",
                "radiotherapy",
                "immunotherapy",
                "other",
                None,
            ],
        },
        "presentation_place": {
            "type": ["string", "null"],
            "enum": [
                "gp_surgery",
                "gp_home_visit",
                "other_primary_care",
                "hospital_outpatient",
                "hospital_inpatient",
                "accident_and_emergency",
                "walk_in_centre",
                "out_of_hours",
                "from_screening",
                "telephone_consultation",
                "email_consultation",
                "video_consultation",
                "dentist",
                "optometrist",
                "community_care_nurse",
                "other",
                "not_known",
                None,
            ],
            "description": (
                "Required when type == 'first_presentation'; null otherwise."
            ),
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasoning": {"type": "string"},
    },
}


_SAFETY_NETTING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recorded", "confidence"],
    "properties": {
        "recorded": {"type": "boolean"},
        "evidence_quote": {"type": ["string", "null"]},
        "encounter_id": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
}

_DISRUPTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "date",
        "category",
        "description",
        "encounter_id",
        "evidence_quote",
        "confidence",
    ],
    "properties": {
        "date": {"type": "string"},
        "category": {
            "type": "string",
            "enum": [
                "referral_lost_or_not_received",
                "referral_rejected_or_returned",
                "repeat_referral_required",
                "appointment_dna",
                "appointment_cancelled_by_patient",
                "appointment_cancelled_by_trust",
                "result_not_received_in_primary_care",
                "letter_received_late",
                "patient_unreachable",
                "mdt_outcome_unclear",
                "other_administrative_delay",
            ],
        },
        "description": {"type": "string"},
        "encounter_id": {"type": "string"},
        "evidence_quote": {"type": "string"},
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
}


SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["episodes", "notes"],
    "properties": {
        "episodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "episode_id",
                    "suspected_site",
                    "episode_type",
                    "window_start",
                    "milestones",
                    "safety_netting",
                    "disruptions",
                    "confidence",
                    "reasoning",
                    "needs_human_review",
                    "merged_from",
                ],
                "properties": {
                    "episode_id": {"type": "string"},
                    "suspected_site": {"type": "string"},
                    "episode_type": {
                        "type": "string",
                        "enum": [
                            "cancer",
                            "multi_site",
                            "benign",
                            "non_cancer",
                            "uncertain",
                        ],
                    },
                    "window_start": {"type": "string"},
                    "window_end": {"type": ["string", "null"]},
                    "milestones": {
                        "type": "array",
                        "items": _MILESTONE_SCHEMA,
                    },
                    "safety_netting": _SAFETY_NETTING_SCHEMA,
                    "disruptions": {
                        "type": "array",
                        "items": _DISRUPTION_SCHEMA,
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "reasoning": {"type": "string"},
                    "needs_human_review": {"type": "boolean"},
                    "merged_from": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "notes": {"type": "string"},
    },
}
