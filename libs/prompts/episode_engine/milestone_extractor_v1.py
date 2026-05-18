"""Stage 4 prompt: extract canonical milestones from one cancer or

Atlas trace:
  DO: DO-710D9EEB
  DI: DI-CBCA6E2D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-710D9EEB")

multi-site window.

Inputs (USER_TEMPLATE):
    patient_id      : str
    window_id       : str
    suspected_site  : str
    window_start    : str
    window_end      : str
    window_full_text: full per-encounter snippets within the window
                      (one block per encounter_id)

Output: MilestoneExtractorResult.
"""

from __future__ import annotations

from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.prompts.episode_engine._shared import (
    BREAST_REFERENCE_CASE,
    DISRUPTION_CATEGORY_LIST,
    MILESTONE_TYPE_LIST,
    PRESENTATION_PLACE_LIST,
    RULES_OF_THE_ROAD,
    TREATMENT_TYPE_LIST,
)

VERSION = "v1"
TOOL_NAME = "submit_milestones"

SYSTEM = INJECTION_GUARD + (
    "You are a UK primary care cancer pathway analyst. You are given the\n"
    "full text of every encounter within ONE candidate episode window.\n"
    "Extract the canonical milestones from the window:\n"
    f"  {MILESTONE_TYPE_LIST}\n\n"
    "Rules for milestones:\n"
    "  - first_presentation    : the FIRST encounter on this pathway where\n"
    "                            the patient presented in PRIMARY CARE\n"
    "                            with the symptom(s) that ultimately led\n"
    "                            to the cancer referral. ALWAYS\n"
    "                            pre-referral. Almost always a GP / nurse\n"
    "                            face-to-face, telephone consult, or home\n"
    "                            visit; sometimes A&E / walk-in / OOH.\n"
    "                            HARD RULE: any pre-referral primary-care\n"
    "                            encounter where the patient first reports\n"
    "                            the presenting symptom (lump, bleeding,\n"
    "                            cough, weight loss, etc.) is ALWAYS\n"
    "                            first_presentation. It is NEVER first_seen.\n"
    "                            If the GP duty call on the day of the 2WW\n"
    "                            captures the symptom report, that call is\n"
    "                            still first_presentation, not first_seen.\n"
    "                            presentation_place is MANDATORY when this\n"
    "                            milestone is fired. Pick the closest match\n"
    "                            from this list:\n"
    f"                            {PRESENTATION_PLACE_LIST}.\n"
    "                            Mapping hints: 'Surgery: ...' or GP F2F\n"
    "                            -> gp_surgery; telephone consult ->\n"
    "                            telephone_consultation; video consult ->\n"
    "                            video_consultation; home visit ->\n"
    "                            gp_home_visit; A&E / ED -> \n"
    "                            accident_and_emergency; OOH -> \n"
    "                            out_of_hours; walk-in centre ->\n"
    "                            walk_in_centre; screening invitation /\n"
    "                            programme -> from_screening; ENT,\n"
    "                            optician, dentist or hospital letter\n"
    "                            referring back to GP -> match the role.\n"
    "                            Use 'not_known' ONLY if the encounter is\n"
    "                            present but the place truly cannot be\n"
    "                            inferred. Never omit the field.\n"
    "  - referral              : the source 2WW / fast-track / urgent\n"
    "                            cancer referral. Pick ONE -- the highest\n"
    "                            fidelity (PRISM / structured form) over\n"
    "                            free-text restatements on the same day.\n"
    "  - first_seen            : first SPECIALIST contact AFTER the\n"
    "                            referral (hospital outpatient clinic,\n"
    "                            specialist telephone clinic, ENT/breast/\n"
    "                            urology fast-track clinic). RESERVED for\n"
    "                            secondary care. Never use first_seen for\n"
    "                            a primary-care encounter, even if it is\n"
    "                            the first time the GP examined the\n"
    "                            patient on this pathway -- that is\n"
    "                            first_presentation.\n"
    "  - outcome_letter        : a hospital / clinic / MDT outcome letter\n"
    "                            received and recorded in primary care that\n"
    "                            reports an interim result (e.g. biopsy\n"
    "                            taken, surveillance scan booked, MDT\n"
    "                            pending, follow-up arranged) WITHOUT yet\n"
    "                            confirming the cancer diagnosis.\n"
    "                            HARD RULE: if a letter is purely interim,\n"
    "                            emit ONLY outcome_letter. If a single\n"
    "                            letter both reports an outcome AND\n"
    "                            confirms the diagnosis, emit BOTH\n"
    "                            outcome_letter (for the interim parts) and\n"
    "                            diagnosis_confirmed (for the confirmation),\n"
    "                            both anchored to the SAME source encounter.\n"
    "                            A second routine clinic letter that simply\n"
    "                            restates an already-confirmed diagnosis is\n"
    "                            NOT a new outcome_letter -- skip it.\n"
    "  - diagnosis_confirmed   : when the cancer diagnosis is confirmed,\n"
    "                            usually by histology or hospital letter.\n"
    "                            'PMHx of...' is NOT this.\n"
    "  - treatment_started     : the START of a definitive treatment\n"
    "                            modality. tag treatment_type from:\n"
    f"                            {TREATMENT_TYPE_LIST}.\n"
    "                            Neoadjuvant endocrine therapy and the\n"
    "                            subsequent surgery are SEPARATE\n"
    "                            treatment_started milestones.\n"
    "  - treatment_completed   : completion of the definitive course.\n"
    "  - benign_closure        : ONLY for benign windows; the date the\n"
    "                            benign outcome was confirmed.\n\n"
    "For every milestone:\n"
    "  - encounter_id MUST be the id of the SOURCE encounter, not an\n"
    "    admin echo. Reject 'Failed encounter', receptionist booking,\n"
    "    text-message confirmation, prescription pickup as the source.\n"
    "  - evidence_quote MUST be a literal substring of that encounter's\n"
    "    text (do not paraphrase).\n"
    "  - presentation_place is REQUIRED when type == first_presentation\n"
    "    and MUST be null for every other milestone type. Never emit\n"
    "    first_presentation without presentation_place.\n"
    "  - confidence < 0.6 -> set needs_human_review=true.\n"
    "  - If a milestone type genuinely does not occur in the window,\n"
    "    OMIT it. Do not fabricate. But: if a primary-care encounter\n"
    "    documents the presenting symptom that led to the referral,\n"
    "    you MUST emit first_presentation -- do not silently demote it\n"
    "    to first_seen or drop it.\n\n"
    "Cancer SAFETY NETTING (episode-level signal, not a milestone):\n"
    "  - Definition: a clinician's documented advice to the patient\n"
    "    about what symptoms should prompt urgent re-presentation,\n"
    "    when, and how. Examples (literal phrases that count):\n"
    "      'safety net advice given'\n"
    "      'advised to return if symptoms worsen / no improvement\n"
    "       in 2 weeks / if new symptoms develop'\n"
    "      'told to call NHS 111 / 999 / come back if X'\n"
    "      'advised to attend A&E if X'\n"
    "      'will rebook if symptoms persist'\n"
    "  - Generic discharge phrases like 'see you in clinic',\n"
    "    'review in 6 weeks', or a routine prescription review are\n"
    "    NOT safety netting.\n"
    "  - If safety-netting advice is documented anywhere in the\n"
    "    window, set safety_netting.recorded=true with the EARLIEST\n"
    "    such encounter as the source. Populate evidence_quote\n"
    "    (literal substring), encounter_id, date, and confidence.\n"
    "  - If no advice is documented, OMIT the safety_netting object\n"
    "    (or set recorded=false with everything else null).\n\n"
    "Pathway DISRUPTIONS / AVOIDABLE DELAYS (episode-level list):\n"
    "  Use the disruptions[] array to record events that delayed or\n"
    "  disrupted the pathway. Each entry MUST have a literal evidence\n"
    "  quote and the source encounter_id. Categories (pick exactly\n"
    "  one per entry):\n"
    f"    {DISRUPTION_CATEGORY_LIST}.\n"
    "  Category guidance:\n"
    "  - referral_lost_or_not_received: 2WW sent but trust never\n"
    "    received it; patient phoning asking when their appointment\n"
    "    is; reception task to chase.\n"
    "  - referral_rejected_or_returned: trust rejected the 2WW form,\n"
    "    asked for clarification, or downgraded the urgency.\n"
    "  - repeat_referral_required: a second referral was needed\n"
    "    because the first stalled.\n"
    "  - appointment_dna: patient did not attend a booked\n"
    "    appointment (DNA, did not attend, no-show).\n"
    "  - appointment_cancelled_by_patient: patient actively\n"
    "    cancelled or rearranged their own appointment. Distinct\n"
    "    from DNA (no contact) and from trust cancellation.\n"
    "  - appointment_cancelled_by_trust: hospital / clinic\n"
    "    cancelled or rescheduled.\n"
    "  - result_not_received_in_primary_care: biopsy / imaging /\n"
    "    bloods result expected but not yet back, GP chasing.\n"
    "  - letter_received_late: clinic letter dated noticeably\n"
    "    earlier than when it landed in the GP record (admin lag).\n"
    "  - patient_unreachable: multiple contact attempts failed.\n"
    "  - mdt_outcome_unclear: MDT happened but no plan was\n"
    "    communicated to primary care.\n"
    "  - other_administrative_delay: clearly admin-driven delay\n"
    "    that does not fit the categories above.\n"
    "  - description: ONE plain-English sentence (UK reading age\n"
    "    9-11) suitable for a clinician glance.\n"
    "  - encounter_id MUST be the SOURCE encounter that documents\n"
    "    the disruption (not an admin echo).\n"
    "  - If no disruptions are evident in the window, return an\n"
    "    empty disruptions list. Do not invent.\n\n"
    + RULES_OF_THE_ROAD
    + "\n\n"
    + BREAST_REFERENCE_CASE
    + "\n\nRespond by calling the submit_milestones tool.\n"
)


