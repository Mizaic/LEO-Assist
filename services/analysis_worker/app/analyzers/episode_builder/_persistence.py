"""Episode persistence: graph writes with retry and structured error logging.

Atlas trace:
  DO: DO-0C7A443A
  Also implements: DO-6C398363
  DI: DI-080A2454, DI-FC264BBF, DI-FF9C74E2
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-0C7A443A")
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

from . import _config as cfg
from . import _cypher as cypher
from ._site_resolution import _extract_condition_key_from_anchor, _site_keys_compatible
from ._types import EpisodeBuildResult, WriteEpisodeParams, _parse_date

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_DELAY_S = 0.3
_CONFIRMED_ASSERTIONS = ("present", "historical")
_FINDING_TAGS = ("finding", "clinical finding", "disorder", "situation")


def _run_with_retry(client: Any, query: str, label: str, **kwargs: Any) -> list:
    """Execute a Cypher query with simple retry for transient failures."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return client.run(query, **kwargs) or []
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "Retrying %s (attempt %d/%d): %s",
                    label,
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                )
                time.sleep(_RETRY_DELAY_S * (attempt + 1))
            else:
                logger.error(
                    "%s failed after %d attempts: %s", label, _MAX_RETRIES + 1, exc
                )
    raise last_exc  # type: ignore[misc]


def _write_episode(
    patient_client: Any,
    params: WriteEpisodeParams,
    result: EpisodeBuildResult,
    episode_ids: list[str],
) -> None:
    """Persist one episode node; updates result counters on success."""
    auto_closed = params.status in (
        "closed_phantom",
        "closed_related",
        "stale_no_diagnosis",
        "stale_post_specialist",
    )
    auto_close_reason = (
        "phantom_multi_referral_encounter"
        if params.status == "closed_phantom"
        else None
    )
    try:
        _run_with_retry(
            patient_client,
            cypher.MERGE_EPISODE,
            f"MERGE episode {params.ep_id}",
            patient_id=params.patient_id,
            episode_id=params.ep_id,
            domain_id=params.domain_id,
            condition_type=params.site_key,
            cancer_type=params.site_key,
            referral_date=params.referral_date,
            end_date=params.end_date,
            specialist_seen=params.claim.specialist_seen,
            specialist_visit_date=params.claim.specialist_visit_date,
            referral_site=params.claim.referral_site_name,
            referral_route=params.referral_route,
            place_of_presentation=params.place_of_presentation,
            first_presentation_date=params.first_presentation_date,
            presenting_complaint=params.presenting_complaint,
            status=params.status,
            auto_closed=auto_closed,
            auto_close_reason=auto_close_reason,
            hitl_flag=params.hitl_flag,
            hitl_reason=params.hitl_reason,
            letter_inferred_benign=params.letter_inferred_benign,
            referral_match_method=params.referral_match_method,
            referral_inferred=params.referral_inferred,
            first_seen_date=params.first_seen_date,
        )
        episode_ids.append(params.ep_id)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"MERGE episode {params.ep_id}: {exc}")


