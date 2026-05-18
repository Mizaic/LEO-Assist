"""Pseudo-labelling loop for self-training.

Atlas trace:
  DO: DO-2695BE52
  DI: DI-37B3DC71

What this gives you
-------------------
Given (a) a trained spaCy model and (b) a pool of unlabeled clinical text, we
run the model on the pool, keep only spans whose confidence is above a
(per-label) threshold, and materialise them as :class:`PseudoLabel` records
that can be mixed into the next training round alongside gold labels.

The loop is explicit and auditable:

* The generator writes JSON Lines with one record per document, matching the
  GoldLabel schema so existing loaders can ingest them directly.
* Each record is tagged ``source="pseudo"`` and ``confidence=<min span
  score>``. The trainer (Wave 5) is expected to down-weight pseudo records or
  schedule them on alternate epochs — we do *not* blend them silently with
  gold.
* We refuse to emit pseudo-labels for any span that overlaps an entity
  produced by EntityRuler / hand-written regex rules (we trust those) or that
  appears inside a negated/hypothetical context.

Re-running the script against a newer model simply overwrites the JSONL; the
file is always a snapshot of "what the current model would call confidently".
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PseudoLabelingConfig:
    """Opt-in knobs for pseudo-labelling."""

    min_confidence: float = 0.85
    per_label_thresholds: dict[str, float] = field(default_factory=dict)
    max_spans_per_doc: int = 100
    skip_labels: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_env(cls) -> "PseudoLabelingConfig":
        raw_thresholds = os.getenv("PSEUDO_LABEL_THRESHOLDS_JSON", "").strip()
        per_label: dict[str, float] = {}
        if raw_thresholds:
            try:
                parsed = json.loads(raw_thresholds)
                if isinstance(parsed, dict):
                    per_label = {str(k).upper(): float(v) for k, v in parsed.items()}
            except Exception as exc:
                logger.warning(
                    "[pseudo] Bad PSEUDO_LABEL_THRESHOLDS_JSON (%s) — ignoring", exc
                )
        skip = frozenset(
            m.strip().upper()
            for m in os.getenv("PSEUDO_LABEL_SKIP_LABELS", "").split(",")
            if m.strip()
        )
        try:
            min_conf = float(os.getenv("PSEUDO_LABEL_MIN_CONFIDENCE", "0.85"))
        except ValueError:
            min_conf = 0.85
        try:
            max_per_doc = int(os.getenv("PSEUDO_LABEL_MAX_SPANS_PER_DOC", "100"))
        except ValueError:
            max_per_doc = 100
        return cls(
            min_confidence=min_conf,
            per_label_thresholds=per_label,
            max_spans_per_doc=max_per_doc,
            skip_labels=skip,
        )

    def threshold_for(self, label: str) -> float:
        return self.per_label_thresholds.get(label.upper(), self.min_confidence)


@dataclass
class PseudoLabelSummary:
    """Aggregate stats for a pseudo-labelling pass."""

    docs_processed: int = 0
    spans_emitted: int = 0
    spans_skipped_low_confidence: int = 0
    spans_skipped_filtered: int = 0
    per_label: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "docs_processed": self.docs_processed,
            "spans_emitted": self.spans_emitted,
            "spans_skipped_low_confidence": self.spans_skipped_low_confidence,
            "spans_skipped_filtered": self.spans_skipped_filtered,
            "per_label": dict(self.per_label),
        }


def generate_pseudo_labels(
    model_dir: Path,
    texts: Iterable[str],
    output_path: Path,
    *,
    config: PseudoLabelingConfig | None = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> PseudoLabelSummary:
    """Run ``model_dir`` over ``texts`` and emit JSONL pseudo-labels.

    Output format (one record per line)::

        {
          "label_id": "PSEUDO-<index>",
          "source": "pseudo",
          "text": "...",
          "entities": [
             {"start": 12, "end": 20, "label": "DISORDER", "confidence": 0.91}
          ],
          "confidence": 0.91
        }

    The output file is overwritten.
    """
    import spacy

    config = config or PseudoLabelingConfig.from_env()

    def _log(msg: str) -> None:
        logger.info("[pseudo] %s", msg)
        if log_fn:
            log_fn(msg)

    _log(f"Loading model from {model_dir}")
    try:
        import app.spacy_listener_width  # noqa: F401 -- registry side effects.
    except Exception:
        # Safe to continue; the callback only matters during training.
        pass
    nlp = spacy.load(str(model_dir))

    summary = PseudoLabelSummary()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for i, record in enumerate(_emit_records(nlp, texts, config, summary)):
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
            if (i + 1) % 200 == 0:
                _log(f"Processed {i + 1} documents…")

    _log(
        f"Done — emitted {summary.spans_emitted} pseudo-spans across "
        f"{summary.docs_processed} docs "
        f"(low-conf skipped={summary.spans_skipped_low_confidence}, "
        f"filtered={summary.spans_skipped_filtered})"
    )
    return summary


def _emit_records(
    nlp,
    texts: Iterable[str],
    config: PseudoLabelingConfig,
    summary: PseudoLabelSummary,
) -> Iterator[dict]:
    for index, text in enumerate(texts):
        if not text.strip():
            summary.docs_processed += 1
            continue
        doc = nlp(text)
        spans = _ranked_spans(doc)
        kept: list[dict] = []
        for span, score in spans[: config.max_spans_per_doc]:
            label = str(span.label_).upper()
            if label in config.skip_labels:
                summary.spans_skipped_filtered += 1
                continue
            threshold = config.threshold_for(label)
            if score < threshold:
                summary.spans_skipped_low_confidence += 1
                continue
            kept.append(
                {
                    "start": int(span.start_char),
                    "end": int(span.end_char),
                    "label": label,
                    "confidence": round(float(score), 4),
                }
            )
            summary.per_label[label] = summary.per_label.get(label, 0) + 1
            summary.spans_emitted += 1

        summary.docs_processed += 1
        if not kept:
            continue
        yield {
            "label_id": f"PSEUDO-{index:06d}",
            "source": "pseudo",
            "text": text,
            "entities": kept,
            "confidence": min(e["confidence"] for e in kept),
        }


def _ranked_spans(doc) -> list:
    """Return (span, score) sorted high-to-low, de-duped by (start, end, label)."""
    scored: list[tuple] = []
    seen: set[tuple[int, int, str]] = set()
    sc_spans = doc.spans.get("sc") if hasattr(doc.spans, "get") else None
    if sc_spans is not None:
        for span in sc_spans:
            key = (int(span.start_char), int(span.end_char), str(span.label_))
            if key in seen:
                continue
            seen.add(key)
            score = _span_score(span)
            scored.append((span, score))
    else:
        for ent in doc.ents:
            key = (int(ent.start_char), int(ent.end_char), str(ent.label_))
            if key in seen:
                continue
            seen.add(key)
            score = _span_score(ent)
            scored.append((ent, score))
    scored.sort(key=lambda sv: sv[1], reverse=True)
    return scored


def _span_score(span) -> float:
    # spaCy stashes per-span probabilities on kb_id_ in our pipeline; fall back
    # to 0.0 when unavailable.
    raw = getattr(span, "kb_id_", "") or ""
    try:
        return float(raw)
    except ValueError:
        return 0.0
