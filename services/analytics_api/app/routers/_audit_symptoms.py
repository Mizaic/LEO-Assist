"""NCDA audit symptoms section.

Atlas trace:
  DO: DO-D5B9FE5F
  DI: DI-6E1B71A4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")

Aggregates distinct-per-patient symptom evidence around the referral on each
audited episode, plus PPV (Positive Predictive Value) by suspected cancer
type with explicit censoring buckets so current-year provisional values are
not confused with resolved cohorts.

Symptom evidence is read from the patient graph via
``Encounter-[:DOCUMENTS {domain: 'symptoms'}]->(s)`` where ``s.conceptId``
falls inside the ``ncda-symptoms`` ValueSet (concept + IS_A descendants).

Cancer-type slicing prefers SNOMED codes from the ``cancer_types``
ValueSet (DOCUMENTS domain ``cancer_types``) and falls back to the
canonical ``ep.cancer_type`` only when the episode has no coded evidence.

PPV definition (per suspected cancer type):

  - ``referrals_n``: episodes with a referral milestone whose
    ``ep.referral_date`` is in the audit window, grouped by suspected
    cancer type (referral-time SNOMED on the episode).
  - ``diagnosed_in_year_n``: of those, episodes with canonical
    ``confirmed_cancer_where('ep')`` and a diagnosis milestone in the
    same audit window.
  - ``no_cancer_in_year_n``: referral episodes resolved as no cancer
    (closed_benign, letter_inferred_benign, or closed without a
    diagnosis milestone).
  - ``diagnosed_following_year_n``: referrals that did not have a
    diagnosis in the window but DID have a confirmed cancer diagnosis
    in the following calendar year. These are excluded from the
    no-diagnosis count to avoid misclassifying delayed pathways as
    false positives.
  - ``unresolved_n``: referrals still in_progress / pending without a
    diagnosis or benign closure. These are reported separately so
    current-year PPV is not artificially deflated.
  - ``ppv_pct = diagnosed_in_year_n / max(referrals_n - unresolved_n -
    diagnosed_following_year_n, 1) * 100`` (resolved-only denominator).
"""

from __future__ import annotations

import json as _json
import logging
from datetime import date
from typing import Any, Optional

from libs.analytics import confirmed_cancer_where
from libs.domain_config.registry import DomainRegistry
from libs.neo4j_client.client import KnowledgeGraphClient, PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type

from ._audit_sections import _SAFE_BIRTH_DATE, _SAFE_REFERRAL_DATE

logger = logging.getLogger(__name__)


# Anchor symptom evidence to the referral. Default lookback follows the NCDA
# 12-month presenting-complaint window. ``ep`` and ``enc`` are bound by the
# caller; this expression returns true when ``enc.date`` is on/before the
# referral date and within the lookback window.
_SYMPTOM_WINDOW_PREDICATE = (
    "enc.date IS NOT NULL "
    "AND ep.referral_date IS NOT NULL "
    "AND enc.date <= date(toString(ep.referral_date)) "
    "AND enc.date >= coalesce("
    "  CASE WHEN trim(coalesce(toString(ep.first_presentation_date), '')) = '' "
    "    THEN NULL "
    "    ELSE date(toString(ep.first_presentation_date)) END, "
    "  date(toString(ep.referral_date)) - duration('P365D'))"
)

_REFERRAL_MILESTONE_EXISTS = (
    "EXISTS { MATCH (:Encounter)-[__ref:IS_PART_OF]->(ep) "
    "WHERE __ref.milestone_type = 'referral' }"
)

