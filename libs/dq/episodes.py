"""Episode health, stale analysis, completeness, and outcome inference."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from libs.dq._filters import DQFilters
from libs.dq._models import (
    EpisodeHealthResult,
    MilestoneRow,
    OutcomeInferenceResult,
    StaleEpisode,
)
from libs.dq.signal_patterns import (
    POST_BENIGN,
    POST_CANCER,
    PRIVATE_MARKERS,
    SPECIALIST_SEEN,
    has_any,
    match_signals,
)

logger = logging.getLogger(__name__)

_HEALTH_Q = """
MATCH (ep:EpisodeOfCare)
RETURN ep.status AS status,
       ep.auto_closed AS auto_closed,
       ep.hitl_flag AS hitl_flag
"""

_STALE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.status IN ['stale_no_diagnosis', 'stale_post_specialist',
                    'in_progress']
  AND ($site IS NULL OR ep.cancer_type = $site)
OPTIONAL MATCH (p:Patient)-[:HAS_EPISODE]->(ep)
OPTIONAL MATCH (p)-[:HAS_ENCOUNTER]->(enc:Encounter)
WITH ep, p, count(enc) AS enc_count,
     max(enc.date) AS last_enc
RETURN ep.id AS episode_id,
       p.id AS patient_id,
       ep.cancer_type AS site,
       ep.status AS status,
       ep.referral_date AS referral_date,
       ep.specialist_visit_date AS specialist_date,
       last_enc AS last_encounter_date,
       enc_count AS encounter_count
ORDER BY ep.referral_date
LIMIT $limit
"""

_COMPLETENESS_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ($site IS NULL OR ep.cancer_type = $site)
OPTIONAL MATCH (p:Patient)-[:HAS_EPISODE]->(ep)
RETURN ep.id AS episode_id,
       p.id AS patient_id,
       ep.cancer_type AS site,
       ep.status AS status,
       ep.referral_date IS NOT NULL AS has_referral,
       ep.specialist_seen AS specialist_seen,
       ep.specialist_visit_date IS NOT NULL AS has_specialist_date
LIMIT $limit
"""

_STALE_ENCOUNTERS_Q = """
MATCH (p:Patient {id: $patient_id})-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE enc.date >= $from_date AND enc.date <= $to_date
RETURN enc.id AS enc_id,
       enc.date AS date,
       enc.flags AS flags,
       enc.text AS text
