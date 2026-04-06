"""Canonical JSON output schema for the extraction prompt.

This is seeded into Neo4j as the ``outputSchema`` field of the
'extraction' PromptConfig node.  The extractor assembles the final
system prompt as:  instructions + format_block(outputSchema) + examples.

The schema serves two purposes:
1. Runtime  — appended to the system prompt so the LLM knows exactly
   what JSON structure to produce.
2. No-code builder — parsed by the pipeline canvas to understand what
   the extraction step emits (field names, types, enum values).
"""

EXTRACTION_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON — no explanation, no markdown, no preamble.",
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "description": "One entry per extracted clinical entity.",
            "items": {
                "type": "object",
                "required": ["sentence_id", "text", "lookup_term", "semantic_tag", "assertion"],
                "properties": {
                    "sentence_id": {
                        "type": "string",
                        "description": "ID of the sentence this entity came from, e.g. 's0'.",
                    },
                    "text": {
                        "type": "string",
                        "description": (
                            "Exact surface form from the sentence. "
                            "For observable entities: the CLINICAL PARAMETER NAME only "
                            "(strip value, unit, reference range, and interpretation suffix)."
                        ),
                    },
                    "lookup_term": {
                        "type": "string",
                        "description": (
                            "Standard clinical term for SNOMED CT lookup. "
                            "Expand abbreviations, use generic drug names, strip Read codes."
                        ),
                    },
                    "semantic_tag": {
                        "type": "string",
                        "description": (
                            "SNOMED CT semantic tag classifying the type of clinical concept. "
                            "Use 'staging scale' for cancer/tumour staging values (e.g. T2N1M0, "
                            "Stage III). Use 'observable entity' for measurable parameters "
                            "(labs, vitals, scores)."
                        ),
                        "enum": [
                            "disorder",
                            "finding",
                            "procedure",
                            "substance",
                            "product",
                            "observable entity",
                            "situation",
                            "regime/therapy",
                            "staging scale",
                        ],
                    },
                    "assertion": {
                        "type": "string",
                        "description": (
                            "Clinical assertion status of the entity in this sentence. "
                            "Use 'present' for confirmed active conditions. "
                            "Use 'historical' for past conditions. "
                            "Use 'absent'/'refuted' for negated conditions. "
                            "Use 'possible' for uncertain/provisional. "
                            "Use 'family' for family history. "
                            "Use 'declined' when patient refused (e.g. 'patient declined statin'). "
                            "Use 'cancelled' when a planned item was stopped or not done."
                        ),
                        "enum": [
                            "present",
                            "absent",
                            "refuted",
                            "possible",
                            "historical",
                            "planned",
                            "hypothetical",
                            "family",
                            "declined",
                            "cancelled",
                        ],
                    },
                    "value": {
                        "type": ["string", "null"],
                        "description": (
                            "Numeric value for observable entities and staging scales "
                            "(e.g. '145/69', '7.2', 'T2N1M0'). Null otherwise."
                        ),
                    },
                    "unit": {
                        "type": ["string", "null"],
                        "description": "Unit of measurement (e.g. 'mmHg', 'mmol/L', 'kg'). Null otherwise.",
                    },
                    "reference_range": {
                        "type": ["string", "null"],
                        "description": "Reference range if stated (e.g. '130-180', '3.5-5.0'). Null otherwise.",
                    },
                },
            },
        }
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the output schema as a prompt section to append to system instructions.

    Only emits the structural constraints (field names, types, enum values).
    Examples are kept in the separate few-shot library and appended independently.
    """
    import json

    lines = ["## Output Format", ""]

    if schema.get("description"):
        lines.append(schema["description"])
        lines.append("")

    # Discover the top-level array name and its item properties
    props = schema.get("properties", {})
    array_name = next(iter(props), "terms")
    items_props: dict = (
        props.get(array_name, {}).get("items", {}).get("properties", {})
    )
    required: list[str] = (
        props.get(array_name, {}).get("items", {}).get("required", [])
    )

    if items_props:
        lines.append(f'Return a JSON object with a single key "{array_name}" whose value is an array.')
        lines.append(f'Each item in the array must be an object with these fields:')
        lines.append("")
        for field, defn in items_props.items():
            raw_type = defn.get("type", "string")
            base_type = (
                next((t for t in raw_type if t != "null"), "string")
                if isinstance(raw_type, list)
                else raw_type
            )
            nullable = isinstance(raw_type, list) and "null" in raw_type
            req_marker = " (required)" if field in required else " (optional, null if not present)"
            desc = defn.get("description", "")

            if "enum" in defn:
                enum_vals = [v for v in defn["enum"] if v is not None]
                allowed = ", ".join(f'"{v}"' for v in enum_vals)
                desc_suffix = f" {desc}" if desc else ""
                lines.append(f'  - **{field}**{req_marker}: one of {allowed}.{desc_suffix}')
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f'  - **{field}**{req_marker}: {type_label}. {desc}')

        lines.append("")
        lines.append(f'Return {{"{array_name}": []}} when no codable entities exist.')

    return "\n".join(lines)
