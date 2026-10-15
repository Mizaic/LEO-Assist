"""Fitted withhold model: learn when today's attached code is likely right.

Features describe the candidate production would attach: its calibrated
score, exact or not, word coverage against the phrase, the gap to the next
candidate, and whether its type matches the expected type. A logistic
model turns these into a probability; we attach only above a threshold
chosen on the training sets to keep 95% of attached codes correct.

Trained on labelled + human_sf; hard (and real, when present) are held out.

Usage:
    python -m scripts.terminology_sim.fitted POOLS_DIR
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from scripts.terminology_sim.evaluate import PASS_BAR, View, _views
from scripts.terminology_sim.features import best_fits, is_qualifier, tokens
from scripts.terminology_sim.pool import Pool, attach
from scripts.terminology_sim.strategies import _cached_baseline, _norm_tag

TRAIN_SETS = ("labelled", "human_sf")
FEATURES = (
    "score",
    "exact",
    "precision",
    "recall",
    "missing_qual_only",
    "n_extra",
    "n_missing_core",
    "gap",
    "tag_match",
    "n_tokens",
)


@dataclass
class Choice:
    concept_id: Optional[str]
    x: Optional[np.ndarray]


def choose(pool: Pool, tag: str | None, stripped: Pool | None) -> Choice:
    """The code today's lookup (plus exact strip) attaches, and its features."""
    for p in ((stripped,) if stripped and stripped.exact and not pool.exact else ()):
        ranked = _cached_baseline(p, tag)
        got = attach(p.case.phrase, tag, ranked)
        if got:
            return Choice(got, _x(p, tag, ranked, got))
    ranked = _cached_baseline(pool, tag)
    got = attach(pool.case.phrase, tag, ranked)
    return Choice(got, _x(pool, tag, ranked, got) if got else None)


def _x(pool: Pool, tag: str | None, ranked, got: str) -> np.ndarray:
    idx = next(i for i, c in enumerate(ranked) if c.snomed_concept_id == got)
    cand = ranked[idx]
    nxt = ranked[idx + 1].score if idx + 1 < len(ranked) else 0.0
    phrase = tokens(pool.case.phrase)
    fit = best_fits(pool).get(got)
    matched = tokens(fit.matched) if fit and not cand.had_exact_match else phrase
    missing = phrase - matched
    return np.array(
        [
            cand.score,
            float(cand.had_exact_match),
            1.0 if cand.had_exact_match else (fit.precision if fit else 0.0),
            1.0 if cand.had_exact_match else (fit.recall if fit else 0.0),
            float(all(is_qualifier(t) for t in missing)),
            float(len(matched - phrase)),
            float(sum(1 for t in missing if not is_qualifier(t))),
            cand.score - nxt,
            float(bool(tag) and _norm_tag(cand.semantic_tag) == _norm_tag(tag)),
            float(len(phrase)),
        ]
    )


def rows(views: list[View]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    xs, ys, groups = [], [], []
    for view in views:
        for pool, tag, bare in view.items:
            ch = choose(pool, tag, bare)
            if ch.concept_id is None:
                continue
            xs.append(ch.x)
            ys.append(float(ch.concept_id in pool.case.expected))
            groups.append(f"{view.name}:{pool.case.case_id}")
    return np.array(xs), np.array(ys), groups


def fit_model(x: np.ndarray, y: np.ndarray) -> LogisticRegression:
    model = LogisticRegression(max_iter=2000, C=1.0)
    model.fit(x, y)
    return model


def pick_threshold(p: np.ndarray, y: np.ndarray, bar: float = PASS_BAR) -> float:
    """Lowest threshold whose attached codes are at least ``bar`` correct."""
    for t in np.round(np.arange(0.30, 0.995, 0.01), 2):
        keep = p >= t
        if keep.sum() and y[keep].mean() >= bar:
            return float(t)
    return 1.0


def _report(name: str, p: np.ndarray, y: np.ndarray, n: int, t: float) -> None:
    keep = p >= t
    correct = int(y[keep].sum())
    wrong = int(keep.sum() - correct)
    prec = correct / keep.sum() if keep.sum() else 1.0
    print(
        f"  {name:22} t={t:.2f} precision={prec:.3f} correct={correct} "
        f"wrong={wrong} coverage={correct / n if n else 0:.2f} (n={n})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pools_dir", type=Path)
    args = parser.parse_args(argv)
    views = _views(args.pools_dir)
    for mode in ("tag", "notag"):
        mv = [v for v in views if v.tag_mode == mode]
        train = [v for v in mv if v.name in TRAIN_SETS]
        x, y, groups = rows(train)
        print(f"== mode={mode} train rows={len(y)} correct={int(y.sum())}")
        cv_p = np.zeros_like(y)
        for tr, te in GroupKFold(n_splits=5).split(x, y, groups):
            cv_p[te] = fit_model(x[tr], y[tr]).predict_proba(x[te])[:, 1]
        t = pick_threshold(cv_p, y)
        model = fit_model(x, y)
        print("  weights", dict(zip(FEATURES, np.round(model.coef_[0], 2))))
        for v in mv:
            vx, vy, _ = rows([v])
            n = sum(1 for p, _, _ in v.items if p.case.expected)
            vp = model.predict_proba(vx)[:, 1] if len(vy) else np.array([])
            if v.name in TRAIN_SETS:
                mask = np.array([g.startswith(v.name + ":") for g in groups])
                vp = cv_p[mask]
            _report(f"{v.name} (cv)" if v.name in TRAIN_SETS else v.name, vp, vy, n, t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
