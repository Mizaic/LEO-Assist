"""Charlson Comorbidity Index (CCI) scoring.

Calculates CCI score for patients based on coded comorbidities
in the Patient Graph. Used for risk stratification and NCDA analysis.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Query

from libs.neo4j_client.client import PatientGraphClient

router = APIRouter()

CCI_WEIGHTS: Dict[str, int] = {
    "myocardial infarction": 1,
    "congestive heart failure": 1,
    "peripheral vascular disease": 1,
    "cerebrovascular disease": 1,
    "dementia": 1,
    "chronic pulmonary disease": 1,
    "connective tissue disease": 1,
    "peptic ulcer disease": 1,
    "mild liver disease": 1,
    "diabetes without complications": 1,
    "diabetes with complications": 2,
    "paraplegia": 2,
    "renal disease": 2,
    "cancer": 2,
    "moderate to severe liver disease": 3,
    "metastatic cancer": 6,
    "hiv/aids": 6,
}


@router.get("/cci/{patient_id}")
def calculate_cci(patient_id: str):
    """Calculate CCI score for a patient from coded encounter data."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[:DOCUMENTS]->(c) "
            "WHERE toString(p.id) = $pid "
            "RETURN DISTINCT c.name AS concept_name, c.conceptId AS concept_id, "
            "       c.semanticTag AS semantic_tag",
            pid=patient_id,
        )

        matched: list[dict[str, Any]] = []
        score = 0
        for row in rows:
            name = (row.get("concept_name") or "").lower()
            for condition, weight in CCI_WEIGHTS.items():
                if condition in name:
                    matched.append({
                        "condition": condition,
                        "weight": weight,
                        "concept_name": row.get("concept_name"),
                        "concept_id": row.get("concept_id"),
                    })
                    score += weight
                    break

        # Persist to patient node
        client.run(
            "MATCH (p:Patient) WHERE toString(p.id) = $pid SET p.cci_score = $score",
            pid=patient_id, score=score,
        )

        return {
            "patient_id": patient_id,
            "cci_score": score,
            "matched_conditions": matched,
        }
    finally:
        client.close()


@router.get("/cci/batch")
def batch_cci(org_id: str = Query(default=None)):
    """Get CCI distribution for an organization."""
    client = PatientGraphClient()
    try:
        return client.run(
            "MATCH (p:Patient) WHERE $org IS NULL OR p.tenantId = $org "
            "RETURN p.cci_score AS cci_score, count(p) AS patient_count "
            "ORDER BY cci_score",
            org=org_id,
        )
    finally:
        client.close()
