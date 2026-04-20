"""Stage-at-diagnosis enrichment subgraph.

Atlas trace:
  DO: DO-6DFD03E0
  Also implements: DO-A23404E0
  DI: DI-23822663, DI-527848A8, DO-671C15BF
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-6DFD03E0")

Scopes staging evidence to a post-diagnosis 90-day window and filters
encounter text through the cancer-type specialty marker (DI-LEO-AI-126,
R-LEO-AI-086). Both controls prevent stage mis-attribution on patients
with multiple concurrent cancer pathways.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from libs.clinical_scoping import filter_rows_by_specialty
from libs.staging.engine import StagingRulesEngine
from libs.staging.tnm_parser import parse_tnm_triplet

# DI-LEO-AI-126: post-diagnosis staging evidence window in days.
STAGING_WINDOW_DAYS = 90

logger = logging.getLogger(__name__)

_EXPLICIT_STAGE_RE = re.compile(
    r"\b(?:stage\s*)?([0-4]|i{1,3}|iv)(?:\s*[abc])?\b", re.IGNORECASE
)

_Q_EPISODE_META = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
OPTIONAL MATCH (diag_enc:Encounter)-[m:IS_PART_OF]->(ep)
  WHERE m.milestone_type IN ['diagnosis', 'diagnosis_confirmed']
WITH ep, min(toString(diag_enc.date)) AS diagnosis_date
RETURN ep.episode_id AS episode_id,
       ep.patient_id AS patient_id,
       toString(ep.referral_date) AS referral_date,
       toString(ep.end_date) AS end_date,
       diagnosis_date,
       toString(ep.cancer_type) AS cancer_type
"""

_Q_STAGING_EVIDENCE = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
MATCH (enc:Encounter)-[:IS_PART_OF]->(ep)
WHERE toString(enc.date) >= $window_start
  AND toString(enc.date) <= $window_end
OPTIONAL MATCH (enc)-[d:DOCUMENTS]->(c)
RETURN toString(enc.date) AS encounter_date,
       coalesce(enc.text, '') AS encounter_text,
       coalesce(toString(c.conceptId), '') AS concept_id,
       coalesce(c.name, '') AS concept_name,
       coalesce(toString(d.domain), '') AS domain,
       coalesce(toString(d.assertion), 'present') AS assertion
ORDER BY encounter_date
"""

_Q_SET_STAGING = """
MATCH (ep:EpisodeOfCare {episode_id: $episode_id})
SET ep.cancer_stage = $cancer_stage,
    ep.cancer_stage_raw = $cancer_stage_raw,
    ep.cancer_stage_group = $cancer_stage_group,
    ep.tnm_t = $tnm_t,
    ep.tnm_n = $tnm_n,
    ep.tnm_m = $tnm_m,
    ep.staging_system = $staging_system,
    ep.staging_source = $staging_source,
    ep.staging_confidence = $staging_confidence,
    ep.updated_at = datetime()
"""


class StagingState(TypedDict, total=False):
    patient_id: str
    episode_ids: list[str]
    errors: list[str]


def _choose_window(meta: dict[str, Any]) -> tuple[str, str]:
    """Select the staging evidence window.

    Preferred: [diagnosis_date, diagnosis_date + STAGING_WINDOW_DAYS].
    Fallback (only when diagnosis_date is missing): [referral_date, end_date]
    to preserve legacy behaviour for episodes that lack a diagnosis anchor.
    """
    diagnosis_date = str(meta.get("diagnosis_date") or "")[:10]
    if diagnosis_date:
        try:
            start_d = date.fromisoformat(diagnosis_date)
            end_d = start_d + timedelta(days=STAGING_WINDOW_DAYS)
            return diagnosis_date, end_d.isoformat()
        except ValueError:
            pass
    referral_date = str(meta.get("referral_date") or "")[:10]
    end_date = str(meta.get("end_date") or "")[:10]
    start = referral_date or diagnosis_date
    end = end_date or diagnosis_date or referral_date
    return start, end


def _extract_evidence(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    explicit_stage: str | None = None
    tnm_triplet: str | None = None
    for row in rows:
        if str(row.get("assertion") or "present").lower() not in ("present", ""):
            continue
        concept_name = str(row.get("concept_name") or "")
        text = str(row.get("encounter_text") or "")
        if explicit_stage is None:
            stage_match = _EXPLICIT_STAGE_RE.search(
                concept_name
            ) or _EXPLICIT_STAGE_RE.search(text)
            if stage_match:
                explicit_stage = stage_match.group(0)
        if tnm_triplet is None:
            maybe = parse_tnm_triplet(concept_name) or parse_tnm_triplet(text)
            if maybe:
                tnm_triplet = maybe.raw
        if explicit_stage and tnm_triplet:
            break
    return explicit_stage, tnm_triplet


def enrich_staging(state: StagingState) -> dict[str, Any]:
    errors = list(state.get("errors") or [])
    episode_ids = list(state.get("episode_ids") or [])
    if not episode_ids:
        return {"errors": errors}

    try:
        from libs.neo4j_client.client import PatientGraphClient
    except Exception as exc:  # noqa: BLE001
        return {"errors": errors + [f"staging_enrichment: client import failed: {exc}"]}

    engine = StagingRulesEngine()
    engine.load_rules()
    client = PatientGraphClient()
    try:
        for episode_id in episode_ids:
            try:
                meta_rows = client.run(_Q_EPISODE_META, episode_id=episode_id) or []
                if not meta_rows:
                    continue
                meta = meta_rows[0]
                window_start, window_end = _choose_window(meta)
                if not window_start or not window_end:
                    continue
                evidence_rows = (
                    client.run(
                        _Q_STAGING_EVIDENCE,
                        episode_id=episode_id,
                        window_start=window_start,
                        window_end=window_end,
                    )
                    or []
                )
                # DI-LEO-AI-126: filter by cancer-type specialty marker so
                # evidence from a concurrent cancer pathway cannot leak into
                # this episode's stage derivation. filter_rows_by_specialty
                # falls back to the unfiltered set when no marker is defined
                # or when zero rows match, so staging coverage is preserved.
                cancer_type = str(meta.get("cancer_type") or "")
                evidence_rows = filter_rows_by_specialty(
                    evidence_rows, cancer_type, text_key="encounter_text"
                )
                explicit_stage, tnm_triplet = _extract_evidence(evidence_rows)
                source = "coded"
                if not explicit_stage and not tnm_triplet:
                    source = "text_scan"
                result = engine.resolve_stage(
                    cancer_type_snomed=str(meta.get("cancer_type") or ""),
                    tnm=tnm_triplet,
                    explicit_stage=explicit_stage,
                    source=source,
                )
                client.run(
                    _Q_SET_STAGING,
                    episode_id=episode_id,
                    cancer_stage=result.cancer_stage,
                    cancer_stage_raw=result.cancer_stage_raw,
                    cancer_stage_group=result.cancer_stage_group,
                    tnm_t=result.tnm_t,
                    tnm_n=result.tnm_n,
                    tnm_m=result.tnm_m,
                    staging_system=result.staging_system,
                    staging_source=result.staging_source,
                    staging_confidence=result.staging_confidence,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("staging enrichment failed for episode %s", episode_id)
                errors.append(f"{episode_id}: {exc}")
    finally:
        client.close()
    return {"errors": errors}


def build_staging_enrichment_subgraph() -> CompiledStateGraph:
    g = StateGraph(StagingState)
    g.add_node("enrich_staging", enrich_staging)
    g.add_edge(START, "enrich_staging")
    g.add_edge("enrich_staging", END)
    return g.compile()
