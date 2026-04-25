"""Clinical n-gram suggester for spancat.

Covers Wave 2 (F7) of the World-Class Clinical NER plan.

The default `spacy.ngram_range_suggester.v1` accepts a contiguous range, but
production needs an explicit span-size contract that tests can inspect.
Completed GoldLabel lab spans include short procedures, mid-length
observable_entity spans, and full abnormal finding lines across 1..24 spaCy
tokens.

The default size buckets can be overridden via the spaCy config ``sizes``
list.
"""

from __future__ import annotations

from typing import Optional, Sequence

from spacy.pipeline.spancat import Suggester, build_ngram_suggester
from spacy.util import registry


_DEFAULT_CLINICAL_SIZES: tuple[int, ...] = tuple(range(1, 25))


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
