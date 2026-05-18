#!/usr/bin/env python3
"""Dry-run the NCDA detector against reviewed patients and compare to gold.

Reads reviewed episodes from Neo4j, fetches ALL encounters for those patients,
runs the role scorer + pair generator + linkage scorer, then prints a
side-by-side comparison of detector output vs reviewed milestones.

Modes
-----
Without --role-model/--linkage-model: deterministic labeller + gap-based scorer.
With both flags: trained role classifier + trained linkage classifier.

No writes are made to the graph.

Usage:
    python scripts/ncda/dry_run_reviewed.py
    python scripts/ncda/dry_run_reviewed.py --patient 6309359401
    python scripts/ncda/dry_run_reviewed.py --role-model artifacts/ncda_models/role.joblib \\
        --linkage-model artifacts/ncda_models/linkage.joblib
    python scripts/ncda/dry_run_reviewed.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "secrets" / ".env.config", override=False)
load_dotenv(ROOT / "secrets" / ".env.secrets", override=False)
load_dotenv(ROOT / "secrets" / ".env", override=False)

from neo4j import GraphDatabase  # noqa: E402

from services.analysis_worker.app.ncda_detector.assignment import assign  # noqa: E402
from services.analysis_worker.app.ncda_detector.linkage import (  # noqa: E402
    LinkageClassifier,
    LinkageScore,
)
from services.analysis_worker.app.ncda_detector.linkage_features import (  # noqa: E402
    PairContext,
    extract_pair_features,
)
from services.analysis_worker.app.ncda_detector.pair_generator import (  # noqa: E402
    AuxiliaryAnchors,
    CandidatePair,
    PairThresholds,
    PairWindow,
    RoleScore,
    generate_pairs,
)
from services.analysis_worker.app.ncda_detector.ftr_clustering import (  # noqa: E402
    cluster_ftrs,
)
from services.analysis_worker.app.ncda_detector.role_classifier import (  # noqa: E402
    RoleClassifier,
)
from services.analysis_worker.app.ncda_detector.silver_labeller import (  # noqa: E402
    deterministic_label,
)
from services.analysis_worker.app.ncda_detector.simple_linker import (  # noqa: E402
    EncounterRow as SimpleEncounterRow,
    link_patient as simple_link_patient,
)
from services.analysis_worker.app.ncda_detector.route_classifier import (  # noqa: E402
    classify_diagnosis_route,
)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_GOLD_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)-[r:IS_PART_OF]->(e:EpisodeOfCare)
WHERE e.reviewed_at IS NOT NULL
  AND r.milestone_type IN [
      'referral','referral_sent','first_seen','diagnosis_confirmed',
      'treatment_started','benign_closure','outcome_letter'
  ]
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    elementId(e) AS episode_id,
    coalesce(e.cancer_type, 'unknown') AS cancer_type,
    enc.id AS encounter_id,
    r.milestone_type AS milestone_type,
    r.outcome AS outcome,
    toString(enc.date) AS encounter_date
ORDER BY patient_id, episode_id, encounter_date
"""

_ALL_ENCOUNTERS_QUERY = """
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(enc:Encounter)
WHERE coalesce(toString(p.id), toString(p.patient_id)) IN $patient_ids
RETURN
    coalesce(toString(p.id), toString(p.patient_id)) AS patient_id,
    enc.id AS encounter_id,
    toString(enc.date) AS encounter_date,
    enc.text AS text,
    enc.flags AS flags
ORDER BY patient_id, encounter_date
"""


# ---------------------------------------------------------------------------
# Gold milestone helpers
# ---------------------------------------------------------------------------

_COHORT_MAP = {
    "referral": "ftr",
    "referral_sent": "ftr",
    "first_seen": "seen",
    "diagnosis_confirmed": "dx",
    "benign_closure": "dx",
    "outcome_letter": "dx",
    "treatment_started": "treatment",
}

_DX_MILESTONES = {"diagnosis_confirmed", "benign_closure", "outcome_letter"}
_FTR_MILESTONES = {"referral", "referral_sent"}
_BENIGN_MILESTONES = {"benign_closure"}


