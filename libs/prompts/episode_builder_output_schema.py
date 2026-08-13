"""Canonical JSON output schemas for the episode builder and consolidation prompts.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Two schemas live here:
  EPISODE_BUILDER_OUTPUT_SCHEMA      -- result from episode_builder_system / episode_builder_task
  EPISODE_CONSOLIDATION_OUTPUT_SCHEMA -- result from episode_consolidation_system / episode_consolidation_task

Both share the same format_output_schema_block() renderer (flat-object style).
"""

EPISODE_BUILDER_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY a single valid JSON object -- no markdown, no preamble.",
    "type": "object",
    "required": [
        "status",
        "confidence",
        "reasoning",
        "diagnosis_date",
        "treatment_date",
    ],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["confirmed", "excluded", "inconclusive"],
            "description": (
                "confirmed = cancer diagnosis confirmed and treatment pathway clear; "
                "excluded = cancer ruled out with reasonable certainty; "
                "inconclusive = insufficient evidence to determine outcome."
            ),
        },
        "confidence": {
            "type": "integer",
            "description": "Confidence score 0-100 reflecting strength of evidence.",
        },
        "reasoning": {
            "type": "string",
            "description": "Short explanation of the decision and evidence used.",
        },
        "diagnosis_date": {
            "type": ["string", "null"],
            "description": "Date cancer was confirmed (YYYY-MM-DD), or null if not confirmed.",
        },
        "treatment_date": {
            "type": ["string", "null"],
            "description": "Date first treatment started (YYYY-MM-DD), or null if not applicable.",
        },
    },
}

EPISODE_CONSOLIDATION_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY a single valid JSON object -- no markdown, no preamble.",
    "type": "object",
    "required": [
        "should_merge",
        "primary_episode_id",
        "reasoning",
        "merged_cancer_type",
    ],
    "properties": {
        "should_merge": {
            "type": "boolean",
            "description": "True if the episodes represent a single cancer journey; false if they are genuinely separate.",
        },
        "primary_episode_id": {
            "type": "string",
            "description": (
                "Episode ID of the episode that represents the actual cancer site. "
                "Do NOT default to the highest-confidence episode; choose based on clinical evidence."
            ),
        },
        "reasoning": {
            "type": "string",
            "description": "Explanation including which cancer site the evidence points to and why.",
        },
        "merged_cancer_type": {
            "type": ["string", "null"],
            "description": "The actual cancer type (e.g. 'renal', 'colorectal') if merging, or null otherwise.",
        },
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render an episode builder output schema as a prompt section (flat-object style)."""
    lines = ["## Output Format", ""]

    if schema.get("description"):
        lines.append(schema["description"])
        lines.append("")

    props = schema.get("properties", {})
    required = schema.get("required", [])

    if props:
        lines.append("Return a JSON object with these fields:")
        lines.append("")
        for field, defn in props.items():
            req_marker = (
                " (required)"
                if field in required
                else " (optional, null if not present)"
            )
            desc = defn.get("description", "")
            raw_type = defn.get("type", "string")
            base_type = (
                next((t for t in raw_type if t != "null"), "string")
                if isinstance(raw_type, list)
                else raw_type
            )
            nullable = isinstance(raw_type, list) and "null" in raw_type
            if "enum" in defn:
                allowed = ", ".join(f'"{v}"' for v in defn["enum"])
                lines.append(f"  - **{field}**{req_marker}: one of {allowed}. {desc}")
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f"  - **{field}**{req_marker}: {type_label}. {desc}")

    return "\n".join(lines)
