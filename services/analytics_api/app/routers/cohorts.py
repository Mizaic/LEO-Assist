"""Cohort management endpoints.

Create, list, and resolve patient cohorts by various filters.
Cohort definitions are stored as Cohort nodes in the Patient Graph.

NHS screening programme presets are defined in code (source of truth, versionable)
and seeded into the graph at startup via `seed_nhs_cohorts()`. They appear in
`GET /cohorts` alongside user-created cohorts, distinguished by `is_system: true`
and the `source: "nhs_preset"` graph property — the UI should show a lock icon
and suppress the delete button for these.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from libs.auth.org_scope import CallerScope, get_caller_scope
from libs.neo4j_client.client import PatientGraphClient

logger = logging.getLogger(__name__)
router = APIRouter()

# Assertions that confirm a condition is present for cohort eligibility.
# 'historical' is included so ex-diagnosis codes are matched (e.g. ex-smoker).
_CONFIRMED_ASSERTIONS: frozenset[str] = frozenset({"present", "historical"})

# ── NHS screening cohort presets — loaded from JSON, not hardcoded ────────
# Edit services/analytics_api/app/data/nhs_screening_cohorts.json to add or
# update programmes. The loader below makes them available at import time so
# seed_nhs_cohorts() can reference them without re-reading the file.

_PRESETS_FILE = Path(__file__).parent.parent / "data" / "nhs_screening_cohorts.json"


def _load_nhs_presets() -> List[Dict[str, Any]]:
    try:
        data = json.loads(_PRESETS_FILE.read_text(encoding="utf-8"))
        return data.get("cohorts", [])
    except FileNotFoundError:
        logger.error("NHS screening cohorts file not found: %s", _PRESETS_FILE)
        return []
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse NHS screening cohorts file: %s", exc)
        return []


NHS_SCREENING_COHORT_PRESETS: List[Dict[str, Any]] = _load_nhs_presets()


# ── Request / Response models ────────────────────────────────────────────


class CohortFilter(BaseModel):
    org_id: Optional[str] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    condition_codes: Optional[List[str]] = None
    episode_status: Optional[List[str]] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    # "female" | "male" | None - maps to p.gender in the Patient graph.
    # Used for gender-specific programmes (breast, cervical screening).
    sex: Optional[str] = None
    # "current_smoker" | "ever_smoker" - shorthand for lifestyle filter.
    smoking_status: Optional[str] = None
    custom_cypher: Optional[str] = None

    # -- Patient finder extensions (DI-LEO-AI-230) --
    # IMD decile of the patient's primary address. 1 = most deprived, 10 = least.
    # Stored on (Patient)-[:HAS_ADDRESS]->(Address) by /imd/enrich.
    imd_decile_min: Optional[int] = None
    imd_decile_max: Optional[int] = None
    # Encounter activity. Window defaults to 12 months ending today.
    encounter_count_min: Optional[int] = None
    encounter_count_max: Optional[int] = None
    encounter_count_window_months: Optional[int] = None
    # Episode of care domain (e.g. "cancer_audit") and subdomain
    # (e.g. "breast"). Subdomain matches against ep.cancer_type when domain
    # is cancer_audit, and against ep.subdomain otherwise.
    episode_domain: Optional[str] = None
    episode_subdomain: Optional[str] = None
    # Episode outcome shorthand. Reuses libs/analytics/cohorts canonical
    # NCDA fragments for cancer outcomes; "in_progress" / "any_open"
    # cover work-in-progress episodes.
    # Allowed: "confirmed_cancer", "two_week_wait_route", "benign",
    # "in_progress", "any_open"
    episode_outcome: Optional[str] = None


class CohortCreateRequest(BaseModel):
    name: str
    description: str = ""
    filters: CohortFilter


class CohortResponse(BaseModel):
    cohort_id: str
    name: str
    description: str
    filters: Dict[str, Any]
    patient_count: int = 0
    created_at: Optional[str] = None
    # True for NHS presets seeded at startup — UI should lock these from deletion.
    is_system: bool = False
    # Additional metadata carried through from NHS presets (programme name, frequency).
    meta: Optional[Dict[str, Any]] = None


class CohortPatientsResponse(BaseModel):
    cohort_id: str
    patient_ids: List[str]
    total: int


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/cohorts", response_model=CohortResponse)
def create_cohort(
    body: CohortCreateRequest,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Create a new saved cohort definition."""
    client = PatientGraphClient()
    cohort_id = f"COH_{uuid4().hex[:12]}"
    try:
        patient_count = _resolve_patient_count(client, body.filters)
        created_by_org = scope.primary_org_id or "platform"
        client.run(
            "CREATE (c:Cohort { "
            "    cohort_id: $cid, name: $name, description: $desc, "
            "    filters: $filters, patient_count: $count, "
            "    source: 'user', "
            "    created_by_org_id: $org_id, "
            "    created_by_email: $email, "
            "    created_at: datetime(), created_by: 'analytics_api' "
            "})",
            cid=cohort_id,
            name=body.name,
            desc=body.description,
            filters=body.filters.model_dump_json(),
            count=patient_count,
            org_id=created_by_org,
            email=scope.email,
        )
        return CohortResponse(
            cohort_id=cohort_id,
            name=body.name,
            description=body.description,
            filters=body.filters.model_dump(),
            patient_count=patient_count,
            is_system=False,
        )
    finally:
        client.close()


