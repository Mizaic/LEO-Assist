from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from services.analysis_worker.app.analyzers.anchor_detector import AnchorResult

# -- Episode time windows --------------------------------------------------
# Referrals for the same site within this many days are the same in-progress episode.
_SAME_EPISODE_DAYS = 180
# Maximum gap from referral to confirmed diagnosis on a 2WW pathway.
# Referral-to-treatment is 62 days (NHS target); referral-to-diagnosis can be
# up to ~180 days in complex investigations.  Use the same window as the
# referral-grouping threshold so that every referral has a fair chance of
# being claimed by its diagnosis.
_DIAG_LOOKBACK_DAYS = 180

# Auto-close thresholds (days)
_STALE_HARD_DAYS = 365          # >12 months with no diagnosis: stale
_STALE_POST_SPECIALIST_DAYS = 90  # >90 days after specialist seen, no diagnosis
_PHANTOM_COMPLETED_WINDOW = 180   # days either side of referral to look for a sibling completed episode


@dataclass
class EpisodeBuildResult:
    patient_id: str
    episodes_created: int = 0
    episodes_completed: int = 0
    episodes_merged: int = 0
    encounters_linked: int = 0
    episode_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# -- Canonical cancer-site keyword map (longest match first) ---------------
_SITE_MAP: list[tuple[str, str]] = [
    # Multi-word phrases first (longest match wins)
    ("head and neck",           "head_and_neck"),
    ("lower gastrointestinal",  "lower_gi"),
    ("lower gi",                "lower_gi"),
    ("upper gastrointestinal",  "upper_gi"),
    ("upper gi",                "upper_gi"),
    ("gynaecological",          "gynaecological"),
    ("gynecological",           "gynaecological"),
    ("haematological",          "haematological"),
    ("haematology",             "haematological"),
    ("hematological",           "haematological"),
    ("non-site-specific",       "non_site_specific"),
    ("non site specific",       "non_site_specific"),
    ("childrens tumour",        "childrens_tumour"),
    ("children's tumour",       "childrens_tumour"),
    # Lower GI
    ("colorectal",              "lower_gi"),
    ("bowel",                   "lower_gi"),
    ("rectal",                  "lower_gi"),
    ("intestin",                "lower_gi"),   # intestine / intestinal
    ("colonic",                 "lower_gi"),
    ("colon",                   "lower_gi"),
    ("sigmoid",                 "lower_gi"),
    ("cecum",                   "lower_gi"),
    ("caecum",                  "lower_gi"),
    ("appendix",                "lower_gi"),
    ("anal ",                   "lower_gi"),   # trailing space avoids "analysis"
    ("anus",                    "lower_gi"),
    # Upper GI
    ("pancreatic",              "upper_gi"),
    ("pancrea",                 "upper_gi"),
    ("oesophag",                "upper_gi"),
    ("esophag",                 "upper_gi"),
    ("gastric",                 "upper_gi"),
    ("stomach",                 "upper_gi"),
    ("hepat",                   "upper_gi"),   # hepatic / hepatocellular
    ("liver",                   "upper_gi"),
    ("biliary",                 "upper_gi"),
    ("duodenum",                "upper_gi"),
    ("duodenal",                "upper_gi"),
    # Urological
    ("urological",              "urological"),
    ("prostate",                "urological"),
    ("bladder",                 "urological"),
    ("renal",                   "urological"),
    ("kidney",                  "urological"),
    ("testis",                  "urological"),
    ("testic",                  "urological"),
    ("ureter",                  "urological"),
    ("urethr",                  "urological"),
    ("penis",                   "urological"),
    ("scrotal",                 "urological"),
    ("scrotum",                 "urological"),
    # Gynaecological
    ("cervix",                  "gynaecological"),
    ("uteri",                   "gynaecological"),
    ("uterus",                  "gynaecological"),
    ("endometr",                "gynaecological"),
    ("ovary",                   "gynaecological"),
    ("ovarian",                 "gynaecological"),
    ("vagina",                  "gynaecological"),
    ("vulva",                   "gynaecological"),
    ("fallopian",               "gynaecological"),
    ("trophoblast",             "gynaecological"),
    # Haematological
    ("lymphoma",                "haematological"),
    ("leukaemia",               "haematological"),
    ("leukemia",                "haematological"),
    ("lymphoid",                "haematological"),
    ("haemopoietic",            "haematological"),
    ("hemopoietic",             "haematological"),
    ("myeloma",                 "haematological"),
    ("myeloid",                 "haematological"),
    ("lymphocytic",             "haematological"),
    # Anatomical single-word
    ("breast",                  "breast"),
    ("lung",                    "lung"),
    ("skin",                    "skin"),
    ("melanoma",                "skin"),
    ("sarcoma",                 "sarcoma"),
    ("brain",                   "brain"),
    ("fast",                    "non_site_specific"),
]