_DIAGNOSIS_MILESTONE_EXISTS = (
    "EXISTS { MATCH (:Encounter)-[__dx:IS_PART_OF]->(ep) "
    "WHERE __dx.milestone_type IN ['diagnosis', 'diagnosis_confirmed'] }"
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
    """Return (or lazily bootstrap) the DomainRegistry singleton."""
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


def _load_symptom_axis_bundle(
    registry: DomainRegistry,
    kg: KnowledgeGraphClient,
) -> Optional[dict[str, Any]]:
    """SNOMED symptom ValueSet groups expanded to descendants.

    Returns dict with:
      - ``concept_groups``: {top_label: [concept_id, ...]}
      - ``id_to_term``: {snomed_id_str: top_label}
      - ``group_key_to_display``: {top_label: friendly display}
      - ``all_ids``: sorted list of concept id strings (top + descendants)
      - ``ordered_keys``: stable ordering for heatmaps / radar
    """
    concept_groups = registry.get_concept_id_groups("symptoms", kg, depth=3)
    if not concept_groups:
        return None

    domain_concepts = registry.get_domain_concepts("symptoms")
    group_key_to_display: dict[str, str] = {}
    ordered_keys: list[str] = []
    seen_k: set[str] = set()
    for concept in domain_concepts:
        gk = concept.benchmark_key or concept.term
        display = concept.term or concept.preferred_term
        group_key_to_display.setdefault(gk, display)
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
        "id_to_term": id_to_term,
        "group_key_to_display": group_key_to_display,
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
        "id_to_term": id_to_term,
        "group_key_to_display": group_key_to_display,
        "all_ids": all_ids,
        "ordered_keys": ordered_keys,
    }


def _suspected_cancer_label(
    cancer_terms: Optional[list[str]],
    cancer_type_raw: Optional[str],
) -> str:
    """Pick a single suspected-cancer-type label.

    Preference order:
      1. SNOMED-coded cancer type buckets (cancer_types domain) on the
         episode encounters - this is the referral-time signal.
      2. ``ep.cancer_type`` normalised through ``normalise_cancer_type``.
      3. ``"No Information"`` sentinel.
    """
    if cancer_terms:
        return cancer_terms[0]
    raw = (cancer_type_raw or "").strip()
    if raw:
        return normalise_cancer_type(raw)
    return "No Information"


def _follow_year_window(date_to: Optional[str]) -> Optional[tuple[str, str]]:
    """Return the calendar year following ``date_to`` if both bounds parse.

    Used to detect referrals that received a cancer diagnosis in year Y+1.
    Returns None when date_to is missing or unparseable, in which case
    callers must skip the following-year exclusion.
    """
    if not date_to:
        return None
    try:
        d = date.fromisoformat(date_to)
    except ValueError:
        return None
    next_start = date(d.year + 1, 1, 1)
    next_end = date(d.year + 1, 12, 31)
    return (next_start.isoformat(), next_end.isoformat())


# ---------------------------------------------------------------------------
# Patient + episode shape
# ---------------------------------------------------------------------------


def _fetch_patient_episode_rows(
    base: str,
    params: dict,
    client: PatientGraphClient,
) -> list[dict[str, Any]]:
    """Resolve one primary episode per patient (latest referral_date)."""
    cc_pred = confirmed_cancer_where("ep")
    return client.run(
        f"{base}"
        "WITH p, ep ORDER BY p.id, ep.referral_date DESC "
        "WITH p, head(collect(ep)) AS ep "
        "WHERE ep IS NOT NULL "
        "WITH p, ep, "
        f"  {_SAFE_BIRTH_DATE} AS birth_date_value, "
        f"  {_SAFE_REFERRAL_DATE} AS referral_date_value, "
        f"  CASE WHEN ({cc_pred}) THEN true ELSE false END AS is_confirmed, "
        f"  {_REFERRAL_MILESTONE_EXISTS} AS has_referral_milestone, "
        f"  {_DIAGNOSIS_MILESTONE_EXISTS} AS has_diagnosis_milestone, "
        "  trim(coalesce(ep.cancer_type, '')) AS cancer_type_raw, "
        "  toString(ep.status) AS ep_status, "
        "  coalesce(ep.letter_inferred_benign, false) AS letter_benign "
        "WITH p, is_confirmed, cancer_type_raw, has_referral_milestone, "
        "  has_diagnosis_milestone, ep_status, letter_benign, "
        "  birth_date_value, referral_date_value, "
        "  CASE WHEN birth_date_value IS NOT NULL "
        "         AND referral_date_value IS NOT NULL "
        "    THEN duration.inDays(birth_date_value, referral_date_value).days / 365.0 "
        "    ELSE null END AS age_at_referral "
        "WITH p, is_confirmed, cancer_type_raw, has_referral_milestone, "
        "  has_diagnosis_milestone, ep_status, letter_benign, age_at_referral, "
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
        "RETURN toString(p.id) AS pid, age_band, gender_bucket, is_confirmed, "
        "  has_referral_milestone, has_diagnosis_milestone, ep_status, "
        "  letter_benign, cancer_type_raw",
        **params,
    )


