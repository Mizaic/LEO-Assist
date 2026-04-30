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

from collections import Counter
from typing import Optional

from libs.analytics import confirmed_cancer_where
from libs.analytics.ncda_ethnicity_snomed import (
    load_ncda_ethnicity_benchmark_table,
    load_ncda_ethnicity_snomed_ids,
)
from libs.domains.ncda_concept_sets import FAST_TRACK_REFERRAL_IDS
from libs.neo4j_client.client import PatientGraphClient
from libs.oncology.cancer_types import normalise_cancer_type

# ---------------------------------------------------------------------------
# SNOMED concept ID → display label for fast-track referral sites.
# Source of truth: FAST_TRACK_REFERRAL_IDS in libs/domains/ncda_concept_sets.py
# ---------------------------------------------------------------------------
_FTR_CONCEPT_LABEL: dict[str, str] = {
    "276281000000104": "Skin",
    "276311000000101": "Gynaecological",
    "276341000000100": "Breast",
    "276371000000106": "Children's Tumour",
    "276401000000108": "Colorectal",
    "276431000000102": "Urological",
    "276461000000107": "Haematology",
    "276491000000101": "Lung",
    "276521000000103": "Sarcoma",
    "276551000000108": "Upper GI",
    "276581000000102": "Brain Tumour",
    "280521000000108": "Head & Neck",
    "892201000000106": "Lower GI",
    "1556551000000104": "NSS",
}

_FTR_IDS_STR: list[str] = [str(c) for c in sorted(FAST_TRACK_REFERRAL_IDS)]
_NSS_CONCEPT_ID = "1556551000000104"
_UNCODED_FTR_SITE_ID = "__uncoded__"

_FTR_TEXT_SITE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("1556551000000104", ("non-site-specific", "non site specific", " nss ")),
    ("276581000000102", ("brain tumour", "brain tumor")),
    (
        "276341000000100",
        ("2ww breast", "breast clinic", "breast cancer", "breast neoplasm"),
    ),
    ("276371000000106", ("children's tumour", "childrens tumour")),
    ("276401000000108", ("colorectal", "bowel cancer", "rectal")),
    ("892201000000106", ("lower gi", "lower gastrointestinal")),
    ("276311000000101", ("gynaecolog", "gynecolog", "ovarian", "endometrial")),
    ("276461000000107", ("haematolog", "hematolog", "lymphoma", "myeloma")),
    ("280521000000108", ("head and neck", "neck cancer", "thyroid")),
    ("276491000000101", ("lung cancer", "chest clinic", "mesothelioma")),
    ("276521000000103", ("sarcoma",)),
    ("276281000000104", ("dermatology", "derm", "skin cancer", "melanoma")),
    (
        "276551000000108",
        ("upper gi", "upper gastrointestinal", "pancreatic", "hepatobiliary", "hpb"),
    ),
    ("276431000000102", ("urology", "urological", "prostate", "bladder")),
)

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
_STAGING_EARLY_LATE_VALUE = (
    "toLower(trim(coalesce(toString(ep.staging_early_late), '')))"
)
_STAGE_GROUP_EXPR = (
    "CASE "
    f"  WHEN {_STAGING_EARLY_LATE_VALUE} IN ['early', 'late'] "
    "THEN toLower(trim(toString(ep.staging_early_late))) "
    "  ELSE 'unknown' "
    "END"
)
_STAGING_VALUE_EXPR = (
    "CASE "
    "  WHEN trim(coalesce(toString(ep.staging_value), '')) = '' THEN 'unknown' "
    "  ELSE trim(toString(ep.staging_value)) "
    "END"
)
_STAGING_RECORDED_EXPR = (
    f"{_STAGING_EARLY_LATE_VALUE} IN ['early', 'late']"
)


# ---------------------------------------------------------------------------
# Cancer type
# ---------------------------------------------------------------------------


