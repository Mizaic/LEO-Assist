"""NCDA audit comorbidity section.

Atlas trace:
  DO: DO-D5B9FE5F
  DI: DI-6E1B71A4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")

Separated from the main section queries because the comorbidity logic
is domain-registry-driven and substantially larger than other sections.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any, Optional

from libs.analytics import confirmed_cancer_where
from libs.domain_config.registry import DomainRegistry
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type

from ._audit_sections import _SAFE_BIRTH_DATE, _SAFE_REFERRAL_DATE

logger = logging.getLogger(__name__)

# Fallback map for comorbidity concepts that don't yet have benchmark_key in
# their ValueSet designation.  Keys are SNOMED concept IDs (strings); values
# are (friendly display label, ncda_2018_benchmarks key).
_COMORBIDITY_CODE_META: dict[str, tuple[str, str]] = {
    # Legacy disorder/findings concepts.
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
    # Current NCDA comorbidity mapping concepts (history-first coding).
    "161501007": ("Hypertension", "comorbidity_hypertension_pct"),
    "266995000": ("Cardiovascular disease", "comorbidity_cvd_pct"),
    "399211009": ("Myocardial infarction", "comorbidity_cvd_pct"),
    "48447003": ("Congestive heart failure", "comorbidity_cvd_pct"),
    "473109007": ("Peripheral vascular disease", "comorbidity_cvd_pct"),
    "308064009": ("Cerebrovascular disease", "comorbidity_cvd_pct"),
    "161445009": ("Diabetes mellitus", "comorbidity_diabetes_pct"),
    "74627003": ("Diabetes with complications", "comorbidity_diabetes_pct"),
    "270473001": ("COPD", "comorbidity_copd_pct"),
    "161465002": ("Dementia", "comorbidity_mental_health_pct"),
    "275540007": ("Cognitive impairment", "comorbidity_mental_health_pct"),
    "472961001": ("Connective tissue disease", "comorbidity_arthritis_pct"),
    "267004000": ("Musculoskeletal disorder", "comorbidity_arthritis_pct"),
    "266998003": ("Peptic ulcer disease", "comorbidity_peptic_ulcer_pct"),
    "161535005": ("Mild liver disease", "comorbidity_liver_disease_pct"),
    "19943007": ("Moderate or severe liver disease", "comorbidity_liver_disease_pct"),
    "50582007": ("Hemiplegia or paraplegia", "comorbidity_disability_pct"),
    "415036007": ("Disability", "comorbidity_disability_pct"),
    "275552000": ("Renal disease", "comorbidity_renal_disease_pct"),
    "266987004": ("Previous cancer", "comorbidity_previous_cancer_pct"),
    "74732009": ("Severe longstanding mental illness", "comorbidity_mental_health_pct"),
}

_REFERRAL_MILESTONE_EXISTS = (
    "EXISTS { MATCH (:Encounter)-[__ref:IS_PART_OF]->(ep) "
    "WHERE __ref.milestone_type = 'referral' }"
)

_AGE_BAND_ORDER: tuple[str, ...] = (
    "0-24",
    "25-49",
    "50-64",
    "65-74",
    "75-84",
    "85+",
    "unknown",
)


def _ensure_registry(kg: KnowledgeGraphClient) -> DomainRegistry:
    """Return (or lazily bootstrap) the DomainRegistry singleton.

    The registry is normally seeded at startup, but if the analytics-api starts
    before the KG is available the singleton may be uninitialised.  This helper
    performs a one-shot bootstrap from ncda-* ValueSet nodes in the knowledge graph
    so that the comorbidities query always has a valid registry to work with.
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


