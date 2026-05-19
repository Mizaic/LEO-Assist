"""Wave 2 (F7) — clinical n-gram suggester."""

from __future__ import annotations

import spacy

from libs.training_ext import suggesters  # registers leo_training.clinical_ngram_suggester.v1
from libs.training_ext.suggesters import (
    _DEFAULT_CLINICAL_SIZES,
    build_clinical_ngram_suggester,
    clinical_ngram_suggester_v1,
)
from spacy.util import registry


def _make_doc(n_tokens: int):
    nlp = spacy.blank("en")
    return nlp.make_doc(" ".join([f"w{i}" for i in range(n_tokens)]))


def test_only_configured_sizes_are_emitted():
    suggester = build_clinical_ngram_suggester(sizes=[1, 3])
    doc = _make_doc(10)
    output = suggester([doc])
    rows = output.dataXd.tolist()
    lengths = {end - start for start, end in rows}
    assert lengths == {1, 3}


def test_default_sizes_cover_full_target_scope_range():
    """Default sizes cover long observable/finding spans in the scoped model."""
    suggester = build_clinical_ngram_suggester()
    doc = _make_doc(30)
    output = suggester([doc])
    rows = output.dataXd.tolist()
    lengths = {end - start for start, end in rows}
    expected = set(range(1, 25))
    assert set(_DEFAULT_CLINICAL_SIZES) == expected
    assert lengths == expected


def test_short_multi_entity_sentence_candidates_are_still_emitted():
    """Procedure, observable, and finding spans can coexist in one sentence."""
    suggester = clinical_ngram_suggester_v1()
    doc = _make_doc(12)
    output = suggester([doc])
    rows = {tuple(row) for row in output.dataXd.tolist()}

    assert (0, 2) in rows
    assert (4, 5) in rows
    assert (7, 10) in rows


def test_registry_entry_returns_callable():
    fn = registry.misc.get("leo_training.clinical_ngram_suggester.v1")
    suggester = fn()
    assert callable(suggester)


def test_empty_doc_produces_empty_ragged():
    suggester = clinical_ngram_suggester_v1()
    doc = _make_doc(0)
    output = suggester([doc])
    assert output.dataXd.shape[0] == 0
    assert list(output.lengths) == [0]


def test_short_doc_does_not_emit_long_spans():
    suggester = clinical_ngram_suggester_v1()
    doc = _make_doc(5)
    output = suggester([doc])
    rows = output.dataXd.tolist()
    lengths = {end - start for start, end in rows}
    assert lengths <= {1, 2, 3, 4, 5}


def test_rejects_empty_size_list():
    import pytest

    with pytest.raises(ValueError):
        build_clinical_ngram_suggester(sizes=[])
