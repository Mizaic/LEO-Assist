"""Schema API for the No-Code Measure Builder.

Exposes a curated subset of the Patient Graph schema for the query builder.
Uses proper FHIR and Neo4j terminology; the UI maps to display labels.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient, run_with_retry

router = APIRouter()

# Curated aggregation targets for measures
AGGREGATION_TARGETS = [
    {"nodeLabel": "Patient", "description": "FHIR Patient resource"},
    {"nodeLabel": "EpisodeOfCare", "description": "Cancer care pathway episode"},
    {"nodeLabel": "Encounter", "description": "FHIR Encounter / consultation"},
    {"nodeLabel": "SafetyNetAlert", "description": "Safety netting alert"},
]

# Curated filters per node (property, type, fhirType, exampleValues)
# place_of_presentation, referral_route, safety_netting_recorded: pipeline extraction in progress
FILTERS = {
    "EpisodeOfCare": [
        {"property": "condition_type", "type": "string", "fhirType": "code", "exampleValues": ["Lung", "Breast"]},
        {"property": "status", "type": "string", "fhirType": "code", "distinctFromNeo4j": True},
        {"property": "referral_date", "type": "string", "fhirType": "date"},
        {"property": "referral_route", "type": "string", "fhirType": "code"},
        {"property": "place_of_presentation", "type": "string", "fhirType": "code"},
        {"property": "diagnosis_date", "type": "string", "fhirType": "date"},
        {"property": "first_presentation_date", "type": "string", "fhirType": "date"},
        {"property": "cancer_stage", "type": "string", "fhirType": "code"},
        {"property": "safety_netting_recorded", "type": "boolean", "fhirType": "boolean"},
    ],
    "Patient": [
        {"property": "gender", "type": "string", "fhirType": "code", "exampleValues": ["male", "female", "other"]},
        {"property": "birthDate", "type": "string", "fhirType": "date"},
        {"property": "ethnicity", "type": "string", "fhirType": "code"},
    ],
    "Encounter": [
        {"property": "date", "type": "string", "fhirType": "date"},
        {"property": "encounter_type", "type": "string", "fhirType": "code"},
    ],
    "SafetyNetAlert": [
        {"property": "actioned", "type": "boolean", "fhirType": "boolean"},
        {"property": "alert_type", "type": "string", "fhirType": "code"},
    ],
}

# Curated groupBy options per node
# Patient.gender for EpisodeOfCare = sex split of patients (group by patient's gender)
# Patient.age_band_at_diagnosis = derived from birthDate + diagnosis_date (0-24, 25-49, 50-64, 65-74, 75-84, 85+)
# valueProperties: numeric fields for median/percentile aggregation (Phase 2)
GROUP_BY = {
    "EpisodeOfCare": [
        "condition_type", "status", "referral_route", "place_of_presentation",
        "Patient.gender", "Patient.age_band_at_diagnosis", "cancer_stage",
        "primary_care_interval_band", "diagnostic_interval_band",
    ],
    "Patient": ["gender", "ethnicity"],
    "Encounter": ["encounter_type", "date", "count_per_patient_band"],
    "SafetyNetAlert": ["alert_type", "actioned"],
}

VALUE_PROPERTIES = {
    "EpisodeOfCare": ["primary_care_interval_days", "diagnostic_interval_days", "age_at_diagnosis"],
    "Encounter": ["count_per_patient"],
}

# Scope types for tenant filtering (hardcoded)
SCOPE_TYPES = [
    {"scopeType": "gp", "paramName": "practiceOdsCode", "label": "GP Practice"},
    {"scopeType": "icb", "paramName": "icbOdsCode", "label": "ICB"},
    {"scopeType": "alliance", "paramName": "allianceOdsCode", "label": "Cancer Alliance"},
]


# Map nodeLabel to (patient_var, target_var, relationship, target_label) for distinct-value queries
_NODE_PATTERNS = {
    "Patient": ("p", "p", None, "Patient"),
    "EpisodeOfCare": ("p", "ep", "HAS_EPISODE_OF_CARE", "EpisodeOfCare"),
    "Encounter": ("p", "e", "HAS_ENCOUNTER", "Encounter"),
    "SafetyNetAlert": ("p", "a", "HAS_SAFETY_NET_ALERT", "SafetyNetAlert"),
}


@router.get("/schema/patient-graph")
def get_patient_graph_schema():
    """Return curated Patient Graph schema for the query builder.

    Technical IDs (nodeLabel, property names) are returned; the UI maps to display labels.
    """
    return {
        "aggregationTargets": AGGREGATION_TARGETS,
        "filters": FILTERS,
        "groupBy": GROUP_BY,
        "scopeTypes": SCOPE_TYPES,
        "valueProperties": VALUE_PROPERTIES,
    }


@router.get("/schema/distinct-values")
def get_distinct_filter_values(
    node_label: str = Query(..., description="Node label (e.g. EpisodeOfCare)"),
    property_name: str = Query(..., description="Property name (e.g. status)"),
):
    """Return distinct values for a filter property from Neo4j.

    Used for properties with a fixed set of values (e.g. status) so the UI
    can show a select/multi-select instead of free text.
    """
    if node_label not in _NODE_PATTERNS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unknown nodeLabel: {node_label}"},
        )
    patient_var, target_var, rel, target_label = _NODE_PATTERNS[node_label]
    prop = property_name.split(".")[-1]
    if rel:
        cypher = (
            f"MATCH ({patient_var})-[:{rel}]->({target_var}:{target_label}) "
            f"WHERE {target_var}.{prop} IS NOT NULL "
            f"RETURN DISTINCT {target_var}.{prop} AS value "
            f"ORDER BY value"
        )
    else:
        cypher = (
            f"MATCH ({target_var}:{target_label}) "
            f"WHERE {target_var}.{prop} IS NOT NULL "
            f"RETURN DISTINCT {target_var}.{prop} AS value "
            f"ORDER BY value"
        )
    try:
        client = PatientGraphClient()
        rows = run_with_retry(client, cypher)
        return [str(r["value"]) for r in rows if r.get("value") is not None]
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": str(e)},
        )


@router.get("/schema/sample-node")
def get_sample_node(
    node_label: str = Query(..., description="Node label to sample (e.g. EncounterCandidate)"),
    graph: str = Query("patient", description="Which graph to query: 'patient' or 'knowledge'"),
    text_property: str = Query("text", description="Property that holds the main text — highlighted in the preview"),
):
    """Return one sample node of the given label so users can verify field names.

    Returns a sanitised dict of property names → truncated values. Long text
    fields are truncated to 300 characters so the preview stays readable.
    Sensitive fields (e.g. NHS number, DOB) are redacted.
    """
    _REDACT = {"nhs_number", "date_of_birth", "dob", "birthdate", "birthDate", "postcode"}
    _MAX_TEXT = 300

    try:
        if graph == "knowledge":
            client = KnowledgeGraphClient()
        else:
            client = PatientGraphClient()

        cypher = f"MATCH (n:{node_label}) RETURN properties(n) AS props LIMIT 1"
        rows = run_with_retry(client, cypher)
        if not rows:
            return JSONResponse(status_code=404, content={"detail": f"No {node_label} nodes found in the {graph} graph."})

        raw: dict = dict(rows[0]["props"])

        def _sanitise(k: str, v):
            if k.lower() in _REDACT:
                return "***redacted***"
            if isinstance(v, str) and len(v) > _MAX_TEXT:
                return v[:_MAX_TEXT] + "…"
            # Neo4j datetime / date objects
            if hasattr(v, "iso_format"):
                return v.iso_format()
            return v

        preview = {k: _sanitise(k, v) for k, v in raw.items()}
        # Ensure the selected text property appears first if present
        ordered = {}
        if text_property in preview:
            ordered[text_property] = preview.pop(text_property)
        ordered.update(preview)

        return {"nodeLabel": node_label, "graph": graph, "textProperty": text_property, "properties": ordered}

    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
