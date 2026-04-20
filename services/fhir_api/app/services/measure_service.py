"""FHIR Measure CRUD and evaluation against the Knowledge Graph.

Atlas trace:
  DO: DO-34E24FA1
  DI: DI-1795254D, DI-710D5213
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-34E24FA1")

Ported from VRB fhir-api/app/services/measure_service.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

_PARAM_RE = re.compile(r"\$`?(\w+)`?")

# Map request/cohort param names to Cypher param names (from cypher_generator)
# Used when Cypher expects params that the frontend sends under different names.
_COHORT_STATUS_DEFAULT = "confirmed"
_COHORT_STATUSES_DEFAULT = ["confirmed", "excluded", "inconclusive"]


def _expand_params_for_cypher(
    params: Dict[str, Any], required_param_names: List[str]
) -> Dict[str, Any]:
    """Expand request params with Cypher param names and sensible defaults.

    The cypher_generator produces params like _cohort_status, f0_referral_date_start,
    f0_referral_date_end, f1_status. The frontend sends periodStart, periodEnd,
    ce_status, ce_referral_date_start, etc. This maps and fills defaults.
    """
    expanded = dict(params)

    period_start = params.get("periodStart") or params.get("ce_referral_date_start")
    period_end = params.get("periodEnd") or params.get("ce_referral_date_end")
    ce_status_list = params.get("ce_status")
    if isinstance(ce_status_list, str):
        ce_status_list = [s.strip() for s in ce_status_list.split(",") if s.strip()]
    if not isinstance(ce_status_list, list):
        ce_status_list = []

    # Map date params: period/referral date range -> f*_referral_date_start/end
    for name in required_param_names:
        if (
            name.endswith("_referral_date_start")
            and period_start
            and name not in expanded
        ):
            expanded[name] = period_start
        elif (
            name.endswith("_referral_date_end") and period_end and name not in expanded
        ):
            expanded[name] = period_end
        elif (
            name.endswith("_start")
            and "referral" in name
            and period_start
            and name not in expanded
        ):
            expanded[name] = period_start
        elif (
            name.endswith("_end")
            and "referral" in name
            and period_end
            and name not in expanded
        ):
            expanded[name] = period_end

    # _cohort_status: single value from ce_status or default
    if "_cohort_status" in required_param_names and "_cohort_status" not in expanded:
        if len(ce_status_list) == 1:
            expanded["_cohort_status"] = ce_status_list[0]
        else:
            expanded["_cohort_status"] = _COHORT_STATUS_DEFAULT

    # _cohort_statuses: list from ce_status or default
    if (
        "_cohort_statuses" in required_param_names
        and "_cohort_statuses" not in expanded
    ):
        if len(ce_status_list) > 1:
            expanded["_cohort_statuses"] = ce_status_list
        else:
            expanded["_cohort_statuses"] = _COHORT_STATUSES_DEFAULT

    # f*_status: from ce_status (first) or default
    for name in required_param_names:
        if (
            name.endswith("_status")
            and name != "_cohort_status"
            and name != "_cohort_statuses"
        ):
            if name not in expanded:
                expanded[name] = (
                    ce_status_list[0] if ce_status_list else _COHORT_STATUS_DEFAULT
                )

    return expanded


def get_measure(measure_id: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (m:Measure {id: $mid}) RETURN m.rawJson AS rawJson LIMIT 1",
            mid=measure_id,
        )
        return (
            json.loads(rows[0]["rawJson"]) if rows and rows[0].get("rawJson") else None
        )
    finally:
        client.close()


def upsert_measure(
    measure_id: str, resource: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (m:Measure {id: $mid}) "
            "SET m.rawJson = $raw, m.name = $name, m.status = $status, "
            "    m.url = $url, m.title = $title, m.isGlobal = true",
            mid=measure_id,
            raw=json.dumps(resource),
            name=resource.get("name"),
            status=resource.get("status", "active"),
            url=resource.get("url"),
            title=resource.get("title"),
        )
        return resource
    finally:
        client.close()


def delete_measure(measure_id: str) -> None:
    client = KnowledgeGraphClient()
    try:
        client.run("MATCH (m:Measure {id: $mid}) DETACH DELETE m", mid=measure_id)
    finally:
        client.close()


def search_measures(
    name: Optional[str] = None,
    status: Optional[str] = None,
    count: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    client = KnowledgeGraphClient()
    try:
        count_rows = client.run(
            "MATCH (m:Measure) WHERE ($name IS NULL OR m.name CONTAINS $name) "
            "AND ($status IS NULL OR m.status = $status) RETURN count(m) AS total",
            name=name,
            status=status,
        )
        total = count_rows[0]["total"] if count_rows else 0
        rows = client.run(
            "MATCH (m:Measure) WHERE ($name IS NULL OR m.name CONTAINS $name) "
            "AND ($status IS NULL OR m.status = $status) "
            "RETURN m.rawJson AS rawJson ORDER BY m.name SKIP $offset LIMIT $limit",
            name=name,
            status=status,
            offset=offset,
            limit=count,
        )
        items = [json.loads(r["rawJson"]) for r in rows if r.get("rawJson")]
        return items, total
    finally:
        client.close()


def evaluate_measure(
    measure_id: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate a Measure by running its Library Cypher query against the Patient Graph.

    Flow:
    1. Load Measure -> extract Library reference
    2. Load Library -> extract + validate Cypher
    3. Execute Cypher with parameters against Patient Graph
    4. Build MeasureReport with results
    """
    measure = get_measure(measure_id)
    if not measure:
        return {"error": f"Measure/{measure_id} not found"}

    library_refs = measure.get("library", [])
    if not library_refs:
        return {"error": "Measure has no library reference"}

    library_id = (
        library_refs[0].split("/")[-1] if "/" in library_refs[0] else library_refs[0]
    )
    library = _get_library(library_id)
    if not library:
        return {"error": f"Library/{library_id} not found"}

    cypher, cypher_hash = extract_cypher_and_hash(library)
    if not cypher:
        return {"error": "Library has no Cypher content"}

    required_param_names = _PARAM_RE.findall(cypher)
    expanded_params = _expand_params_for_cypher(params, required_param_names)
    cypher_params = {
        p: expanded_params.get(p)
        for p in required_param_names
        if expanded_params.get(p) is not None
    }

    missing = [p for p in required_param_names if p not in cypher_params]
    if missing:
        return {
            "error": f"Measure Cypher expects parameters that could not be resolved: {missing}"
        }

    patient_client = PatientGraphClient()
    try:
        results = patient_client.run(cypher, **cypher_params)
    finally:
        patient_client.close()

    org_id = params.get("_org_id")
    org_name = params.get("_org_name")
    return _build_measure_report(
        measure_id, measure, results, org_id=org_id, org_name=org_name
    )