@router.get("/cohorts", response_model=List[CohortResponse])
def list_cohorts(scope: CallerScope = Depends(get_caller_scope)):
    """List saved cohort definitions visible to the caller.

    Returns NHS presets (visible to all) + user-created cohorts whose
    ``created_by_org_id`` is within the caller's org hierarchy.
    Admins see everything.
    """
    client = PatientGraphClient()
    try:
        if scope.is_admin:
            where = ""
            params: dict[str, Any] = {}
        else:
            where = (
                "WHERE c.source = 'nhs_preset' "
                "   OR c.created_by_org_id IN $scope_org_ids "
                "   OR c.created_by_org_id IS NULL "
            )
            params = {"scope_org_ids": scope.org_ids}
        rows = client.run(
            f"MATCH (c:Cohort) {where}"
            "RETURN c.cohort_id AS cohort_id, c.name AS name, "
            "       c.description AS description, c.filters AS filters, "
            "       c.patient_count AS patient_count, "
            "       toString(c.created_at) AS created_at, "
            "       coalesce(c.source, 'user') AS source, "
            "       c.meta AS meta "
            "ORDER BY c.source DESC, c.created_at ASC",
            **params,
        )
        result = []
        for row in rows:
            filters_raw = row.get("filters", "{}")
            try:
                filters = (
                    json.loads(filters_raw)
                    if isinstance(filters_raw, str)
                    else filters_raw
                )
            except (json.JSONDecodeError, TypeError):
                filters = {}
            meta_raw = row.get("meta")
            try:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            except (json.JSONDecodeError, TypeError):
                meta = None
            result.append(
                CohortResponse(
                    cohort_id=row["cohort_id"],
                    name=row.get("name", ""),
                    description=row.get("description", ""),
                    filters=filters,
                    patient_count=row.get("patient_count", 0),
                    created_at=row.get("created_at"),
                    is_system=(row.get("source") == "nhs_preset"),
                    meta=meta,
                )
            )
        return result
    finally:
        client.close()


@router.get("/cohorts/{cohort_id}/patients", response_model=CohortPatientsResponse)
def resolve_cohort(
    cohort_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Resolve a cohort to a list of patient IDs."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) "
            "RETURN c.filters AS filters, coalesce(c.source, 'user') AS source, "
            "       c.created_by_org_id AS created_by_org_id",
            cid=cohort_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cohort not found")
        row0 = rows[0]
        is_preset = row0.get("source") == "nhs_preset"
        owner_org = row0.get("created_by_org_id")
        if (
            not scope.is_admin
            and not is_preset
            and owner_org
            and owner_org not in scope.org_ids
        ):
            raise HTTPException(status_code=404, detail="Cohort not found")

        filters_raw = rows[0].get("filters", "{}")
        try:
            filters_dict = (
                json.loads(filters_raw) if isinstance(filters_raw, str) else filters_raw
            )
        except (json.JSONDecodeError, TypeError):
            filters_dict = {}

        filters = CohortFilter(**filters_dict)
        patient_ids = _resolve_patients(client, filters)

        client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) SET c.patient_count = $count",
            cid=cohort_id,
            count=len(patient_ids),
        )

        return CohortPatientsResponse(
            cohort_id=cohort_id,
            patient_ids=patient_ids,
            total=len(patient_ids),
        )
    finally:
        client.close()


class CohortPreviewResponse(BaseModel):
    """Lightweight count + sample for an unsaved CohortFilter.

    Used by the PatientFinder primitive's Filter tab so a reviewer can
    refine the filter ('how many patients does this match?') before
    deciding whether to persist a Cohort node.
    """

    patient_count: int
    sample_patient_ids: List[str]