def _load_comorbidity_axis_bundle(
    registry: DomainRegistry,
    kg: KnowledgeGraphClient,
) -> Optional[dict[str, Any]]:
    """Shared registry SNOMED groups + stable radar order + display maps."""
    concept_groups = registry.get_concept_id_groups("comorbidities", kg, depth=3)
    if not concept_groups:
        return None

    domain_concepts = registry.get_domain_concepts("comorbidities")
    group_key_to_display: dict[str, str] = {}
    group_key_to_bm_key: dict[str, Optional[str]] = {}
    ordered_keys: list[str] = []
    seen_k: set[str] = set()
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
        if gk not in seen_k:
            seen_k.add(gk)
            ordered_keys.append(gk)

    id_to_term: dict[str, str] = {}
    all_ids: list[str] = []
    for term, ids in concept_groups.items():
        for cid in ids:
            cid_str = str(cid)
            if cid_str not in id_to_term:
                id_to_term[cid_str] = term
            if cid_str not in all_ids:
                all_ids.append(cid_str)

    return {
        "concept_groups": concept_groups,
        "group_key_to_display": group_key_to_display,
        "group_key_to_bm_key": group_key_to_bm_key,
        "id_to_term": id_to_term,
        "all_ids": all_ids,
        "ordered_keys": ordered_keys,
    }


def _load_cancer_type_axis_bundle(
    registry: DomainRegistry,
    kg: KnowledgeGraphClient,
) -> Optional[dict[str, Any]]:
    """SNOMED cancer-type ValueSet groups expanded to descendants."""
    concept_groups = registry.get_concept_id_groups("cancer_types", kg, depth=3)
    if not concept_groups:
        return None

    domain_concepts = registry.get_domain_concepts("cancer_types")
    group_key_to_display: dict[str, str] = {}
    ordered_keys: list[str] = []
    seen_k: set[str] = set()
    for concept in domain_concepts:
        gk = concept.benchmark_key or concept.term
        group_key_to_display.setdefault(gk, concept.term or concept.preferred_term)
        if gk not in seen_k:
            seen_k.add(gk)
            ordered_keys.append(gk)

    id_to_term: dict[str, str] = {}
    all_ids: list[str] = []
    for term, ids in concept_groups.items():
        for cid in ids:
            cid_str = str(cid)
            if cid_str not in id_to_term:
                id_to_term[cid_str] = term
            if cid_str not in all_ids:
                all_ids.append(cid_str)

    return {
        "concept_groups": concept_groups,
        "group_key_to_display": group_key_to_display,
        "id_to_term": id_to_term,
        "all_ids": all_ids,
        "ordered_keys": ordered_keys,
    }


def _outcome_label(
    is_confirmed: bool,
    cancer_type_raw: Optional[str],
    has_referral_milestone: bool,
    cancer_type_labels: Optional[list[str]] = None,
) -> str:
    if is_confirmed:
        if cancer_type_labels:
            return cancer_type_labels[0]
        return normalise_cancer_type((cancer_type_raw or "").strip() or "No Information")
    if has_referral_milestone:
        return "Referral without cancer diagnosis"
    return "Other"