def _infer_gold_cohort(milestones: list[dict]) -> str:
    types = {m["milestone_type"] for m in milestones}
    has_ftr = bool(types & _FTR_MILESTONES)
    has_dx = bool(types & _DX_MILESTONES)
    is_benign = bool(types & _BENIGN_MILESTONES) or any(
        m["milestone_type"] in _DX_MILESTONES
        and m.get("outcome") == "cancer_excluded"
        for m in milestones
    )
    if has_ftr and has_dx:
        return "1b" if is_benign else "1a"
    if has_ftr:
        return "2"
    if has_dx and not is_benign:
        return "3"
    return "?"


def _milestone_date(milestones: list[dict], mtype: str) -> str | None:
    for m in milestones:
        if m["milestone_type"] == mtype:
            return m["encounter_date"]
    return None


# ---------------------------------------------------------------------------
# Deterministic role scorer -> RoleScore conversion
# ---------------------------------------------------------------------------

ROLES = ("ftr", "seen", "dx", "treatment", "none")


def _label_to_role_score(label) -> RoleScore:
    """Convert a SilverLabel into the RoleScore the pair generator expects."""
    probs: dict[str, float] = {r: 0.05 for r in ROLES}
    probs[label.role] = label.confidence
    if label.role == "ftr":
        probs["seen"] = 0.1
    return RoleScore(
        encounter_id=label.encounter_id,
        encounter_date=label.encounter_date or "",
        role_probabilities=probs,
        outcome=label.outcome,
        outcome_probability=0.7 if label.outcome else None,
        text=label.supporting_quote,
        flags=None,
    )


def _prediction_to_role_score(pred, enc_row: dict) -> RoleScore:
    """Convert a RoleClassifier prediction into the pair-generator RoleScore."""
    return RoleScore(
        encounter_id=pred.encounter_id,
        encounter_date=enc_row.get("encounter_date") or "",
        role_probabilities=pred.role_probabilities,
        outcome=pred.outcome,
        outcome_probability=pred.outcome_probability,
        text=enc_row.get("text"),
        flags=enc_row.get("flags"),
    )


# ---------------------------------------------------------------------------
# Rule-based (stub) linkage scorer — used when no trained model is present
# ---------------------------------------------------------------------------

def _gap_linkage(gap_days: int | None) -> LinkageScore:
    """Simple gap-based linkage probability for dry-run use only."""
    if gap_days is None:
        return LinkageScore(probability=0.4, tier="suggest")
    if gap_days < 0 or gap_days > 365:
        return LinkageScore(probability=0.2, tier="review")
    if gap_days <= 28:
        return LinkageScore(probability=0.88, tier="auto")
    if gap_days <= 62:
        return LinkageScore(probability=0.78, tier="suggest")
    return LinkageScore(probability=0.60, tier="suggest")


def _ml_linkage(
    pair: CandidatePair,
    all_scores: list[RoleScore],
    classifier: LinkageClassifier,
) -> LinkageScore:
    """Score a pair with the trained linkage classifier."""
    ftr_score = next((s for s in all_scores if s.encounter_id == pair.ftr_encounter_id), None)
    dx_score = next((s for s in all_scores if s.encounter_id == pair.dx_encounter_id), None)
    fd = _to_date_str(pair.ftr_date)
    dd = _to_date_str(pair.dx_date)
    intervening = [
        s for s in all_scores
        if s.encounter_id not in (pair.ftr_encounter_id, pair.dx_encounter_id)
        and fd and dd and fd < (s.encounter_date or "") <= dd
    ]
    ctx = PairContext(
        ftr_encounter=ftr_score,
        dx_encounter=dx_score,
        intervening=intervening,
        recurrent_ftr=sum(1 for s in all_scores if s.role_probabilities.get("ftr", 0) >= 0.5) > 1,
    )
    seen_scores = [s for s in all_scores if s.role_probabilities.get("seen", 0) >= 0.4]
    tx_scores = [s for s in all_scores if s.role_probabilities.get("treatment", 0) >= 0.4]
    feats = extract_pair_features(pair, ctx, seen_encounters=seen_scores, treatment_encounters=tx_scores)
    return classifier.score_one(feats)


