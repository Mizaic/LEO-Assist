"""Post-training evaluation: precision/recall per entity label.

Loads the trained model from disk and runs it against the dev DocBin.
Compares predicted entities to gold entities and computes per-label
and aggregate P/R/F1 scores.

Returns a metrics dict compatible with ModelRegistry.validate_offline().
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MIN_PRECISION = float(os.getenv("MODEL_MIN_PRECISION", "0.80"))
_MIN_RECALL = float(os.getenv("MODEL_MIN_RECALL", "0.75"))


def evaluate_model(
    model_dir: Path,
    dev_path: Path,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict:
    """Evaluate the trained model on the dev set.

    Args:
        model_dir: Path to the spaCy model directory (model-best).
        dev_path: Path to the dev.spacy DocBin.
        log_fn: Optional log line callback.

    Returns:
        dict with keys: precision, recall, f1, per_label, passed_gates.

    Raises:
        RuntimeError: If model fails to load.
    """
    import spacy
    from spacy.tokens import DocBin
    from spacy.scorer import Scorer
    from spacy.training import Example

    def _log(msg: str) -> None:
        logger.info("[evaluator] %s", msg)
        if log_fn:
            log_fn(msg)

    _log(f"Loading model from {model_dir}…")
    try:
        nlp = spacy.load(str(model_dir))
    except Exception as exc:
        raise RuntimeError(f"Failed to load model for evaluation: {exc}") from exc

    _log(f"Loading dev set from {dev_path}…")
    dev_bin = DocBin().from_disk(dev_path)
    gold_docs = list(dev_bin.get_docs(nlp.vocab))

    if not gold_docs:
        raise RuntimeError("Dev set is empty — cannot evaluate")

    _log(f"Evaluating on {len(gold_docs)} dev documents…")

    # Batch inference via nlp.pipe — more efficient than calling nlp() in a loop,
    # especially with GPU/transformer models where batching amortises overhead.
    texts = [doc.text for doc in gold_docs]
    pred_docs = list(nlp.pipe(texts))
    examples = [Example(pred, gold) for pred, gold in zip(pred_docs, gold_docs)]

    scorer = Scorer()
    scores = scorer.score(examples)

    ents_p = round(float(scores.get("ents_p", 0.0)), 4)
    ents_r = round(float(scores.get("ents_r", 0.0)), 4)
    ents_f = round(float(scores.get("ents_f", 0.0)), 4)

    per_label: dict[str, dict] = {}
    for label, label_scores in (scores.get("ents_per_type") or {}).items():
        per_label[label] = {
            "precision": round(float(label_scores.get("p", 0.0)), 4),
            "recall": round(float(label_scores.get("r", 0.0)), 4),
            "f1": round(float(label_scores.get("f", 0.0)), 4),
        }

    passed = ents_p >= _MIN_PRECISION and ents_r >= _MIN_RECALL

    _log(f"Results: P={ents_p:.3f}  R={ents_r:.3f}  F1={ents_f:.3f}")
    _log(f"Gates: min_precision={_MIN_PRECISION}  min_recall={_MIN_RECALL}  passed={passed}")
    if not passed:
        _log(
            f"GATE FAILED — P={ents_p:.3f} (need {_MIN_PRECISION}) "
            f"R={ents_r:.3f} (need {_MIN_RECALL})"
        )

    return {
        "precision": ents_p,
        "recall": ents_r,
        "f1": ents_f,
        "per_label": per_label,
        "passed_gates": passed,
        "min_precision": _MIN_PRECISION,
        "min_recall": _MIN_RECALL,
        "dev_doc_count": len(gold_docs),
    }
