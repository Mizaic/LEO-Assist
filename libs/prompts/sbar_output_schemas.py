"""JSON schemas for the three SBAR prompts.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

These are stored as PromptConfig.outputSchema in Neo4j (seeded from
``scripts/seed_prompt_configs.py``) so they can be edited at runtime.
"""

from __future__ import annotations

SBAR_SITUATION_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["situation_markdown"],
    "properties": {
        "situation_markdown": {"type": "string", "minLength": 1},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source_type", "source_id"],
                "properties": {
                    "source_type": {"type": "string"},
                    "source_id": {"type": "string"},
                    "snippet": {"type": "string"},
                },
            },
        },
        "missing": {"type": "array", "items": {"type": "string"}},
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["description"],
                "properties": {
                    "description": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


SBAR_BACKGROUND_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["background_markdown"],
    "properties": {
        "background_markdown": {"type": "string", "minLength": 1},
        "citations": SBAR_SITUATION_OUTPUT_SCHEMA["properties"]["citations"],
        "missing": SBAR_SITUATION_OUTPUT_SCHEMA["properties"]["missing"],
        "conflicts": SBAR_SITUATION_OUTPUT_SCHEMA["properties"]["conflicts"],
    },
}


SBAR_RECALL_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["missing"],
    "properties": {
        "reason_text": {"type": "string"},
        "chunk_id": {"type": "string"},
        "missing": {"type": "array", "items": {"type": "string"}},
        "complete": {"type": "boolean"},
    },
}


SBAR_RECOMMENDATION_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recommendation_markdown", "actions"],
    "properties": {
        "recommendation_markdown": {"type": "string", "minLength": 1},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["action", "priority"],
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string", "minLength": 1},
                    "priority": {
                        "type": "string",
                        "enum": ["immediate", "2ww", "urgent", "routine"],
                    },
                    "due_days": {"type": ["integer", "null"], "minimum": 0},
                    "rationale": {"type": "string"},
                    "rule_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "citations": SBAR_SITUATION_OUTPUT_SCHEMA["properties"]["citations"],
        "missing": SBAR_SITUATION_OUTPUT_SCHEMA["properties"]["missing"],
        "conflicts": SBAR_SITUATION_OUTPUT_SCHEMA["properties"]["conflicts"],
    },
}
