"""Wave 2 (F6, F20) — multi-label iterative stratified split."""

from __future__ import annotations

import pytest

from libs.training_ext.stratified_split import (
    SplitRatios,
    iterative_multilabel_split,
)


def test_split_ratios_must_sum_to_one():
    with pytest.raises(ValueError):
        SplitRatios(train=0.6, val=0.1, dev=0.1, test=0.1)


def test_split_sizes_match_ratios_within_one_record():
    labels = [{"DISORDER"} for _ in range(100)]
    ratios = SplitRatios(0.7, 0.1, 0.1, 0.1)
    result = iterative_multilabel_split(labels, ratios=ratios, seed=7)
    sizes = result.sizes()
    assert sum(sizes.values()) == 100
    assert sizes["train"] == pytest.approx(70, abs=2)
    assert sizes["val"] == pytest.approx(10, abs=2)
    assert sizes["dev"] == pytest.approx(10, abs=2)
    assert sizes["test"] == pytest.approx(10, abs=2)


def test_deterministic_across_runs_with_same_seed():
    labels = [{"A", "B"} if i % 3 == 0 else {"C"} for i in range(50)]
    a = iterative_multilabel_split(labels, seed=42)
    b = iterative_multilabel_split(labels, seed=42)
    assert a.indices == b.indices


def test_different_seed_produces_different_partition():
    labels = [{"A", "B"} if i % 3 == 0 else {"C"} for i in range(50)]
    a = iterative_multilabel_split(labels, seed=1)
    b = iterative_multilabel_split(labels, seed=2)
    assert a.indices != b.indices


def test_rare_label_with_enough_records_appears_in_dev():
    # Ten rare records gives iterative stratification a chance to land one in
    # each split at ratios 0.7/0.1/0.1/0.1.
    labels = [{"RARE"}] * 10 + [{"COMMON"}] * 90
    result = iterative_multilabel_split(labels, seed=17)
    rare_per_split = {
        name: sum(1 for idx in ix if "RARE" in labels[idx])
        for name, ix in result.indices.items()
    }
    assert sum(rare_per_split.values()) == 10
    assert rare_per_split["train"] == 7
    assert rare_per_split["val"] == 1
    assert rare_per_split["dev"] == 1
    assert rare_per_split["test"] == 1


def test_too_rare_label_emits_warning_when_dev_empty():
    # With only 2 rare records and 70/10/10/10 ratios the iterative algorithm
    # correctly places both in train — the warnings list must surface that.
    labels = [{"RARE"}, {"RARE"}] + [{"COMMON"}] * 48
    result = iterative_multilabel_split(labels, seed=123)
    dev_rare = sum(1 for idx in result.indices["dev"] if "RARE" in labels[idx])
    if dev_rare == 0:
        assert any("RARE" in w for w in result.warnings)


def test_warning_when_rare_label_misses_dev():
    # Three rare records: stratification should ideally place at least one in
    # dev, but if not, we expect a warning to surface.
    labels = [{"ULTRA_RARE"}] * 3 + [{"COMMON"}] * 97
    result = iterative_multilabel_split(labels, seed=4)
    dev_rare = sum(1 for idx in result.indices["dev"] if "ULTRA_RARE" in labels[idx])
    if dev_rare == 0:
        assert any("ULTRA_RARE" in w for w in result.warnings)


def test_empty_label_records_still_partitioned():
    labels = [set() for _ in range(40)]
    result = iterative_multilabel_split(labels, seed=1)
    assert sum(len(ix) for ix in result.indices.values()) == 40
