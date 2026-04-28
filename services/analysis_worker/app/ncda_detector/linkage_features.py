"""Stage 6 - Linkage-classifier feature extraction.

Pure functions that take one CandidatePair plus the patient's surrounding
encounter context and produce a feature dict for the linkage classifier.

The training side (services.training_worker.app.ncda_linkage_trainer)
imports this so train- and predict-time features stay aligned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from services.analysis_worker.app.ncda_detector.pair_generator import (
    CandidatePair,
    RoleScore,
)

# NCDA breach thresholds (national rules).
FDS_28 = 28
TREATMENT_31 = 31
REFERRAL_62 = 62


@dataclass(frozen=True)
class PairContext:
    """Context the linkage classifier needs around a single pair.

    Attributes:
        ftr_encounter: RoleScore for the FTR endpoint (None for Dx-only).
        dx_encounter: RoleScore for the Dx endpoint (None for FTR-only).
        intervening: All RoleScores between FTR_date and Dx_date (open
            interval) used for the intervening histogram features.
        ftr_window_mean_vec: Mean vector across (FTR +/- 14d) encounters.
        dx_window_mean_vec: Mean vector across (Dx +/- 14d) encounters.
        recurrent_ftr: True when this patient has multiple FTRs.
    """

    ftr_encounter: RoleScore | None
    dx_encounter: RoleScore | None
    intervening: Sequence[RoleScore]
    ftr_window_mean_vec: Sequence[float] | None = None
    dx_window_mean_vec: Sequence[float] | None = None
    recurrent_ftr: bool = False


def gap_features(pair: CandidatePair) -> dict[str, float]:
    """gap_days plus breach-flag booleans."""
    gap = pair.gap_days
    if gap is None:
        return {
            "gap_days": 0,
            "gap_breaches_28": 0,
            "gap_breaches_62": 0,
            "gap_breaches_negative": 0,
            "gap_missing": 1,
        }
    return {
        "gap_days": float(gap),
        "gap_breaches_28": int(gap > FDS_28),
        "gap_breaches_62": int(gap > REFERRAL_62),
        "gap_breaches_negative": int(gap < 0),
        "gap_missing": 0,
    }


def role_probability_features(pair: CandidatePair) -> dict[str, float]:
    return {
        "ftr_role_p": float(pair.ftr_role_p or 0.0),
        "dx_role_p": float(pair.dx_role_p or 0.0),
        "dx_outcome_p": float(pair.dx_outcome_p or 0.0),
        "dx_is_cancer_found": int(pair.dx_outcome == "cancer_found"),
        "dx_is_cancer_excluded": int(pair.dx_outcome == "cancer_excluded"),
        "ftr_missing": int(pair.ftr_encounter_id is None),
        "dx_missing": int(pair.dx_encounter_id is None),
    }


def vector_cosine_features(context: PairContext) -> dict[str, float]:
    """Cosine FTR-encounter vs Dx-encounter and FTR-window vs Dx-window."""
    out = {"vec_cosine_anchor": 0.0, "vec_cosine_window": 0.0}
    if (
        context.ftr_encounter
        and context.dx_encounter
        and getattr(context.ftr_encounter, "vector", None)
        and getattr(context.dx_encounter, "vector", None)
    ):
        out["vec_cosine_anchor"] = _cosine(
            context.ftr_encounter.vector, context.dx_encounter.vector  # type: ignore[attr-defined]
        )
    if context.ftr_window_mean_vec and context.dx_window_mean_vec:
        out["vec_cosine_window"] = _cosine(
            context.ftr_window_mean_vec, context.dx_window_mean_vec
        )
    return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


def intervening_histogram(context: PairContext) -> dict[str, int]:
    """Counts of role-flagged encounters in (FTR, Dx)."""
    counts = {"between_ftr": 0, "between_seen": 0, "between_dx": 0, "between_treatment": 0}
    for enc in context.intervening:
        for role in ("ftr", "seen", "dx", "treatment"):
            if enc.role_probabilities.get(role, 0.0) >= 0.5:
                counts[f"between_{role}"] += 1
    return counts


def recurrent_ftr_feature(context: PairContext) -> dict[str, int]:
    return {"recurrent_ftr": int(context.recurrent_ftr)}


def aux_anchor_features(
    context: PairContext,
    *,
    seen_encounters: Sequence[RoleScore],
    treatment_encounters: Sequence[RoleScore],
) -> dict[str, float]:
    """Days-to-nearest auxiliary anchor inside relevant intervals."""
    out = {
        "days_ftr_to_first_seen": 0.0,
        "seen_role_p": 0.0,
        "days_dx_to_first_treatment": 0.0,
        "treatment_role_p": 0.0,
        "seen_present": 0,
        "treatment_present": 0,
    }
    if context.ftr_encounter and context.dx_encounter:
        seen_in_window = [
            s for s in seen_encounters if _in_open_window(s, context, "seen")
        ]
        if seen_in_window:
            seen = min(
                seen_in_window,
                key=lambda s: abs(_days_between(s.encounter_date, context.ftr_encounter.encounter_date)),  # type: ignore[union-attr]
            )
            out["days_ftr_to_first_seen"] = float(
                _days_between(context.ftr_encounter.encounter_date, seen.encounter_date)
            )
            out["seen_role_p"] = seen.role_probabilities.get("seen", 0.0)
            out["seen_present"] = 1
    if context.dx_encounter and context.dx_encounter.outcome == "cancer_found":
        tx_window = [
            t for t in treatment_encounters if _post_dx_window(t, context.dx_encounter, 180)
        ]
        if tx_window:
            tx = min(
                tx_window,
                key=lambda t: _days_between(context.dx_encounter.encounter_date, t.encounter_date),  # type: ignore[union-attr]
            )
            out["days_dx_to_first_treatment"] = float(
                _days_between(context.dx_encounter.encounter_date, tx.encounter_date)
            )
            out["treatment_role_p"] = tx.role_probabilities.get("treatment", 0.0)
            out["treatment_present"] = 1
    return out


def _in_open_window(score: RoleScore, context: PairContext, role: str) -> bool:
    if not context.ftr_encounter or not context.dx_encounter:
        return False
    a = _to_date(context.ftr_encounter.encounter_date)
    b = _to_date(context.dx_encounter.encounter_date)
    s = _to_date(score.encounter_date)
    if a is None or b is None or s is None:
        return False
    return a < s <= b


def _post_dx_window(score: RoleScore, dx: RoleScore, max_days: int) -> bool:
    a = _to_date(dx.encounter_date)
    s = _to_date(score.encounter_date)
    if a is None or s is None:
        return False
    return s >= a and (s - a).days <= max_days


def _days_between(a: str, b: str) -> int:
    d_a = _to_date(a)
    d_b = _to_date(b)
    if d_a is None or d_b is None:
        return 0
    return (d_b - d_a).days


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def extract_pair_features(
    pair: CandidatePair,
    context: PairContext,
    *,
    seen_encounters: Sequence[RoleScore],
    treatment_encounters: Sequence[RoleScore],
) -> dict[str, float]:
    """Combined linkage feature dict ready for DictVectorizer / LightGBM."""
    out: dict[str, float] = {}
    out.update(gap_features(pair))
    out.update(role_probability_features(pair))
    out.update(vector_cosine_features(context))
    out.update(intervening_histogram(context))
    out.update(recurrent_ftr_feature(context))
    out.update(
        aux_anchor_features(
            context,
            seen_encounters=seen_encounters,
            treatment_encounters=treatment_encounters,
        )
    )
    return out
