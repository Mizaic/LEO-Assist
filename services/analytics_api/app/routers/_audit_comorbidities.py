"""NCDA audit comorbidity section.

Separated from the main section queries because the comorbidity logic
is domain-registry-driven and substantially larger than other sections.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Optional

from libs.domain_config.registry import DomainRegistry
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient

logger = logging.getLogger(__name__)

# Fallback map for comorbidity concepts that don't yet have benchmark_key in
# their ValueSet designation.  Keys are SNOMED concept IDs (strings); values
# are (friendly display label, ncda_2018_benchmarks key).
_COMORBIDITY_CODE_META: dict[str, tuple[str, str]] = {
    "38341003": ("Hypertension", "comorbidity_hypertension_pct"),
    "49601007": ("Cardiovascular disease", "comorbidity_cvd_pct"),
    "3723001": ("Arthritis", "comorbidity_arthritis_pct"),
    "928000": ("Musculoskeletal disorder", "comorbidity_arthritis_pct"),
    "73211009": ("Diabetes mellitus", "comorbidity_diabetes_pct"),
    "13645005": ("COPD", "comorbidity_copd_pct"),
    "62914000": ("Cerebrovascular disease", "comorbidity_cvd_pct"),
    "386806002": ("Impaired cognition", "comorbidity_mental_health_pct"),
    "74732009": ("Mental health disorder", "comorbidity_mental_health_pct"),
    "21134002": ("Disability", "comorbidity_disability_pct"),
    "266987004": ("Previous cancer", "comorbidity_previous_cancer_pct"),
}


def _ensure_registry(kg: KnowledgeGraphClient) -> DomainRegistry:
    """Return (or lazily bootstrap) the DomainRegistry singleton.

    The registry is normally seeded at startup, but if the analytics-api starts
    before the KG is available the singleton may be uninitialised.  This helper
    performs a one-shot bootstrap from ncda-* ValueSet nodes in the KG so that
    the comorbidities query always has a valid registry to work with.
    """
    try:
        return DomainRegistry.get_instance()
    except RuntimeError:
        pass

    rows = kg.run(
        "MATCH (v:ValueSet) WHERE v.id STARTS WITH 'ncda-' "
        "RETURN v.id AS id, v.rawJson AS raw_json"
    )
    valuesets: dict = {}
    for r in rows or []:
        raw = r.get("raw_json")
        if not raw:
            continue
        try:
            vs_dict = _json.loads(raw) if isinstance(raw, str) else raw
            valuesets[r["id"]] = vs_dict
        except Exception:  # noqa: BLE001
            pass

    if valuesets:
        return DomainRegistry.from_fhir(valuesets)
    raise RuntimeError(
        "DomainRegistry: no ncda-* ValueSet nodes found in the knowledge graph. "
        "Seed the KG with domain ValueSets before starting the analytics-api."
    )


def _q_comorbidities(
    base: str, params: dict, client: PatientGraphClient
) -> dict:
    """Query comorbidity prevalence from HAS_DISEASE relationships.

    Top-level concepts are loaded from the cancer_audit/comorbidities subdomain.
    Each concept is expanded via IS_A hierarchy to capture all clinical variants.
    Results are grouped back to the top-level category term.
    """
    kg = KnowledgeGraphClient()
    try:
        registry = _ensure_registry(kg)
    except Exception:  # noqa: BLE001
        kg.close()
        return {"comorbidities": [], "total_patients": 0}

    try:
        concept_groups = registry.get_concept_id_groups(
            "comorbidities", kg, depth=3
        )
    finally:
        kg.close()

    if not concept_groups:
        return {"comorbidities": [], "total_patients": 0}

    domain_concepts = registry.get_domain_concepts("comorbidities")
    group_key_to_display: dict[str, str] = {}
    group_key_to_bm_key: dict[str, Optional[str]] = {}
    for concept in domain_concepts:
        gk = concept.benchmark_key or concept.term
        code_str = str(concept.concept_id)
        if code_str in _COMORBIDITY_CODE_META and not concept.benchmark_key:
            friendly_label, fallback_bm_key = _COMORBIDITY_CODE_META[code_str]
        else:
            friendly_label = concept.preferred_term
            fallback_bm_key = concept.benchmark_key
        if gk not in group_key_to_display:
            group_key_to_display[gk] = friendly_label
            group_key_to_bm_key[gk] = fallback_bm_key

    id_to_term: dict[str, str] = {}
    all_ids: list[str] = []
    for term, ids in concept_groups.items():
        for cid in ids:
            cid_str = str(cid)
            if cid_str not in id_to_term:
                id_to_term[cid_str] = term
            if cid_str not in all_ids:
                all_ids.append(cid_str)

    total_rows = client.run(
        f"{base}RETURN count(DISTINCT p) AS n",
        **params,
    )
    total = (total_rows[0]["n"] if total_rows else 0) or 1

    disease_rows = client.run(
        f"{base}"
        "WITH p "
        "OPTIONAL MATCH (p)-[r1:HAS_DISEASE]->(d1) "
        "  WHERE d1.conceptId IN $concept_ids "
        "AND r1.domain = 'comorbidities' "
        "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[r2:DOCUMENTS]->(d2) "
        "  WHERE d2.conceptId IN $concept_ids "
        "AND r2.domain = 'comorbidities' "
        "WITH p, collect(DISTINCT d1.conceptId) "
        "+ collect(DISTINCT d2.conceptId) AS cids "
        "UNWIND cids AS concept_id "
        "WITH p, concept_id WHERE concept_id IS NOT NULL "
        "RETURN concept_id, collect(DISTINCT toString(p.id)) AS patient_ids",
        **{**params, "concept_ids": all_ids},
    )

    group_patients: dict[str, set] = {term: set() for term in concept_groups}
    for row in disease_rows:
        cid_str = str(row.get("concept_id") or "")
        if not cid_str:
            continue
        top_term = id_to_term.get(cid_str)
        if top_term and top_term in group_patients:
            group_patients[top_term].update(row.get("patient_ids") or [])

    counts: dict[str, int] = {
        term: len(patients) for term, patients in group_patients.items()
    }

    comorbidities = sorted(
        [
            {
                "condition": group_key_to_display.get(term, term),
                "n": n,
                "pct": round(n * 100.0 / total, 1),
                "benchmark_key": group_key_to_bm_key.get(term),
            }
            for term, n in counts.items()
        ],
        key=lambda x: x["pct"],
        reverse=True,
    )

    return {"comorbidities": comorbidities, "total_patients": total}
