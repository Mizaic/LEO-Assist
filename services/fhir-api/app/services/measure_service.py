"""FHIR Measure CRUD and evaluation against the Knowledge Graph.

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


def get_measure(measure_id: str) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        rows = client.run(
            "MATCH (m:Measure {id: $mid}) RETURN m.rawJson AS rawJson LIMIT 1",
            mid=measure_id,
        )
        return json.loads(rows[0]["rawJson"]) if rows and rows[0].get("rawJson") else None
    finally:
        client.close()


def upsert_measure(measure_id: str, resource: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    client = KnowledgeGraphClient()
    try:
        client.run(
            "MERGE (m:Measure {id: $mid}) "
            "SET m.rawJson = $raw, m.name = $name, m.status = $status, m.url = $url",
            mid=measure_id,
            raw=json.dumps(resource),
            name=resource.get("name"),
            status=resource.get("status", "active"),
            url=resource.get("url"),
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
            name=name, status=status,
        )
        total = count_rows[0]["total"] if count_rows else 0
        rows = client.run(
            "MATCH (m:Measure) WHERE ($name IS NULL OR m.name CONTAINS $name) "
            "AND ($status IS NULL OR m.status = $status) "
            "RETURN m.rawJson AS rawJson ORDER BY m.name SKIP $offset LIMIT $limit",
            name=name, status=status, offset=offset, limit=count,
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

    library_id = library_refs[0].split("/")[-1] if "/" in library_refs[0] else library_refs[0]
    library = _get_library(library_id)
    if not library:
        return {"error": f"Library/{library_id} not found"}

    cypher, cypher_hash = extract_cypher_and_hash(library)
    if not cypher:
        return {"error": "Library has no Cypher content"}

    cypher_params = {p: params.get(p) for p in _PARAM_RE.findall(cypher) if p in params}

    patient_client = PatientGraphClient()
    try:
        results = patient_client.run(cypher, **cypher_params)
    finally:
        patient_client.close()

    return _build_measure_report(measure_id, measure, results)


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
        return json.loads(rows[0]["rawJson"]) if rows and rows[0].get("rawJson") else None
    finally:
        client.close()


def _build_measure_report(
    measure_id: str,
    measure: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "resourceType": "MeasureReport",
        "status": "complete",
        "type": "summary",
        "measure": f"Measure/{measure_id}",
        "extension": [
            {
                "url": "http://example.org/fhir/StructureDefinition/query-result",
                "valueString": json.dumps(results, default=str),
            }
        ],
    }
