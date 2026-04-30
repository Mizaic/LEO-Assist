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
# Prior cancer-related consultations + NCDA "multiple consultations" factors
# ---------------------------------------------------------------------------


def _q_prior_consultations(
    base: str, params: dict, client: PatientGraphClient
) -> dict:
    """NCDA Section 7 ("multiple consultations") per-cohort breakdown.

    Mirrors :func:`_q_care_obstructions` so the front-end can reuse the
    same EvolutionYearCard / EvolutionDetailDialog components.  Reads
    the ``prior_consultations_*`` properties stamped onto each
    EpisodeOfCare by
    ``libs/oncology/prior_consultations.classify_episode_consultations``
    and ``scripts/ncda/run_prior_consultations_enrichment.py``.

    Returns:
      - Headline metric: % of episodes with 2+ cancer-related
        consultations in the year before the FTR (the NCDA "multiple
        consultations" condition).
      - Distribution buckets (0 / 1 / 2-3 / 4-6 / 7+ consultations).
      - Per-contact-type means (f2f, phone, nurse, email, specialist
        clinic, home visit, phlebotomy, result review).
      - Top-N NCDA factor codes proposed by the LLM, ranked by
        frequency, suitable for the dialog "Why multiple consultations?"
        bar chart.
      - Aggregated LLM cost / token / call counts so the dashboard can
        surface the per-tile spend without hitting LLMSpendPanel.
    """
    rows = client.run(
        f"{base}"
        "OPTIONAL MATCH (ep)<-[:HAS_AUDIT_EVENT|HAS_AUDIT]-(:Patient)"
        "  -[:HAS_AUDIT_EVENT]->(ae:AuditEvent {"
        "    type:'PipelineRun', event_type:'ncda_prior_consultations'})"
        "  WHERE ae.episode_id = ep.episode_id "
        "WITH ep, ae, ep.multiple_consultations_factors_auto AS factors_auto "
        "RETURN "
        "  count(DISTINCT ep) AS total_episodes, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 2 "
        "       THEN 1 ELSE 0 END) AS multi_n, "
        "  sum(CASE WHEN ep.prior_consultations_n IS NOT NULL "
        "       THEN 1 ELSE 0 END) AS enriched_n, "
        "  sum(CASE WHEN coalesce(ep.prior_consultations_n, 0) = 0 "
        "       THEN 1 ELSE 0 END) AS bucket_zero, "
        "  sum(CASE WHEN ep.prior_consultations_n = 1 "
        "       THEN 1 ELSE 0 END) AS bucket_one, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 2 "
        "       AND ep.prior_consultations_n <= 3 "
        "       THEN 1 ELSE 0 END) AS bucket_two_three, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 4 "
        "       AND ep.prior_consultations_n <= 6 "
        "       THEN 1 ELSE 0 END) AS bucket_four_six, "
        "  sum(CASE WHEN ep.prior_consultations_n >= 7 "
        "       THEN 1 ELSE 0 END) AS bucket_seven_plus, "
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
        "  collect(factors_auto) AS factor_arrays, "
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
    s = rows[0] if rows else {}
    total = int(s.get("total_episodes") or 0)
    safe_total = total or 1
    enriched = int(s.get("enriched_n") or 0)
    multi = int(s.get("multi_n") or 0)
    safe_enriched = enriched or 1

    factor_counts: dict[str, int] = {}
    for arr in s.get("factor_arrays") or []:
        if not arr:
            continue
        for code in arr:
            if not code or code == "no_multiple_consultations":
                continue
            factor_counts[code] = factor_counts.get(code, 0) + 1
    top_factors = sorted(
        ({"factor": k, "n": v} for k, v in factor_counts.items()),
        key=lambda r: (-r["n"], r["factor"]),
    )[:10]

    return {
        # Headline % drives the snapshot tile.
        "multiple_consultations_pct": round(multi * 100.0 / safe_total, 1),
        "multiple_consultations_n": multi,
        "total_episodes": total,
        "enriched_n": enriched,
        "enriched_pct": round(enriched * 100.0 / safe_total, 1),
        # Distribution buckets for the dialog histogram.
        "buckets": {
            "0":      int(s.get("bucket_zero") or 0),
            "1":      int(s.get("bucket_one") or 0),
            "2-3":    int(s.get("bucket_two_three") or 0),
            "4-6":    int(s.get("bucket_four_six") or 0),
            "7+":     int(s.get("bucket_seven_plus") or 0),
        },
        "buckets_pct": {
            "0":   round(int(s.get("bucket_zero") or 0)      * 100.0 / safe_total, 1),
            "1":   round(int(s.get("bucket_one") or 0)       * 100.0 / safe_total, 1),
            "2-3": round(int(s.get("bucket_two_three") or 0) * 100.0 / safe_total, 1),
            "4-6": round(int(s.get("bucket_four_six") or 0)  * 100.0 / safe_total, 1),
            "7+":  round(int(s.get("bucket_seven_plus") or 0) * 100.0 / safe_total, 1),
        },
        # Mean per enriched episode by contact type.
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
        # Aggregated totals (for the dialog footer).
        "total_consultations":     int(s.get("total_consultations") or 0),
        "unrelated_filtered_total": int(s.get("unrelated_filtered_total") or 0),
        # Top NCDA factor codes (drives the "Why multiple consultations?"
        # bar chart in the dialog).
        "top_factors": top_factors,
        # LLM cost / token telemetry -- exposed so the dashboard can show
        # the spend behind this tile without hitting LLMSpendPanel.
        "llm_cost_usd": round(float(s.get("llm_cost_usd") or 0.0), 4),
        "llm_input_tokens":  int(s.get("llm_input_tokens") or 0),
        "llm_output_tokens": int(s.get("llm_output_tokens") or 0),
        "llm_calls":         int(s.get("llm_calls") or 0),
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