@router.post("/cohorts/preview", response_model=CohortPreviewResponse)
def preview_cohort(
    filters: CohortFilter,
    scope: CallerScope = Depends(get_caller_scope),  # noqa: ARG001 -- gating
):
    """Resolve an ad-hoc CohortFilter without persisting a Cohort node.

    Returns the total count of matching patients and up to 25 sample
    patient ids for a quick UI preview. The filter is not saved.
    """
    client = PatientGraphClient()
    try:
        count = _resolve_patient_count(client, filters)
        sample: List[str] = []
        if count > 0:
            where_clause, params = _build_where_clauses(filters)
            rows = client.run(
                f"MATCH (p:Patient) WHERE {where_clause} "
                f"RETURN toString(p.id) AS patient_id "
                f"ORDER BY p.id LIMIT 25",
                **params,
            )
            sample = [str(r["patient_id"]) for r in rows]
        return CohortPreviewResponse(
            patient_count=count, sample_patient_ids=sample
        )
    finally:
        client.close()


@router.delete("/cohorts/{cohort_id}")
def delete_cohort(
    cohort_id: str,
    scope: CallerScope = Depends(get_caller_scope),
):
    """Delete a saved cohort definition. NHS system presets cannot be deleted."""
    client = PatientGraphClient()
    try:
        rows = client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) "
            "RETURN coalesce(c.source, 'user') AS source, "
            "       c.created_by_org_id AS created_by_org_id",
            cid=cohort_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cohort not found")
        if rows[0].get("source") == "nhs_preset":
            raise HTTPException(
                status_code=403,
                detail="NHS system cohorts cannot be deleted. "
                "Use POST /cohorts to create a copy.",
            )
        owner_org = rows[0].get("created_by_org_id")
        if not scope.is_admin and owner_org and owner_org not in scope.org_ids:
            raise HTTPException(
                status_code=403, detail="Not authorized to delete this cohort"
            )
        client.run(
            "MATCH (c:Cohort {cohort_id: $cid}) DELETE c",
            cid=cohort_id,
        )
        return {"success": True}
    finally:
        client.close()


# ── NHS preset seeding (called at app startup) ────────────────────────────


def seed_nhs_cohorts(client: Optional[PatientGraphClient] = None) -> int:
    """Idempotently persist NHS screening programme presets into the graph.

    Called from the analytics API lifespan at startup. Only seeds when no NHS
    preset cohorts exist; skips if any are already present to avoid overwriting.
    Returns the number of presets upserted (0 when skipped).
    """
    own_client = client is None
    if own_client:
        client = PatientGraphClient()
    seeded = 0
    try:
        rows = client.run(
            "MATCH (c:Cohort) WHERE c.source = 'nhs_preset' RETURN count(c) AS cnt"
        )
        existing = rows[0]["cnt"] if rows else 0
        if existing > 0:
            logger.debug(
                "[Cohorts] %d NHS preset(s) already present; skipping seed",
                existing,
            )
            return 0

        for preset in NHS_SCREENING_COHORT_PRESETS:
            cohort_id = f"COH_NHS_{preset['id']}"
            filters = CohortFilter(**preset["filters"])
            try:
                patient_count = _resolve_patient_count(client, filters)
            except Exception as exc:
                logger.warning(
                    "Could not count patients for %s: %s", preset["name"], exc
                )
                patient_count = 0

            meta = json.dumps(
                {
                    "programme": preset.get("programme"),
                    "invite_frequency_years": preset.get("invite_frequency_years"),
                }
            )

            client.run(
                "MERGE (c:Cohort {cohort_id: $cid}) "
                "ON CREATE SET "
                "    c.name = $name, c.description = $desc, "
                "    c.filters = $filters, c.patient_count = $count, "
                "    c.source = 'nhs_preset', c.meta = $meta, "
                "    c.created_at = datetime(), c.created_by = 'system' "
                "ON MATCH SET "
                "    c.description = $desc, "
                "    c.patient_count = $count, "
                "    c.meta = $meta",
                cid=cohort_id,
                name=preset["name"],
                desc=preset["description"],
                filters=filters.model_dump_json(),
                count=patient_count,
                meta=meta,
            )
            logger.info(
                "NHS cohort seeded: %s → %d patients", preset["name"], patient_count
            )
            seeded += 1
    finally:
        if own_client:
            client.close()
    return seeded


# ── Filter resolution helpers ────────────────────────────────────────────