def _extract_condition_key(concept_name: str) -> str:
    """Map a SNOMED concept name to a canonical cancer-site key."""
    name = concept_name.lower()
    for keyword, key in _SITE_MAP:
        if keyword in name:
            return key
    return "unknown"


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if hasattr(val, "year"):
        try:
            return date(val.year, val.month, val.day)
        except Exception:
            return None
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _episode_id(patient_id: str, condition_key: str, earliest: str) -> str:
    raw = f"{patient_id}|{condition_key}|{earliest}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _group_referrals_by_time(
    anchors: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split same-site referral anchors (sorted by date) into time-window groups."""
    if not anchors:
        return []
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [anchors[0]]
    prev_date = _parse_date(anchors[0].get("encounter_date"))

    for anchor in anchors[1:]:
        this_date = _parse_date(anchor.get("encounter_date"))
        if this_date and prev_date:
            gap = (this_date - prev_date).days
            if gap > _SAME_EPISODE_DAYS:
                groups.append(current)
                current = []
        current.append(anchor)
        if this_date:
            prev_date = this_date

    groups.append(current)
    return groups


def _group_specialists(
    specialist_anchors: list[dict[str, Any]],
    referral_keys: list[str],
) -> tuple[dict[str, bool], dict[str, str]]:
    """Return (specialist_seen_by_key, referral_site_by_key)."""
    seen: dict[str, bool] = {}
    site: dict[str, str] = {}
    for anchor in specialist_anchors:
        key = _extract_condition_key(str(anchor.get("concept_name") or ""))
        if key == "unknown" or key not in set(referral_keys):
            key = referral_keys[0] if referral_keys else "unknown"
        seen[key] = True
        if key not in site:
            site[key] = str(anchor.get("concept_name") or "")
    return seen, site


def _find_best_referral(
    diag_date: date,
    diag_key: str,
    sorted_ref: list[dict[str, Any]],
    claimed: set[int],
) -> tuple[int, date] | None:
    """Return (index, ref_date) of the closest unclaimed same-site referral within
    _DIAG_LOOKBACK_DAYS, or None if none exists.  NSS referrals are accepted for
    any diagnosis site.
    """
    best_idx: int | None = None
    best_gap = timedelta(days=_DIAG_LOOKBACK_DAYS + 1)
    best_date: date | None = None
    for idx, ref in enumerate(sorted_ref):
        if idx in claimed:
            continue
        r_date = _parse_date(ref.get("encounter_date"))
        if not r_date:
            continue
        gap = diag_date - r_date
        if gap < timedelta(0) or gap > timedelta(days=_DIAG_LOOKBACK_DAYS):
            continue
        ref_key = _extract_condition_key(str(ref.get("concept_name") or ""))
        # "unknown" diag_key = generic concept (e.g. adenocarcinoma) -> match any referral.
        # NSS referrals also match any specific cancer site.
        if diag_key not in ("unknown",) and ref_key != diag_key and ref_key != "non_site_specific":
            continue
        if gap < best_gap:
            best_gap = gap
            best_idx = idx
            best_date = r_date
    if best_idx is None or best_date is None:
        return None
    return best_idx, best_date


def _claim_window_referrals(
    sorted_ref: list[dict[str, Any]],
    claimed: set[int],
    diag_key: str,
    diag_date: date,
    primary_idx: int,
) -> list[dict[str, Any]]:
    """Collect the primary referral plus any other unclaimed same-site referrals
    that fall within the lookback window of this diagnosis.
    Returns the list sorted by encounter date (earliest first).
    """
    claimed.add(primary_idx)
    result = [sorted_ref[primary_idx]]
    for idx, ref in enumerate(sorted_ref):
        if idx == primary_idx or idx in claimed:
            continue
        r_date = _parse_date(ref.get("encounter_date"))
        if not r_date:
            continue
        ref_key = _extract_condition_key(str(ref.get("concept_name") or ""))
        site_match = (
            diag_key == "unknown"
            or ref_key == diag_key
            or ref_key == "non_site_specific"
        )
        if not site_match:
            continue
        gap = diag_date - r_date
        if timedelta(0) <= gap <= timedelta(days=_DIAG_LOOKBACK_DAYS):
            result.append(ref)
            claimed.add(idx)
    result.sort(key=lambda a: str(a.get("encounter_date") or ""))
    return result


def _group_open_referrals(
    unclaimed: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group referrals that were not claimed by any diagnosis into in-progress
    episodes, split by site key and then by the _SAME_EPISODE_DAYS time window.
    """
    by_site: dict[str, list[dict[str, Any]]] = {}
    for ref in unclaimed:
        key = _extract_condition_key(str(ref.get("concept_name") or ""))
        by_site.setdefault(key, []).append(ref)
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for site_key, refs in by_site.items():
        refs.sort(key=lambda a: str(a.get("encounter_date") or ""))
        for group in _group_referrals_by_time(refs):
            groups.append((site_key, group))
    return groups


