"""Canonical JSON output schema for the encounter_classify prompt.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Seeded into Neo4j as the ``outputSchema`` field of the
'encounter_classify' PromptConfig node (version 1).
"""

ENCOUNTER_CLASSIFY_OUTPUT_SCHEMA: dict = {
    "description": "Return ONLY valid JSON -- no explanation, no markdown, no preamble.",
    "type": "object",
    "required": [
        "content_type",
        "domains",
        "encounter_purpose",
        "key_clinical_signals",
        "expected_semantic_tags",
        "clinical_significance",
    ],
    "properties": {
        "content_type": {
            "type": "string",
            "enum": ["admin_only", "document_transfer", "clinical"],
            "description": (
                "admin_only = no clinical assessment or findings present; "
                "document_transfer = a document was filed without GP annotation; "
                "clinical = a clinician performed or recorded a clinical assessment."
            ),
        },
        "domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Zero or more clinical domains present. Empty list for non-clinical encounters. "
                "Allowed values: oncology, metabolic, cardiovascular, respiratory, "
                "musculoskeletal, mental_health, neurology, gastroenterology, urology, "
                "gynaecology, dermatology, haematology, renal, ophthalmology, ent, "
                "infectious_disease, immunisation, womens_health, paediatrics, other."
            ),
        },
        "encounter_purpose": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "One or more purposes. Use ['admin'] for non-clinical encounters. "
                "Allowed values: consultation, telephone, referral, investigation_request, "
                "investigation_result, medication_review, immunisation, screening, procedure, "
                "follow_up, discharge_summary, clinic_letter, admin."
            ),
        },
        "key_clinical_signals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short phrases describing the main clinical signals. Empty list for non-clinical.",
        },
        "expected_semantic_tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "SNOMED CT semantic tags expected for entities in this encounter. "
                "Empty list for non-clinical. Example values: disorder, finding, procedure, "
                "substance, observable entity, situation."
            ),
        },
        "clinical_significance": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": (
                "high = active diagnosis, acute symptoms, urgent referral, or significant results; "
                "medium = routine follow-up, chronic disease monitoring, medication review; "
                "low = minor notes, routine immunisations, or non-clinical encounters."
            ),
        },
    },
}


def format_output_schema_block(schema: dict) -> str:
    """Render the encounter_classify output schema as a prompt section."""
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
            req_marker = " (required)" if field in required else " (optional)"
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
            elif base_type == "array":
                items_type = defn.get("items", {}).get("type", "string")
                lines.append(
                    f"  - **{field}**{req_marker}: array of {items_type}. {desc}"
                )
            else:
                type_label = f"{base_type}, nullable" if nullable else base_type
                lines.append(f"  - **{field}**{req_marker}: {type_label}. {desc}")

    return "\n".join(lines)