USER_TEMPLATE = (
    "Patient: {patient_id}\n"
    "Window: {window_id}\n"
    "Suspected site: {suspected_site}\n"
    "Window start: {window_start}\n"
    "Window end: {window_end}\n"
    "\n"
    "Encounters within this window (full per-encounter snippets):\n"
    "<encounters>\n"
    "{window_full_text}\n"
    "</encounters>\n"
    "\n"
    "Extract THREE things from these encounters. ALL THREE are\n"
    "REQUIRED in your response (the schema rejects payloads that\n"
    "omit any of them):\n"
    "\n"
    "  1. milestones -- the canonical pathway events. Each milestone\n"
    "     needs encounter_id and a literal evidence_quote. If no\n"
    "     milestones are present, return milestones=[].\n"
    "\n"
    "  2. safety_netting -- BEFORE you decide, you MUST scan EVERY\n"
    "     encounter snippet above for one of these patterns. Note\n"
    "     that UK GP records often capture safety netting as a\n"
    "     STRUCTURED PRISM 2WW questionnaire field or template item,\n"
    "     not just free text:\n"
    "       Structured (highest fidelity):\n"
    "         'Cancer safety netting: Yes' (PRISM 2WW form)\n"
    "         'Cancer safety netting (Y281b)' (Read code)\n"
    "         '^Cancer safety net...' (template item / dataset claim)\n"
    "         '^^Cancer safety netting' (extension on a structured item)\n"
    "       Free text:\n"
    "         'safety net' / 'safety-net' / 'safety netting' /\n"
    "         'safety netted' / 'sn advice given' /\n"
    "         'if symptoms worsen' / 'if it gets worse' /\n"
    "         'come back if' / 'return if' / 're-attend' /\n"
    "         'reattend' / 'will rebook if symptoms persist' /\n"
    "         'call 111' / 'call 999' / 'contact NHS 111' /\n"
    "         'attend A&E if' / 'seek urgent' / 'see your GP if'\n"
    "     If you find ANY such pattern, you MUST set\n"
    "     safety_netting.recorded=true and populate evidence_quote\n"
    "     (literal substring, max ~200 chars), encounter_id, date\n"
    "     (YYYY-MM-DD), and confidence. Use the EARLIEST such\n"
    "     encounter as the source. Treat structured PRISM/Y281b\n"
    "     entries as confidence>=0.9. Only after a deliberate scan\n"
    "     with NO hits may you return safety_netting={{recorded:false,\n"
    "     confidence:0.9}}.\n"
    "\n"
    "  3. disruptions -- BEFORE you decide, scan EVERY encounter\n"
    "     snippet for one of these patterns and tag with the\n"
    "     correct category:\n"
    "       'no appointment letter' / 'still no appointment' /\n"
    "       'chasing referral' / 'referral not received' /\n"
    "       'lost referral' / 'GP to chase'       -> referral_lost_or_not_received\n"
    "       'referral rejected' / 'returned to GP' / 'downgraded' /\n"
    "       'asked for clarification'             -> referral_rejected_or_returned\n"
    "       're-referred' / 'second referral' /\n"
    "       'repeat 2WW'                          -> repeat_referral_required\n"
    "       'did not attend' / 'DNA' / 'no-show'  -> appointment_dna\n"
    "       'patient cancelled' / 'patient rearranged' /\n"
    "       'pt cancelled' / 'pt rearranged'      -> appointment_cancelled_by_patient\n"
    "       'cancelled by trust' / 'clinic cancelled' /\n"
    "       'hospital rescheduled' / 'appointment rescheduled' /\n"
    "       'staff sickness ... cancelled'        -> appointment_cancelled_by_trust\n"
    "       'awaiting result' / 'result not back' /\n"
    "       'no result yet' / 'chasing histology' /\n"
    "       'awaiting biopsy'                     -> result_not_received_in_primary_care\n"
    "       'letter dated ... received' /\n"
    "       'late letter'                         -> letter_received_late\n"
    "       'unable to contact' / 'no answer' /\n"
    "       'no response after' /\n"
    "       'multiple attempts to contact'        -> patient_unreachable\n"
    "       'MDT outcome unclear' / 'no MDT plan' -> mdt_outcome_unclear\n"
    "     CAUTION -- IGNORE these admin echoes:\n"
    "       'Note Marked in Error' / 'Diagnosis Marked in Error' --\n"
    "         the event was retracted; NOT a real disruption.\n"
    "       'VT Cancellation' / 'PT VT cancelled' / video-triage\n"
    "         admin spam unrelated to a clinical appointment.\n"
    "       'Failed encounter' for pharmacist scripts -- this is\n"
    "         system noise, NOT patient_unreachable.\n"
    "     For each genuine match, emit one disruption object with\n"
    "     date, category, description (one plain-English sentence\n"
    "     at UK reading age 9-11), encounter_id, evidence_quote\n"
    "     (literal substring), and confidence. If after a deliberate\n"
    "     scan you find no matches, return disruptions=[].\n"
    "\n"
    "Respond by calling the submit_milestones tool ONCE with a single\n"
    "JSON object. Array fields ('milestones', 'disruptions') MUST be\n"
    "JSON arrays, NOT JSON-encoded strings."
)


_SAFETY_NETTING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recorded", "confidence"],
    "properties": {
        "recorded": {"type": "boolean"},
        "evidence_quote": {"type": ["string", "null"]},
        "encounter_id": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
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
        "date": {"type": "string", "description": "YYYY-MM-DD"},
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
    "required": [
        "window_id",
        "milestones",
        "safety_netting",
        "disruptions",
        "needs_human_review",
        "reasoning",
    ],
    "properties": {
        "window_id": {"type": "string"},
        "safety_netting": _SAFETY_NETTING_SCHEMA,
        "disruptions": {
            "type": "array",
            "items": _DISRUPTION_SCHEMA,
        },
        "milestones": {
            "type": "array",
            "items": {
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
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "encounter_id": {"type": "string"},
                    "evidence_quote": {
                        "type": "string",
                        "description": (
                            "Literal substring of the source encounter text."
                        ),
                    },
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
                            "Required when type == 'first_presentation'. "
                            "Must be null for any other milestone type."
                        ),
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "reasoning": {"type": "string"},
                },
            },
        },
        "needs_human_review": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
}