def _build_diagnosis_led_groups(
    referral_anchors: list[dict[str, Any]],
    diagnosis_anchors: list[dict[str, Any]],
) -> tuple[
    list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]],
    list[tuple[str, list[dict[str, Any]]]],
]:
    """Diagnosis-first grouping: each diagnosis claims its nearest preceding referral.

    Returns:
        closed_groups: list of (site_key, ref_anchors, diag_anchors).
            ref_anchors may be empty if the diagnosis has no preceding referral
            within _DIAG_LOOKBACK_DAYS (established/incidental cancer).
        open_groups: list of (site_key, ref_anchors) for referrals not claimed
            by any diagnosis -- these become in_progress episodes.
    """
    sorted_diag = sorted(
        diagnosis_anchors, key=lambda a: str(a.get("encounter_date") or "")
    )
    sorted_ref = sorted(
        referral_anchors, key=lambda a: str(a.get("encounter_date") or "")
    )
    claimed: set[int] = set()
    # Episodes anchored to a referral (referral found within lookback window)
    ref_keyed: dict[str, tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = {}
    # Diagnoses with no referral in window -- grouped by site for deduplication
    floating: dict[str, list[dict[str, Any]]] = {}

    for diag in sorted_diag:
        d_date = _parse_date(diag.get("encounter_date"))
        if not d_date:
            continue
        diag_key = _extract_condition_key(str(diag.get("concept_name") or ""))
        match = _find_best_referral(d_date, diag_key, sorted_ref, claimed)
        if match:
            primary_idx, _ = match
            refs = _claim_window_referrals(sorted_ref, claimed, diag_key, d_date, primary_idx)
            # Merge diagnoses that share the same primary referral into one episode
            ref_anchor_date = str(refs[0].get("encounter_date") or "")
            group_key = f"{diag_key}|{ref_anchor_date}"
            if group_key in ref_keyed:
                sk, existing_refs, existing_diags = ref_keyed[group_key]
                ref_keyed[group_key] = (sk, existing_refs, existing_diags + [diag])
            else:
                ref_keyed[group_key] = (diag_key, refs, [diag])
        else:
            # No referral found -- bucket by site for later deduplication
            floating.setdefault(diag_key, []).append(diag)

    # Reduce floating diagnoses: earliest per site within _SAME_EPISODE_DAYS becomes one episode
    floating_groups: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for site_key, diags in floating.items():
        diags.sort(key=lambda a: str(a.get("encounter_date") or ""))
        for time_group in _group_referrals_by_time(diags):
            floating_groups.append((site_key, [], time_group))

    closed_groups = list(ref_keyed.values()) + floating_groups
    unclaimed = [ref for idx, ref in enumerate(sorted_ref) if idx not in claimed]
    open_groups = _group_open_referrals(unclaimed)
    return closed_groups, open_groups


def _detect_phantom_sites(
    referrals_by_site: dict[str, list[dict[str, Any]]],
) -> set[str]:
    """Return site keys whose referrals come ONLY from multi-referral encounters.

    A phantom episode arises when a single encounter is coded with multiple
    cancer referral types (e.g. a 2WW status template that carries over an old
    referral code alongside the current one). The phantom site is the one with
    fewer referrals that shares ALL its encounter IDs with another site.
    """
    encounter_to_sites: dict[str, set[str]] = {}
    for site_key, anchors in referrals_by_site.items():
        for anchor in anchors:
            eid = str(anchor.get("encounter_id") or "")
            if eid:
                encounter_to_sites.setdefault(eid, set()).add(site_key)

    multi_ref_encounters = {
        eid for eid, sites in encounter_to_sites.items() if len(sites) > 1
    }
    if not multi_ref_encounters:
        return set()

    phantom_sites: set[str] = set()
    site_referral_counts = {sk: len(anchors) for sk, anchors in referrals_by_site.items()}

    for site_key, anchors in referrals_by_site.items():
        eids = {str(a.get("encounter_id") or "") for a in anchors if a.get("encounter_id")}
        if not eids or not eids.issubset(multi_ref_encounters):
            continue
        # All encounters for this site are shared -- check if there's a dominant site
        for eid in eids:
            sibling_sites = encounter_to_sites.get(eid, set()) - {site_key}
            dominant = any(
                site_referral_counts.get(s, 0) > site_referral_counts.get(site_key, 0)
                for s in sibling_sites
            )
            if dominant:
                phantom_sites.add(site_key)
                break

    return phantom_sites


# -- Cypher -----------------------------------------------------------------

_NO_CANCER_CONCEPT_ID = 395100000
_MAX_BENIGN_CLOSURE_DAYS = 365

_BENIGN_CLOSURE_QUERY = (
    "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[r:DOCUMENTS]->(c) "
    "WHERE toString(p.id) = $patient_id "
    "  AND c.conceptId = $concept_id "
    "  AND coalesce(r.assertion, 'present') = 'present' "
    "  AND toString(e.date) >= $after_date "
    "  AND toString(e.date) <= $before_date "
    "RETURN "
    "    toString(e.id)   AS encounter_id, "
    "    toString(e.date) AS encounter_date, "
    "    c.conceptId      AS concept_id, "
    "    c.name           AS concept_name "
    "ORDER BY encounter_date"
)

_MERGE_EPISODE = (
    "MERGE (ep:EpisodeOfCare {episode_id: $episode_id}) "
    "SET ep.patient_id        = $patient_id, "
    "    ep.domain_id         = $domain_id, "
    "    ep.condition_type    = $condition_type, "
    "    ep.cancer_type       = $cancer_type, "
    "    ep.referral_date     = $referral_date, "
    "    ep.end_date          = $end_date, "
    "    ep.specialist_seen   = $specialist_seen, "
    "    ep.referral_site     = $referral_site, "
    "    ep.status            = $status, "
    "    ep.auto_closed       = $auto_closed, "
    "    ep.auto_close_reason = $auto_close_reason, "
    "    ep.hitl_flag         = $hitl_flag, "
    "    ep.hitl_reason       = $hitl_reason, "
    "    ep.updated_at        = datetime() "
    "RETURN ep"
)

# Stale and cross-domain auto-close applied as a second pass.
_STALE_CLOSE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $patient_id
  AND ep.episode_id IN $episode_ids
  AND ep.status = 'in_progress'
  AND ep.auto_closed <> true
WITH ep,
     date(ep.referral_date) AS ref_date,
     date() AS today
SET ep.status = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(ref_date, today).days > $post_spec_days
        THEN 'stale_post_specialist'
      WHEN duration.inDays(ref_date, today).days > $hard_days
        THEN 'stale_no_diagnosis'
      ELSE ep.status
    END,
    ep.auto_closed = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(ref_date, today).days > $post_spec_days THEN true
      WHEN duration.inDays(ref_date, today).days > $hard_days THEN true
      ELSE false
    END,
    ep.auto_close_reason = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(ref_date, today).days > $post_spec_days
        THEN 'auto_stale_90d_post_specialist'
      WHEN duration.inDays(ref_date, today).days > $hard_days
        THEN 'auto_stale_12m_no_diagnosis'
      ELSE null
    END,
    ep.hitl_flag = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(ref_date, today).days > $post_spec_days THEN true
      WHEN duration.inDays(ref_date, today).days > $hard_days THEN true
      ELSE ep.hitl_flag
    END,
    ep.hitl_reason = CASE
      WHEN ep.specialist_seen = true
           AND duration.inDays(ref_date, today).days > $post_spec_days
        THEN 'Auto-closed: specialist seen >90 days ago, no diagnosis coded. Verify pathway outcome.'
      WHEN duration.inDays(ref_date, today).days > $hard_days
        THEN 'Auto-closed: >12 months since referral, no diagnosis coded. Verify pathway outcome.'
      ELSE ep.hitl_reason
    END
"""

# Close NSS in_progress episodes when a sibling completed episode exists nearby.
_RELATED_CLOSE_Q = """
MATCH (ep:EpisodeOfCare)
WHERE ep.patient_id = $patient_id
  AND ep.episode_id IN $episode_ids
  AND ep.status = 'in_progress'
  AND ep.cancer_type = 'non_site_specific'
  AND ep.auto_closed <> true
WITH ep
MATCH (other:EpisodeOfCare)
WHERE other.patient_id = $patient_id
  AND other.status = 'completed'
  AND other.episode_id <> ep.episode_id
  AND abs(duration.inDays(date(other.referral_date), date(ep.referral_date)).days) <= $window_days
SET ep.status          = 'closed_related',
    ep.auto_closed     = true,
    ep.auto_close_reason = 'auto_related_cancer_found_other_pathway',
    ep.hitl_flag       = true,
    ep.hitl_reason     = 'Auto-closed: cancer confirmed via ' + other.cancer_type +
                         ' pathway. Verify these are the same investigation.'
"""


def _benign_closure_for_episode(
    patient_id: str,
    ref_date: date,
    patient_client,
    anchors: AnchorResult,
) -> date | None:
    """Return earliest benign-closure date within episode window, or None."""
    after_date = ref_date.isoformat()
    before_date = (ref_date + timedelta(days=_MAX_BENIGN_CLOSURE_DAYS)).isoformat()

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
            _BENIGN_CLOSURE_QUERY,
            patient_id=patient_id,
            concept_id=_NO_CANCER_CONCEPT_ID,
            after_date=after_date,
            before_date=before_date,
        )
        dates = [_parse_date(r.get("encounter_date")) for r in (rows or [])]
        clean = [d for d in dates if d]
        return min(clean) if clean else None
    except Exception:
        return None


def _has_confirmed_diagnosis(diag_anchors: list[dict[str, Any]]) -> bool:
    """True if at least one diagnosis anchor has assertion = 'present'."""
    return any(
        str(a.get("assertion", "present")) in ("present", "")
        for a in diag_anchors
    )


def _has_possible_only_diagnosis(diag_anchors: list[dict[str, Any]]) -> bool:
    """True if ALL diagnosis anchors are [possible] -- none are confirmed present."""
    if not diag_anchors:
        return False
    return all(str(a.get("assertion", "present")) == "possible" for a in diag_anchors)


def _treatment_after_referral(
    treatment_anchors: list[dict[str, Any]], ref_date: date | None
) -> bool:
    """True if any treatment anchor occurs on or after the referral date."""
    if not ref_date or not treatment_anchors:
        return False
    return any(
        (d := _parse_date(a.get("encounter_date"))) and d >= ref_date
        for a in treatment_anchors
    )


def _determine_episode_status(
    has_diagnosis: bool,
    diag_anchors: list[dict[str, Any]],
    benign_date: date | None,
    treatment_anchors: list[dict[str, Any]],
    ref_date: date | None,
    is_phantom: bool,
) -> tuple[str, bool, str | None]:
    """Return (status, hitl_flag, hitl_reason)."""
    if is_phantom:
        return (
            "closed_phantom",
            True,
            "Auto-closed: referral encounter also codes another cancer pathway. "
            "Likely a phantom episode from a multi-referral template. Review manually.",
        )

    if has_diagnosis:
        # Possible-only diagnosis + confirmed treatment = close with HITL
        if _has_possible_only_diagnosis(diag_anchors) and _treatment_after_referral(
            treatment_anchors, ref_date
        ):
            return (
                "completed",
                True,
                "Completed: [possible] cancer diagnosis with subsequent treatment. "
                "Confirm diagnosis from clinic letter.",
            )
        return ("completed", False, None)

    if benign_date:
        return ("closed_benign", False, None)

    return ("in_progress", False, None)


def _write_episode(
    patient_client,
    patient_id: str,
    ep_id: str,
    domain_id: str,
    site_key: str,
    referral_date: str,
    end_date: str | None,
    specialist_seen: dict[str, bool],
    referral_site: dict[str, str],
    status: str,
    hitl_flag: bool,
    hitl_reason: str | None,
    result: EpisodeBuildResult,
    episode_ids: list[str],
) -> None:
    """Persist one episode node; updates result counters on success."""
    auto_closed = status in (
        "closed_phantom", "closed_related", "stale_no_diagnosis", "stale_post_specialist"
    )
    auto_close_reason = (
        "phantom_multi_referral_encounter" if status == "closed_phantom" else None
    )
    try:
        patient_client.run(
            _MERGE_EPISODE,
            patient_id=patient_id,
            episode_id=ep_id,
            domain_id=domain_id,
            condition_type=site_key,
            cancer_type=site_key,
            referral_date=referral_date,
            end_date=end_date,
            specialist_seen=specialist_seen.get(site_key, False),
            referral_site=referral_site.get(site_key, ""),
            status=status,
            auto_closed=auto_closed,
            auto_close_reason=auto_close_reason,
            hitl_flag=hitl_flag,
            hitl_reason=hitl_reason,
        )
        episode_ids.append(ep_id)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(str(exc))


def _apply_auto_close_rules(
    patient_id: str,
    episode_ids: list[str],
    patient_client,
) -> None:
    """Second-pass Cypher updates: stale and cross-domain closure with HITL flags."""
    if not episode_ids:
        return
    try:
        # Related-close FIRST: NSS episodes with a completed sibling must be
        # resolved before stale-close fires -- otherwise the NSS episode
        # becomes stale_no_diagnosis and is no longer in_progress to match.
        patient_client.run(
            _RELATED_CLOSE_Q,
            patient_id=patient_id,
            episode_ids=episode_ids,
            window_days=_PHANTOM_COMPLETED_WINDOW,
        )
        patient_client.run(
            _STALE_CLOSE_Q,
            patient_id=patient_id,
            episode_ids=episode_ids,
            post_spec_days=_STALE_POST_SPECIALIST_DAYS,
            hard_days=_STALE_HARD_DAYS,
        )
    except Exception:
        pass


def _build_closed_episode(
    patient_id: str,
    site_key: str,
    ref_anchors: list[dict[str, Any]],
    diag_anchors: list[dict[str, Any]],
    phantom_sites: set[str],
    specialist_seen: dict[str, bool],
    referral_site: dict[str, str],
    anchors: "AnchorResult",
    patient_client,
    domain_id: str,
    result: EpisodeBuildResult,
    episode_ids: list[str],
) -> None:
    """Write one diagnosis-led (completed) episode and update result counters."""
    all_anchors = ref_anchors + diag_anchors
    all_dates_str = [str(a.get("encounter_date") or "") for a in all_anchors if a.get("encounter_date")]
    earliest_str = min(all_dates_str) if all_dates_str else ""
    referral_date = str(ref_anchors[0].get("encounter_date") or earliest_str) if ref_anchors else earliest_str
    ep_id = _episode_id(patient_id, site_key, earliest_str)
    result.episode_ids.append(ep_id)
    result.episodes_created += 1
    result.encounters_linked += len(
        {str(a.get("encounter_id") or "") for a in all_anchors if a.get("encounter_id")}
    )
    has_diag = _has_confirmed_diagnosis(diag_anchors) or bool(
        diag_anchors and not _has_possible_only_diagnosis(diag_anchors)
    )
    ref_date = _parse_date(referral_date)
    is_phantom = site_key in phantom_sites
    status, hitl_flag, hitl_reason = _determine_episode_status(
        has_diag, diag_anchors, None, anchors.treatment_anchors, ref_date, is_phantom
    )
    end_date = max(all_dates_str) if all_dates_str else None
    _write_episode(
        patient_client, patient_id, ep_id, domain_id, site_key,
        referral_date, end_date, specialist_seen, referral_site,
        status, hitl_flag, hitl_reason, result, episode_ids,
    )


def _build_open_episode(
    patient_id: str,
    site_key: str,
    group: list[dict[str, Any]],
    phantom_sites: set[str],
    specialist_seen: dict[str, bool],
    referral_site: dict[str, str],
    anchors: "AnchorResult",
    patient_client,
    domain_id: str,
    result: EpisodeBuildResult,
    episode_ids: list[str],
) -> None:
    """Write one referral-only (in_progress) episode and update result counters."""
    earliest_str = str(group[0].get("encounter_date") or "")
    ep_id = _episode_id(patient_id, site_key, earliest_str)
    result.episode_ids.append(ep_id)
    result.episodes_created += 1
    result.encounters_linked += len(
        {str(r.get("encounter_id") or "") for r in group if r.get("encounter_id")}
    )
    ref_date = _parse_date(group[0].get("encounter_date"))
    is_phantom = site_key in phantom_sites
    benign_date: date | None = None
    if not is_phantom and ref_date:
        benign_date = _benign_closure_for_episode(patient_id, ref_date, patient_client, anchors)
    status, hitl_flag, hitl_reason = _determine_episode_status(
        False, [], benign_date, anchors.treatment_anchors, ref_date, is_phantom
    )
    if benign_date:
        end_date: str | None = benign_date.isoformat()
    elif status == "closed_phantom":
        end_date = earliest_str
    else:
        end_date = None
    _write_episode(
        patient_client, patient_id, ep_id, domain_id, site_key,
        earliest_str, end_date, specialist_seen, referral_site,
        status, hitl_flag, hitl_reason, result, episode_ids,
    )


async def build_episodes(
    patient_id: str,
    anchors: AnchorResult,
    patient_client,
    domain_id: str = "",
) -> EpisodeBuildResult:
    """Build EpisodeOfCare nodes using a diagnosis-led algorithm.

    Each confirmed diagnosis claims the nearest same-site referral within
    _DIAG_LOOKBACK_DAYS.  Unclaimed referrals become in_progress episodes.
    """
    result = EpisodeBuildResult(patient_id=patient_id)
    if not anchors.referral_anchors and not anchors.diagnosis_anchors:
        return result

    # Phantom detection requires the full referral set grouped by site
    referrals_by_site: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchors.referral_anchors:
        key = _extract_condition_key(str(anchor.get("concept_name") or ""))
        referrals_by_site.setdefault(key, []).append(anchor)
    phantom_sites = _detect_phantom_sites(referrals_by_site)

    # Diagnosis-first grouping
    closed_groups, open_groups = _build_diagnosis_led_groups(
        anchors.referral_anchors, anchors.diagnosis_anchors
    )

    # Specialist visits against the union of all episode site keys
    all_site_keys = [g[0] for g in closed_groups] + [g[0] for g in open_groups]
    specialist_seen, referral_site = _group_specialists(
        anchors.specialist_visit_anchors, all_site_keys
    )

    episode_ids: list[str] = []
    shared = (phantom_sites, specialist_seen, referral_site, anchors, patient_client, domain_id, result, episode_ids)

    for site_key, ref_anchors, diag_anchors in closed_groups:
        _build_closed_episode(patient_id, site_key, ref_anchors, diag_anchors, *shared)

    for site_key, group in open_groups:
        _build_open_episode(patient_id, site_key, group, *shared)

    _apply_auto_close_rules(patient_id, episode_ids, patient_client)
    return result