def _q_cancer_type(base: str, params: dict, client: PatientGraphClient) -> list:
    # Post-migration every ep.cancer_type is one of the canonical NCDA
    # values (libs.oncology.cancer_types). Normalise on read as a
    # safety net for any value the migration missed; collapse synonyms
    # into a single bucket. The Unknown Primary / No Information / Other
    # sentinels are intentionally surfaced -- without this, confirmed
    # cancers visible in /care/patients with a missing or unmapped
    # cancer_type silently disappear from the radar (see
    # DI-LEO-AI-134 / R-LEO-AI-092).
    rows = client.run(
        f"{base}"
        f"AND {confirmed_cancer_where('ep')} "
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


def _stage_percent_rows(rows: list[dict]) -> list[dict]:
    total = sum(r["n"] for r in rows) or 1
    return [
        {
            "stage_group": r["stage_group"],
            "n": r["n"],
            "pct": round(r["n"] * 100.0 / total, 1),
        }
        for r in rows
    ]


def _stage_detail_payload(rows: list[dict]) -> list[dict]:
    return [
        {
            "cancer_stage_group": r["cancer_stage_group"],
            "staging_value": r["cancer_stage_group"],
            "stage_group": r["stage_group"],
            "n": r["n"],
        }
        for r in rows
    ]


def _stage_coverage(
    confirmed_base: str,
    params: dict,
    client: PatientGraphClient,
) -> tuple[float, int, int]:
    denom_row = client.run(
        f"{confirmed_base}RETURN count(DISTINCT ep) AS denom",
        **params,
    )
    numerator_row = client.run(
        f"{confirmed_base}"
        f"RETURN count(DISTINCT CASE WHEN {_STAGING_RECORDED_EXPR} "
        "THEN ep END) AS numer",
        **params,
    )
    denom = int((denom_row[0] or {}).get("denom") or 0) if denom_row else 0
    numer = int((numerator_row[0] or {}).get("numer") or 0) if numerator_row else 0
    coverage = round((numer * 100.0 / denom), 1) if denom > 0 else 0.0
    return coverage, numer, denom


def _q_cancer_stage(base: str, params: dict, client: PatientGraphClient) -> dict:
    confirmed_base = (
        f"{base}"
        f"AND {confirmed_cancer_where('ep')} "
    )

    rows = client.run(
        f"{confirmed_base}"
        f"WITH ep, {_STAGE_GROUP_EXPR} AS stage_group "
        "RETURN stage_group, "
        "count(DISTINCT ep) AS n "
        "ORDER BY stage_group",
        **params,
    )
    by_stage = _stage_percent_rows(rows)

    by_system_rows = client.run(
        f"{confirmed_base}"
        "WITH CASE "
        "  WHEN trim(coalesce(toString(ep.staging_system), '')) = '' THEN 'unknown' "
        "  ELSE trim(toString(ep.staging_system)) "
        "END AS staging_system, ep "
        "RETURN staging_system, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC, staging_system",
        **params,
    )
    by_source_rows = client.run(
        f"{confirmed_base}"
        "WITH CASE "
        "  WHEN trim(coalesce(toString(ep.staging_source), '')) = '' THEN 'none' "
        "  ELSE trim(toString(ep.staging_source)) "
        "END AS staging_source, ep "
        "RETURN staging_source, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC, staging_source",
        **params,
    )
    group_rows = client.run(
        f"{confirmed_base}"
        f"WITH ep, {_STAGING_VALUE_EXPR} AS staging_value, "
        f"{_STAGE_GROUP_EXPR} AS stage_group "
        "WHERE staging_value <> 'unknown' "
        "RETURN staging_value AS cancer_stage_group, "
        "stage_group, "
        "count(DISTINCT ep) AS n "
        "ORDER BY n DESC, cancer_stage_group",
        **params,
    )
    by_cancer_type_rows = client.run(
        f"{confirmed_base}"
        "WITH coalesce(ep.cancer_type, 'unknown') AS cancer_type, "
        f"     {_STAGE_GROUP_EXPR} AS stage_group, "
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

    coverage, numer, denom = _stage_coverage(confirmed_base, params, client)

    return {
        "rows": by_stage,
        "by_stage_group": by_stage,
        "by_system": [
            {"staging_system": r["staging_system"], "n": r["n"]} for r in by_system_rows
        ],
        "by_source": [
            {"staging_source": r["staging_source"], "n": r["n"]} for r in by_source_rows
        ],
        "by_stage_group_detail": _stage_detail_payload(group_rows),
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
        "WITH p, "
        "  CASE WHEN age_at_referral < 25 THEN '0-24' "
        "       WHEN age_at_referral < 50 THEN '25-49' "
        "       WHEN age_at_referral < 65 THEN '50-64' "
        "       WHEN age_at_referral < 75 THEN '65-74' "
        "       WHEN age_at_referral < 85 THEN '75-84' "
        "       ELSE '85+' END AS age_band "
        "RETURN age_band, count(DISTINCT p) AS n ORDER BY age_band",
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
        "WITH p, p.gender AS gender, "
        "  CASE WHEN age_at_referral < 25 THEN '0-24' "
        "       WHEN age_at_referral < 50 THEN '25-49' "
        "       WHEN age_at_referral < 65 THEN '50-64' "
        "       WHEN age_at_referral < 75 THEN '65-74' "
        "       WHEN age_at_referral < 85 THEN '75-84' "
        "       ELSE '85+' END AS age_band "
        "RETURN gender, age_band, count(DISTINCT p) AS n ORDER BY gender, age_band",
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
        "WITH ep, CASE "
        "  WHEN trim(coalesce(toString(ep.place_of_presentation), '')) <> '' "
        "THEN trim(toString(ep.place_of_presentation)) "
        "  WHEN trim(coalesce(toString(ep.place_of_presetnation), '')) <> '' "
        "THEN trim(toString(ep.place_of_presetnation)) "
        "  ELSE 'Not recorded' "
        "END AS place "
        "RETURN place, "
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
# Consultations  (NCDA Section 7 -- Haiku-enriched)
# ---------------------------------------------------------------------------


def _q_consultations(base: str, params: dict, client: PatientGraphClient) -> dict:
    """NCDA Section 7 -- cancer-related consultations in the year before the FTR.

    Reads the ``prior_consultations_*`` properties stamped on each
    EpisodeOfCare by ``libs/oncology/prior_consultations.py`` (Claude Haiku
    4.5 enrichment pass).  Returns the richer payload consumed by both
    ``ConsultationsSection`` (how-many view) and
    ``MultipleConsultationsSection`` (why view) so the two sections share a
    single API call.

    Returns NCDA-native polarity: ``three_or_more_*`` is the headline.
    ``fewer_than_3_*`` is kept for benchmark-overlay compatibility.
    """
    # Aggregate row -- one query does everything except the per-episode list.
    agg_rows = client.run(
        f"{base}"
        "WITH ep, ep.multiple_consultations_factors_auto AS factors_auto, "
        "     ep.cancer_type AS cancer_type "
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        # NCDA "multiple consultations" = 3 or more pre-referral contacts.
        "  sum(CASE WHEN ep.prior_consultations_n >= 3 "
        "       THEN 1 ELSE 0 END) AS three_or_more, "
        "  sum(CASE WHEN ep.prior_consultations_n IS NOT NULL "
        "       AND ep.prior_consultations_n < 3 "
        "       THEN 1 ELSE 0 END) AS fewer_than_3, "
        "  sum(CASE WHEN ep.prior_consultations_n IS NOT NULL "
        "       THEN 1 ELSE 0 END) AS enriched_n, "
        "  sum(CASE WHEN coalesce(ep.prior_consultations_n, 0) = 0 "
        "       THEN 1 ELSE 0 END) AS bucket_zero, "
        "  sum(CASE WHEN ep.prior_consultations_n = 1 "
        "       THEN 1 ELSE 0 END) AS bucket_one, "
        "  sum(CASE WHEN ep.prior_consultations_n = 2 "
        "       THEN 1 ELSE 0 END) AS bucket_two, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 3 "
        "       AND ep.prior_consultations_n <= 4 "
        "       THEN 1 ELSE 0 END) AS bucket_three_four, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 5 "
        "       AND ep.prior_consultations_n <= 7 "
        "       THEN 1 ELSE 0 END) AS bucket_five_seven, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 8 "
        "       THEN 1 ELSE 0 END) AS bucket_eight_plus, "
        "  sum(coalesce(ep.prior_consultations_n, 0)) AS total_consultations, "
        "  sum(coalesce(ep.prior_consultations_f2f_n, 0)) AS f2f_total, "
        "  sum(coalesce(ep.prior_consultations_phone_n, 0)) AS phone_total, "
        "  sum(coalesce(ep.prior_consultations_nurse_n, 0)) AS nurse_total, "
        "  sum(coalesce(ep.prior_consultations_email_n, 0)) AS email_total, "
        "  sum(coalesce(ep.prior_consultations_specialist_clinic_n, 0)) "
        "    AS specialist_clinic_total, "
        "  sum(coalesce(ep.prior_consultations_home_visit_n, 0)) "
        "    AS home_visit_total, "
        "  sum(coalesce(ep.prior_consultations_phlebotomy_n, 0)) "
        "    AS phlebotomy_total, "
        "  sum(coalesce(ep.prior_consultations_result_review_n, 0)) "
        "    AS result_review_total, "
        "  sum(coalesce(ep.prior_consultations_unrelated_filtered_n, 0)) "
        "    AS unrelated_filtered_total, "
        "  collect({n: ep.prior_consultations_n, "
        "           factors: factors_auto, "
        "           cancer_type: cancer_type, "
        "           episode_id: ep.episode_id}) AS episodes_raw, "
        "  sum(coalesce(ep.prior_consultations_llm_cost_usd, 0.0)) "
        "    AS llm_cost_usd, "
        "  sum(coalesce(ep.prior_consultations_llm_input_tokens, 0)) "
        "    AS llm_input_tokens, "
        "  sum(coalesce(ep.prior_consultations_llm_output_tokens, 0)) "
        "    AS llm_output_tokens, "
        "  sum(coalesce(ep.prior_consultations_llm_calls, 0)) "
        "    AS llm_calls",
        **params,
    )

    # Per-cancer-type live breakdown (drives the tumour-site table).
    by_ct_rows = client.run(
        f"{base}"
        "WITH ep, coalesce(ep.cancer_type, 'Unknown') AS ct "
        "RETURN "
        "  ct AS cancer_type, "
        "  count(DISTINCT ep) AS n_total, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 3 "
        "       THEN 1 ELSE 0 END) AS n_three_or_more, "
        "  sum(CASE WHEN ep.prior_consultations_n IS NOT NULL "
        "       THEN 1 ELSE 0 END) AS n_enriched, "
        "  avg(CASE WHEN ep.prior_consultations_n IS NOT NULL "
        "       THEN toFloat(ep.prior_consultations_n) END) AS mean_n "
        "ORDER BY n_total DESC",
        **params,
    )
    by_cancer_type_live = []
    for row in by_ct_rows:
        ct_total = int(row.get("n_total") or 0)
        ct_three = int(row.get("n_three_or_more") or 0)
        ct_enriched = int(row.get("n_enriched") or 0)
        by_cancer_type_live.append({
            "cancer_type": row.get("cancer_type") or "Unknown",
            "n_total": ct_total,
            "n_three_or_more": ct_three,
            "n_enriched": ct_enriched,
            "three_or_more_pct": round(ct_three * 100.0 / ct_total, 1) if ct_total else None,
            "mean_consultations": round(float(row["mean_n"]), 1) if row.get("mean_n") is not None else None,
        })

    s = agg_rows[0] if agg_rows else {}
    total = int(s.get("total_episodes") or 0)
    safe_total = total or 1
    enriched = int(s.get("enriched_n") or 0)
    three_plus = int(s.get("three_or_more") or 0)
    fewer = int(s.get("fewer_than_3") or 0)
    safe_enriched = enriched or 1

    # Compute median + IQR from the per-episode list returned inline.
    ep_raw = s.get("episodes_raw") or []
    counts = sorted(
        int(ep["n"])
        for ep in ep_raw
        if ep.get("n") is not None
    )
    n_counts = len(counts)
    median_val: float | None = (
        float(counts[n_counts // 2])
        if n_counts % 2
        else (float(counts[n_counts // 2 - 1] + counts[n_counts // 2]) / 2)
        if n_counts
        else None
    )
    iqr_low: float | None = float(counts[n_counts // 4]) if n_counts else None
    iqr_high: float | None = float(counts[3 * n_counts // 4]) if n_counts else None

    # Global factor frequency + per-cancer-type factor breakdown.
    factor_counts: dict[str, int] = {}
    factors_by_cancer_type: dict[str, dict[str, int]] = {}
    episode_evidence: list[dict] = []

    for ep in ep_raw:
        ct = ep.get("cancer_type") or "Unknown"
        ep_factors = ep.get("factors") or []
        ep_n = ep.get("n")
        eid = ep.get("episode_id") or ""
        fct_clean = [
            f for f in ep_factors if f and f != "no_multiple_consultations"
        ]
        for code in fct_clean:
            factor_counts[code] = factor_counts.get(code, 0) + 1
            ct_map = factors_by_cancer_type.setdefault(ct, {})
            ct_map[code] = ct_map.get(code, 0) + 1
        episode_evidence.append({
            "episode_id": eid,
            "cancer_type": ct,
            "n": ep_n,
            "factors": fct_clean,
            "evidence_quotes": None,  # populated in a future detector pass
        })

    top_factors = sorted(
        ({"factor": k, "n": v} for k, v in factor_counts.items()),
        key=lambda r: (-r["n"], r["factor"]),
    )[:10]

    return {
        # NCDA-native polarity: 3+ is the "multiple consultations" headline.
        "three_or_more_pct": round(three_plus * 100.0 / safe_total, 1),
        "three_or_more_n": three_plus,
        # Kept for benchmark-overlay compatibility (fewer_than_3_pct key
        # matches the existing BenchmarkValue metric_id in the KG).
        "fewer_than_3_pct": round(fewer * 100.0 / safe_total, 1),
        "fewer_than_3_n": fewer,
        # Enrichment coverage
        "total_episodes": total,
        "enriched_n": enriched,
        "enriched_pct": round(enriched * 100.0 / safe_total, 1),
        # Distribution -- drives the Consultations section breakdown dialog.
        "median_consultations": median_val,
        "iqr_low": iqr_low,
        "iqr_high": iqr_high,
        # Buckets aligned to NCDA threshold (< 3 = not multiple, >= 3 = multiple).
        "buckets": {
            "0":   int(s.get("bucket_zero") or 0),
            "1":   int(s.get("bucket_one") or 0),
            "2":   int(s.get("bucket_two") or 0),
            "3-4": int(s.get("bucket_three_four") or 0),
            "5-7": int(s.get("bucket_five_seven") or 0),
            "8+":  int(s.get("bucket_eight_plus") or 0),
        },
        "buckets_pct": {
            "0":   round(int(s.get("bucket_zero") or 0)        * 100.0 / safe_total, 1),
            "1":   round(int(s.get("bucket_one") or 0)         * 100.0 / safe_total, 1),
            "2":   round(int(s.get("bucket_two") or 0)         * 100.0 / safe_total, 1),
            "3-4": round(int(s.get("bucket_three_four") or 0)  * 100.0 / safe_total, 1),
            "5-7": round(int(s.get("bucket_five_seven") or 0)  * 100.0 / safe_total, 1),
            "8+":  round(int(s.get("bucket_eight_plus") or 0)  * 100.0 / safe_total, 1),
        },
        # Contact-type means -- drives the dialog contact-type table.
        "mean_per_episode": {
            "total":    round(int(s.get("total_consultations") or 0) / safe_enriched, 2),
            "f2f":      round(int(s.get("f2f_total") or 0)    / safe_enriched, 2),
            "phone":    round(int(s.get("phone_total") or 0)  / safe_enriched, 2),
            "nurse":    round(int(s.get("nurse_total") or 0)  / safe_enriched, 2),
            "email":    round(int(s.get("email_total") or 0)  / safe_enriched, 2),
            "specialist_clinic": round(
                int(s.get("specialist_clinic_total") or 0) / safe_enriched, 2
            ),
            "home_visit": round(int(s.get("home_visit_total") or 0) / safe_enriched, 2),
            "phlebotomy": round(int(s.get("phlebotomy_total") or 0) / safe_enriched, 2),
            "result_review": round(
                int(s.get("result_review_total") or 0) / safe_enriched, 2
            ),
        },
        # Aggregated totals.
        "total_consultations": int(s.get("total_consultations") or 0),
        "unrelated_filtered_total": int(s.get("unrelated_filtered_total") or 0),
        # Top NCDA factor codes -- drives the "why" bar chart.
        "top_factors": top_factors,
        # Per-cancer-type factor breakdown -- drives the heatmap.
        "factors_by_cancer_type": factors_by_cancer_type,
        # Per-episode evidence list -- drives the evidence drawer.
        "episode_evidence": episode_evidence,
        # Per-tumour-site live breakdown.
        "by_cancer_type_live": by_cancer_type_live,
        # LLM cost / token telemetry.
        "llm_cost_usd": round(float(s.get("llm_cost_usd") or 0.0), 4),
        "llm_input_tokens":  int(s.get("llm_input_tokens") or 0),
        "llm_output_tokens": int(s.get("llm_output_tokens") or 0),
        "llm_calls":         int(s.get("llm_calls") or 0),
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
# Fast-track referral types
# ---------------------------------------------------------------------------


def _infer_ftr_concept_id(cids: list, texts: list) -> str:
    coded = sorted({str(cid) for cid in cids if cid is not None})
    if coded:
        return coded[0]
    joined = f" {' '.join(str(t or '') for t in texts)} ".lower()
    for concept_id, phrases in _FTR_TEXT_SITE_PATTERNS:
        if any(phrase in joined for phrase in phrases):
            return concept_id
    return _UNCODED_FTR_SITE_ID


def _q_fast_track_referrals(base: str, params: dict, client: PatientGraphClient) -> list:
    # The denominator is the NCDA FTR cohort (1a + 1b), matching the dashboard
    # hero cards. Coded SNOMED sites win; when missing, infer from the referral
    # wording such as "Fast Track Referral for Suspected X cancer".
    rows = client.run(
        f"{base}"
        "AND coalesce(ep.cohort, '') IN ['1a', '1b'] "
        "WITH DISTINCT ep "
        "OPTIONAL MATCH (enc:Encounter)-[__mp:IS_PART_OF]->(ep) "
        "  WHERE __mp.milestone_type = 'referral' "
        "OPTIONAL MATCH (enc)-[:DOCUMENTS]->(c) "
        "  WHERE toString(c.conceptId) IN $ftr_ids "
        "RETURN ep.episode_id AS episode_id, "
        "collect(DISTINCT toString(c.conceptId)) AS cids, "
        "collect(DISTINCT enc.text) AS texts",
        **{
            **params,
            "ftr_ids": _FTR_IDS_STR,
        },
    )
    by_concept: Counter = Counter()
    for row in rows:
        concept_id = _infer_ftr_concept_id(row.get("cids") or [], row.get("texts") or [])
        by_concept[concept_id] += 1
    total = sum(by_concept.values()) or 1
    return [
        {
            "referral_site": _FTR_CONCEPT_LABEL.get(
                concept_id, "Uncoded site"
            ),
            "concept_id": concept_id,
            "n": n,
            "pct": round(n * 100.0 / total, 1),
        }
        for concept_id, n in by_concept.most_common()
    ]


def _q_nss_outcomes(base: str, params: dict, client: PatientGraphClient) -> dict:
    # Two complementary ways to identify NSS episodes:
    #  1. Legacy path: DOCUMENTS -> SNOMED concept 1556551000000104 on the referral
    #     milestone encounter (used by the old NER-based detector).
    #  2. ncda_detector path: ep.nss_referral = true, written at write-back time
    #     when Y3dd2 appears in the FTR encounter text.
    # Both return (episode_id, outcome) rows; UNION deduplicates across sources.
    confirmed_clause = confirmed_cancer_where("ep")
    outcome_expr = (
        f"CASE WHEN {confirmed_clause} "
        "THEN coalesce(ep.cancer_type, 'Cancer diagnosed') "
        "ELSE 'No cancer diagnosed' END"
    )
    rows = client.run(
        # SNOMED-DOCUMENTS path (legacy)
        f"{base}"
        "MATCH (enc:Encounter)-[__mp:IS_PART_OF]->(ep) "
        "WHERE __mp.milestone_type = 'referral' "
        "MATCH (enc)-[:DOCUMENTS]->(c) "
        "WHERE toString(c.conceptId) = $nss_id "
        f"RETURN ep.episode_id AS eid, {outcome_expr} AS outcome "
        "UNION "
        # ep.nss_referral path (ncda_detector)
        f"{base}"
        "AND ep.nss_referral = true "
        f"RETURN ep.episode_id AS eid, {outcome_expr} AS outcome",
        **{**params, "nss_id": _NSS_CONCEPT_ID},
    )
    outcome_counter: Counter = Counter()
    for r in rows:
        outcome_counter[r["outcome"]] += 1
    outcomes = sorted(
        [{"outcome": k, "n": v} for k, v in outcome_counter.items()],
        key=lambda x: -x["n"],
    )
    total = sum(o["n"] for o in outcomes) or 0
    no_cancer_n = next(
        (o["n"] for o in outcomes if o["outcome"] == "No cancer diagnosed"), 0
    )
    return {
        "total_nss": total,
        "cancer_diagnosed_n": total - no_cancer_n,
        "outcomes": outcomes,
    }


# ---------------------------------------------------------------------------
# Safety netting
# ---------------------------------------------------------------------------


def _q_safety_netting(base: str, params: dict, client: PatientGraphClient) -> dict:
    """Section 8 (safety netting) per-year breakdown.

    Returns the headline 'recorded' rate (strong+medium signal) plus
    the full four-bucket signal-strength hierarchy stamped onto each
    episode by ``libs/oncology/safety_netting.detect_safety_netting``.
    The /care/audit Safety Netting section reads this to render the
    'Open detail' dialog (signal-strength bar chart) -- see
    SafetyNettingSection.tsx.
    """
    rows = client.run(
        f"{base}"
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        "  sum(CASE WHEN ep.safety_netting_recorded = true "
        "THEN 1 ELSE 0 END) AS recorded, "
        "  sum(CASE WHEN ep.safety_netting_signal = 'strong' "
        "THEN 1 ELSE 0 END) AS strong_n, "
        "  sum(CASE WHEN ep.safety_netting_signal = 'medium' "
        "THEN 1 ELSE 0 END) AS medium_n, "
        "  sum(CASE WHEN ep.safety_netting_signal = 'advice_only' "
        "THEN 1 ELSE 0 END) AS advice_only_n, "
        "  sum(CASE WHEN coalesce(ep.safety_netting_signal, 'none') "
        "= 'none' THEN 1 ELSE 0 END) AS none_n",
        **params,
    )
    s = rows[0] if rows else {}
    total = int(s.get("total_episodes") or 0)
    safe_total = total or 1
    recorded = int(s.get("recorded") or 0)
    strong_n = int(s.get("strong_n") or 0)
    medium_n = int(s.get("medium_n") or 0)
    advice_only_n = int(s.get("advice_only_n") or 0)
    none_n = int(s.get("none_n") or 0)
    return {
        "recorded_pct": round(recorded * 100.0 / safe_total, 1),
        "not_recorded_pct": round((safe_total - recorded) * 100.0 / safe_total, 1),
        "recorded_n": recorded,
        "total_episodes": total,
        # Signal-strength breakdown — drives the Open-detail dialog.
        "signal_counts": {
            "strong": strong_n,
            "medium": medium_n,
            "advice_only": advice_only_n,
            "none": none_n,
        },
        "signal_pct": {
            "strong": round(strong_n * 100.0 / safe_total, 1),
            "medium": round(medium_n * 100.0 / safe_total, 1),
            "advice_only": round(advice_only_n * 100.0 / safe_total, 1),
            "none": round(none_n * 100.0 / safe_total, 1),
        },
        # Strict ('strong only') subset surfaced for the dialog header.
        "strong_n": strong_n,
        "strong_pct": round(strong_n * 100.0 / safe_total, 1),
    }


def _q_care_obstructions(
    base: str, params: dict, client: PatientGraphClient
) -> dict:
    """Care-obstruction per-year breakdown.

    Mirrors the safety-netting helper shape so the front-end can reuse
    the same EvolutionYearCard / EvolutionDetailDialog rendering.
    Returns the headline 'recorded' rate (any non-none signal) plus the
    full signal-severity breakdown stamped onto each episode by
    ``libs/oncology/care_obstruction.detect_care_obstructions``.
    The /care/audit Care Obstructions section reads this to render the
    'Open detail' dialog (signal-severity bar chart) -- see
    CareObstructionsSection.tsx.
    """
    rows = client.run(
        f"{base}"
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        "  sum(CASE WHEN ep.care_obstruction_recorded = true "
        "THEN 1 ELSE 0 END) AS recorded, "
        "  sum(CASE WHEN ep.care_obstruction_signal = 'rejection' "
        "THEN 1 ELSE 0 END) AS rejection_n, "
        "  sum(CASE WHEN ep.care_obstruction_signal = 'dna' "
        "THEN 1 ELSE 0 END) AS dna_n, "
        "  sum(CASE WHEN ep.care_obstruction_signal = 'cancellation' "
        "THEN 1 ELSE 0 END) AS cancellation_n, "
        "  sum(CASE WHEN ep.care_obstruction_signal = 'access_barrier' "
        "THEN 1 ELSE 0 END) AS access_barrier_n, "
        "  sum(CASE WHEN coalesce(ep.care_obstruction_signal, 'none') "
        "= 'none' THEN 1 ELSE 0 END) AS none_n, "
        "  sum(coalesce(ep.care_obstruction_evidence_count, 0)) "
        "AS total_events, "
        "  sum(coalesce(ep.care_obstruction_confirmed_n, 0)) "
        "AS confirmed_events, "
        "  sum(coalesce(ep.care_obstruction_unrelated_filtered_n, 0)) "
        "AS unrelated_filtered_events, "
        "  sum(CASE WHEN coalesce(ep.care_obstruction_confirmed_n, 0) > 0 "
        "THEN 1 ELSE 0 END) AS confirmed_episodes",
        **params,
    )
    s = rows[0] if rows else {}
    total = int(s.get("total_episodes") or 0)
    safe_total = total or 1
    recorded = int(s.get("recorded") or 0)
    rejection_n = int(s.get("rejection_n") or 0)
    dna_n = int(s.get("dna_n") or 0)
    cancellation_n = int(s.get("cancellation_n") or 0)
    access_barrier_n = int(s.get("access_barrier_n") or 0)
    none_n = int(s.get("none_n") or 0)
    severe_n = rejection_n + dna_n
    confirmed_episodes = int(s.get("confirmed_episodes") or 0)
    return {
        "recorded_pct": round(recorded * 100.0 / safe_total, 1),
        "not_recorded_pct": round((safe_total - recorded) * 100.0 / safe_total, 1),
        "recorded_n": recorded,
        "total_episodes": total,
        "total_events": int(s.get("total_events") or 0),
        # Severity breakdown — drives the Open-detail dialog.
        "signal_counts": {
            "rejection": rejection_n,
            "dna": dna_n,
            "cancellation": cancellation_n,
            "access_barrier": access_barrier_n,
            "none": none_n,
        },
        "signal_pct": {
            "rejection": round(rejection_n * 100.0 / safe_total, 1),
            "dna": round(dna_n * 100.0 / safe_total, 1),
            "cancellation": round(cancellation_n * 100.0 / safe_total, 1),
            "access_barrier": round(access_barrier_n * 100.0 / safe_total, 1),
            "none": round(none_n * 100.0 / safe_total, 1),
        },
        # 'Severe' subset (rejection + dna): the events that hard-stop
        # the workup.  Surfaced for the dialog header.
        "severe_n": severe_n,
        "severe_pct": round(severe_n * 100.0 / safe_total, 1),
        # Pathway-relatedness breakdown.  ``confirmed_n`` is the count
        # of episodes where AT LEAST ONE recorded obstruction came
        # with explicit cancer-pathway markers (2WW, FTR, oncology,
        # site-specific specialty); these are the events a clinician
        # would unambiguously agree delayed THIS pathway.
        # ``unrelated_filtered_events`` is the total number of
        # encounter rows that tripped an obstruction phrase but were
        # filtered as clearly non-cancer (midwife, district nurse,
        # phlebotomy, UTC, cardiac rehab, etc.) and therefore are
        # NOT counted in `recorded_n` / `signal_counts`.  Surfaced
        # for the tile tooltip and the dialog footer.
        "confirmed_n": confirmed_episodes,
        "confirmed_pct": round(
            confirmed_episodes * 100.0 / safe_total, 1
        ),
        "confirmed_events": int(s.get("confirmed_events") or 0),
        "unrelated_filtered_events": int(s.get("unrelated_filtered_events") or 0),
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


# ---------------------------------------------------------------------------
# Blood signal (GDS enrichment results)
# ---------------------------------------------------------------------------

_BLOOD_SIGNAL_FEATURE_KEYS: list[str] = [
    "bf_lymphocyte_z",
    "bf_nucleated_rbc_z",
    "bf_neutrophil_pct_z",
    "bf_mcv_z",
    "bf_mch_z",
    "bf_haemoglobin_z",
    "bf_monocyte_z",
    "bf_rbc_z",
    "bf_platelet_z",
    "bf_alp_z",
    "bf_albumin_z",
    "bf_bilirubin_z",
    "bf_phosphate_z",
    "bf_sodium_z",
    "bf_total_protein_z",
    "bf_calcium_z",
    "bf_hba1c_z",
    "bf_folate_z",
    "bf_ldl_z",
    "bf_hdl_z",
    "bf_total_chol_z",
]

_BLOOD_SIGNAL_FEATURE_LABELS: dict[str, str] = {
    "bf_lymphocyte_z":     "Lymphocyte",
    "bf_nucleated_rbc_z":  "Nucleated RBC",
    "bf_neutrophil_pct_z": "Neutrophil %",
    "bf_mcv_z":            "MCV",
    "bf_mch_z":            "MCH",
    "bf_haemoglobin_z":    "Haemoglobin",
    "bf_monocyte_z":       "Monocyte",
    "bf_rbc_z":            "RBC",
    "bf_platelet_z":       "Platelets",
    "bf_alp_z":            "ALP",
    "bf_albumin_z":        "Albumin",
    "bf_bilirubin_z":      "Bilirubin",
    "bf_phosphate_z":      "Phosphate",
    "bf_sodium_z":         "Sodium",
    "bf_total_protein_z":  "Total Protein",
    "bf_calcium_z":        "Calcium",
    "bf_hba1c_z":          "HbA1c",
    "bf_folate_z":         "Folate",
    "bf_ldl_z":            "LDL Chol",
    "bf_hdl_z":            "HDL Chol",
    "bf_total_chol_z":     "Total Chol",
}

_BLOOD_EPISODE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.bf_cohort_label IS NOT NULL
RETURN ep.episode_id    AS episode_id,
       ep.bf_cohort_label  AS cohort_label,
       ep.bf_cancer_type   AS cancer_type,
       ep.bf_cluster       AS cluster,
       ep.bf_label         AS bf_label,
       ep.bf_lymphocyte_z     AS bf_lymphocyte_z,
       ep.bf_nucleated_rbc_z  AS bf_nucleated_rbc_z,
       ep.bf_neutrophil_pct_z AS bf_neutrophil_pct_z,
       ep.bf_mcv_z            AS bf_mcv_z,
       ep.bf_mch_z            AS bf_mch_z,
       ep.bf_haemoglobin_z    AS bf_haemoglobin_z,
       ep.bf_monocyte_z       AS bf_monocyte_z,
       ep.bf_rbc_z            AS bf_rbc_z,
       ep.bf_platelet_z       AS bf_platelet_z,
       ep.bf_alp_z            AS bf_alp_z,
       ep.bf_albumin_z        AS bf_albumin_z,
       ep.bf_bilirubin_z      AS bf_bilirubin_z,
       ep.bf_phosphate_z      AS bf_phosphate_z,
       ep.bf_sodium_z         AS bf_sodium_z,
       ep.bf_total_protein_z  AS bf_total_protein_z,
       ep.bf_calcium_z        AS bf_calcium_z,
       ep.bf_hba1c_z          AS bf_hba1c_z,
       ep.bf_folate_z         AS bf_folate_z,
       ep.bf_ldl_z            AS bf_ldl_z,
       ep.bf_hdl_z            AS bf_hdl_z,
       ep.bf_total_chol_z     AS bf_total_chol_z
ORDER BY ep.bf_cohort_label, ep.episode_id
"""

_BLOOD_PANEL_Q = """
MATCH (bp:BloodPanel)
WHERE bp.bf_cohort_label IS NOT NULL
RETURN bp.patient_id    AS episode_id,
       bp.bf_cohort_label  AS cohort_label,
       null                AS cancer_type,
       bp.bf_cluster       AS cluster,
       bp.bf_label         AS bf_label,
       bp.bf_lymphocyte_z     AS bf_lymphocyte_z,
       bp.bf_nucleated_rbc_z  AS bf_nucleated_rbc_z,
       bp.bf_neutrophil_pct_z AS bf_neutrophil_pct_z,
       bp.bf_mcv_z            AS bf_mcv_z,
       bp.bf_mch_z            AS bf_mch_z,
       bp.bf_haemoglobin_z    AS bf_haemoglobin_z,
       bp.bf_monocyte_z       AS bf_monocyte_z,
       bp.bf_rbc_z            AS bf_rbc_z,
       bp.bf_platelet_z       AS bf_platelet_z,
       bp.bf_alp_z            AS bf_alp_z,
       bp.bf_albumin_z        AS bf_albumin_z,
       bp.bf_bilirubin_z      AS bf_bilirubin_z,
       bp.bf_phosphate_z      AS bf_phosphate_z,
       bp.bf_sodium_z         AS bf_sodium_z,
       bp.bf_total_protein_z  AS bf_total_protein_z,
       bp.bf_calcium_z        AS bf_calcium_z,
       bp.bf_hba1c_z          AS bf_hba1c_z,
       bp.bf_folate_z         AS bf_folate_z,
       bp.bf_ldl_z            AS bf_ldl_z,
       bp.bf_hdl_z            AS bf_hdl_z,
       bp.bf_total_chol_z     AS bf_total_chol_z
ORDER BY bp.patient_id
"""

_BLOOD_ANALYSIS_Q = """
MATCH (ar:BloodSignalAnalysis {name: 'blood_signal_v1'})
RETURN ar.feature_correlations_json AS correlations_json,
       ar.updated_at AS updated_at
"""


_BLOOD_DIST_EP_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.bf_cohort_label IS NOT NULL AND ep.bf_anchor_date IS NOT NULL
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date(ep.bf_anchor_date) - duration({years: 1})
  AND date(enc.date) <= date(ep.bf_anchor_date) + duration({days: 28})
WITH toFloat(toString(d.value)) AS v, d.referenceRange AS ref_range, d.unit AS unit,
     ep.bf_cohort_label AS cohort
WHERE v IS NOT NULL
RETURN cohort,
       percentileCont(v, 0.1)  AS p10,
       percentileCont(v, 0.25) AS q1,
       percentileCont(v, 0.5)  AS median,
       percentileCont(v, 0.75) AS q3,
       percentileCont(v, 0.9)  AS p90,
       min(v) AS min_v, max(v) AS max_v,
       avg(v) AS mean_v, count(v) AS n,
       collect(DISTINCT ref_range)[0] AS ref_range,
       collect(DISTINCT unit)[0] AS unit
"""

_BLOOD_DIST_BP_Q = """
MATCH (bp:BloodPanel)
WHERE bp.bf_anchor_date IS NOT NULL
MATCH (p:Patient {id: bp.patient_id})-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date(bp.bf_anchor_date) - duration({years: 1})
  AND date(enc.date) <= date(bp.bf_anchor_date) + duration({days: 28})
WITH toFloat(toString(d.value)) AS v, d.referenceRange AS ref_range, d.unit AS unit
WHERE v IS NOT NULL
RETURN percentileCont(v, 0.1)  AS p10,
       percentileCont(v, 0.25) AS q1,
       percentileCont(v, 0.5)  AS median,
       percentileCont(v, 0.75) AS q3,
       percentileCont(v, 0.9)  AS p90,
       min(v) AS min_v, max(v) AS max_v,
       avg(v) AS mean_v, count(v) AS n,
       collect(DISTINCT ref_range)[0] AS ref_range,
       collect(DISTINCT unit)[0] AS unit
"""

# Fetch all raw values for a test (used for individual scatter dots in the UI)
_BLOOD_VALUES_EP_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.bf_cohort_label IS NOT NULL AND ep.bf_anchor_date IS NOT NULL
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date(ep.bf_anchor_date) - duration({years: 1})
  AND date(enc.date) <= date(ep.bf_anchor_date) + duration({days: 28})
WITH ep.episode_id AS id, ep.bf_cohort_label AS cohort,
     ep.bf_cancer_type AS cancer_type, toFloat(toString(d.value)) AS v
WHERE v IS NOT NULL
RETURN id, cohort, cancer_type, avg(v) AS value
"""

_BLOOD_VALUES_BP_Q = """
MATCH (bp:BloodPanel)
WHERE bp.bf_anchor_date IS NOT NULL
MATCH (p:Patient {id: bp.patient_id})-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date(bp.bf_anchor_date) - duration({years: 1})
  AND date(enc.date) <= date(bp.bf_anchor_date) + duration({days: 28})
WITH bp.patient_id AS id, 'benign' AS cohort, null AS cancer_type,
     toFloat(toString(d.value)) AS v
WHERE v IS NOT NULL
RETURN id, cohort, cancer_type, avg(v) AS value
"""


import re as _re


def _parse_ref_range(raw: str | None) -> tuple[float, float] | None:
    if not raw:
        return None
    m = _re.search(r"([\d.]+)\s*[-\u2013to ]+\s*([\d.]+)", raw)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None
    return None


def _box_dict(row: dict) -> dict | None:
    if not row or not row.get("n"):
        return None
    return {
        "n":      int(row["n"]),
        "p10":    round(float(row["p10"]), 3),
        "q1":     round(float(row["q1"]), 3),
        "median": round(float(row["median"]), 3),
        "q3":     round(float(row["q3"]), 3),
        "p90":    round(float(row["p90"]), 3),
        "min":    round(float(row["min_v"]), 3),
        "max":    round(float(row["max_v"]), 3),
        "mean":   round(float(row["mean_v"]), 3),
    }


def _q_blood_signal_distributions(client: PatientGraphClient) -> list[dict]:
    """Per-test box plot statistics for cancer vs benign, with NHS reference range."""
    results: list[dict] = []
    for prop_key in _BLOOD_SIGNAL_FEATURE_KEYS:
        snomed_name = _SNOMED_NAME.get(prop_key, "")
        if not snomed_name:
            continue

        ep_rows = {
            r["cohort"]: r
            for r in client.run(_BLOOD_DIST_EP_Q, test_name=snomed_name)
        }
        bp_row = (client.run(_BLOOD_DIST_BP_Q, test_name=snomed_name) or [None])[0]

        cancer_row = ep_rows.get("cancer")
        benign_ep  = ep_rows.get("benign")

        # Merge benign episode + BloodPanel distributions via combined values
        # (approximate: use whichever has more data, or use ep_row if no bp_row)
        # For the reference range, try cancer row first then bp_row
        ref_raw = (
            (cancer_row or {}).get("ref_range")
            or (bp_row or {}).get("ref_range")
        )
        unit = (
            (cancer_row or {}).get("unit")
            or (bp_row or {}).get("unit")
            or ""
        )
        ref_range = _parse_ref_range(ref_raw)

        # For benign, prefer BloodPanel (more patients) if both exist
        benign_box = _box_dict(dict(bp_row) if bp_row else {}) or _box_dict(dict(benign_ep) if benign_ep else {})
        cancer_box = _box_dict(dict(cancer_row) if cancer_row else {})

        if not cancer_box and not benign_box:
            continue

        results.append({
            "key":        prop_key,
            "label":      _BLOOD_SIGNAL_FEATURE_LABELS[prop_key],
            "unit":       unit,
            "ref_low":    ref_range[0] if ref_range else None,
            "ref_high":   ref_range[1] if ref_range else None,
            "ref_raw":    ref_raw,
            "cancer":     cancer_box,
            "benign":     benign_box,
        })

    return results


def _q_blood_signal_values(client: PatientGraphClient, prop_key: str) -> list[dict]:
    """Raw per-patient mean values for one test — used for scatter dots."""
    snomed_map = {
        "bf_lymphocyte_z":     "Lymphocyte count",
        "bf_nucleated_rbc_z":  "Nucleated red blood cell count",
        "bf_neutrophil_pct_z": "Neutrophil percent count in blood",
        "bf_mcv_z":            "Mean corpuscular volume",
        "bf_mch_z":            "Mean corpuscular haemoglobin",
        "bf_haemoglobin_z":    "Mass concentration of haemoglobin in blood (observable entity)",
        "bf_monocyte_z":       "Monocyte count",
        "bf_alp_z":            "Serum alkaline phosphatase placental enzyme level",
        "bf_albumin_z":        "Serum albumin level",
        "bf_hba1c_z":          "Haemoglobin A1c level (observable entity)",
        "bf_folate_z":         "Serum folate level (observable entity)",
        "bf_calcium_z":        "Serum calcium level (observable entity)",
    }
    test_name = snomed_map.get(prop_key, "")
    if not test_name:
        return []
    ep_rows = client.run(_BLOOD_VALUES_EP_Q, test_name=test_name)
    bp_rows = client.run(_BLOOD_VALUES_BP_Q, test_name=test_name)
    all_rows = []
    for r in ep_rows + bp_rows:
        v = r.get("value")
        if v is not None:
            all_rows.append({
                "id":          str(r["id"] or ""),
                "cohort_label": str(r["cohort"] or "benign"),
                "cancer_type":  str(r.get("cancer_type") or "") or None,
                "value":        round(float(v), 3),
            })
    return all_rows


_SNOMED_NAME: dict[str, str] = {
    "bf_lymphocyte_z":     "Lymphocyte count",
    "bf_nucleated_rbc_z":  "Nucleated red blood cell count",
    "bf_neutrophil_pct_z": "Neutrophil percent count in blood",
    "bf_mcv_z":            "Mean corpuscular volume",
    "bf_mch_z":            "Mean corpuscular haemoglobin",
    "bf_haemoglobin_z":    "Mass concentration of haemoglobin in blood (observable entity)",
    "bf_monocyte_z":       "Monocyte count",
    "bf_rbc_z":            "Red blood cell count",
    "bf_platelet_z":       "Platelet count",
    "bf_alp_z":            "Serum alkaline phosphatase placental enzyme level",
    "bf_albumin_z":        "Serum albumin level",
    "bf_bilirubin_z":      "Serum bilirubin level",
    "bf_phosphate_z":      "Serum inorganic phosphate level",
    "bf_sodium_z":         "Serum sodium level (observable entity)",
    "bf_total_protein_z":  "Serum total protein",
    "bf_calcium_z":        "Serum calcium level (observable entity)",
    "bf_hba1c_z":          "Haemoglobin A1c level (observable entity)",
    "bf_folate_z":         "Serum folate level (observable entity)",
    "bf_ldl_z":            "Serum random low density lipoprotein cholesterol level",
    "bf_hdl_z":            "Serum random high density lipoprotein cholesterol level (obs",
    "bf_total_chol_z":     "Total cholesterol level (observable entity)",
}

# Per-patient mean value + reference range for one test, cancer episodes only.
_CANCER_PATIENT_VALUES_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.bf_cohort_label = 'cancer'
  AND ep.bf_anchor_date IS NOT NULL
WITH ep,
     CASE WHEN toLower(ep.bf_cancer_type) = 'breast'
          THEN 'Breast' ELSE ep.bf_cancer_type END AS cancer_type
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date(ep.bf_anchor_date) - duration({years: 1})
  AND date(enc.date) <= date(ep.bf_anchor_date) + duration({days: 28})
WITH ep.episode_id AS episode_id,
     cancer_type,
     avg(toFloat(toString(d.value))) AS mean_value,
     collect(DISTINCT toString(d.referenceRange))[0] AS ref_range,
     collect(DISTINCT toString(d.unit))[0] AS unit
RETURN episode_id, cancer_type, mean_value, ref_range, unit
ORDER BY cancer_type, episode_id
"""

# Benign aggregate per test (combined episodes + no-episode FTR patients).
_BENIGN_AGG_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.bf_cohort_label = 'benign'
  AND ep.bf_anchor_date IS NOT NULL
MATCH (p:Patient)-[:HAS_EPISODE_OF_CARE]->(ep)
MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)-[d:DOCUMENTS]->(obs:Observable_entity)
WHERE obs.name = $test_name
  AND d.value IS NOT NULL AND trim(toString(d.value)) <> ''
  AND toFloat(toString(d.value)) IS NOT NULL
  AND date(enc.date) >= date(ep.bf_anchor_date) - duration({years: 1})
  AND date(enc.date) <= date(ep.bf_anchor_date) + duration({days: 28})
WITH toFloat(toString(d.value)) AS v, d.referenceRange AS ref_range
WHERE v IS NOT NULL
WITH collect(v) AS ep_vals, collect(DISTINCT ref_range) AS refs

// Also pull in BloodPanel (no-episode FTR patients)
CALL {
  MATCH (bp:BloodPanel)
  WHERE bp.bf_anchor_date IS NOT NULL
  MATCH (p2:Patient {id: bp.patient_id})-[:HAS_ENCOUNTER]->(enc2:Encounter)-[d2:DOCUMENTS]->(obs2:Observable_entity)
  WHERE obs2.name = $test_name
    AND d2.value IS NOT NULL AND trim(toString(d2.value)) <> ''
    AND toFloat(toString(d2.value)) IS NOT NULL
    AND date(enc2.date) >= date(bp.bf_anchor_date) - duration({years: 1})
    AND date(enc2.date) <= date(bp.bf_anchor_date) + duration({days: 28})
  WITH toFloat(toString(d2.value)) AS v2, d2.referenceRange AS ref2
  WHERE v2 IS NOT NULL
  RETURN collect(v2) AS bp_vals, collect(DISTINCT ref2) AS bp_refs
}

WITH ep_vals + bp_vals AS all_vals,
     refs + bp_refs AS all_refs

UNWIND all_vals AS v
RETURN avg(v) AS mean_v,
       stDev(v) AS std_v,
       percentileCont(v, 0.5) AS median_v,
       count(v) AS n,
       all_refs[0] AS ref_range
"""


def _q_blood_cancer_type_matrix(client: "PatientGraphClient") -> dict:  # type: ignore[name-defined]
    """
    Returns the data needed for the By Cancer Type heatmap + patient flag matrix.

    For every (cancer_type, test) pair:
      heatmap_rows  — per-cancer-type aggregated effect size vs benign
      patient_flags — per-episode flag (high / low / normal / no_data) for each test
    """
    # ------------------------------------------------------------------
    # 1. Benign baseline stats per test
    # ------------------------------------------------------------------
    benign_stats: dict[str, dict] = {}
    for key in _BLOOD_SIGNAL_FEATURE_KEYS:
        test_name = _SNOMED_NAME.get(key, "")
        if not test_name:
            continue
        rows = client.run(_BENIGN_AGG_Q, test_name=test_name)
        if rows:
            r = rows[0]
            benign_stats[key] = {
                "mean":   float(r["mean_v"] or 0),
                "std":    float(r["std_v"] or 1),
                "median": float(r["median_v"] or 0),
                "n":      int(r["n"] or 0),
                "ref_range": r.get("ref_range"),
            }

    # ------------------------------------------------------------------
    # 2. Per-cancer-type, per-test: individual patient mean values
    # ------------------------------------------------------------------
    # Structure: {episode_id: {test_key: {value, ref_range, unit}}}
    episode_data: dict[str, dict] = {}
    # Structure: {episode_id: cancer_type}
    episode_cancer_type: dict[str, str] = {}

    for key in _BLOOD_SIGNAL_FEATURE_KEYS:
        test_name = _SNOMED_NAME.get(key, "")
        if not test_name:
            continue
        rows = client.run(_CANCER_PATIENT_VALUES_Q, test_name=test_name)
        for r in rows:
            eid = str(r["episode_id"] or "")
            ct = str(r.get("cancer_type") or "Unknown")
            episode_cancer_type[eid] = ct

            if eid not in episode_data:
                episode_data[eid] = {}

            mv = r.get("mean_value")
            episode_data[eid][key] = {
                "value":     round(float(mv), 3) if mv is not None else None,
                "ref_range": r.get("ref_range"),
                "unit":      r.get("unit") or "",
            }

    # ------------------------------------------------------------------
    # 3. Compute per-patient flags and per-cancer-type aggregates
    # ------------------------------------------------------------------
    # Group episodes by cancer type
    by_ct: dict[str, list[str]] = {}
    for eid, ct in episode_cancer_type.items():
        by_ct.setdefault(ct, []).append(eid)

    # For each cancer type sort episodes for stable ordering
    for ct in by_ct:
        by_ct[ct].sort()

    # patient_flags: list of row dicts for the flag matrix
    patient_flags: list[dict] = []
    # heatmap_rows: list of {cancer_type, test_key, n, effect_size, pct_high, pct_low}
    heatmap_cells: list[dict] = []

    for ct in sorted(by_ct.keys()):
        episodes = by_ct[ct]
        # Counters per test for this cancer type
        test_counts: dict[str, dict] = {
            k: {"n": 0, "high": 0, "low": 0, "values": []}
            for k in _BLOOD_SIGNAL_FEATURE_KEYS
        }

        for idx, eid in enumerate(episodes, start=1):
            row_flags: dict[str, str] = {}
            test_vals = episode_data.get(eid, {})

            for key in _BLOOD_SIGNAL_FEATURE_KEYS:
                td = test_vals.get(key, {})
                value = td.get("value") if isinstance(td, dict) else None
                ref_raw = td.get("ref_range") if isinstance(td, dict) else None
                ref = _parse_ref_range(ref_raw)

                if value is None:
                    row_flags[key] = "no_data"
                    continue

                test_counts[key]["n"] += 1
                test_counts[key]["values"].append(value)

                if ref:
                    if value > ref[1]:
                        row_flags[key] = "high"
                        test_counts[key]["high"] += 1
                    elif value < ref[0]:
                        row_flags[key] = "low"
                        test_counts[key]["low"] += 1
                    else:
                        row_flags[key] = "normal"
                else:
                    row_flags[key] = "normal"

            patient_flags.append({
                "label":       f"{ct} {idx}",
                "cancer_type": ct,
                "episode_id":  eid,
                "flags":       row_flags,
                # also carry raw values for tooltip
                "values":      {
                    k: (episode_data.get(eid, {}).get(k, {}) or {}).get("value")
                    for k in _BLOOD_SIGNAL_FEATURE_KEYS
                },
            })

        # Heatmap cells for this cancer type
        for key in _BLOOD_SIGNAL_FEATURE_KEYS:
            tc = test_counts[key]
            vals = tc["values"]
            bs = benign_stats.get(key, {})
            median_v = sorted(vals)[len(vals) // 2] if vals else None
            benign_std = bs.get("std") or 1.0
            benign_median = bs.get("median") or 0.0
            effect = round((median_v - benign_median) / benign_std, 3) if median_v is not None else None
            n_total = len(episodes)
            heatmap_cells.append({
                "cancer_type":  ct,
                "test_key":     key,
                "n_with_data":  tc["n"],
                "n_total":      n_total,
                "effect_size":  effect,
                "pct_high":     round(tc["high"] / tc["n"] * 100, 1) if tc["n"] else None,
                "pct_low":      round(tc["low"]  / tc["n"] * 100, 1) if tc["n"] else None,
                "median_value": median_v,
                "benign_median": round(benign_median, 3),
                "ref_range_raw": benign_stats.get(key, {}).get("ref_range"),
            })

    # Ordered cancer types (by descending n_total)
    cancer_types_ordered = sorted(
        by_ct.keys(), key=lambda ct: -len(by_ct[ct])
    )

    tests_meta = [
        {"key": k, "label": _BLOOD_SIGNAL_FEATURE_LABELS[k]}
        for k in _BLOOD_SIGNAL_FEATURE_KEYS
    ]

    return {
        "cancer_types":  cancer_types_ordered,
        "tests":         tests_meta,
        "heatmap_cells": heatmap_cells,
        "patient_flags": patient_flags,
    }


def _q_blood_signal(client: PatientGraphClient) -> dict:
    import json

    def _row_to_dict(r: dict) -> dict:
        features: dict[str, float | None] = {}
        for k in _BLOOD_SIGNAL_FEATURE_KEYS:
            v = r.get(k)
            features[k] = float(v) if v is not None else None
        return {
            "id":          str(r.get("episode_id") or ""),
            "cohort_label": str(r.get("cohort_label") or "benign"),
            "cancer_type":  str(r.get("cancer_type") or "") or None,
            "cluster":      int(r["cluster"]) if r.get("cluster") is not None else None,
            "features":     features,
        }

    ep_rows = client.run(_BLOOD_EPISODE_Q)
    bp_rows = client.run(_BLOOD_PANEL_Q)

    all_rows = [_row_to_dict(dict(r)) for r in ep_rows + bp_rows]

    correlations: dict[str, float] = {}
    updated_at: str | None = None
    analysis_rows = client.run(_BLOOD_ANALYSIS_Q)
    if analysis_rows:
        ar = analysis_rows[0]
        if ar.get("correlations_json"):
            correlations = json.loads(ar["correlations_json"])
        updated_at = str(ar.get("updated_at") or "")

    cancer_n = sum(1 for r in all_rows if r["cohort_label"] == "cancer")
    benign_n = sum(1 for r in all_rows if r["cohort_label"] == "benign")

    return {
        "episodes":      all_rows,
        "feature_keys":  _BLOOD_SIGNAL_FEATURE_KEYS,
        "feature_labels": _BLOOD_SIGNAL_FEATURE_LABELS,
        "correlations":  correlations,
        "cancer_n":      cancer_n,
        "benign_n":      benign_n,
        "total_n":       len(all_rows),
        "updated_at":    updated_at,
    }
