"""Post-training evaluation: precision/recall per entity label.

Loads the trained model from disk and runs it against the dev DocBin.
Compares predicted entities to gold entities and computes per-label
and aggregate P/R/F1 scores.

Also runs a second evaluation pass against the frozen golden set (GoldLabel
nodes with frozen_golden_set=true) when any exist. The golden set score is
kept separate from the dev-split score so it serves as an immutable regression
benchmark across training runs.

Returns a metrics dict compatible with ModelRegistry.validate_offline().
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MIN_PRECISION = float(os.getenv("MODEL_MIN_PRECISION", "0.80"))
_MIN_RECALL = float(os.getenv("MODEL_MIN_RECALL", "0.75"))
_MIN_GOLDEN_F1 = float(os.getenv("MODEL_MIN_GOLDEN_F1", "0.70"))


def _as_float(value: object, default: float = 0.0) -> float:
    """Convert score values to float, treating None/invalid values as default."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_numeric(scores: dict, keys: tuple[str, ...], default: float = 0.0) -> float:
    """Return first non-None numeric value from score keys."""
    for key in keys:
        if key not in scores:
            continue
        value = scores.get(key)
        if value is None:
            continue
        return _as_float(value, default=default)
    return default


def _register_training_architectures() -> None:
    """Register custom spaCy architectures used by training configs."""
    try:
        import app.spacy_listener_width  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            f"Failed to register training architectures before model load: {exc}"
        ) from exc


def _score_examples(nlp, docs) -> dict:
    """Run inference and return scorer output dict."""
    from spacy.scorer import Scorer
    from spacy.training import Example

    texts = [doc.text for doc in docs]
    pred_docs = list(nlp.pipe(texts))
    examples = [Example(pred, gold) for pred, gold in zip(pred_docs, docs)]
    scorer = Scorer()
    return scorer.score(examples)


def _build_per_label(scores: dict) -> dict[str, dict]:
    per_label: dict[str, dict] = {}
    per_type = scores.get("spans_sc_per_type") or scores.get("ents_per_type") or {}
    for label, ls in per_type.items():
        per_label[label] = {
            "precision": round(_as_float(ls.get("p", 0.0)), 4),
            "recall": round(_as_float(ls.get("r", 0.0)), 4),
            "f1": round(_as_float(ls.get("f", 0.0)), 4),
        }
    return per_label


def _fetch_golden_set_docs(nlp, log):
    """Return spaCy docs for frozen golden set labels, or empty list."""
    try:
        import spacy

        from libs.neo4j_client.client import KnowledgeGraphClient
        from libs.cypher.golden_set_queries import GET_GOLDEN_SET_LABELS

        kg = KnowledgeGraphClient()
        try:
            with kg.session() as session:
                rows = list(session.run(GET_GOLDEN_SET_LABELS))
        finally:
            kg.close()

        if not rows:
            return []

        docs = []
        for row in rows:
            text = str(row["text"] or "")
            entities = json.loads(row["entities_json"] or "[]")
            doc = nlp.make_doc(text)
            spans = []
            for ent in entities:
                start = int(ent.get("start", 0))
                end = int(ent.get("end", 0))
                label = str(ent.get("label", "")).upper()
                if not label or end <= start:
                    continue
                span = doc.char_span(start, end, label=label, alignment_mode="expand")
                if span is None:
                    continue
                spans.append(span)
            doc.spans["sc"] = spans
            docs.append(doc)
        return docs
    except Exception as exc:
        log(f"[evaluator] Golden set fetch failed (skipping): {exc}")
        return []


def evaluate_model(
    model_dir: Path,
    dev_path: Path,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict:
    """Evaluate the trained model on the dev set and the frozen golden set.

    Args:
        model_dir: Path to the spaCy model directory (model-best).
        dev_path: Path to the dev.spacy DocBin.
        log_fn: Optional log line callback.

    Returns:
        dict with keys: precision, recall, f1, per_label, passed_gates,
        and optionally golden_precision, golden_recall, golden_f1,
        golden_passed, golden_doc_count.

    Raises:
        RuntimeError: If model fails to load or dev set is empty.
    """
    import spacy
    from spacy.tokens import DocBin

    def _log(msg: str) -> None:
        logger.info("[evaluator] %s", msg)
        if log_fn:
            log_fn(msg)

    _register_training_architectures()
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
    scores = _score_examples(nlp, gold_docs)

    spans_p = round(_first_numeric(scores, ("spans_sc_p", "ents_p")), 4)
    spans_r = round(_first_numeric(scores, ("spans_sc_r", "ents_r")), 4)
    spans_f = round(_first_numeric(scores, ("spans_sc_f", "ents_f")), 4)
    per_label = _build_per_label(scores)

    passed = spans_p >= _MIN_PRECISION and spans_r >= _MIN_RECALL

    _log(f"Dev results: P={spans_p:.3f}  R={spans_r:.3f}  F1={spans_f:.3f}")
    _log(
        f"Gates: min_precision={_MIN_PRECISION}  min_recall={_MIN_RECALL}  "
        f"passed={passed}"
    )
    if not passed:
        _log(
            f"GATE FAILED — P={spans_p:.3f} (need {_MIN_PRECISION}) "
            f"R={spans_r:.3f} (need {_MIN_RECALL})"
        )

    result: dict = {
        "precision": spans_p,
        "recall": spans_r,
        "f1": spans_f,
        "per_label": per_label,
        "passed_gates": passed,
        "min_precision": _MIN_PRECISION,
        "min_recall": _MIN_RECALL,
        "dev_doc_count": len(gold_docs),
    }

    # --- Second pass: frozen golden set -----------------------------------
    _log("Fetching frozen golden set from Knowledge Graph…")
    golden_docs = _fetch_golden_set_docs(nlp, _log)

    if golden_docs:
        _log(f"Evaluating golden set ({len(golden_docs)} documents)…")
        gs = _score_examples(nlp, golden_docs)
        g_p = round(_first_numeric(gs, ("spans_sc_p", "ents_p")), 4)
        g_r = round(_first_numeric(gs, ("spans_sc_r", "ents_r")), 4)
        g_f = round(_first_numeric(gs, ("spans_sc_f", "ents_f")), 4)
        g_passed = g_f >= _MIN_GOLDEN_F1
        _log(
            f"Golden set: P={g_p:.3f}  R={g_r:.3f}  F1={g_f:.3f}  "
            f"(threshold={_MIN_GOLDEN_F1}  passed={g_passed})"
        )
        if not g_passed:
            _log(
                f"GOLDEN GATE FAILED — F1={g_f:.3f} (need {_MIN_GOLDEN_F1}). "
                "Model regressed on frozen benchmark."
            )
            result["passed_gates"] = False
        result.update(
            {
                "golden_precision": g_p,
                "golden_recall": g_r,
                "golden_f1": g_f,
                "golden_passed": g_passed,
                "golden_doc_count": len(golden_docs),
                "min_golden_f1": _MIN_GOLDEN_F1,
            }
        )
    else:
        _log("No frozen golden set labels found — skipping golden set evaluation.")

    return result
