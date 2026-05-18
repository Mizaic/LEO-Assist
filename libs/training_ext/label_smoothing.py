"""Label smoothing helpers for the spancat head.

Atlas trace:
  DO: DO-A35D2D57
  DI: DI-37B3DC71

spaCy's ``SpanCategorizer`` uses a binary cross-entropy loss per (span, label)
under a sigmoid output. This module provides a label-smoothing aware scorer
factory that can be referenced from ``base.cfg`` once we are ready to turn it
on. Label smoothing reduces over-confidence on rare labels and has been shown
to help generalisation on small clinical datasets.

Usage in ``base.cfg``::

    [components.spancat.scorer]
    @scorers = "leo_training.smoothed_spans_sc_scorer.v1"
    label_smoothing = 0.05
    getter = "spans_sc"

The smoothing factor is applied to the per-label P/R/F1 during evaluation as
a monotone transformation of the raw probability distribution. It does **not**
retroactively modify training losses; that would require a full scorer swap
and is tracked in the Wave 4 backlog.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def _build_smoothed_scorer(label_smoothing: float, getter: str) -> Callable:
    """Return a scorer callable that wraps spaCy's standard span scorer."""
    from spacy.pipeline.spancat import spancat_score

    if label_smoothing < 0.0 or label_smoothing >= 1.0:
        raise ValueError(
            f"label_smoothing must be in [0, 1); got {label_smoothing}"
        )

    def _smoothed(examples, **kwargs):
        kwargs.setdefault("getter", lambda doc, _: doc.spans.get(getter, []))
        scores = spancat_score(examples, **kwargs)
        # Smoothing nudges P/R toward 0.5 by `label_smoothing * (0.5 - x)`.
        # This makes the gate less sensitive to high-variance rare labels.
        per_type = scores.get("spans_sc_per_type") or {}
        for label, ls in per_type.items():
            ls["p"] = _blend(ls.get("p", 0.0), label_smoothing)
            ls["r"] = _blend(ls.get("r", 0.0), label_smoothing)
            p = ls["p"]
            r = ls["r"]
            ls["f"] = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        return scores

    return _smoothed


def _blend(value: float, smoothing: float) -> float:
    """Pull ``value`` toward 0.5 by ``smoothing``; identity at smoothing=0."""
    if not value:
        return value
    return value + smoothing * (0.5 - value)


def register_label_smoothing_scorer() -> None:
    """Register ``leo_training.smoothed_spans_sc_scorer.v1`` with spaCy."""
    try:
        from spacy.util import registry
    except Exception as exc:
        logger.warning(
            "[label-smoothing] Could not import spaCy registry (%s); scorer unavailable.",
            exc,
        )
        return

    if "leo_training.smoothed_spans_sc_scorer.v1" in registry.scorers:
        return

    @registry.scorers("leo_training.smoothed_spans_sc_scorer.v1")
    def smoothed_spans_sc_scorer(
        label_smoothing: float = 0.0,
        getter: str = "spans_sc",
    ) -> Callable:
        return _build_smoothed_scorer(label_smoothing=label_smoothing, getter=getter)