def extract_cypher_and_hash(library: Dict[str, Any]) -> Tuple[str, str]:
    cypher = ""
    cypher_hash = ""
    for content in library.get("content", []):
        if content.get("title") == "cypher" and content.get("data"):
            cypher = base64.b64decode(content["data"]).decode("utf-8")
        elif content.get("title") == "cypher-sha256" and content.get("data"):
            cypher_hash = base64.b64decode(content["data"]).decode("utf-8")
    return cypher, cypher_hash


def _get_library(library_id: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (l:Library {id: $lid}) RETURN l.rawJson AS rawJson LIMIT 1",
            lid=library_id,
        )
        return (
            json.loads(rows[0]["rawJson"]) if rows and rows[0].get("rawJson") else None
        )
    finally:
        client.close()


def _results_to_practice_benchmark(
    results: List[Dict[str, Any]],
    metric_id: str,
    unit: str,
    label: str,
) -> Optional[Dict[str, Any]]:
    """Convert measure query results to practice benchmark value (live data).

    For demographics.sex: expects rows with name/value (Male/Female or male/female)
    -> returns value_breakdown {male: pct, female: pct}.
    For scalar metrics: returns value from first row.
    """
    if not results:
        return None

    # Detect sex distribution: rows with male/female or Male/Female
    male_val = None
    female_val = None
    for row in results:
        name = (row.get("name") or row.get("gender") or "").lower().strip()
        val = row.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if name in ("male", "m"):
                male_val = float(val)
            elif name in ("female", "f"):
                female_val = float(val)

    if male_val is not None and female_val is not None:
        total = male_val + female_val
        if total > 0:
            return {
                "metric_id": metric_id,
                "label": label,
                "scope_type": "practice",
                "scope_name": "Practice",
                "value": None,
                "value_breakdown": {
                    "male": round(male_val / total * 100, 1),
                    "female": round(female_val / total * 100, 1),
                },
                "unit": unit or "pct",
                "source": "live",
            }

    # Scalar: use first row value
    first = results[0]
    val = first.get("value")
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return {
            "metric_id": metric_id,
            "label": label,
            "scope_type": "practice",
            "scope_name": "Practice",
            "value": val,
            "unit": unit or "",
            "source": "live",
        }
    return None


def _build_measure_report(
    measure_id: str,
    measure: Dict[str, Any],
    results: List[Dict[str, Any]],
    org_id: Optional[str] = None,
    org_name: Optional[str] = None,
) -> Dict[str, Any]:
    extensions = [
        {
            "url": "http://example.org/fhir/StructureDefinition/query-result",
            "valueString": json.dumps(results, default=str),
        }
    ]

    benchmark_config = measure.get("benchmarkConfig")
    if benchmark_config:
        from services.fhir_api.app.services import benchmark_service

        set_id = benchmark_config.get("benchmarkSetId")
        metric_mapping = benchmark_config.get("metricMapping") or []
        metric_id = (
            metric_mapping[0].get("benchmarkMetricId") if metric_mapping else None
        )

        if set_id and metric_id:
            benchmarks = benchmark_service.get_benchmark_comparison(set_id, metric_id)
            if benchmarks:
                label = (
                    benchmarks[0].get("label", metric_id) if benchmarks else metric_id
                )
                unit = benchmarks[0].get("unit", "pct")
                practice_live = _results_to_practice_benchmark(
                    results, metric_id, unit, label
                )
                if practice_live:
                    practice_live["scope_name"] = org_name or "Practice"
                # Replace practice row with live data; keep alliance and england (2018)
                out = []
                for pt in benchmarks:
                    if pt.get("scope_type") == "practice":
                        if practice_live:
                            out.append(practice_live)
                        # else keep 2018 practice if no live data
                        elif org_name:
                            pt_copy = dict(pt)
                            pt_copy["scope_name"] = org_name
                            out.append(pt_copy)
                        else:
                            out.append(pt)
                    else:
                        out.append(pt)
                extensions.append(
                    {
                        "url": "http://example.org/fhir/StructureDefinition/benchmark-comparison",
                        "valueString": json.dumps(out, default=str),
                    }
                )

    return {
        "resourceType": "MeasureReport",
        "status": "complete",
        "type": "summary",
        "measure": f"Measure/{measure_id}",
        "extension": extensions,
    }