def _to_date_str(v: str | None) -> str:
    return str(v)[:10] if v else ""


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _date_diff(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        da = date.fromisoformat(a[:10])
        db = date.fromisoformat(b[:10])
        return abs((da - db).days)
    except ValueError:
        return None


_MATCH_WINDOW = 7  # days within which we call it a match

_CANCER_TYPE_TO_SITE = {
    "breast": "breast",
    "melanoma": "skin",
    "skin": "skin",
    "prostate": "urological",
    "urological": "urological",
    "lymphoma": "haematological",
    "haematological": "haematological",
    "oesophageal": "upper_gi",
    "upper_gi": "upper_gi",
    "lung": "lung",
}


def _gold_site(cancer_type: str | None) -> str | None:
    if not cancer_type:
        return None
    key = str(cancer_type).strip().lower().replace(" ", "_")
    return _CANCER_TYPE_TO_SITE.get(key)


def _site_match_for_compare(gold_site: str | None, detected_site: str | None) -> bool:
    if not gold_site or not detected_site:
        return True
    if gold_site == detected_site:
        return True
    return gold_site == "haematological" or detected_site == "haematological"


def _compare_anchor(
    label: str, gold_date: str | None, detected_date: str | None
) -> dict:
    diff = _date_diff(gold_date, detected_date)
    if gold_date and detected_date:
        status = "MATCH" if (diff is not None and diff <= _MATCH_WINDOW) else f"DATE-OFF({diff}d)"
    elif gold_date and not detected_date:
        status = "MISSED"
    elif not gold_date and detected_date:
        status = "EXTRA"
    else:
        status = "N/A"
    return {
        "anchor": label,
        "gold": gold_date,
        "detected": detected_date,
        "diff_days": diff,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

_STATUS_ICONS = {"MATCH": "OK", "MISSED": "!!", "EXTRA": "+?", "N/A": "--"}


def _fmt(result: dict, json_mode: bool) -> str:
    if json_mode:
        return json.dumps(result, indent=2)
    lines: list[str] = []
    for pid, episodes in result.items():
        lines.append(f"\n{'='*72}")
        lines.append(f"Patient {pid}")
        for ep in episodes:
            lines.append(f"\n  Episode {ep['episode_id']} [{ep['cancer_type']}]")
            lines.append(f"  Gold cohort: {ep['gold_cohort']}  Detected cohort: {ep['detected_cohort']}")
            cohort_ok = ep["gold_cohort"] == ep["detected_cohort"]
            lines.append(f"  Cohort match: {'OK' if cohort_ok else '!!'}")
            lines.append(f"  {'Anchor':<12} {'Gold date':<14} {'Detected date':<14} {'Diff':>6}  Status")
            lines.append(f"  {'-'*12} {'-'*14} {'-'*14} {'-'*6}  {'-'*10}")
            for anchor in ep["anchors"]:
                icon = _STATUS_ICONS.get(anchor["status"], "??")
                diff_str = f"{anchor['diff_days']}d" if anchor["diff_days"] is not None else "-"
                lines.append(
                    f"  {anchor['anchor']:<12} {anchor['gold'] or '-':<14} "
                    f"{anchor['detected'] or '-':<14} {diff_str:>6}  [{icon}] {anchor['status']}"
                )
            if ep.get("detected_candidates"):
                lines.append(f"\n  All detector candidates ({len(ep['detected_candidates'])}):")
                for c in ep["detected_candidates"]:
                    lines.append(
                        f"    cohort={c['cohort']} tier={c['tier']} "
                        f"linkage_p={c['linkage_probability']:.2f} "
                        f"ftr={c['ftr_date']} dx={c['dx_date']} "
                        f"seen={c['seen_date']} tx={c['treatment_date']}"
                    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _anchor_match_cost(
    *,
    gold_ftr: str | None,
    gold_seen: str | None,
    gold_dx: str | None,
    gold_tx: str | None,
    detected_ftr: str | None,
    detected_seen: str | None,
    detected_dx: str | None,
    detected_tx: str | None,
    gold_site: str | None = None,
    detected_site: str | None = None,
) -> int:
    """Return a cost for matching one detected pathway to one gold episode.

    Diagnosis date carries the highest weight because multi-pathway patients can
    have several same-day FTRs but only one pathway should own the reviewed
    outcome.  Missing gold anchors are ignored here; extras are still reported in
    the anchor table.
    """
    weighted = [
        (gold_ftr, detected_ftr, 1),
        (gold_seen, detected_seen, 1),
        (gold_dx, detected_dx, 3),
        (gold_tx, detected_tx, 2),
    ]
    cost = 0
    for gold, detected, weight in weighted:
        if not gold:
            continue
        diff = _date_diff(gold, detected)
        # Missing anchors should hurt, but should not dominate an exact Dx match
        # in multi-pathway patients where Seen-In or Treatment is absent from the
        # detector output.
        cost += (diff if diff is not None else 180) * weight
    if not _site_match_for_compare(gold_site, detected_site):
        cost += 1000
    return cost

def _connect():
    uri = os.environ.get("NEO4J_PATIENT_URI", "").strip() or os.environ.get("NEO4J_URI", "").strip()
    user = os.environ.get("NEO4J_PATIENT_USER", "").strip() or os.environ.get("NEO4J_USER", "").strip()
    pw = os.environ.get("NEO4J_PATIENT_PASSWORD", "").strip() or os.environ.get("NEO4J_PASSWORD", "").strip()
    if not all([uri, user, pw]):
        raise SystemExit("ERROR: NEO4J credentials missing.")
    return GraphDatabase.driver(uri, auth=(user, pw))


def run_dry(
    *,
    patient_filter: str | None = None,
    threshold: float = 0.3,
    role_classifier: RoleClassifier | None = None,
    linkage_classifier: LinkageClassifier | None = None,
    session,
) -> dict:
    """Pull data, run detector, compare. Returns structured result dict."""
    # --- gold milestones ---
    gold_rows = [dict(r) for r in session.run(_GOLD_QUERY)]
    if patient_filter:
        gold_rows = [r for r in gold_rows if r["patient_id"] == patient_filter]
    if not gold_rows:
        return {}

    patient_ids = list({r["patient_id"] for r in gold_rows})

    # Group gold by (patient_id, episode_id)
    gold_by_ep: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in gold_rows:
        gold_by_ep[(r["patient_id"], str(r["episode_id"]))].append(r)

    # --- all encounters for these patients ---
    enc_rows = [dict(r) for r in session.run(_ALL_ENCOUNTERS_QUERY, patient_ids=patient_ids)]

    # Group encounters by patient
    enc_by_patient: dict[str, list[dict]] = defaultdict(list)
    for r in enc_rows:
        enc_by_patient[r["patient_id"]].append(r)

    mode = "ML" if (role_classifier and linkage_classifier) else "deterministic"
    thresholds = PairThresholds(ftr=threshold, dx=threshold, seen=threshold, treatment=threshold)

    result: dict[str, list] = defaultdict(list)

    for pid in patient_ids:
        enc_list = enc_by_patient.get(pid, [])
        if not enc_list:
            continue

        # Score encounters: ML classifier if available, else deterministic
        if role_classifier:
            predictions = role_classifier.predict_many([
                {
                    "encounter_id": r["encounter_id"],
                    "text": r.get("text") or "",
                    "flags": r.get("flags"),
                    "encounter_date": r.get("encounter_date"),
                }
                for r in enc_list
            ])
            enc_by_id = {r["encounter_id"]: r for r in enc_list}
            scores = [
                _prediction_to_role_score(pred, enc_by_id[pred.encounter_id])
                for pred in predictions
            ]
        else:
            labels = [
                deterministic_label(
                    patient_id=pid,
                    encounter_id=r["encounter_id"],
                    encounter_date=r.get("encounter_date"),
                    text=r.get("text") or "",
                    flags=r.get("flags"),
                )
                for r in enc_list
            ]
            scores = [_label_to_role_score(lb) for lb in labels]

        # Collapse same-referral FTR duplicates (same day / within 3 days,
        # compatible cancer site) before passing to the pair generator.
        scores_clustered = cluster_ftrs(scores, ftr_threshold=thresholds.ftr)

        # Generate pairs
        pairs, aux = generate_pairs(
            patient_id=pid,
            scores=scores_clustered,
            thresholds=thresholds,
            window=PairWindow(min_gap_days=-90, max_gap_days=365),
        )

        # Score pairs: ML or gap-based stub
        if linkage_classifier:
            pairs_with_scores = [
                (pair, _ml_linkage(pair, scores_clustered, linkage_classifier)) for pair in pairs
            ]
        else:
            pairs_with_scores = [
                (pair, _gap_linkage(pair.gap_days)) for pair in pairs
            ]

        # Assign
        assignment = assign(pid, pairs_with_scores, aux)

        # Pick the best candidate per gold episode (cheapest match by distance)
        for (ep_pid, ep_id), milestones in gold_by_ep.items():
            if ep_pid != pid:
                continue

            gold_cohort = _infer_gold_cohort(milestones)
            gold_ftr = _milestone_date(milestones, "referral") or _milestone_date(milestones, "referral_sent")
            gold_seen = _milestone_date(milestones, "first_seen")
            gold_dx = _milestone_date(milestones, "diagnosis_confirmed") or _milestone_date(milestones, "benign_closure") or _milestone_date(milestones, "outcome_letter")
            gold_tx = _milestone_date(milestones, "treatment_started")

            candidates = assignment.candidates
            # Pick the candidate whose dx_date is closest to gold_dx (or ftr_date closest to gold_ftr)
            best = None
            if candidates:
                def _anchor_diff(c):
                    return _anchor_match_cost(
                        gold_ftr=gold_ftr,
                        gold_seen=gold_seen,
                        gold_dx=gold_dx,
                        gold_tx=gold_tx,
                        detected_ftr=c.ftr_date,
                        detected_seen=c.seen_date,
                        detected_dx=c.dx_date,
                        detected_tx=c.treatment_date,
                        gold_site=_gold_site(milestones[0]["cancer_type"]),
                    )

                best = min(candidates, key=_anchor_diff)

            detected_cohort = best.cohort if best else "?"
            detected_ftr = best.ftr_date if best else None
            detected_seen = best.seen_date if best else None
            detected_dx = best.dx_date if best else None
            detected_tx = best.treatment_date if best else None

            anchors = [
                _compare_anchor("FTR", gold_ftr, detected_ftr),
                _compare_anchor("Seen-In", gold_seen, detected_seen),
                _compare_anchor("Diagnosis", gold_dx, detected_dx),
                _compare_anchor("Treatment", gold_tx, detected_tx),
            ]

            result[pid].append({
                "episode_id": ep_id,
                "cancer_type": milestones[0]["cancer_type"],
                "gold_cohort": gold_cohort,
                "detected_cohort": detected_cohort,
                "anchors": anchors,
                "detected_candidates": [
                    {k: getattr(c, k) for k in (
                        "cohort", "tier", "linkage_probability",
                        "ftr_date", "seen_date", "dx_date", "treatment_date",
                    )}
                    for c in candidates
                ],
                "n_encounters_labelled": len(scores),
                "n_pairs_generated": len(pairs),
            })

    return dict(result)


# ---------------------------------------------------------------------------
# Simple-linker mode: site-aware same-cancer-type 180-day window
# ---------------------------------------------------------------------------

def run_simple(
    *,
    patient_filter: str | None = None,
    window_days: int = 180,
    session,
) -> dict:
    """Run the site-aware simple linker against reviewed gold milestones.

    Each encounter is scored deterministically, converted to a SimpleEncounterRow,
    then fed to ``simple_link_patient``.  The result is compared to gold using the
    same anchor comparison logic as ``run_dry``.
    """
    gold_rows = [dict(r) for r in session.run(_GOLD_QUERY)]
    if patient_filter:
        gold_rows = [r for r in gold_rows if r["patient_id"] == patient_filter]
    if not gold_rows:
        return {}

    patient_ids = list({r["patient_id"] for r in gold_rows})

    gold_by_ep: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in gold_rows:
        gold_by_ep[(r["patient_id"], str(r["episode_id"]))].append(r)

    enc_rows = [dict(r) for r in session.run(_ALL_ENCOUNTERS_QUERY, patient_ids=patient_ids)]
    enc_by_patient: dict[str, list[dict]] = defaultdict(list)
    for r in enc_rows:
        enc_by_patient[r["patient_id"]].append(r)

    result: dict[str, list] = defaultdict(list)

    for pid in patient_ids:
        enc_list = enc_by_patient.get(pid, [])
        if not enc_list:
            continue

        # Deterministic role labelling
        labels = [
            deterministic_label(
                patient_id=pid,
                encounter_id=r["encounter_id"],
                encounter_date=r.get("encounter_date"),
                text=r.get("text") or "",
                flags=r.get("flags"),
            )
            for r in enc_list
        ]

        enc_by_id = {r["encounter_id"]: r for r in enc_list}

        # Convert to SimpleEncounterRow (site is populated by annotate_sites inside link_patient)
        simple_encs: list[SimpleEncounterRow] = [
            SimpleEncounterRow(
                encounter_id=lb.encounter_id,
                encounter_date=lb.encounter_date or "",
                role=lb.role,
                outcome=lb.outcome,
                text=enc_by_id[lb.encounter_id].get("text") or "",
            )
            for lb in labels
        ]

        pathways = simple_link_patient(pid, simple_encs, link_window_days=window_days)

        labeled_for_route: list[tuple[str, str, str]] = sorted(
            [
                (
                    lb.encounter_date or "",
                    enc_by_id[lb.encounter_id].get("text") or "",
                    lb.role,
                )
                for lb in labels
            ],
            key=lambda x: x[0],
        )

        # Compare each gold episode to the detected pathways
        for (ep_pid, ep_id), milestones in gold_by_ep.items():
            if ep_pid != pid:
                continue

            gold_cohort = _infer_gold_cohort(milestones)
            gold_ftr = _milestone_date(milestones, "referral") or _milestone_date(milestones, "referral_sent")
            gold_seen = _milestone_date(milestones, "first_seen")
            gold_dx = (
                _milestone_date(milestones, "diagnosis_confirmed")
                or _milestone_date(milestones, "benign_closure")
                or _milestone_date(milestones, "outcome_letter")
            )
            gold_tx = _milestone_date(milestones, "treatment_started")

            # Pick the pathway whose anchors are closest to the gold episode
            def _pathway_diff(pw):
                detected_pathway_site = (
                    str(pw.ftr_site)
                    if pw.ftr_site
                    else str(pw.dx.site)
                    if pw.dx and pw.dx.site
                    else None
                )
                return _anchor_match_cost(
                    gold_ftr=gold_ftr,
                    gold_seen=gold_seen,
                    gold_dx=gold_dx,
                    gold_tx=gold_tx,
                    detected_ftr=(pw.ftr.encounter_date if pw.ftr else None),
                    detected_seen=(pw.seen.encounter_date if pw.seen else None),
                    detected_dx=(pw.dx.encounter_date if pw.dx else None),
                    detected_tx=(pw.treatment.encounter_date if pw.treatment else None),
                    gold_site=_gold_site(milestones[0]["cancer_type"]),
                    detected_site=detected_pathway_site,
                )

            best = min(pathways, key=_pathway_diff) if pathways and gold_cohort != "?" else None

            detected_cohort = best.cohort if best else "?"
            detected_ftr = (best.ftr.encounter_date if best and best.ftr else None)
            detected_seen = (best.seen.encounter_date if best and best.seen else None)
            detected_dx = (best.dx.encounter_date if best and best.dx else None)
            detected_tx = (best.treatment.encounter_date if best and best.treatment else None)
            detected_site = str(best.ftr_site) if best and best.ftr_site else "?"

            anchors = [
                _compare_anchor("FTR", gold_ftr, detected_ftr),
                _compare_anchor("Seen-In", gold_seen, detected_seen),
                _compare_anchor("Diagnosis", gold_dx, detected_dx),
                _compare_anchor("Treatment", gold_tx, detected_tx),
            ]

            if best:
                rc = classify_diagnosis_route(
                    best,
                    labeled_encounters=labeled_for_route,
                )
                diagnosis_route = rc.route
                route_rationale = list(rc.rationale)
            else:
                diagnosis_route = "unknown"
                route_rationale = ["no_matching_pathway"]

            result[pid].append({
                "episode_id": ep_id,
                "cancer_type": milestones[0]["cancer_type"],
                "gold_cohort": gold_cohort,
                "detected_cohort": detected_cohort,
                "detected_site": detected_site,
                "diagnosis_route": diagnosis_route,
                "route_rationale": route_rationale,
                "anchors": anchors,
                "n_pathways": len(pathways),
                "pathway_notes": best.notes if best else [],
                "n_encounters_labelled": len(labels),
            })

    return dict(result)


def _fmt_simple(result: dict) -> str:
    lines: list[str] = []
    for pid, episodes in result.items():
        lines.append(f"\n{'='*72}")
        lines.append(f"Patient {pid}")
        for ep in episodes:
            lines.append(f"\n  Episode {ep['episode_id']} [{ep['cancer_type']}] site={ep['detected_site']}")
            lines.append(f"  Gold cohort: {ep['gold_cohort']}  Detected cohort: {ep['detected_cohort']}")
            cohort_ok = ep["gold_cohort"] == ep["detected_cohort"]
            lines.append(f"  Cohort match: {'OK' if cohort_ok else '!!'}")
            dr = ep.get("diagnosis_route", "unknown")
            rr = ep.get("route_rationale") or []
            lines.append(f"  Diagnosis route: {dr}  ({'; '.join(rr)})")
            lines.append(f"  {'Anchor':<12} {'Gold date':<14} {'Detected date':<14} {'Diff':>6}  Status")
            lines.append(f"  {'-'*12} {'-'*14} {'-'*14} {'-'*6}  {'-'*10}")
            for anchor in ep["anchors"]:
                icon = _STATUS_ICONS.get(anchor["status"], "??")
                diff_str = f"{anchor['diff_days']}d" if anchor["diff_days"] is not None else "-"
                lines.append(
                    f"  {anchor['anchor']:<12} {anchor['gold'] or '-':<14} "
                    f"{anchor['detected'] or '-':<14} {diff_str:>6}  [{icon}] {anchor['status']}"
                )
            if ep.get("pathway_notes"):
                lines.append(f"  Notes: {'; '.join(ep['pathway_notes'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient", default=None, help="Limit to one NHS number.")
    parser.add_argument("--threshold", type=float, default=0.3,
                        help="Role probability threshold (default 0.3).")
    parser.add_argument("--role-model", type=Path, default=None,
                        help="Path to trained role classifier joblib artifact.")
    parser.add_argument("--linkage-model", type=Path, default=None,
                        help="Path to trained linkage classifier joblib artifact.")
    parser.add_argument("--simple", action="store_true",
                        help="Use site-aware simple linker (same site, 180-day window). "
                             "No ML classifier required.")
    parser.add_argument("--window", type=int, default=180,
                        help="FTR-to-Dx window in days for --simple mode (default 180).")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    driver = _connect()
    try:
        with driver.session() as session:
            if args.simple:
                print(f"Running in SIMPLE mode (site-aware, {args.window}-day window).\n")
                result = run_simple(
                    patient_filter=args.patient,
                    window_days=args.window,
                    session=session,
                )
                if not result:
                    print("No reviewed patients found (or no encounters for the filter).")
                    return 0
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(_fmt_simple(result))
                    _print_summary(result)
                return 0

            role_clf: RoleClassifier | None = None
            linkage_clf: LinkageClassifier | None = None
            if args.role_model and args.linkage_model:
                print(f"Loading role model from {args.role_model} ...")
                role_clf = RoleClassifier(args.role_model)
                print(f"Loading linkage model from {args.linkage_model} ...")
                linkage_clf = LinkageClassifier(args.linkage_model)
                print("Running in ML mode.\n")
            else:
                print("Running in deterministic mode (no trained models supplied).\n")

            result = run_dry(
                patient_filter=args.patient,
                threshold=args.threshold,
                role_classifier=role_clf,
                linkage_classifier=linkage_clf,
                session=session,
            )
    finally:
        driver.close()

    if not result:
        print("No reviewed patients found (or no encounters for the filter).")
        return 0

    print(_fmt(result, args.json))
    _print_summary(result)
    return 0


def _print_summary(result: dict) -> None:
    total_ep = sum(len(v) for v in result.values())
    cohort_match = 0
    anchor_stats: dict[str, dict[str, int]] = {}
    for episodes in result.values():
        for ep in episodes:
            if ep["gold_cohort"] == ep["detected_cohort"]:
                cohort_match += 1
            for a in ep["anchors"]:
                name = a["anchor"]
                if name not in anchor_stats:
                    anchor_stats[name] = {"MATCH": 0, "MISSED": 0, "EXTRA": 0, "N/A": 0, "DATE-OFF": 0}
                status = a["status"]
                if status.startswith("DATE-OFF"):
                    anchor_stats[name]["DATE-OFF"] += 1
                else:
                    anchor_stats[name][status] = anchor_stats[name].get(status, 0) + 1

    print(f"\n{'='*72}")
    print(f"SUMMARY: {total_ep} episode(s) across {len(result)} patient(s)")
    print(f"Cohort match: {cohort_match}/{total_ep}")
    print("Anchor recovery:")
    for anchor, counts in anchor_stats.items():
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()) if v > 0)
        print(f"  {anchor:<12}: {parts}")


if __name__ == "__main__":
    sys.exit(main())
