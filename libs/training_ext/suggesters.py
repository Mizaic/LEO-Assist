"""Clinical n-gram suggester for spancat.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Covers Wave 2 (F7) of the World-Class Clinical NER plan.

The default `spacy.ngram_range_suggester.v1` enumerates every span from
`min_size` to `max_size`. With `max_size=24`, that produces a large volume of
negative candidates that can drown the head in false-positive signal.

This suggester emits spans from 1..24 tokens. The training exporter now scopes
the model to the production extraction labels only, so the wider candidate set
is needed to keep long observable/finding spans proposable without asking the
head to learn every historical semantic type.

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
