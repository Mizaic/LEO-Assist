"""Canonical JSON output schema for the verification prompt (v1).

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")
"""

VERIFICATION_OUTPUT_SCHEMA: dict = {
    "description": "Return JSON only — no markdown.",
    "type": "object",
    "required": ["is_accurate", "confidence", "issues"],
    "properties": {
        "is_accurate": {
            "type": "boolean",
            "description": (
                "True when the extraction is clinically acceptable overall. "
                "Set false only for material errors, not stylistic preferences."
            ),
        },
        "confidence": {
            "type": "number",
            "description": "Overall confidence from 0.0 to 1.0.",
        },
        "issues": {
            "type": "array",
            "description": "Material issues only. Empty when is_accurate is true.",
            "items": {"type": "string"},
        },
        "corrections": {
            "type": "array",
            "description": "Optional structured fixes for specific entities.",
            "items": {
                "type": "object",
                "required": ["entity_index"],
                "properties": {
                    "entity_index": {
                        "type": "integer",
                        "description": "Index of the entity in the input array (0-based).",
                    },
                    "drop": {
                        "type": "boolean",
                        "description": "True when the entity should be removed entirely.",
                    },
                    "corrected_label": {
                        "type": "string",
                        "description": "Corrected clinical label if materially wrong.",
                    },
                    "corrected_lookup_term": {
                        "type": "string",
                        "description": "Corrected lookup term if materially needed.",
                    },
                    "corrected_assertion": {
                        "type": "string",
                        "description": "Corrected assertion if materially wrong.",
                    },
                },
            },
        },
    },
}