ORDER BY enc.date
"""


def get_episode_health(client: Any, filters: Optional[DQFilters] = None) -> EpisodeHealthResult:
    """Return episode status distribution and summary counts."""
    from libs.neo4j_client.client import run_with_retry

    rows = run_with_retry(client, _HEALTH_Q)
    status_counts: dict[str, int] = {}
    hitl_count = 0
    auto_closed_count = 0

    for r in rows:
        s = r.get("status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
        if r.get("hitl_flag"):
            hitl_count += 1
        if r.get("auto_closed"):
            auto_closed_count += 1

    stale_count = sum(
        v for k, v in status_counts.items()
        if "stale" in k
    )
    return EpisodeHealthResult(
        total_count=len(rows),
        status_counts=status_counts,
        stale_count=stale_count,
        hitl_count=hitl_count,
        auto_closed_count=auto_closed_count,
    )


def get_stale_episodes(
    client: Any, filters: Optional[DQFilters] = None, threshold_days: int = 90
) -> list[StaleEpisode]:
    """Return stale or long-running in_progress episodes."""
    from libs.neo4j_client.client import run_with_retry

    f = filters or DQFilters()
    rows = run_with_retry(
        client, _STALE_Q, site=f.site, limit=f.limit
    )
    today = date.today()
    result = []
    for r in rows:
        ref = r.get("referral_date")
        days = _days_since(ref, today) if ref else 0
        result.append(StaleEpisode(
            patient_id=r.get("patient_id") or "",
            episode_id=r.get("episode_id") or "",
            site=r.get("site") or "unknown",
            status=r.get("status") or "unknown",
            days_stale=days,
            referral_date=ref,
            specialist_date=r.get("specialist_date"),
            last_encounter_date=r.get("last_encounter_date"),
            encounter_count=int(r.get("encounter_count") or 0),
        ))
    return result


def get_completeness(
    client: Any, filters: Optional[DQFilters] = None
) -> list[MilestoneRow]:
    """Return per-episode milestone presence matrix."""
    from libs.neo4j_client.client import run_with_retry

    f = filters or DQFilters()
    rows = run_with_retry(
        client, _COMPLETENESS_Q, site=f.site, limit=f.limit
    )
    return [
        MilestoneRow(
            patient_id=r.get("patient_id") or "",
            episode_id=r.get("episode_id") or "",
            site=r.get("site") or "unknown",
            status=r.get("status") or "unknown",
            has_referral=bool(r.get("has_referral")),
            has_specialist=bool(r.get("specialist_seen")),
            has_diagnosis=False,  # enriched by caller if needed
            has_treatment=False,
            has_letter=False,
            has_benign_closure=False,
        )
        for r in rows
    ]


def infer_outcome(
    patient_id: str,
    episode_id: str,
    site: str,
    referral_date: str,
    specialist_date: Optional[str],
    client: Any,
    window_days: int = 180,
) -> OutcomeInferenceResult:
    """Infer episode outcome from post-specialist encounter text signals."""
    from libs.neo4j_client.client import run_with_retry

    from_date = referral_date
    ref_d = _parse_date(referral_date)
    window_end = str(ref_d + timedelta(days=window_days)) if ref_d else None

    rows = run_with_retry(
        client,
        _STALE_ENCOUNTERS_Q,
        patient_id=patient_id,
        from_date=from_date,
        to_date=window_end or "",
    )

    phase2_rows = _phase2(rows, specialist_date)
    phase1_rows = [r for r in rows if r not in phase2_rows]

    private_blocked = any(
        has_any((r.get("text") or "") + (r.get("flags") or ""), PRIVATE_MARKERS)
        for r in phase1_rows
    )
    specialist_confirmed = any(
        has_any((r.get("text") or "") + (r.get("flags") or ""), SPECIALIST_SEEN)
        for r in phase1_rows
    )

    cancer_hits: list = []
    benign_hits: list = []
    for r in phase2_rows:
        combined = (r.get("text") or "") + " " + (r.get("flags") or "")
        cancer_hits += match_signals(combined, POST_CANCER, date=r.get("date", ""))
        benign_hits += match_signals(combined, POST_BENIGN, date=r.get("date", ""))

    verdict, flag = _verdict(cancer_hits, benign_hits, private_blocked)
    return OutcomeInferenceResult(
        patient_id=patient_id,
        episode_id=episode_id,
        site=site,
        referral_date=referral_date,
        specialist_date=specialist_date,
        window_end=window_end,
        verdict=verdict,
        flag=flag,
        cancer_signals=cancer_hits,
        benign_signals=benign_hits,
        private_blocked=private_blocked,
        specialist_confirmed=specialist_confirmed,
        phase2_encounter_count=len(phase2_rows),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phase2(rows: list[dict], specialist_date: Optional[str]) -> list[dict]:
    if not specialist_date:
        return []
    return [r for r in rows if (r.get("date") or "") > specialist_date]


def _verdict(
    cancer_hits: list, benign_hits: list, private_blocked: bool
) -> tuple[str, str]:
    nc, nb = len(cancer_hits), len(benign_hits)
    if nc == 0 and nb == 0:
        if private_blocked:
            return "UNRESOLVABLE", "HITL_REQUIRED"
        return "UNRESOLVABLE", "HITL_REQUIRED"
    if nb > 0 and nc == 0:
        return "INFERRED_BENIGN", "INFERRED_BENIGN"
    if nc > 0 and nb == 0:
        return "INFERRED_CANCER", "INFERRED_CANCER"
    if nc > nb:
        return f"INFERRED_CANCER (weighted: {nc} vs {nb})", "INFERRED_CANCER_WEAK"
    if nb > nc:
        return f"INFERRED_BENIGN (weighted: {nb} vs {nc})", "INFERRED_BENIGN_WEAK"
    return "AMBIGUOUS", "HITL_REQUIRED"


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _days_since(date_str: Optional[str], today: date) -> int:
    d = _parse_date(date_str)
    return (today - d).days if d else 0
