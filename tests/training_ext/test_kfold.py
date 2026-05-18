"""Wave 3 tests for K-fold stratified split."""

from __future__ import annotations

import pytest

from libs.training_ext.stratified_split import kfold_multilabel_split


def test_kfold_covers_every_record_exactly_once():
    label_sets = [{"A"}, {"A", "B"}, {"B"}, {"A"}, {"B"}, {"A", "B"}, {"A"}, {"C"}]
    folds = kfold_multilabel_split(label_sets, k=4, seed=0)

    seen: list[int] = []
    for f in folds:
        seen.extend(f.val_indices)
    assert sorted(seen) == list(range(len(label_sets)))


def test_kfold_train_and_val_disjoint():
    label_sets = [{"A"}, {"B"}, {"A", "B"}, {"A"}, {"B"}, {"A"}]
    folds = kfold_multilabel_split(label_sets, k=3, seed=0)
    for f in folds:
        assert set(f.train_indices).isdisjoint(set(f.val_indices))
        assert len(f.train_indices) + len(f.val_indices) == len(label_sets)


def test_kfold_is_deterministic_for_same_seed():
    labels = [{"X"}, {"Y"}, {"X", "Y"}, {"Y"}, {"X"}, {"Y"}]
    a = kfold_multilabel_split(labels, k=3, seed=7)
    b = kfold_multilabel_split(labels, k=3, seed=7)
    assert [f.val_indices for f in a] == [f.val_indices for f in b]


def test_kfold_requires_valid_k():
    with pytest.raises(ValueError):
        kfold_multilabel_split([{"A"}], k=1)
    with pytest.raises(ValueError):
        kfold_multilabel_split([{"A"}, {"B"}], k=5)
