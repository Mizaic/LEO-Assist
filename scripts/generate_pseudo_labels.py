"""Generate pseudo-labels from an unlabelled corpus.

Atlas trace:
  DO: DO-2695BE52
  DI: DI-37B3DC71

Usage::

    python -m scripts.generate_pseudo_labels \
        --model-dir models/clinical-ner-v5 \
        --corpus-file data/unlabelled_clinical.txt \
        --output-file data/pseudo_labels_v5.jsonl \
        --min-confidence 0.9

One passage per line in the corpus file — the same convention as
``scripts/mlm_pretrain.py``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from libs.training_ext.pseudo_labeller import (
    PseudoLabelingConfig,
    generate_pseudo_labels,
)

logger = logging.getLogger("generate_pseudo_labels")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--corpus-file", required=True, type=Path)
    parser.add_argument("--output-file", required=True, type=Path)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument(
        "--max-spans-per-doc",
        type=int,
        default=100,
        help="Upper bound on emitted spans per document.",
    )
    parser.add_argument(
        "--skip-labels",
        default="",
        help=(
            "Comma-separated labels to ignore (e.g. temporal placeholders). "
            "All labels are kept by default."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not args.corpus_file.exists():
        logger.error("Corpus file %s not found", args.corpus_file)
        return 2
    texts = [
        line.strip()
        for line in args.corpus_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    skip = frozenset(
        m.strip().upper() for m in args.skip_labels.split(",") if m.strip()
    )
    config = PseudoLabelingConfig(
        min_confidence=args.min_confidence,
        max_spans_per_doc=args.max_spans_per_doc,
        skip_labels=skip,
    )
    summary = generate_pseudo_labels(
        args.model_dir,
        texts,
        args.output_file,
        config=config,
        log_fn=lambda line: logger.info("%s", line),
    )
    logger.info("Summary: %s", summary.to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
