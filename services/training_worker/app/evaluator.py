"""Post-training evaluation: precision/recall per entity label.

Atlas trace:
  DO: DO-54397CCD
  Also implements: DO-A35D2D57
  DI: DI-37B3DC71, DI-6EFD68D0
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-54397CCD")

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

from libs.training_ext.training_quality import evaluate_label_coverage

logger = logging.getLogger(__name__)

_MIN_PRECISION = float(os.getenv("MODEL_MIN_PRECISION", "0.80"))
_MIN_RECALL = float(os.getenv("MODEL_MIN_RECALL", "0.75"))
_MIN_GOLDEN_F1 = float(os.getenv("MODEL_MIN_GOLDEN_F1", "0.70"))
_MIN_LABEL_GATE_SUPPORT = int(os.getenv("LABEL_MIN_F1_SUPPORT", "25"))

# Per-label minimum F1 gates.  Labels absent from the dev split are skipped
# (zero-shot absence is a data-volume issue, not a regression signal).
#
# Tiers are based on:
#   - Clinical safety impact if the label is systematically wrong
#   - Frequency in UK primary care GP text (higher freq = more training signal)
#   - Inherent expression variability (ambiguous types carry lower floors)
#
# Override individual values via LABEL_MIN_F1_JSON env var (JSON object).
_LABEL_MIN_F1_DEFAULTS: dict[str, float] = {
    # -- Tier 1: safety-critical, high-frequency core coding entities --------
    # Lit benchmark: disorders 0.80-0.90, medications 0.85-0.95 (i2b2 / n2c2)
    "DISORDER": 0.82,
    "MEDICINAL_PRODUCT": 0.82,
    "PROCEDURE": 0.80,
    "CLINICAL_DRUG": 0.80,
    # -- Tier 2: high clinical importance, moderate frequency ----------------
    # Lit benchmark: findings/symptoms 0.75-0.85; substance/allergy 0.75-0.90
    "FINDING": 0.78,
    "SUBSTANCE": 0.75,
    "OBSERVABLE": 0.75,
    "MORPHOLOGIC_ABNORMALITY": 0.72,
    "BODY_STRUCTURE": 0.72,
    # -- Tier 3: moderate importance, higher expression variability ----------
    "DOSAGE": 0.72,
    "FREQUENCY": 0.72,
    "QUALIFIER": 0.70,
    "REGIME_THERAPY": 0.70,
    "ROUTE": 0.70,
    "TEMPORAL": 0.68,
    "SITUATION": 0.68,
    "ASSESSMENT_SCALE": 0.68,
    "TUMOR_STAGING": 0.65,
    "STAGING_SCALE": 0.65,
    # -- Tier 4: low frequency / informational -- floors guard regression ----
    "ORGANISM": 0.62,
    "EVENT": 0.60,
    "RECORD_ARTIFACT": 0.55,
    "PHYSICAL_OBJECT": 0.55,
    "OCCUPATION": 0.55,
    "ATTRIBUTE": 0.55,
    "ENVIRONMENT": 0.55,
    "PRODUCT": 0.55,
}


def _load_label_min_f1() -> dict[str, float]:
    """Return per-label gate dict.

    Resolution order (later wins):
      1. Hard-coded defaults in this module.
      2. Neo4j ``(:PrecisionGate)`` nodes (Wave 5) — optional. Controlled by
         ``PRECISION_GATES_FROM_NEO4J`` (default ``true``).
      3. ``LABEL_MIN_F1_JSON`` env var — ad-hoc overrides per run.
    """
    merged: dict[str, float] = dict(_LABEL_MIN_F1_DEFAULTS)

    if os.getenv("PRECISION_GATES_FROM_NEO4J", "true").lower() in ("1", "true", "yes"):
        try:
            from libs.training_ext.precision_gates import load_precision_gates_from_neo4j

            merged = load_precision_gates_from_neo4j(merged)
        except Exception as exc:
            logger.warning(
                "[evaluator] precision_gates loader failed (%s) -- using defaults",
                exc,
            )

    overrides_raw = os.getenv("LABEL_MIN_F1_JSON", "")
    if overrides_raw:
        try:
            overrides = json.loads(overrides_raw)
            if not isinstance(overrides, dict):
                raise ValueError("LABEL_MIN_F1_JSON must be a JSON object")
            merged.update({str(k).upper(): float(v) for k, v in overrides.items()})
        except Exception as exc:
            logger.warning(
                "[evaluator] LABEL_MIN_F1_JSON parse error (%s) -- ignoring", exc
            )
    return merged


def _check_label_gates(
    per_label: dict[str, dict],
    label_min_f1: dict[str, float],
    *,
    min_support: int = 0,
    skipped: list[str] | None = None,
) -> list[str]:
    """Return human-readable failure messages for any per-label F1 gate breach.

    Labels absent from per_label (not seen in the dev split) are skipped --
    zero-shot absence is a training-data volume problem, not a regression.
    Labels present with support below ``min_support`` are also skipped and
    reported through ``skipped`` so small dev counts become coverage findings
    rather than unstable promotion blockers.
    """
    failures = []
    for label, threshold in sorted(label_min_f1.items()):
        scores = per_label.get(label)
        if scores is None:
            continue
        support = scores.get("support")
        if support is not None:
            support_n = int(_as_float(support, default=0.0))
            if min_support > 0 and support_n < min_support:
                if skipped is not None:
                    skipped.append(
                        f"{label}: support={support_n} < min_support {min_support}"
                    )
                continue
        f1 = _as_float(scores.get("f1", 0.0))
        if f1 < threshold:
            failures.append(
                f"{label}: F1={f1:.3f} < min {threshold:.2f}"
            )
    return failures


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


def _assert_transformer_ready(nlp) -> None:
    """Raise a clear RuntimeError if any Transformer component has a None tokenizer.

    This can happen when a model-last was saved during a training run that
    crashed before the HuggingFace tokenizer was initialised (e.g. the
    after_init callback bug where nlp.pipeline skipped disabled components).
    Catching it here gives a diagnostic message instead of a cryptic
    TypeError deep in spacy-transformers.
    """
    try:
        from spacy_transformers import Transformer as _SpacyTransformer
    except ImportError:
        return
    for name, pipe in nlp.components:
        if not isinstance(pipe, _SpacyTransformer):
            continue
        tokenizer = pipe.model.attrs.get("tokenizer") or getattr(pipe.model, "tokenizer", None)
        if tokenizer is None:
            raise RuntimeError(
                f"Transformer component '{name}' has no tokenizer after model load "
                f"(has_transformer={pipe.model.attrs.get('has_transformer', False)}). "
                "The model was likely saved in an uninitialised state. "
                "Re-run training to produce a valid model artefact."
            )


_SCORE_COMPONENTS = {"spancat", "ner"}


def _score_examples(nlp, docs) -> dict:
    """Run inference and return scorer output dict.

    Uses each pipeline component's own .score() method so that spancat
    (spans_sc_*) and NER (ents_*) scorers are both handled correctly.
    A bare Scorer() only runs generic token-level scorers and misses the
    component-registered span/entity scorers entirely.

    Scorer exceptions from the components we rely on for gate evaluation
    (``spancat`` and ``ner``) are fatal — silently swallowing them would
    produce empty per-label metrics and let a broken model through the
    gates.  Scorer exceptions from auxiliary components (logger stubs,
    tok2vec, transformer) are logged and skipped so an unrelated scorer
    registration issue cannot break evaluation.
    """
    from spacy.training import Example

    texts = [doc.text for doc in docs]
    pred_docs = list(nlp.pipe(texts))
    examples = [Example(pred, gold) for pred, gold in zip(pred_docs, docs)]
    scores: dict = {}
    for name, component in nlp.pipeline:
        if not hasattr(component, "score"):
            continue
        try:
            scores.update(component.score(examples))
        except Exception as exc:
            if name in _SCORE_COMPONENTS:
                raise RuntimeError(
                    f"Scorer for gate-critical component {name!r} raised "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            logger.warning(
                "[evaluator] Scorer for auxiliary component %r raised "
                "%s: %s -- skipping",
                name,
                type(exc).__name__,
                exc,
            )
    return scores


def _count_gold_label_support(docs) -> dict[str, int]:
    """Count gold examples per label from spaCy dev docs."""
    support: dict[str, int] = {}
    for doc in docs:
        spans = getattr(doc, "spans", None)
        if hasattr(spans, "get"):
            for span in spans.get("sc", []):
                label = str(getattr(span, "label_", "") or "")
                if label:
                    support[label] = support.get(label, 0) + 1
        for ent in getattr(doc, "ents", []) or []:
            label = str(getattr(ent, "label_", "") or "")
            if label:
                support[label] = support.get(label, 0) + 1
    return support


def _rounded_int(value: object) -> int | None:
    """Return a rounded non-negative int for numeric scorer counts."""
    try:
        if value is None:
            return None
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return None


def _build_per_label(
    scores: dict,
    support_counts: dict[str, int] | None = None,
) -> dict[str, dict]:
    per_label: dict[str, dict] = {}
    per_type = scores.get("spans_sc_per_type") or scores.get("ents_per_type") or {}
    for label, ls in per_type.items():
        support = (
            support_counts.get(label)
            if support_counts is not None and label in support_counts
            else _rounded_int(ls.get("support") or ls.get("total"))
        )
        p = _as_float(ls.get("p", 0.0))
        r = _as_float(ls.get("r", 0.0))
        f1 = _as_float(ls.get("f", 0.0))
        row = {
            "precision": round(_as_float(ls.get("p", 0.0)), 4),
            "recall": round(_as_float(ls.get("r", 0.0)), 4),
            "f1": round(_as_float(ls.get("f", 0.0)), 4),
        }
        if support is not None:
            tp = _rounded_int(ls.get("tp"))
            fn = _rounded_int(ls.get("fn"))
            fp = _rounded_int(ls.get("fp"))
            if tp is None:
                tp = _rounded_int(r * support)
            if fn is None and tp is not None:
                fn = max(0, support - tp)
            if fp is None and tp is not None:
                fp = _rounded_int((tp / p) - tp) if p > 0 else 0
            row.update(
                {
                    "support": support,
                    "true_positive": tp,
                    "false_positive": fp,
                    "false_negative": fn,
                }
            )
        per_label[label] = row
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


def _apply_calibration_thresholds(nlp, model_dir: Path, log) -> Optional[dict]:
    """Load ``calibration.json`` (if present) and apply per-label thresholds.

    Returns the parsed calibration payload or None if no file exists / the
    pipeline has no spancat component. SpanCategorizer only supports a single
    global threshold, so we set ``spancat.cfg["threshold"]`` to the minimum
    per-label threshold (keeping all candidates) and perform label-wise
    post-filtering during evaluation. The returned payload is used by the
    caller to rescore predictions.
    """
    calib_path = model_dir / "calibration.json"
    if not calib_path.exists():
        return None
    try:
        payload = json.loads(calib_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"[evaluator] Could not parse calibration.json ({exc}) — skipping")
        return None
    per_label = payload.get("per_label") or {}
    if not per_label:
        return None
    if "spancat" not in nlp.pipe_names:
        return payload
    # Lower the global threshold so every candidate above the *minimum* per-
    # label threshold survives and label-wise filtering happens in scoring.
    thresholds = [float(v.get("threshold", 0.5)) for v in per_label.values()]
    if thresholds:
        min_t = max(0.01, min(thresholds))
        spancat = nlp.get_pipe("spancat")
        if hasattr(spancat, "cfg"):
            spancat.cfg["threshold"] = min_t
            log(
                f"[evaluator] Applied calibration: set spancat.threshold = {min_t:.2f} "
                f"(per-label thresholds in calibration.json)"
            )
    return payload


def _score_with_calibration(
    scores: dict,
    per_label_thresholds: dict[str, float],
) -> tuple[float, float, float, dict[str, dict]]:
    """Collapse per-label scores using calibration thresholds.

    spaCy's built-in Scorer already thresholds at the pipeline's global
    threshold. We rely on the caller having lowered that threshold to the
    minimum per-label value, then apply per-label filtering post-hoc by
    re-weighting the per-label P/R/F1. This is an approximation but useful
    as a diagnostic until a dedicated calibrated Scorer is added.
    """
    per_type = scores.get("spans_sc_per_type") or scores.get("ents_per_type") or {}
    per_label: dict[str, dict] = {}
    micro_p_num = micro_p_den = micro_r_num = micro_r_den = 0.0
    for label, ls in per_type.items():
        p = _as_float(ls.get("p", 0.0))
        r = _as_float(ls.get("r", 0.0))
        f1 = _as_float(ls.get("f", 0.0))
        per_label[label] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "threshold": round(per_label_thresholds.get(label, 0.5), 4),
        }
        # Approximate support counts from P/R to rebuild micro averages.
        # support = tp + fn  ≈ ls["support"] when present.
        support = _as_float(ls.get("support") or ls.get("total") or 0.0)
        if support > 0:
            tp = r * support
            fp = (tp / p - tp) if p > 0 else 0.0
            micro_p_num += tp
            micro_p_den += tp + fp
            micro_r_num += tp
            micro_r_den += support
    if micro_p_den > 0 and micro_r_den > 0:
        P = micro_p_num / micro_p_den
        R = micro_r_num / micro_r_den
        F1 = 2 * P * R / (P + R) if (P + R) > 0 else 0.0
    else:
        P = _first_numeric(scores, ("spans_sc_p", "ents_p"))
        R = _first_numeric(scores, ("spans_sc_r", "ents_r"))
        F1 = _first_numeric(scores, ("spans_sc_f", "ents_f"))
    return round(P, 4), round(R, 4), round(F1, 4), per_label


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
    _assert_transformer_ready(nlp)

    _log(f"Loading dev set from {dev_path}…")
    dev_bin = DocBin().from_disk(dev_path)
    gold_docs = list(dev_bin.get_docs(nlp.vocab))

    if not gold_docs:
        raise RuntimeError("Dev set is empty — cannot evaluate")

    _log(f"Evaluating on {len(gold_docs)} dev documents…")
    scores = _score_examples(nlp, gold_docs)
    support_counts = _count_gold_label_support(gold_docs)

    spans_p = round(_first_numeric(scores, ("spans_sc_p", "ents_p")), 4)
    spans_r = round(_first_numeric(scores, ("spans_sc_r", "ents_r")), 4)
    spans_f = round(_first_numeric(scores, ("spans_sc_f", "ents_f")), 4)
    per_label = _build_per_label(scores, support_counts)
    label_coverage = evaluate_label_coverage(per_label)
    macro_f1 = label_coverage["macro_f1"]

    passed = spans_p >= _MIN_PRECISION and spans_r >= _MIN_RECALL

    _log(f"Dev results: P={spans_p:.3f}  R={spans_r:.3f}  F1={spans_f:.3f}")
    _log(f"Macro F1: {macro_f1:.3f}")
    _log(
        f"Gates: min_precision={_MIN_PRECISION}  min_recall={_MIN_RECALL}  "
        f"passed={passed}"
    )
    if not passed:
        _log(
            f"GATE FAILED — P={spans_p:.3f} (need {_MIN_PRECISION}) "
            f"R={spans_r:.3f} (need {_MIN_RECALL})"
        )

    label_min_f1 = _load_label_min_f1()
    label_gate_skips: list[str] = []
    label_failures = _check_label_gates(
        per_label,
        label_min_f1,
        min_support=_MIN_LABEL_GATE_SUPPORT,
        skipped=label_gate_skips,
    )
    if label_gate_skips:
        for msg in label_gate_skips:
            _log(f"LABEL GATE SKIPPED — {msg}")
    if label_failures:
        for msg in label_failures:
            _log(f"LABEL GATE FAILED — {msg}")
        passed = False
    if label_coverage["failures"]:
        for msg in label_coverage["failures"]:
            _log(f"LABEL COVERAGE GATE FAILED — {msg}")
        passed = False

    result: dict = {
        "precision": spans_p,
        "recall": spans_r,
        "f1": spans_f,
        "macro_f1": macro_f1,
        "per_label": per_label,
        "label_coverage": label_coverage,
        "passed_gates": passed,
        "label_gate_failures": label_failures,
        "label_gate_skips": label_gate_skips,
        "min_label_gate_support": _MIN_LABEL_GATE_SUPPORT,
        "min_precision": _MIN_PRECISION,
        "min_recall": _MIN_RECALL,
        "dev_doc_count": len(gold_docs),
    }

    # --- Optional pass: calibrated evaluation ----------------------------
    # If a calibration.json is present in the model dir, apply per-label
    # thresholds and record the calibrated metrics as a diagnostic. Gates
    # continue to run against the raw (non-calibrated) metrics so the
    # calibration payload is transparent rather than load-bearing until the
    # inference service knows how to honour it.
    calibration_payload = _apply_calibration_thresholds(nlp, model_dir, _log)
    if calibration_payload is not None:
        _log("Running calibrated evaluation pass…")
        try:
            cal_scores = _score_examples(nlp, gold_docs)
            thresholds = {
                label: float(meta.get("threshold", 0.5))
                for label, meta in (calibration_payload.get("per_label") or {}).items()
            }
            cal_p, cal_r, cal_f, cal_per_label = _score_with_calibration(
                cal_scores, thresholds
            )
            result["calibrated_precision"] = cal_p
            result["calibrated_recall"] = cal_r
            result["calibrated_f1"] = cal_f
            result["calibrated_per_label"] = cal_per_label
            _log(
                f"Calibrated pass: P={cal_p:.3f}  R={cal_r:.3f}  F1={cal_f:.3f}"
            )
        except Exception as exc:
            _log(f"Calibrated evaluation failed ({exc}) — skipping diagnostic")

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