def _build_where_clauses(f: CohortFilter) -> tuple[str, Dict[str, Any]]:
    """Build Cypher WHERE clauses from cohort filters."""
    clauses: List[str] = []
    params: Dict[str, Any] = {}

    if f.org_id:
        # Traverse GP -> ICB -> CancerAlliance hierarchy so filtering works at any level
        clauses.append(
            "EXISTS { "
            "MATCH (_scope:Organization {id: $org_id}) "
            "MATCH (p)-[:HAS_GENERAL_PRACTITIONER]->(gp) "
            "WHERE (gp.id = $org_id) OR (gp)-[:COMMISSIONED_BY]->(_scope) "
            "   OR (gp)-[:COMMISSIONED_BY]->(:ICB)-[:PART_OF_ALLIANCE]->(_scope) "
            "}"
        )
        params["org_id"] = f.org_id

    if f.date_range_start:
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(e.date) >= $date_start }"
        )
        params["date_start"] = f.date_range_start

    if f.date_range_end:
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->(e:Encounter) "
            "WHERE toString(e.date) <= $date_end }"
        )
        params["date_end"] = f.date_range_end

    if f.condition_codes:
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->()-[r:DOCUMENTS]->(c) "
            "WHERE toString(c.conceptId) IN $codes "
            "  AND coalesce(r.assertion, 'present') IN $confirmed_assertions }"
        )
        params["codes"] = f.condition_codes
        params["confirmed_assertions"] = list(_CONFIRMED_ASSERTIONS)

    if f.episode_status:
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
            "WHERE ep.status IN $ep_statuses }"
        )
        params["ep_statuses"] = f.episode_status

    if f.age_min is not None:
        clauses.append("p.age >= $age_min")
        params["age_min"] = f.age_min

    if f.age_max is not None:
        clauses.append("p.age <= $age_max")
        params["age_max"] = f.age_max

    if f.sex:
        clauses.append("toLower(coalesce(p.gender, p.sex, '')) = toLower($sex)")
        params["sex"] = f.sex

    if f.smoking_status == "ever_smoker":
        # SNOMED: 160625004 Ex-smoker, 77176002 Smoker, 449868002 Smokes tobacco daily
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->()-[r:DOCUMENTS]->(c) "
            "WHERE c.conceptId IN [160625004, 77176002, 449868002, 230059006] "
            "  AND coalesce(r.assertion, 'present') IN $confirmed_assertions }"
        )
        params.setdefault("confirmed_assertions", list(_CONFIRMED_ASSERTIONS))
    elif f.smoking_status == "current_smoker":
        # SNOMED: 77176002 Smoker, 449868002 Smokes tobacco daily
        clauses.append(
            "EXISTS { MATCH (p)-[:HAS_ENCOUNTER]->()-[r:DOCUMENTS]->(c) "
            "WHERE c.conceptId IN [77176002, 449868002, 230059006] "
            "  AND coalesce(r.assertion, 'present') IN $confirmed_assertions }"
        )
        params.setdefault("confirmed_assertions", list(_CONFIRMED_ASSERTIONS))

    _append_imd_clause(f, clauses, params)
    _append_encounter_count_clause(f, clauses, params)
    _append_episode_domain_clause(f, clauses, params)
    _append_episode_outcome_clause(f, clauses, params)

    return " AND ".join(clauses) if clauses else "true", params


# -- Patient finder filter helpers (DI-LEO-AI-230) ------------------------
#
# Each helper appends WHERE-clause fragments for one extension dimension.
# Kept as small named functions to keep _build_where_clauses() readable
# and to give each filter a single test target.


def _append_imd_clause(
    f: CohortFilter, clauses: List[str], params: Dict[str, Any]
) -> None:
    if f.imd_decile_min is None and f.imd_decile_max is None:
        return
    inner: list[str] = []
    if f.imd_decile_min is not None:
        inner.append("a.imd_decile >= $imd_decile_min")
        params["imd_decile_min"] = f.imd_decile_min
    if f.imd_decile_max is not None:
        inner.append("a.imd_decile <= $imd_decile_max")
        params["imd_decile_max"] = f.imd_decile_max
    clauses.append(
        "EXISTS { MATCH (p)-[:HAS_ADDRESS]->(a:Address) "
        "WHERE a.imd_decile IS NOT NULL AND " + " AND ".join(inner) + " }"
    )