def _condition_rows_for_slice(
    slice_pids: set[str],
    pid_terms: dict[str, set[str]],
    ordered_keys: list[str],
    group_key_to_display: dict[str, str],
    group_key_to_bm_key: dict[str, Optional[str]],
    denom: int,
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for key in ordered_keys:
        n = sum(1 for pid in slice_pids if key in pid_terms.get(pid, set()))
        pct = round(n * 100.0 / denom, 1) if denom else 0.0
        rows_out.append(
            {
                "condition": group_key_to_display.get(key, key),
                "n": n,
                "pct": pct,
                "benchmark_key": group_key_to_bm_key.get(key),
            }
        )
    return rows_out


def _q_comorbidities(base: str, params: dict, client: PatientGraphClient) -> dict:
    """Query comorbidity prevalence from HAS_DISEASE relationships.

    Top-level concepts are loaded from the cancer_audit/comorbidities subdomain.
    Each concept is expanded via IS_A hierarchy to capture all clinical variants.
    Results are grouped back to the top-level category term.
    """
    kg = KnowledgeGraphClient()
    try:
        registry = _ensure_registry(kg)
        bundle = _load_comorbidity_axis_bundle(registry, kg)
    except Exception:  # noqa: BLE001
        kg.close()
        return {"comorbidities": [], "radar": [], "total_patients": 0}
    kg.close()

    if bundle is None:
        return {"comorbidities": [], "radar": [], "total_patients": 0}

    concept_groups = bundle["concept_groups"]
    group_key_to_display = bundle["group_key_to_display"]
    group_key_to_bm_key = bundle["group_key_to_bm_key"]
    id_to_term = bundle["id_to_term"]
    all_ids = bundle["all_ids"]
    ordered_keys = bundle["ordered_keys"]

    total_rows = client.run(
        f"{base}RETURN count(DISTINCT p) AS n",
        **params,
    )
    raw_total = int(total_rows[0]["n"] if total_rows else 0)
    total = raw_total or 1

    disease_rows = client.run(
        f"{base}"
        "WITH p "
        "OPTIONAL MATCH (p)-[r1:HAS_DISEASE]->(d1) "
        "  WHERE toString(d1.conceptId) IN $concept_ids "
        "AND r1.domain = 'comorbidities' "
        "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[r2:DOCUMENTS]->(d2) "
        "  WHERE toString(d2.conceptId) IN $concept_ids "
        "AND r2.domain = 'comorbidities' "
        "WITH p, collect(DISTINCT toString(d1.conceptId)) "
        "+ collect(DISTINCT toString(d2.conceptId)) AS cids "
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

    radar = [
        {
            "condition": group_key_to_display.get(k, k),
            "benchmark_key": group_key_to_bm_key.get(k),
            "n": counts.get(k, 0),
            "pct": round(counts.get(k, 0) * 100.0 / total, 1),
        }
        for k in ordered_keys
    ]

    return {
        "comorbidities": comorbidities,
        "radar": radar,
        "total_patients": raw_total,
    }


def _q_comorbidities_drilldown(base: str, params: dict, client: PatientGraphClient) -> dict:
    """Practice-scope slices: age band, gender, referral outcome vs comorbidity profile.

    Primary episode per patient: latest referral_date in scope. Outcome uses
    libs.analytics.confirmed_cancer_where(ep); cancer site labels use
    libs.oncology.normalise_cancer_type on ep.cancer_type. Referral-without-cancer
    requires a referral milestone and no confirmed cancer diagnosis on that episode.
    """
    kg = KnowledgeGraphClient()
    try:
        registry = _ensure_registry(kg)
        bundle = _load_comorbidity_axis_bundle(registry, kg)
        cancer_bundle = _load_cancer_type_axis_bundle(registry, kg)
    except Exception:  # noqa: BLE001
        kg.close()
        return {
            "total_patients": 0,
            "by_age_band": [],
            "by_gender": [],
            "by_referral_outcome": [],
        }

    kg.close()

    if bundle is None:
        return {
            "total_patients": 0,
            "by_age_band": [],
            "by_gender": [],
            "by_referral_outcome": [],
        }

    concept_groups = bundle["concept_groups"]
    group_key_to_display = bundle["group_key_to_display"]
    group_key_to_bm_key = bundle["group_key_to_bm_key"]
    id_to_term = bundle["id_to_term"]
    all_ids = bundle["all_ids"]
    ordered_keys = bundle["ordered_keys"]
    cancer_id_to_term: dict[str, str] = {}
    cancer_group_key_to_display: dict[str, str] = {}
    cancer_all_ids: list[str] = []
    cancer_order: list[str] = []
    if cancer_bundle is not None:
        cancer_id_to_term = cancer_bundle["id_to_term"]
        cancer_group_key_to_display = cancer_bundle["group_key_to_display"]
        cancer_all_ids = cancer_bundle["all_ids"]
        cancer_order = cancer_bundle["ordered_keys"]

    cc_pred = confirmed_cancer_where("ep")

    patient_rows = client.run(
        f"{base}"
        "WITH p, ep ORDER BY p.id, ep.referral_date DESC "
        "WITH p, head(collect(ep)) AS ep "
        "WHERE ep IS NOT NULL "
        "WITH p, ep, "
        f"  {_SAFE_BIRTH_DATE} AS birth_date_value, "
        f"  {_SAFE_REFERRAL_DATE} AS referral_date_value, "
        f"  CASE WHEN ({cc_pred}) THEN true ELSE false END AS is_confirmed, "
        "  trim(ep.cancer_type) AS cancer_type_raw, "
        f"  {_REFERRAL_MILESTONE_EXISTS} AS has_referral_milestone "
        "WITH p, is_confirmed, cancer_type_raw, has_referral_milestone, birth_date_value, referral_date_value, "
        "  CASE WHEN birth_date_value IS NOT NULL AND referral_date_value IS NOT NULL "
        "    THEN duration.inDays(birth_date_value, referral_date_value).days / 365.0 "
        "    ELSE null END AS age_at_referral "
        "WITH p, is_confirmed, cancer_type_raw, has_referral_milestone, age_at_referral, "
        "  CASE WHEN age_at_referral IS NULL THEN 'unknown' "
        "       WHEN age_at_referral < 25 THEN '0-24' "
        "       WHEN age_at_referral < 50 THEN '25-49' "
        "       WHEN age_at_referral < 65 THEN '50-64' "
        "       WHEN age_at_referral < 75 THEN '65-74' "
        "       WHEN age_at_referral < 85 THEN '75-84' "
        "       ELSE '85+' END AS age_band, "
        "  CASE WHEN toLower(trim(coalesce(p.gender, ''))) STARTS WITH 'm' THEN 'male' "
        "       WHEN toLower(trim(coalesce(p.gender, ''))) STARTS WITH 'f' THEN 'female' "
        "       ELSE 'unknown' END AS gender_bucket "
        "RETURN toString(p.id) AS pid, age_band, gender_bucket, is_confirmed, cancer_type_raw, has_referral_milestone",
        **params,
    )

    cancer_type_rows = []
    if cancer_all_ids:
        cancer_type_rows = client.run(
            f"{base}"
            "WITH p, ep ORDER BY p.id, ep.referral_date DESC "
            "WITH p, head(collect(ep)) AS ep "
            "WHERE ep IS NOT NULL "
            "MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[d:DOCUMENTS]->(s) "
            "WHERE EXISTS { MATCH (enc)-[:IS_PART_OF]->(ep) } "
            "  AND coalesce(d.domain, '') = 'cancer_types' "
            "  AND toString(s.conceptId) IN $cancer_type_ids "
            "RETURN toString(p.id) AS pid, collect(DISTINCT toString(s.conceptId)) AS concept_ids",
            **{**params, "cancer_type_ids": cancer_all_ids},
        )

    disease_rows = client.run(
        f"{base}"
        "WITH p, ep ORDER BY p.id, ep.referral_date DESC "
        "WITH p, head(collect(ep)) AS ep "
        "WHERE ep IS NOT NULL "
        "WITH p "
        "OPTIONAL MATCH (p)-[r1:HAS_DISEASE]->(d1) "
        "  WHERE toString(d1.conceptId) IN $concept_ids "
        "AND r1.domain = 'comorbidities' "
        "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[r2:DOCUMENTS]->(d2) "
        "  WHERE toString(d2.conceptId) IN $concept_ids "
        "AND r2.domain = 'comorbidities' "
        "WITH p, collect(DISTINCT toString(d1.conceptId)) + collect(DISTINCT toString(d2.conceptId)) AS cids "
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

    cancer_order_index = {key: i for i, key in enumerate(cancer_order)}
    cancer_terms_by_pid: dict[str, list[str]] = {}
    for row in cancer_type_rows:
        pid = str(row.get("pid") or "")
        terms: set[str] = set()
        for cid in row.get("concept_ids") or []:
            term = cancer_id_to_term.get(str(cid))
            if term:
                terms.add(term)
        ordered_terms = sorted(
            terms,
            key=lambda t: (cancer_order_index.get(t, 999), t),
        )
        cancer_terms_by_pid[pid] = [
            cancer_group_key_to_display.get(term, term) for term in ordered_terms
        ]

    patients: dict[str, dict[str, Any]] = {}
    for row in patient_rows:
        pid = str(row.get("pid") or "")
        if not pid:
            continue
        oc = _outcome_label(
            bool(row.get("is_confirmed")),
            row.get("cancer_type_raw"),
            bool(row.get("has_referral_milestone")),
            cancer_terms_by_pid.get(pid),
        )
        patients[pid] = {
            "age_band": str(row.get("age_band") or "unknown"),
            "gender_bucket": str(row.get("gender_bucket") or "unknown"),
            "outcome": oc,
        }

    pid_terms: dict[str, set[str]] = {pid: set() for pid in patients}
    for term, pids in group_patients.items():
        for pid in pids:
            if pid in pid_terms:
                pid_terms[pid].add(term)

    total_patients = len(patients)
    if total_patients == 0:
        return {
            "total_patients": 0,
            "by_age_band": [],
            "by_gender": [],
            "by_referral_outcome": [],
        }

    # Age band
    buckets_age: dict[str, set[str]] = {}
    for pid, meta in patients.items():
        buckets_age.setdefault(meta["age_band"], set()).add(pid)
    by_age_band: list[dict[str, Any]] = []
    for band in _AGE_BAND_ORDER:
        pids = buckets_age.get(band, set())
        if not pids:
            continue
        denom = len(pids)
        by_age_band.append(
            {
                "slice_key": band,
                "slice_label": band,
                "cohort_n": denom,
                "rows": _condition_rows_for_slice(
                    pids,
                    pid_terms,
                    ordered_keys,
                    group_key_to_display,
                    group_key_to_bm_key,
                    denom,
                ),
            }
        )

    buckets_g: dict[str, set[str]] = {}
    for pid, meta in patients.items():
        buckets_g.setdefault(meta["gender_bucket"], set()).add(pid)
    gender_order = ("male", "female", "unknown")
    by_gender: list[dict[str, Any]] = []
    for g in gender_order:
        pids = buckets_g.get(g, set())
        if not pids:
            continue
        denom = len(pids)
        by_gender.append(
            {
                "slice_key": g,
                "slice_label": g.capitalize(),
                "cohort_n": denom,
                "rows": _condition_rows_for_slice(
                    pids,
                    pid_terms,
                    ordered_keys,
                    group_key_to_display,
                    group_key_to_bm_key,
                    denom,
                ),
            }
        )

    buckets_o: dict[str, set[str]] = {}
    for pid, meta in patients.items():
        buckets_o.setdefault(meta["outcome"], set()).add(pid)
    outcome_labels = sorted(buckets_o.keys(), key=lambda x: (x == "Other", x))
    by_referral_outcome: list[dict[str, Any]] = []
    for label in outcome_labels:
        pids = buckets_o[label]
        denom = len(pids)
        by_referral_outcome.append(
            {
                "slice_key": label,
                "slice_label": label,
                "cohort_n": denom,
                "rows": _condition_rows_for_slice(
                    pids,
                    pid_terms,
                    ordered_keys,
                    group_key_to_display,
                    group_key_to_bm_key,
                    denom,
                ),
            }
        )

    return {
        "total_patients": total_patients,
        "by_age_band": by_age_band,
        "by_gender": by_gender,
        "by_referral_outcome": by_referral_outcome,
    }
