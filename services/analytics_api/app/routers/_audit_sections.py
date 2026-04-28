"""NCDA audit section query functions.

Atlas trace:
  DO: DO-A6D3FE39
  DI: DI-BA2C8F3E
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A6D3FE39")

Each ``_q_*`` function takes (base_cypher, params, client) and returns
the section-specific payload.  They are called by ``_run_multi_scope``
for practice, alliance, and england scopes.

Cohort selection goes through libs.analytics.cohorts so that every
audit endpoint agrees on what 'confirmed cancer episode' means
(DI-LEO-AI-134, R-LEO-AI-092).
"""

from __future__ import annotations

from typing import Optional

from libs.analytics import confirmed_cancer_where
from libs.analytics.ncda_ethnicity_snomed import (
    load_ncda_ethnicity_benchmark_table,
    load_ncda_ethnicity_snomed_ids,
)
from libs.neo4j_client.client import PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type

_SAFE_BIRTH_DATE = (
    "CASE "
    "  WHEN trim(coalesce(toString(p.birthDate), '')) = '' THEN NULL "
    "  ELSE date(toString(p.birthDate)) "
    "END"
)
_SAFE_REFERRAL_DATE = (
    "CASE "
    "  WHEN trim(coalesce(toString(ep.referral_date), '')) = '' THEN NULL "
    "  ELSE date(toString(ep.referral_date)) "
    "END"
)
_SAFE_FIRST_PRESENTATION_DATE = (
    "CASE "
    "  WHEN trim(coalesce(toString(ep.first_presentation_date), '')) = '' THEN NULL "
    "  ELSE date(toString(ep.first_presentation_date)) "
    "END"
)


# ---------------------------------------------------------------------------
# Cancer type
# ---------------------------------------------------------------------------


def _q_cancer_type(base: str, params: dict, client: PatientGraphClient) -> list:
    # Post-migration every ep.cancer_type is one of the canonical NCDA
    # values (libs.oncology.cancer_types). Normalise on read as a
    # safety net for any value the migration missed; collapse synonyms
    # into a single bucket. The Unknown Primary / No Information / Other
    # sentinels are intentionally surfaced (they were silently hidden
    # under the legacy exclusion list).
    rows = client.run(
        f"{base}"
        f"AND {confirmed_cancer_where('ep')} "
        "AND ep.cancer_type IS NOT NULL "
        "RETURN ep.cancer_type AS cancer_type, count(DISTINCT ep) AS n",
        **params,
    )
    by_canonical: dict[str, int] = {}
    for r in rows:
        canonical = normalise_cancer_type(r.get("cancer_type"))
        by_canonical[canonical] = by_canonical.get(canonical, 0) + int(r["n"] or 0)
    total = sum(by_canonical.values()) or 1
    ordered = sorted(by_canonical.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        {
            "cancer_type": canonical,
            "n": n,
            "pct": round(n * 100.0 / total, 1),
        }
        for canonical, n in ordered
    ]


# ---------------------------------------------------------------------------
# Cancer stage
# ---------------------------------------------------------------------------


