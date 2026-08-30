"""ConText NLP must start when spaCy loads installed factories.

spaCy ``blank('en')`` loads every registered factory, including
spacy-transformers if it is installed. sentence-transformers 6 pulls
transformers 5, which no longer exports BatchEncoding where
spacy-transformers 1.3 looks for it. ConText then never starts and
post-processing fail-closes.

This test is the boot check for that SOUP clash.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
"""

from __future__ import annotations

from libs.ner.context_engine import _build_nlp


def test_transformers_exports_batch_encoding_for_spacy_transformers() -> None:
    from transformers.tokenization_utils import BatchEncoding

    assert BatchEncoding is not None


def test_context_engine_nlp_pipeline_starts() -> None:
    nlp = _build_nlp()
    assert nlp.has_pipe("medspacy_context")