def _fetch_cancer_type_terms(
    base: str,
    params: dict,
    client: PatientGraphClient,
    cancer_all_ids: list[str],
) -> list[dict[str, Any]]:
    if not cancer_all_ids:
        return []
    return client.run(
        f"{base}"
        "WITH p, ep ORDER BY p.id, ep.referral_date DESC "
        "WITH p, head(collect(ep)) AS ep "
        "WHERE ep IS NOT NULL "
        "MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[d:DOCUMENTS]->(s) "
        "WHERE EXISTS { MATCH (enc)-[:IS_PART_OF]->(ep) } "
        "  AND coalesce(d.domain, '') = 'cancer_types' "
        "  AND toString(s.conceptId) IN $cancer_type_ids "
        "RETURN toString(p.id) AS pid, "
        "  collect(DISTINCT toString(s.conceptId)) AS concept_ids",
        **{**params, "cancer_type_ids": cancer_all_ids},
    )


def _fetch_symptom_evidence(
    base: str,
    params: dict,
    client: PatientGraphClient,
    symptom_all_ids: list[str],
) -> list[dict[str, Any]]:
    """Distinct symptom concept ids per patient, anchored at referral."""
    if not symptom_all_ids:
        return []
    return client.run(
        f"{base}"
        "WITH p, ep ORDER BY p.id, ep.referral_date DESC "
        "WITH p, head(collect(ep)) AS ep "
        "WHERE ep IS NOT NULL "
        "MATCH (p)-[:HAS_ENCOUNTER]->(enc)-[d:DOCUMENTS]->(s) "
        "WHERE coalesce(d.domain, '') = 'symptoms' "
        "  AND toString(s.conceptId) IN $symptom_ids "
        f"  AND {_SYMPTOM_WINDOW_PREDICATE} "
        "RETURN toString(p.id) AS pid, "
        "  collect(DISTINCT toString(s.conceptId)) AS concept_ids",
        **{**params, "symptom_ids": symptom_all_ids},
    )


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _patient_symptom_terms(
    rows: list[dict[str, Any]],
    id_to_term: dict[str, str],
) -> dict[str, set[str]]:
    """Map pid -> set of top-level symptom group keys."""
    out: dict[str, set[str]] = {}
    for row in rows:
        pid = str(row.get("pid") or "")
        if not pid:
            continue
        terms: set[str] = set()
        for cid in row.get("concept_ids") or []:
            term = id_to_term.get(str(cid))
            if term:
                terms.add(term)
        if terms:
            out[pid] = terms
    return out


def _patient_cancer_terms(
    rows: list[dict[str, Any]],
    id_to_term: dict[str, str],
    group_key_to_display: dict[str, str],
    ordered_keys: list[str],
) -> dict[str, list[str]]:
    """Map pid -> ordered list of cancer-type display labels."""
    order_index = {key: i for i, key in enumerate(ordered_keys)}
    out: dict[str, list[str]] = {}
    for row in rows:
        pid = str(row.get("pid") or "")
        if not pid:
            continue
        terms: set[str] = set()
        for cid in row.get("concept_ids") or []:
            term = id_to_term.get(str(cid))
            if term:
                terms.add(term)
        ordered_terms = sorted(
            terms,
            key=lambda t: (order_index.get(t, 999), t),
        )
        out[pid] = [group_key_to_display.get(t, t) for t in ordered_terms]
    return out


