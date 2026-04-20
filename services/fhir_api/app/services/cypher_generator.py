"""Cypher generator for the No-Code Measure Builder.

Atlas trace:
  DO: DO-34E24FA1
  DI: DI-1795254D, DI-710D5213
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-34E24FA1")

Turns a visual query definition into valid Cypher that returns { name, value }[]
for charts/tables. Uses hardcoded scope patterns for tenant isolation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.fhir_api.app.config.scopes import get_scope_cypher_fragment

# Cohort variants: filter EpisodeOfCare by status
# Values must match episode_builder (confirmed|excluded|inconclusive)
# diagnosed = cancer confirmed; referred_excluded = cancer ruled out; all_referred = all three
COHORT_STATUS_FILTERS = {
    "diagnosed": "confirmed",
    "referred_excluded": "excluded",
    "all_referred": ["confirmed", "excluded", "inconclusive"],
}

# Derived value properties: computed in Cypher (node_label -> property -> expression)
DERIVED_VALUE_EXPRESSIONS = {
    "EpisodeOfCare": {
        "primary_care_interval_days": (
            "duration.between(date(ep.first_presentation_date), date(ep.referral_date)).days"
        ),
        "diagnostic_interval_days": (
            "duration.between(date(ep.first_presentation_date), date(ep.diagnosis_date)).days"
        ),
        "age_at_diagnosis": (
            "toInteger(duration.between(date(p.birthDate), date(ep.diagnosis_date)).days / 365.25)"
        ),
    },
}

# Map nodeLabel to (patient_var, target_var, relationship, target_label)
# Pattern: (p:Patient)-[:REL]->(target:TargetLabel)
NODE_PATTERNS = {
    "Patient": ("p", "p", None, "Patient"),  # count patients directly
    "EpisodeOfCare": ("p", "ep", "HAS_EPISODE_OF_CARE", "EpisodeOfCare"),
    "Encounter": ("p", "e", "HAS_ENCOUNTER", "Encounter"),
    "SafetyNetAlert": ("p", "a", "HAS_SAFETY_NET_ALERT", "SafetyNetAlert"),
}


def _escape_cypher_string(s: str) -> str:
    """Escape single quotes for Cypher string literals."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _normalize_list_value(value: Any) -> Optional[List[str]]:
    """Convert value to list of strings for in/nin operators."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [v.strip() for v in value.split(",") if v.strip()]
    return None


def _build_filter_conditions(
    node_label: str,
    target_var: str,
    filters: List[Dict[str, Any]],
) -> tuple[List[str], Dict[str, Any]]:
    """Build filter conditions and params from filters. Returns (conditions_list, params)."""
    conditions: List[str] = []
    params: Dict[str, Any] = {}

    for i, f in enumerate(filters):
        prop = f.get("property")
        op = f.get("op", "eq")
        value = f.get("value")
        if not prop:
            continue

        param_key = f"f{i}_{prop}"
        if op == "eq":
            if isinstance(value, bool):
                conditions.append(f"{target_var}.{prop} = ${param_key}")
                params[param_key] = value
            elif isinstance(value, (int, float)):
                conditions.append(f"{target_var}.{prop} = ${param_key}")
                params[param_key] = value
            else:
                conditions.append(f"{target_var}.{prop} = ${param_key}")
                params[param_key] = str(value) if value is not None else None
        elif op == "in":
            vals = _normalize_list_value(value)
            if vals:
                conditions.append(f"{target_var}.{prop} IN ${param_key}")
                params[param_key] = vals
        elif op == "nin":
            vals = _normalize_list_value(value)
            if vals:
                conditions.append(f"NOT ({target_var}.{prop} IN ${param_key})")
                params[param_key] = vals
        elif op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
            start_key = f"{param_key}_start"
            end_key = f"{param_key}_end"
            conditions.append(
                f"{target_var}.{prop} >= date(${start_key}) AND {target_var}.{prop} <= date(${end_key})"
            )
            params[start_key] = str(value[0])
            params[end_key] = str(value[1])
        elif op == "neq":
            conditions.append(f"{target_var}.{prop} <> ${param_key}")
            params[param_key] = str(value) if value is not None else None

    return conditions, params


def generate_cypher(definition: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Generate Cypher from a query definition.

    Input:
        nodeLabel: Patient | EpisodeOfCare | Encounter | SafetyNetAlert
        filters: [{ property, op, value }]
        groupBy: property name or null for single total
        scopeType: "gp" | "icb" | "alliance" (required for tenant scoping)

    Output:
        (cypher_string, params_dict)
    """
    node_label = definition.get("nodeLabel", "EpisodeOfCare")
    filters = definition.get("filters", [])
    group_by = definition.get("groupBy")
    scope_type = definition.get("scopeType", "gp")

    if node_label not in NODE_PATTERNS:
        raise ValueError(f"Unknown nodeLabel: {node_label}")

    patient_var, target_var, rel, target_label = NODE_PATTERNS[node_label]
    scope_fragment = get_scope_cypher_fragment(scope_type)
    if not scope_fragment:
        raise ValueError(f"Unknown scopeType: {scope_type}")

    parts: List[str] = []
    params: Dict[str, Any] = {}

    # Scope filter (required)
    parts.append(scope_fragment)

    # Target match
    if rel:
        parts.append(f"MATCH ({patient_var})-[:{rel}]->({target_var}:{target_label})")
    # else: Patient - we're already matching p

    # User filters
    filter_conditions, filter_params = _build_filter_conditions(
        node_label, target_var, filters
    )
    params.update(filter_params)

    # Cohort filter (when target is EpisodeOfCare) - inject status filter
    cohort_variant = definition.get("cohortVariant", "diagnosed")
    cohort_cond = ""
    if node_label == "EpisodeOfCare" and cohort_variant in COHORT_STATUS_FILTERS:
        status_val = COHORT_STATUS_FILTERS[cohort_variant]
        if isinstance(status_val, list):
            params["_cohort_statuses"] = status_val
            cohort_cond = f"{target_var}.status IN $_cohort_statuses"
        else:
            params["_cohort_status"] = status_val
            cohort_cond = f"{target_var}.status = $_cohort_status"

    all_conditions = ([cohort_cond] if cohort_cond else []) + filter_conditions
    if all_conditions:
        parts.append(" WHERE " + " AND ".join(all_conditions))

    # Build RETURN (Cypher implicitly groups by non-aggregate expressions)
    # Support groupBy from Patient when target is EpisodeOfCare (e.g. Patient.gender for sex split)
    # Patient.age_band_at_diagnosis: derived from birthDate + diagnosis_date
    if group_by and group_by.startswith("Patient."):
        patient_prop = group_by.replace("Patient.", "")
        group_var = patient_var
    else:
        group_var = target_var
        patient_prop = None

    aggregation = definition.get("aggregation", "count")
    value_property = definition.get("valueProperty")
    percentage_property = definition.get("percentageProperty")
    percentage_value = definition.get("percentageValue", True)

    if aggregation == "median" and value_property and node_label == "EpisodeOfCare":
        expr = DERIVED_VALUE_EXPRESSIONS.get("EpisodeOfCare", {}).get(value_property)
        if expr:
            parts.append(f"WITH {target_var}, {expr} AS val " "WHERE val IS NOT NULL ")
            parts.append(
                "WITH collect(val) AS vals "
                "RETURN 'Median' AS name, percentileCont(vals, 0.5) AS value, "
                "percentileCont(vals, 0.25) AS iqr_low, percentileCont(vals, 0.75) AS iqr_high"
            )
            cypher = " ".join(parts)
            return cypher, params
    elif (
        aggregation == "percentage"
        and percentage_property
        and node_label == "EpisodeOfCare"
    ):
        parts.append(
            f"WITH count(*) AS total, "
            f"sum(CASE WHEN {target_var}.{percentage_property} = $pct_val THEN 1 ELSE 0 END) AS yes_count "
        )
        params["pct_val"] = percentage_value
        parts.append(
            "RETURN 'Yes' AS name, CASE WHEN total > 0 THEN yes_count * 100.0 / total ELSE 0 END AS value"
        )
        cypher = " ".join(parts)
        return cypher, params

    if group_by:
        if patient_prop == "age_band_at_diagnosis" and node_label == "EpisodeOfCare":
            age_expr = "toInteger(duration.between(date(p.birthDate), date(ep.diagnosis_date)).days / 365.25)"
            band_expr = (
                f"CASE WHEN {age_expr} < 25 THEN '0-24' "
                f"WHEN {age_expr} < 50 THEN '25-49' "
                f"WHEN {age_expr} < 65 THEN '50-64' "
                f"WHEN {age_expr} < 75 THEN '65-74' "
                f"WHEN {age_expr} < 85 THEN '75-84' "
                f"ELSE '85+' END"
            )
            parts.append(
                f"WITH {patient_var}, {target_var}, {band_expr} AS age_band "
                "WHERE ep.diagnosis_date IS NOT NULL AND p.birthDate IS NOT NULL "
            )
            parts.append(
                "RETURN coalesce(age_band, '(unknown)') AS name, count(*) AS value "
                "ORDER BY value DESC"
            )
        elif patient_prop is not None:
            parts.append(
                f"RETURN coalesce(toString({group_var}.{patient_prop}), '(unknown)') AS name, count(*) AS value "
                "ORDER BY value DESC"
            )
        elif (
            group_by in ("primary_care_interval_band", "diagnostic_interval_band")
            and node_label == "EpisodeOfCare"
        ):
            if group_by == "primary_care_interval_band":
                days_expr = "duration.between(date(ep.first_presentation_date), date(ep.referral_date)).days"
            else:
                days_expr = "duration.between(date(ep.first_presentation_date), date(ep.diagnosis_date)).days"
            band_expr = (
                f"CASE WHEN {days_expr} IS NULL THEN '(unknown)' "
                f"WHEN {days_expr} < 8 THEN '0-7' "
                f"WHEN {days_expr} < 15 THEN '8-14' "
                f"WHEN {days_expr} < 31 THEN '15-30' "
                f"WHEN {days_expr} < 91 THEN '31-90' "
                f"ELSE '91+' END"
            )
            parts.append(
                f"WITH {target_var}, {band_expr} AS band "
                f"WHERE {days_expr} IS NOT NULL "
            )
            parts.append(
                "RETURN coalesce(band, '(unknown)') AS name, count(*) AS value "
                "ORDER BY value DESC"
            )
        elif group_by == "count_per_patient_band" and node_label == "Encounter":
            parts.append(f"WITH {patient_var}, count({target_var}) AS cnt ")
            parts.append("WITH CASE WHEN cnt < 3 THEN '<3' ELSE '3+' END AS band ")
            parts.append(
                "RETURN coalesce(band, '(unknown)') AS name, count(*) AS value "
                "ORDER BY value DESC"
            )
        else:
            parts.append(
                f"RETURN coalesce(toString({target_var}.{group_by}), '(unknown)') AS name, count(*) AS value "
                "ORDER BY value DESC"
            )
    else:
        if (
            aggregation == "median"
            and node_label == "Encounter"
            and (not value_property or value_property == "count_per_patient")
        ):
            parts.append(f"WITH {patient_var}, count({target_var}) AS cnt ")
            parts.append("WITH collect(cnt) AS counts ")
            parts.append(
                "RETURN 'Median' AS name, percentileCont(counts, 0.5) AS value, "
                "percentileCont(counts, 0.25) AS iqr_low, percentileCont(counts, 0.75) AS iqr_high"
            )
        else:
            parts.append("RETURN 'Total' AS name, count(*) AS value")

    cypher = " ".join(parts)
    return cypher, params
