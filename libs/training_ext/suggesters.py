"""Clinical n-gram suggester for spancat.

Covers Wave 2 (F7) of the World-Class Clinical NER plan.

The default `spacy.ngram_range_suggester.v1` enumerates every span from
`min_size` to `max_size`. With `max_size=24`, that produces a large volume of
negative candidates that can drown the head in false-positive signal.

This suggester emits a bounded clinical set:
  * short to medium spans (1..10 tokens) - covers p95 of curated gold spans
  * selected long lab spans (15, 20..24 tokens) - covers known lab triples

The default size buckets can be overridden via the spaCy config ``sizes``
list.
"""

from __future__ import annotations

from typing import Optional, Sequence

from spacy.pipeline.spancat import Suggester, build_ngram_suggester
from spacy.util import registry


_DEFAULT_CLINICAL_SIZES: tuple[int, ...] = (
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    15,
    20,
    21,
    22,
    23,
    24,
)


def build_clinical_ngram_suggester(
    sizes: Sequence[int] = _DEFAULT_CLINICAL_SIZES,
) -> Suggester:
    """Return a suggester that only enumerates spans of the given sizes."""
    size_list = sorted({int(s) for s in sizes if int(s) > 0})
    if not size_list:
        raise ValueError(
            "clinical_ngram_suggester requires at least one positive size"
        )
    return build_ngram_suggester(size_list)


@registry.misc("leo_training.clinical_ngram_suggester.v1")
def clinical_ngram_suggester_v1(
    sizes: Optional[Sequence[int]] = None,
) -> Suggester:
    """Registry hook — spaCy config ``@misc`` entry."""
    if sizes is None:
        sizes = _DEFAULT_CLINICAL_SIZES
    return build_clinical_ngram_suggester(sizes)