def _symptom_rows_for_slice(
    slice_pids: set[str],
    pid_terms: dict[str, set[str]],
    ordered_keys: list[str],
    group_key_to_display: dict[str, str],
    denom: int,
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for key in ordered_keys:
        n = sum(1 for pid in slice_pids if key in pid_terms.get(pid, set()))
        pct = round(n * 100.0 / denom, 1) if denom else 0.0
        rows_out.append(
            {
                "symptom": group_key_to_display.get(key, key),
                "n": n,
                "pct": pct,
            }
        )
    return rows_out


def _heatmap_rows(
    bucket_pids: dict[str, set[str]],
    pid_terms: dict[str, set[str]],
    ordered_symptom_keys: list[str],
    symptom_display: dict[str, str],
    bucket_order: list[str],
) -> list[dict[str, Any]]:
    """Long-format heatmap rows: one entry per (bucket, symptom) pair.

    Each row carries the cohort denominator for that bucket so the UI
    can render % of slice without re-deriving denominators.
    """
    rows: list[dict[str, Any]] = []
    seen_buckets = [b for b in bucket_order if b in bucket_pids and bucket_pids[b]]
    extras = sorted(
        b for b in bucket_pids if bucket_pids[b] and b not in seen_buckets
    )
    for bucket in seen_buckets + extras:
        pids = bucket_pids.get(bucket) or set()
        denom = len(pids)
        if denom == 0:
            continue
        for key in ordered_symptom_keys:
            n = sum(1 for pid in pids if key in pid_terms.get(pid, set()))
            pct = round(n * 100.0 / denom, 1) if denom else 0.0
            rows.append(
                {
                    "bucket_key": bucket,
                    "bucket_label": bucket,
                    "cohort_n": denom,
                    "symptom": symptom_display.get(key, key),
                    "n": n,
                    "pct": pct,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# PPV
# ---------------------------------------------------------------------------


def _resolve_ep_status(
    is_confirmed: bool,
    has_diagnosis_milestone: bool,
    ep_status: str,
    letter_benign: bool,
) -> str:
    """Bucket the episode into one of: diagnosed, no_cancer, unresolved."""
    if is_confirmed and has_diagnosis_milestone:
        return "diagnosed"
    status = (ep_status or "").lower()
    if (
        status in {"closed_benign", "closed", "completed"}
        or letter_benign
    ):
        return "no_cancer"
    return "unresolved"


def _fetch_following_year_diagnosis_pids(
    base: str,
    params: dict,
    client: PatientGraphClient,
    follow_window: tuple[str, str],
) -> set[str]:
    """Patients with a confirmed cancer in the calendar year after the audit window.

    The query intentionally drops the inherited ``date_from`` / ``date_to``
    filters from ``params`` (they constrain the audit window) and applies
    the follow-year window directly.
    """
    cc_pred = confirmed_cancer_where("ep2")
    follow_params = {k: v for k, v in params.items() if k not in {"date_from", "date_to"}}
    rows = client.run(
        f"{base}"
        "WITH DISTINCT p "
        "MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep2:EpisodeOfCare) "
        "WHERE NOT ep2.status IN "
        "['merged', 'closed_phantom', 'closed_related'] "
        f"  AND {cc_pred} "
        "  AND ep2.referral_date IS NOT NULL "
        "  AND ep2.referral_date >= $follow_from "
        "  AND ep2.referral_date <= $follow_to "
        "RETURN DISTINCT toString(p.id) AS pid",
        **{
            **follow_params,
            "follow_from": follow_window[0],
            "follow_to": follow_window[1],
        },
    )
    return {str(r.get("pid") or "") for r in rows if r.get("pid")}


def _q_ppv_by_suspected_cancer_type(
    base: str,
    params: dict,
    client: PatientGraphClient,
    patient_rows: list[dict[str, Any]],
    pid_cancer_terms: dict[str, list[str]],
    date_to: Optional[str],
) -> list[dict[str, Any]]:
    """Compute PPV bands per suspected cancer type.

    Denominator is the referral cohort: episodes with a referral milestone
    in the audit window. Numerator is canonical confirmed-cancer.
    Following-year diagnoses and unresolved episodes are reported in
    separate buckets so the UI can flag provisional values.
    """
    follow_window = _follow_year_window(date_to)
    if follow_window is not None:
        try:
            following_pids = _fetch_following_year_diagnosis_pids(
                base, params, client, follow_window
            )
        except Exception:  # noqa: BLE001
            logger.exception("Following-year diagnosis lookup failed")
            following_pids = set()
    else:
        following_pids = set()

    buckets: dict[str, dict[str, int]] = {}

    for row in patient_rows:
        pid = str(row.get("pid") or "")
        if not pid:
            continue
        if not bool(row.get("has_referral_milestone")):
            continue
        label = _suspected_cancer_label(
            pid_cancer_terms.get(pid),
            row.get("cancer_type_raw"),
        )
        bucket = buckets.setdefault(
            label,
            {
                "referrals_n": 0,
                "diagnosed_in_year_n": 0,
                "no_cancer_in_year_n": 0,
                "diagnosed_following_year_n": 0,
                "unresolved_n": 0,
            },
        )
        bucket["referrals_n"] += 1
        status = _resolve_ep_status(
            bool(row.get("is_confirmed")),
            bool(row.get("has_diagnosis_milestone")),
            str(row.get("ep_status") or ""),
            bool(row.get("letter_benign")),
        )
        if status == "diagnosed":
            bucket["diagnosed_in_year_n"] += 1
        elif pid in following_pids:
            bucket["diagnosed_following_year_n"] += 1
        elif status == "no_cancer":
            bucket["no_cancer_in_year_n"] += 1
        else:
            bucket["unresolved_n"] += 1

    rows_out: list[dict[str, Any]] = []
    for label, b in buckets.items():
        resolved = (
            b["referrals_n"]
            - b["unresolved_n"]
            - b["diagnosed_following_year_n"]
        )
        ppv_pct = (
            round(b["diagnosed_in_year_n"] * 100.0 / resolved, 1)
            if resolved > 0
            else None
        )
        rows_out.append(
            {
                "cancer_type": label,
                "referrals_n": b["referrals_n"],
                "diagnosed_in_year_n": b["diagnosed_in_year_n"],
                "no_cancer_in_year_n": b["no_cancer_in_year_n"],
                "diagnosed_following_year_n": b["diagnosed_following_year_n"],
                "unresolved_n": b["unresolved_n"],
                "ppv_pct": ppv_pct,
                "provisional": (
                    b["unresolved_n"] > 0 or b["diagnosed_following_year_n"] > 0
                ),
            }
        )
    rows_out.sort(
        key=lambda r: (-int(r.get("referrals_n") or 0), str(r.get("cancer_type") or ""))
    )
    return rows_out


# ---------------------------------------------------------------------------
# Main section query
# ---------------------------------------------------------------------------


def _q_symptoms(
    base: str,
    params: dict,
    client: PatientGraphClient,
    date_to: Optional[str] = None,
) -> dict:
    """Symptom prevalence at referral plus PPV by suspected cancer type."""
    kg = KnowledgeGraphClient()
    try:
        registry = _ensure_registry(kg)
        symptom_bundle = _load_symptom_axis_bundle(registry, kg)
        cancer_bundle = _load_cancer_type_axis_bundle(registry, kg)
    except Exception:  # noqa: BLE001
        kg.close()
        logger.exception("Failed to bootstrap registry / symptom axes")
        return _empty_symptoms_payload()
    kg.close()

    if symptom_bundle is None:
        return _empty_symptoms_payload()

    symptom_id_to_term = symptom_bundle["id_to_term"]
    symptom_all_ids = symptom_bundle["all_ids"]
    symptom_ordered_keys = symptom_bundle["ordered_keys"]
    symptom_display = symptom_bundle["group_key_to_display"]

    cancer_id_to_term: dict[str, str] = {}
    cancer_display: dict[str, str] = {}
    cancer_all_ids: list[str] = []
    cancer_order: list[str] = []
    if cancer_bundle is not None:
        cancer_id_to_term = cancer_bundle["id_to_term"]
        cancer_display = cancer_bundle["group_key_to_display"]
        cancer_all_ids = cancer_bundle["all_ids"]
        cancer_order = cancer_bundle["ordered_keys"]

    patient_rows = _fetch_patient_episode_rows(base, params, client)
    if not patient_rows:
        return _empty_symptoms_payload()

    cancer_rows = _fetch_cancer_type_terms(base, params, client, cancer_all_ids)
    pid_cancer_terms = _patient_cancer_terms(
        cancer_rows, cancer_id_to_term, cancer_display, cancer_order
    )

    symptom_rows = _fetch_symptom_evidence(base, params, client, symptom_all_ids)
    pid_symptom_terms = _patient_symptom_terms(symptom_rows, symptom_id_to_term)

    total_referrals = sum(
        1 for r in patient_rows if bool(r.get("has_referral_milestone"))
    )
    cohort_n = len(patient_rows)
    denom = max(cohort_n, 1)

    symptom_counts: dict[str, int] = {key: 0 for key in symptom_ordered_keys}
    for terms in pid_symptom_terms.values():
        for t in terms:
            if t in symptom_counts:
                symptom_counts[t] += 1

    symptoms = [
        {
            "symptom": symptom_display.get(key, key),
            "n": symptom_counts.get(key, 0),
            "pct": round(symptom_counts.get(key, 0) * 100.0 / denom, 1),
        }
        for key in symptom_ordered_keys
    ]
    symptoms.sort(key=lambda r: (-r["n"], r["symptom"]))

    suspected_pids: dict[str, set[str]] = {}
    diagnosed_pids: dict[str, set[str]] = {}
    for row in patient_rows:
        pid = str(row.get("pid") or "")
        if not pid:
            continue
        suspected_label = _suspected_cancer_label(
            pid_cancer_terms.get(pid),
            row.get("cancer_type_raw"),
        )
        suspected_pids.setdefault(suspected_label, set()).add(pid)
        if bool(row.get("is_confirmed")):
            confirmed_label = (
                pid_cancer_terms.get(pid, [None])[0]
                if pid_cancer_terms.get(pid)
                else normalise_cancer_type(
                    (row.get("cancer_type_raw") or "").strip() or "No Information"
                )
            )
            diagnosed_pids.setdefault(confirmed_label or "No Information", set()).add(pid)

    cancer_bucket_order = [
        cancer_display.get(k, k) for k in cancer_order
    ]

    heatmap_by_suspected = _heatmap_rows(
        suspected_pids,
        pid_symptom_terms,
        symptom_ordered_keys,
        symptom_display,
        cancer_bucket_order,
    )
    heatmap_by_diagnosed = _heatmap_rows(
        diagnosed_pids,
        pid_symptom_terms,
        symptom_ordered_keys,
        symptom_display,
        cancer_bucket_order,
    )

    ppv_rows = _q_ppv_by_suspected_cancer_type(
        base, params, client, patient_rows, pid_cancer_terms, date_to
    )

    return {
        "total_referrals": total_referrals,
        "cohort_n": cohort_n,
        "symptom_axis": [
            {
                "key": key,
                "symptom": symptom_display.get(key, key),
            }
            for key in symptom_ordered_keys
        ],
        "symptoms": symptoms,
        "heatmap_by_suspected_cancer_type": heatmap_by_suspected,
        "heatmap_by_diagnosed_cancer_type": heatmap_by_diagnosed,
        "ppv_by_suspected_cancer_type": ppv_rows,
    }


def _empty_symptoms_payload() -> dict:
    return {
        "total_referrals": 0,
        "cohort_n": 0,
        "symptom_axis": [],
        "symptoms": [],
        "heatmap_by_suspected_cancer_type": [],
        "heatmap_by_diagnosed_cancer_type": [],
        "ppv_by_suspected_cancer_type": [],
    }


# ---------------------------------------------------------------------------
# Drilldown
# ---------------------------------------------------------------------------


def _q_symptoms_drilldown(
    base: str,
    params: dict,
    client: PatientGraphClient,
) -> dict:
    """Symptom prevalence sliced by suspected/diagnosed cancer, age, gender."""
    kg = KnowledgeGraphClient()
    try:
        registry = _ensure_registry(kg)
        symptom_bundle = _load_symptom_axis_bundle(registry, kg)
        cancer_bundle = _load_cancer_type_axis_bundle(registry, kg)
    except Exception:  # noqa: BLE001
        kg.close()
        logger.exception("Failed to bootstrap registry / symptom axes")
        return _empty_drilldown_payload()
    kg.close()

    if symptom_bundle is None:
        return _empty_drilldown_payload()

    symptom_id_to_term = symptom_bundle["id_to_term"]
    symptom_all_ids = symptom_bundle["all_ids"]
    symptom_ordered_keys = symptom_bundle["ordered_keys"]
    symptom_display = symptom_bundle["group_key_to_display"]

    cancer_id_to_term: dict[str, str] = {}
    cancer_display: dict[str, str] = {}
    cancer_all_ids: list[str] = []
    cancer_order: list[str] = []
    if cancer_bundle is not None:
        cancer_id_to_term = cancer_bundle["id_to_term"]
        cancer_display = cancer_bundle["group_key_to_display"]
        cancer_all_ids = cancer_bundle["all_ids"]
        cancer_order = cancer_bundle["ordered_keys"]

    patient_rows = _fetch_patient_episode_rows(base, params, client)
    if not patient_rows:
        return _empty_drilldown_payload()

    cancer_rows = _fetch_cancer_type_terms(base, params, client, cancer_all_ids)
    pid_cancer_terms = _patient_cancer_terms(
        cancer_rows, cancer_id_to_term, cancer_display, cancer_order
    )

    symptom_rows = _fetch_symptom_evidence(base, params, client, symptom_all_ids)
    pid_symptom_terms = _patient_symptom_terms(symptom_rows, symptom_id_to_term)

    age_buckets: dict[str, set[str]] = {}
    gender_buckets: dict[str, set[str]] = {}
    suspected_buckets: dict[str, set[str]] = {}
    diagnosed_buckets: dict[str, set[str]] = {}
    for row in patient_rows:
        pid = str(row.get("pid") or "")
        if not pid:
            continue
        age_buckets.setdefault(str(row.get("age_band") or "unknown"), set()).add(pid)
        gender_buckets.setdefault(
            str(row.get("gender_bucket") or "unknown"), set()
        ).add(pid)
        suspected_label = _suspected_cancer_label(
            pid_cancer_terms.get(pid),
            row.get("cancer_type_raw"),
        )
        suspected_buckets.setdefault(suspected_label, set()).add(pid)
        if bool(row.get("is_confirmed")):
            confirmed = (
                pid_cancer_terms.get(pid, [None])[0]
                if pid_cancer_terms.get(pid)
                else normalise_cancer_type(
                    (row.get("cancer_type_raw") or "").strip() or "No Information"
                )
            )
            diagnosed_buckets.setdefault(
                confirmed or "No Information", set()
            ).add(pid)

    by_age_band = _slice_table(
        age_buckets, _AGE_BAND_ORDER, pid_symptom_terms,
        symptom_ordered_keys, symptom_display,
    )
    gender_order = ("male", "female", "unknown")
    by_gender = _slice_table(
        gender_buckets, gender_order, pid_symptom_terms,
        symptom_ordered_keys, symptom_display,
        label_fn=lambda g: g.capitalize(),
    )
    cancer_bucket_order = [cancer_display.get(k, k) for k in cancer_order]
    by_suspected = _slice_table(
        suspected_buckets,
        tuple(cancer_bucket_order),
        pid_symptom_terms,
        symptom_ordered_keys,
        symptom_display,
        include_extras=True,
    )
    by_diagnosed = _slice_table(
        diagnosed_buckets,
        tuple(cancer_bucket_order),
        pid_symptom_terms,
        symptom_ordered_keys,
        symptom_display,
        include_extras=True,
    )

    return {
        "total_patients": len(patient_rows),
        "symptom_axis": [
            {"key": k, "symptom": symptom_display.get(k, k)}
            for k in symptom_ordered_keys
        ],
        "by_age_band": by_age_band,
        "by_gender": by_gender,
        "by_suspected_cancer_type": by_suspected,
        "by_diagnosed_cancer_type": by_diagnosed,
    }


def _slice_table(
    bucket_pids: dict[str, set[str]],
    bucket_order: tuple[str, ...] | tuple,
    pid_terms: dict[str, set[str]],
    ordered_keys: list[str],
    group_display: dict[str, str],
    label_fn=None,
    include_extras: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen = list(bucket_order) if bucket_order else []
    for key in seen:
        pids = bucket_pids.get(key) or set()
        if not pids:
            continue
        denom = len(pids)
        rows.append(
            {
                "slice_key": key,
                "slice_label": label_fn(key) if label_fn else key,
                "cohort_n": denom,
                "rows": _symptom_rows_for_slice(
                    pids, pid_terms, ordered_keys, group_display, denom
                ),
            }
        )
    if include_extras:
        leftovers = sorted(
            k for k in bucket_pids if bucket_pids[k] and k not in seen
        )
        for key in leftovers:
            pids = bucket_pids[key]
            denom = len(pids)
            rows.append(
                {
                    "slice_key": key,
                    "slice_label": label_fn(key) if label_fn else key,
                    "cohort_n": denom,
                    "rows": _symptom_rows_for_slice(
                        pids, pid_terms, ordered_keys, group_display, denom
                    ),
                }
            )
    return rows


def _empty_drilldown_payload() -> dict:
    return {
        "total_patients": 0,
        "symptom_axis": [],
        "by_age_band": [],
        "by_gender": [],
        "by_suspected_cancer_type": [],
        "by_diagnosed_cancer_type": [],
    }


__all__ = [
    "_ensure_registry",
    "_q_symptoms",
    "_q_symptoms_drilldown",
]