def _q_cancer_stage(base: str, params: dict, client: PatientGraphClient) -> dict:
    confirmed_base = (
        f"{base}"
        f"AND {confirmed_cancer_where('ep')} "
    )

    rows = client.run(
        f"{confirmed_base}"
        "RETURN coalesce(ep.cancer_stage, 'unknown') AS stage_group, "
        "count(DISTINCT ep) AS n "
        "ORDER BY stage_group",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    by_stage = [
        {
            "stage_group": r["stage_group"],
            "n": r["n"],
            "pct": round(r["n"] * 100.0 / total, 1),
        }
        for r in rows
    ]

    by_system_rows = client.run(
        f"{confirmed_base}"
        "RETURN coalesce(ep.staging_system, 'unknown') AS staging_system, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC, staging_system",
        **params,
    )
    by_source_rows = client.run(
        f"{confirmed_base}"
        "RETURN coalesce(ep.staging_source, 'none') AS staging_source, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC, staging_source",
        **params,
    )
    group_rows = client.run(
        f"{confirmed_base}"
        "WITH ep "
        "WHERE coalesce(ep.cancer_stage_group, '') <> '' "
        "RETURN ep.cancer_stage_group AS cancer_stage_group, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC, cancer_stage_group",
        **params,
    )
    by_cancer_type_rows = client.run(
        f"{confirmed_base}"
        "WITH coalesce(ep.cancer_type, 'unknown') AS cancer_type, "
        "     coalesce(ep.cancer_stage, 'unknown') AS stage_group, "
        "     count(DISTINCT ep) AS n "
        "WITH cancer_type, collect({stage_group: stage_group, n: n}) AS buckets, "
        "sum(n) AS total "
        "UNWIND buckets AS bucket "
        "RETURN cancer_type, "
        "       bucket.stage_group AS stage_group, "
        "       bucket.n AS n, "
        "       CASE WHEN total > 0 "
        "         THEN round((toFloat(bucket.n) * 1000.0) / toFloat(total)) / 10.0 "
        "         ELSE 0.0 "
        "       END AS pct "
        "ORDER BY cancer_type, stage_group",
        **params,
    )

    denom_row = client.run(
        f"{confirmed_base}RETURN count(DISTINCT ep) AS denom",
        **params,
    )
    numerator_row = client.run(
        f"{confirmed_base}"
        "RETURN count(DISTINCT CASE WHEN coalesce(ep.cancer_stage, 'unknown') "
        "<> 'unknown' THEN ep END) AS numer",
        **params,
    )
    denom = int((denom_row[0] or {}).get("denom") or 0) if denom_row else 0
    numer = int((numerator_row[0] or {}).get("numer") or 0) if numerator_row else 0
    coverage = round((numer * 100.0 / denom), 1) if denom > 0 else 0.0

    return {
        "rows": by_stage,
        "by_stage_group": by_stage,
        "by_system": [
            {"staging_system": r["staging_system"], "n": r["n"]} for r in by_system_rows
        ],
        "by_source": [
            {"staging_source": r["staging_source"], "n": r["n"]} for r in by_source_rows
        ],
        "by_stage_group_detail": [
            {"cancer_stage_group": r["cancer_stage_group"], "n": r["n"]}
            for r in group_rows
        ],
        "by_cancer_type": [
            {
                "cancer_type": normalise_cancer_type(r["cancer_type"]),
                "stage_group": r["stage_group"],
                "n": r["n"],
                "pct": r["pct"],
            }
            for r in by_cancer_type_rows
        ],
        "coverage_pct": coverage,
        "coverage_numerator": numer,
        "coverage_denominator": denom,
    }


# ---------------------------------------------------------------------------
# Demographics
# ---------------------------------------------------------------------------


def _q_demographics(base: str, params: dict, client: PatientGraphClient) -> dict:
    sex_rows = client.run(
        f"{base}"
        "AND p.gender IS NOT NULL "
        "RETURN p.gender AS gender, count(DISTINCT p) AS n ORDER BY n DESC",
        **params,
    )
    age_rows = client.run(
        f"{base}"
        "WITH p, ep, "
        f"  {_SAFE_BIRTH_DATE} AS birth_date_value, "
        f"  {_SAFE_REFERRAL_DATE} AS referral_date_value "
        "WHERE birth_date_value IS NOT NULL AND referral_date_value IS NOT NULL "
        "WITH p, ep, "
        "  duration.inDays(birth_date_value, "
        "referral_date_value).days / 365 AS age_at_referral "
        "WITH age_at_referral, "
        "  CASE WHEN age_at_referral < 25 THEN '0-24' "
        "       WHEN age_at_referral < 50 THEN '25-49' "
        "       WHEN age_at_referral < 65 THEN '50-64' "
        "       WHEN age_at_referral < 75 THEN '65-74' "
        "       WHEN age_at_referral < 85 THEN '75-84' "
        "       ELSE '85+' END AS age_band "
        "RETURN age_band, count(*) AS n ORDER BY age_band",
        **params,
    )
    age_vals_rows = client.run(
        f"{base}"
        "WITH p, ep, "
        f"  {_SAFE_BIRTH_DATE} AS birth_date_value, "
        f"  {_SAFE_REFERRAL_DATE} AS referral_date_value "
        "WHERE birth_date_value IS NOT NULL AND referral_date_value IS NOT NULL "
        "WITH duration.inDays(birth_date_value, "
        "referral_date_value).days / 365 AS age "
        "RETURN age ORDER BY age",
        **params,
    )
    eth_rows = client.run(
        f"{base}"
        "AND p.ethnicity IS NOT NULL "
        "RETURN p.ethnicity AS ethnicity, count(DISTINCT p) AS n ORDER BY n DESC",
        **params,
    )
    # DI-87D92943: age x sex cross-tab so the audit demographics evolution
    # cards can render a true population pyramid per calendar-year window.
    # `pct` is expressed as percentage of the total demographic population
    # for that window (not row-stochastic by gender) so cards stay
    # directly comparable across years.
    age_band_by_sex_rows = client.run(
        f"{base}"
        "AND p.gender IS NOT NULL "
        "WITH p, ep, "
        f"  {_SAFE_BIRTH_DATE} AS birth_date_value, "
        f"  {_SAFE_REFERRAL_DATE} AS referral_date_value "
        "WHERE birth_date_value IS NOT NULL AND referral_date_value IS NOT NULL "
        "WITH p, "
        "  duration.inDays(birth_date_value, "
        "referral_date_value).days / 365 AS age_at_referral "
        "WITH p.gender AS gender, "
        "  CASE WHEN age_at_referral < 25 THEN '0-24' "
        "       WHEN age_at_referral < 50 THEN '25-49' "
        "       WHEN age_at_referral < 65 THEN '50-64' "
        "       WHEN age_at_referral < 75 THEN '65-74' "
        "       WHEN age_at_referral < 85 THEN '75-84' "
        "       ELSE '85+' END AS age_band "
        "RETURN gender, age_band, count(*) AS n ORDER BY gender, age_band",
        **params,
    )
    ts = sum(r["n"] for r in sex_rows) or 1
    ta = sum(r["n"] for r in age_rows) or 1
    te = sum(r["n"] for r in eth_rows) or 1
    tas = sum(r["n"] for r in age_band_by_sex_rows) or 1
    # NCDA ethnicity ValueSet (configs/snomed/snomed_ncda_ethnicity_mapping.json):
    # distinct patients per SNOMED coded via Encounter-[:DOCUMENTS {domain:
    # 'ethnicity'}]->(s) where s.conceptId is in the benchmark set. Supports
    # radar charts aligned to terminology ValueSet ncda-ethnicity.
    eth_snomed_ids = load_ncda_ethnicity_snomed_ids()
    benchmark_by_snomed = {
        row["snomed"]: row for row in load_ncda_ethnicity_benchmark_table()
    }
    cohort_n = sum(r["n"] for r in sex_rows)
    patients_with_ethnicity_snomed_n = 0
    if eth_snomed_ids:
        merged_eth_params = {**params, "eth_snomed_ids": list(eth_snomed_ids)}
        eth_snomed_rows = client.run(
            f"{base}"
            "WITH DISTINCT p "
            "MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter)-[d:DOCUMENTS]->(s) "
            "WHERE coalesce(d.domain, '') = 'ethnicity' "
            "  AND s.conceptId IS NOT NULL "
            "  AND toString(s.conceptId) IN $eth_snomed_ids "
            "RETURN toString(s.conceptId) AS snomed, count(DISTINCT p) AS n "
            "ORDER BY snomed",
            **merged_eth_params,
        )
        eth_cover_rows = client.run(
            f"{base}"
            "WITH DISTINCT p "
            "MATCH (p)-[:HAS_ENCOUNTER]->(:Encounter)-[d:DOCUMENTS]->(s) "
            "WHERE coalesce(d.domain, '') = 'ethnicity' "
            "  AND s.conceptId IS NOT NULL "
            "  AND toString(s.conceptId) IN $eth_snomed_ids "
            "RETURN count(DISTINCT p) AS n",
            **merged_eth_params,
        )
        if eth_cover_rows:
            patients_with_ethnicity_snomed_n = int(eth_cover_rows[0]["n"] or 0)
    else:
        eth_snomed_rows = []
    counts_by_snomed = {str(r["snomed"]): int(r["n"] or 0) for r in eth_snomed_rows}
    ethnicity_snomed_coverage_pct = (
        round(patients_with_ethnicity_snomed_n * 100.0 / cohort_n, 1)
        if cohort_n > 0
        else None
    )
    age_vals = sorted([r["age"] for r in age_vals_rows if r.get("age") is not None])
    n_age = len(age_vals)
    median_age = (
        round(
            (
                age_vals[n_age // 2]
                if n_age % 2
                else (age_vals[n_age // 2 - 1] + age_vals[n_age // 2]) / 2
            ),
            1,
        )
        if age_vals
        else None
    )
    return {
        "sex": [
            {
                "gender": r["gender"],
                "n": r["n"],
                "pct": round(r["n"] * 100.0 / ts, 1),
            }
            for r in sex_rows
        ],
        "age_bands": [
            {
                "age_band": r["age_band"],
                "n": r["n"],
                "pct": round(r["n"] * 100.0 / ta, 1),
            }
            for r in age_rows
        ],
        "median_age": median_age,
        "ethnicity": [
            {
                "ethnicity": r["ethnicity"],
                "n": r["n"],
                "pct": round(r["n"] * 100.0 / te, 1),
            }
            for r in eth_rows
        ],
        "age_band_by_sex": [
            {
                "gender": r["gender"],
                "age_band": r["age_band"],
                "n": r["n"],
                "pct": round(r["n"] * 100.0 / tas, 1),
            }
            for r in age_band_by_sex_rows
        ],
        "ethnicity_by_snomed": [
            {
                "snomed": sid,
                "benchmark_key": str(benchmark_by_snomed[sid]["benchmark_key"]),
                "preferred_term": str(benchmark_by_snomed[sid]["preferred_term"]),
                "n": counts_by_snomed.get(sid, 0),
                "pct": round(counts_by_snomed.get(sid, 0) * 100.0 / ts, 1),
            }
            for sid in sorted(benchmark_by_snomed.keys())
        ],
        "demographics_cohort_n": cohort_n,
        "patients_with_ethnicity_snomed_n": patients_with_ethnicity_snomed_n,
        "ethnicity_snomed_coverage_pct": ethnicity_snomed_coverage_pct,
    }


# ---------------------------------------------------------------------------
# Place of presentation
# ---------------------------------------------------------------------------


def _q_place(base: str, params: dict, client: PatientGraphClient) -> list:
    rows = client.run(
        f"{base}"
        "RETURN coalesce(ep.place_of_presentation, 'Not recorded') AS place, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    return [
        {
            "place": r["place"],
            "n": r["n"],
            "pct": round(r["n"] * 100.0 / total, 1),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Consultations
# ---------------------------------------------------------------------------


def _q_consultations(base: str, params: dict, client: PatientGraphClient) -> dict:
    # NCDA definition: GP consultations BEFORE referral to secondary care.
    # Window: first_presentation_date (or 365d before referral) up to referral.
    _PRE_REF = (
        f"WITH ep, p, enc, {_SAFE_REFERRAL_DATE} AS referral_date_value, "
        f"{_SAFE_FIRST_PRESENTATION_DATE} AS first_presentation_date_value "
        "  WHERE enc.date IS NOT NULL AND referral_date_value IS NOT NULL "
        "    AND coalesce(enc.classification_content_type, 'clinical') = 'clinical' "
        "    AND enc.date <= referral_date_value "
        "    AND enc.date >= coalesce("
        "      first_presentation_date_value, "
        "      referral_date_value - duration('P365D')"
        "    ) "
    )
    rows = client.run(
        f"{base}"
        "WITH DISTINCT ep, p "
        "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
        f"{_PRE_REF}"
        "WITH ep, count(enc) AS consult_count "
        "RETURN "
        "  sum(CASE WHEN consult_count < 3 THEN 1 ELSE 0 END) AS fewer_than_3, "
        "  sum(CASE WHEN consult_count >= 3 THEN 1 ELSE 0 END) AS three_or_more, "
        "  count(DISTINCT ep) AS total_episodes, "
        "  avg(consult_count) AS avg_consultations",
        **params,
    )
    per_ep = client.run(
        f"{base}"
        "WITH DISTINCT ep, p "
        "OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter) "
        f"{_PRE_REF}"
        "WITH ep, count(enc) AS consult_count "
        "RETURN consult_count ORDER BY consult_count",
        **params,
    )
    counts = sorted(
        [r["consult_count"] for r in per_ep if r.get("consult_count") is not None]
    )
    n = len(counts)
    median_val = (
        counts[n // 2]
        if n % 2
        else ((counts[n // 2 - 1] + counts[n // 2]) / 2) if n else None
    )
    iqr_low = counts[n // 4] if n else None
    iqr_high = counts[3 * n // 4] if n else None

    s = rows[0] if rows else {}
    total = s.get("total_episodes") or 1
    fewer = s.get("fewer_than_3") or 0
    three_plus = s.get("three_or_more") or 0
    return {
        "fewer_than_3_pct": round(fewer * 100.0 / total, 1),
        "three_or_more_pct": round(three_plus * 100.0 / total, 1),
        "fewer_than_3_n": fewer,
        "three_or_more_n": three_plus,
        "total_episodes": total,
        "median_consultations": median_val,
        "iqr_low": iqr_low,
        "iqr_high": iqr_high,
    }


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------

_INVESTIGATION_TYPES = (
    "['investigation','blood_test','imaging','urinalysis',"
    "'biopsy','endoscopy','symptomatic_fit','other_investigation']"
)


def _q_investigations(base: str, params: dict, client: PatientGraphClient) -> dict:
    summary_rows = client.run(
        f"{base}"
        "WITH DISTINCT ep "
        "OPTIONAL MATCH (enc:Encounter)-[:IS_PART_OF]->(ep) "
        f"  WHERE enc.encounter_type IN {_INVESTIGATION_TYPES} "
        "WITH ep, count(enc) AS inv_count "
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        "  sum(CASE WHEN inv_count > 0 THEN 1 ELSE 0 END) AS has_investigation, "
        "  sum(CASE WHEN inv_count = 0 THEN 1 ELSE 0 END) AS no_investigation",
        **params,
    )
    type_rows = client.run(
        f"{base}"
        "WITH DISTINCT ep "
        "MATCH (enc:Encounter)-[:IS_PART_OF]->(ep) "
        f"  WHERE enc.encounter_type IN {_INVESTIGATION_TYPES} "
        "RETURN enc.encounter_type AS investigation_type, "
        "count(DISTINCT ep.episode_id) AS n "
        "ORDER BY n DESC",
        **params,
    )
    s = summary_rows[0] if summary_rows else {}
    total = s.get("total_episodes") or 1
    has_inv = s.get("has_investigation") or 0
    inv_total = sum(r["n"] for r in type_rows) or 1
    return {
        "has_investigation_pct": round(has_inv * 100.0 / total, 1),
        "no_investigation_pct": round(
            (s.get("no_investigation") or 0) * 100.0 / total, 1
        ),
        "total_episodes": total,
        "types": [
            {
                "type": r["investigation_type"],
                "n": r["n"],
                "pct": round(r["n"] * 100.0 / inv_total, 1),
            }
            for r in type_rows
        ],
    }


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------


def _q_referrals(base: str, params: dict, client: PatientGraphClient) -> list:
    rows = client.run(
        f"{base}"
        "RETURN coalesce(ep.referral_route, 'Not recorded') AS referral_route, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC",
        **params,
    )
    total = sum(r["n"] for r in rows) or 1
    return [
        {
            "referral_route": r["referral_route"],
            "n": r["n"],
            "pct": round(r["n"] * 100.0 / total, 1),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Safety netting
# ---------------------------------------------------------------------------


def _q_safety_netting(base: str, params: dict, client: PatientGraphClient) -> dict:
    rows = client.run(
        f"{base}"
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        "  sum(CASE WHEN ep.safety_netting_recorded = true "
        "THEN 1 ELSE 0 END) AS recorded",
        **params,
    )
    s = rows[0] if rows else {}
    total = s.get("total_episodes") or 1
    recorded = s.get("recorded") or 0
    return {
        "recorded_pct": round(recorded * 100.0 / total, 1),
        "not_recorded_pct": round((total - recorded) * 100.0 / total, 1),
        "recorded_n": recorded,
        "total_episodes": total,
    }


# ---------------------------------------------------------------------------
# Avoidable delays
# ---------------------------------------------------------------------------


def _q_avoidable_delays(base: str, params: dict, client: PatientGraphClient) -> dict:
    rows = client.run(
        f"{base}"
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        "  sum(CASE WHEN ep.avoidable_delay = true THEN 1 ELSE 0 END) "
        "AS has_delay, "
        "  sum(CASE WHEN ep.avoidable_delay_phase = 'before_presentation' "
        "THEN 1 ELSE 0 END) AS before_pres, "
        "  sum(CASE WHEN ep.avoidable_delay_phase = 'pres_to_referral' "
        "THEN 1 ELSE 0 END) AS pres_to_ref, "
        "  sum(CASE WHEN ep.avoidable_delay_phase = 'after_referral' "
        "THEN 1 ELSE 0 END) AS after_ref",
        **params,
    )
    s = rows[0] if rows else {}
    total = s.get("total_episodes") or 1
    has_delay = s.get("has_delay") or 0
    has_phases = has_delay > 0
    return {
        "avoidable_delay_pct": round(has_delay * 100.0 / total, 1),
        "avoidable_delay_n": has_delay,
        "total_episodes": total,
        "delay_before_presentation_pct": (
            round((s.get("before_pres") or 0) * 100.0 / has_delay, 1)
            if has_phases
            else None
        ),
        "delay_pres_to_referral_pct": (
            round((s.get("pres_to_ref") or 0) * 100.0 / has_delay, 1)
            if has_phases
            else None
        ),
        "delay_after_referral_pct": (
            round((s.get("after_ref") or 0) * 100.0 / has_delay, 1)
            if has_phases
            else None
        ),
    }
