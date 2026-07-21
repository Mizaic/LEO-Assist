"""Prompts and tool configs for Validation Lab scenario brainstorm.

Atlas trace:
  DO: DO-A0ADDB38
  DI: DI-EB716E68
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")

Atlas: DI-EB716E68 / DO-A0ADDB38
"""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "v1.2"

SYSTEM_PROMPT = """\
You are the Validation Lab scenario assistant. You help a QA or clinical \
safety reviewer brainstorm synthetic test patients for the LEO Clinical \
Decision Support pipeline. This is TEST DATA only.

Each turn:
  1. Read the conversation, attached recommendations, and answers so far.
  2. If you need a real SNOMED code, call search_snomed. NEVER invent a \
concept_id -- only use ids returned by search_snomed.
  3. For lab-value triggers, search with semantic_tags including \
observable_entity, then put the result in observations[].
  4. If you need a guideline title, call search_guidelines.
  5. For understand/clarify, call gather_scenario_questions with 3-6 \
questions when anything is unclear. Use allow_multiple=true with a \
max_selections when the scenario has several independent trigger paths. \
Dedupe long disjunctive lists into clinical categories. You MAY skip \
clarification when the scenario is already clear.
  6. For propose_variants, call propose_variants with the number of \
trigger-positive variants requested in the user payload (default 3 per \
attached recommendation). Set targetRecId on every variant to the \
recommendation being tested. Exactly one trigger-positive variant per \
targetRecId must be recommended=true. At most 1 optional control overall \
(never recommended). When no recommendations are attached, propose at \
most 5 freeform variants. Equity values must come from the fixed \
taxonomy. When a recommendation uses inclusive or trans-inclusive \
language about reproductive organs, include at least one variant that \
exercises anatomy-conflict review (recorded patientSex one way with \
opposite-sex anatomy concepts in triggerConceptIds).

Catalog fields on every variant (required for the Lab patient list):
  - title: a short distinctive clinical name (e.g. "Raised CA125, Core20 \
decile 2"). NEVER use "Variant 1", "Variant 2", or similar placeholders.
  - summary: one plain-English sentence describing who the patient is and \
what triggers the rule (max ~160 characters). This is searchable.
  - tags: 3 to 6 short filter chips (e.g. "CA125", "2WW", "Core20", \
"trans-inclusive", guideline code). Prefer clinical keywords over ids.

Hard rules:
  - Never invent identifiers. Stay faithful to the reviewer request.
  - Referral text should read like a UK GP letter with concrete \
identity fields filled in (patient name, date of birth, GP or practice \
name). Do NOT leave unfilled bracket placeholders such as \
[Patient Name], [DOB], or [GP Name]. The Lab will synthesise a separate \
SOAP GP consultation encounter from the clinical content; do not put \
the letter greeting into a consultation note.
  - When blood results drive the referral (PSA, CA125, FBC, iron panel, \
lipids, HbA1c, U&E, etc.), put those values in observations[] and in \
the letter body so timing can reflect a short wait for results.
  - Write assistant replies in plain English (UK reading age 11-13).
"""

GATHER_SCENARIO_QUESTIONS_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "gather_scenario_questions",
        "description": (
            "Ask 3-6 multiple-choice questions to clarify the scenario. "
            "Skip this tool when you already have enough to propose variants."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "intent_summary": {"type": "string"},
                    "questions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "question": {"type": "string"},
                                "allowMultiple": {"type": "boolean"},
                                "maxSelections": {"type": "integer"},
                                "options": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "label": {"type": "string"},
                                            "recommended": {"type": "boolean"},
                                        },
                                        "required": [
                                            "id",
                                            "label",
                                            "recommended",
                                        ],
                                    },
                                },
                            },
                            "required": ["id", "question", "options"],
                        },
                    },
                },
                "required": ["intent_summary", "questions"],
            }
        },
    }
}

SEARCH_SNOMED_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "search_snomed",
        "description": (
            "Search SNOMED CT. Pass semantic_tags=['observable_entity'] "
            "for lab observables."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "semantic_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["query"],
            }
        },
    }
}

SEARCH_GUIDELINES_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "search_guidelines",
        "description": "Search loaded NICE guideline titles.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }
        },
    }
}

PROPOSE_VARIANTS_TOOL: dict[str, Any] = {
    "toolSpec": {
        "name": "propose_variants",
        "description": (
            "Propose trigger-positive ScenarioVariant objects for the "
            "attached recommendation(s) (see variants_requested in the "
            "user payload; default 3 per recommendation) plus at most 1 "
            "control when asked. Every variant MUST include title, "
            "summary, and tags for Lab list search/filter. "
            "expectedTrigger guesses are discarded by the router."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "variants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "variantId": {"type": "string"},
                                "targetRecId": {"type": "string"},
                                "title": {"type": "string"},
                                "label": {"type": "string"},
                                "summary": {"type": "string"},
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "rationale": {"type": "string"},
                                "recommended": {"type": "boolean"},
                                "isControl": {"type": "boolean"},
                                "referralText": {"type": "string"},
                                "patientName": {"type": "string"},
                                "patientAge": {"type": "string"},
                                "patientSex": {"type": "string"},
                                "pmh": {"type": "array"},
                                "observations": {"type": "array"},
                                "equity": {"type": "object"},
                                "triggerConceptIds": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "title",
                                "summary",
                                "tags",
                                "rationale",
                                "referralText",
                            ],
                        },
                    }
                },
                "required": ["variants"],
            }
        },
    }
}

UNDERSTAND_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        GATHER_SCENARIO_QUESTIONS_TOOL,
        SEARCH_SNOMED_TOOL,
        SEARCH_GUIDELINES_TOOL,
    ]
}

PROPOSE_TOOL_CONFIG: dict[str, Any] = {
    "tools": [
        SEARCH_SNOMED_TOOL,
        SEARCH_GUIDELINES_TOOL,
        PROPOSE_VARIANTS_TOOL,
    ]
}