def _append_encounter_count_clause(
    f: CohortFilter, clauses: List[str], params: Dict[str, Any]
) -> None:
    if f.encounter_count_min is None and f.encounter_count_max is None:
        return
    months = f.encounter_count_window_months or 12
    params["encounter_window_months"] = months
    # COUNT { ... } subquery (Neo4j 5.x) is the cleanest way to express
    # "encounters in the last N months" without a top-level WITH that
    # would clash with the cohort caller's MATCH / WHERE pipeline.
    count_expr = (
        "COUNT { (p)-[:HAS_ENCOUNTER]->(_e:Encounter) "
        "WHERE _e.date IS NOT NULL "
        "AND date(_e.date) >= "
        "date() - duration({months: $encounter_window_months}) }"
    )
    bounds: list[str] = []
    if f.encounter_count_min is not None:
        bounds.append(f"{count_expr} >= $encounter_count_min")
        params["encounter_count_min"] = f.encounter_count_min
    if f.encounter_count_max is not None:
        bounds.append(f"{count_expr} <= $encounter_count_max")
        params["encounter_count_max"] = f.encounter_count_max
    clauses.append("(" + " AND ".join(bounds) + ")")


def _append_episode_domain_clause(
    f: CohortFilter, clauses: List[str], params: Dict[str, Any]
) -> None:
    if not f.episode_domain and not f.episode_subdomain:
        return
    # Subdomain on cancer_audit episodes maps to ep.cancer_type for backward
    # compatibility with the NCDA episode builder. For other audit domains
    # we look at ep.subdomain.
    inner: list[str] = []
    if f.episode_domain:
        inner.append("coalesce(ep.domain, 'cancer_audit') = $episode_domain")
        params["episode_domain"] = f.episode_domain
    if f.episode_subdomain:
        if (f.episode_domain or "cancer_audit") == "cancer_audit":
            inner.append("ep.cancer_type = $episode_subdomain")
        else:
            inner.append("coalesce(ep.subdomain, '') = $episode_subdomain")
        params["episode_subdomain"] = f.episode_subdomain
    clauses.append(
        "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        "WHERE " + " AND ".join(inner) + " }"
    )


def _append_episode_outcome_clause(
    f: CohortFilter, clauses: List[str], params: Dict[str, Any]
) -> None:
    """Filter patients by episode-level outcome shorthand.

    Reuses canonical NCDA fragments from libs.analytics.cohorts so this
    cohort agrees with /audit/summary on what 'confirmed cancer' means.
    """
    if not f.episode_outcome:
        return
    from libs.analytics.cohorts import (
        confirmed_cancer_where,
        suspected_cancer_referral_where,
    )

    outcome = f.episode_outcome
    if outcome == "confirmed_cancer":
        predicate = confirmed_cancer_where("ep")
    elif outcome == "two_week_wait_route":
        predicate = suspected_cancer_referral_where("ep")
    elif outcome == "benign":
        predicate = (
            "(ep.status = 'closed_benign' "
            "OR coalesce(ep.letter_inferred_benign, false) = true)"
        )
    elif outcome == "in_progress":
        predicate = "ep.status = 'in_progress'"
    elif outcome == "any_open":
        predicate = (
            "NOT ep.status IN "
            "['merged', 'closed_phantom', 'closed_related']"
        )
    else:
        # Unknown outcome -> no clause added; treat as a no-op so a typo
        # doesn't silently match every patient via false-WHERE collapse.
        return
    clauses.append(
        "EXISTS { MATCH (p)-[:HAS_EPISODE_OF_CARE]->(ep:EpisodeOfCare) "
        f"WHERE {predicate} }}"
    )


def _resolve_patients(client: PatientGraphClient, f: CohortFilter) -> List[str]:
    """Resolve a filter to a list of patient IDs."""
    if f.custom_cypher:
        rows = client.run(f.custom_cypher)
        return [str(r.get("patient_id", r.get("id", ""))) for r in rows if r]

    where_clause, params = _build_where_clauses(f)
    rows = client.run(
        f"MATCH (p:Patient) WHERE {where_clause} "
        f"RETURN toString(p.id) AS patient_id ORDER BY p.id LIMIT 10000",
        **params,
    )
    return [str(r["patient_id"]) for r in rows]


def _resolve_patient_count(client: PatientGraphClient, f: CohortFilter) -> int:
    """Count patients matching a filter without returning all IDs."""
    if f.custom_cypher:
        rows = client.run(f"WITH {{ {f.custom_cypher} }} AS sub RETURN count(*) AS cnt")
        return rows[0].get("cnt", 0) if rows else 0

    where_clause, params = _build_where_clauses(f)
    rows = client.run(
        f"MATCH (p:Patient) WHERE {where_clause} RETURN count(p) AS cnt",
        **params,
    )
    return rows[0].get("cnt", 0) if rows else 0