def _link_encounters_to_episode(
    patient_client: Any,
    episode_id: str,
    anchors_by_type: list[tuple[list[dict[str, Any]], str]],
    *,
    lock_state: Any = None,
) -> None:
    """Replace IS_PART_OF edges for one episode with current milestone links.

    DI-C424BB44 rebuild guard: when ``lock_state`` is provided, any
    ``"<encounter_id>:<episode_id>"`` key present in
    ``lock_state.locked_is_part_of_keys`` is added to the Cypher
    parameter ``locked_keys`` so the LINK_ENCOUNTERS query's WHERE NOT
    clause preserves it across the delete-and-recreate cycle.
    """
    if not episode_id:
        return
    encounter_links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor_list, milestone_type in anchors_by_type:
        for anchor in anchor_list:
            eid = str(anchor.get("encounter_id") or "")
            if eid and eid not in seen:
                # DI-LEO-AI-182: persist referral_subtype on the
                # IS_PART_OF edge when present so DQ tooling can
                # measure rejection-to-resubmission delays. Empty
                # string when the subtype is not relevant (non-referral
                # milestones) -- avoids NULL-vs-missing ambiguity.
                referral_subtype = anchor.get("referral_subtype") or ""
                encounter_links.append(
                    {
                        "encounter_id": eid,
                        "milestone_type": milestone_type,
                        "referral_subtype": referral_subtype,
                    }
                )
                seen.add(eid)
    locked_encounter_ids: list[str] = []
    if lock_state is not None and getattr(lock_state, "locked_is_part_of_keys", None):
        suffix = ":" + episode_id
        locked_encounter_ids = [
            key[: -len(suffix)]
            for key in lock_state.locked_is_part_of_keys
            if key.endswith(suffix) and key != suffix
        ]
    try:
        _run_with_retry(
            patient_client,
            cypher.LINK_ENCOUNTERS,
            f"LINK encounters -> {episode_id}",
            episode_id=episode_id,
            encounters=encounter_links,
            locked_encounter_ids=locked_encounter_ids,
        )
    except Exception:  # noqa: BLE001
        logger.error(
            "Failed to link %d encounters to episode %s",
            len(encounter_links),
            episode_id,
        )


def _benign_closure_for_episode(
    patient_id: str,
    ref_date: date,
    patient_client: Any,
    anchors: AnchorResult,
) -> date | None:
    """Return earliest benign-closure date within episode window, or None."""
    after_date = ref_date.isoformat()
    before_date = (ref_date + timedelta(days=cfg.MAX_BENIGN_CLOSURE_DAYS)).isoformat()

    if anchors.benign_closure_anchors:
        valid = [
            _parse_date(a.get("encounter_date"))
            for a in anchors.benign_closure_anchors
            if after_date <= str(a.get("encounter_date") or "") <= before_date
        ]
        clean = [d for d in valid if d]
        return min(clean) if clean else None

    try:
        rows = patient_client.run(
            cypher.BENIGN_CLOSURE_QUERY,
            patient_id=patient_id,
            concept_id=cfg.NO_CANCER_CONCEPT_ID,
            after_date=after_date,
            before_date=before_date,
        )
        dates = [_parse_date(r.get("encounter_date")) for r in (rows or [])]
        clean = [d for d in dates if d]
        return min(clean) if clean else None
    except Exception:  # noqa: BLE001
        logger.warning(
            "Benign closure query failed for patient %s ref_date %s",
            patient_id,
            ref_date,
        )
        return None


def _benign_qualifier_closure_for_episode(
    patient_id: str,
    site_key: str,
    ref_date: date,
    patient_client: Any,
) -> date | None:
    """Return earliest site-compatible benign/normal qualifier date, or None."""
    if site_key in ("unknown", "non_site_specific"):
        return None
    if not cfg.BENIGN_QUALIFIER_CONCEPT_IDS:
        return None

    after_date = ref_date.isoformat()
    before_date = (
        ref_date + timedelta(days=cfg.BENIGN_QUALIFIER_WINDOW_DAYS)
    ).isoformat()

    try:
        rows = patient_client.run(
            cypher.BENIGN_QUALIFIER_CLOSURE_QUERY,
            patient_id=patient_id,
            after_date=after_date,
            before_date=before_date,
            qualifier_ids=[str(i) for i in cfg.BENIGN_QUALIFIER_CONCEPT_IDS],
            assertions=list(_CONFIRMED_ASSERTIONS),
            finding_tags=list(_FINDING_TAGS),
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "Benign qualifier closure query failed for patient %s ref_date %s",
            patient_id,
            ref_date,
        )
        return None

    valid_dates: list[date] = []
    for row in rows or []:
        finding_key = _extract_condition_key_from_anchor(row)
        if finding_key in ("unknown", "non_site_specific"):
            continue
        if not _site_keys_compatible(site_key, finding_key):
            continue
        d = _parse_date(row.get("encounter_date"))
        if d:
            valid_dates.append(d)
    return min(valid_dates) if valid_dates else None
