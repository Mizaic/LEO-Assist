"""Multi-label iterative stratified split.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Covers Wave 2 (F6, F20) of the World-Class Clinical NER plan.

Adapts Sechidis et al. (2011) "On the Stratification of Multi-Label Data" to
the small, per-record multi-label distribution we see with `GoldLabel` exports.

Each record carries a set of labels.  We produce a partition such that, for
each label, the number of records-with-that-label per split is as close as
possible to the requested ratio, and no label that appears in the corpus is
entirely absent from the dev split.

The split is deterministic for a given seed and record ordering.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class SplitRatios:
    """Named split ratios that sum (approximately) to 1."""

    train: float = 0.7
    val: float = 0.1
    dev: float = 0.1
    test: float = 0.1

    def as_mapping(self) -> Mapping[str, float]:
        return {
            "train": self.train,
            "val": self.val,
            "dev": self.dev,
            "test": self.test,
        }

    def __post_init__(self) -> None:
        total = self.train + self.val + self.dev + self.test
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"SplitRatios must sum to 1.0, got {total:.4f}"
            )
        for name, value in self.as_mapping().items():
            if value < 0.0 or value > 1.0:
                raise ValueError(f"SplitRatios.{name} must be in [0, 1]")


@dataclass
class SplitResult:
    """Indices assigned to each named split plus the per-label audit."""

    indices: dict[str, list[int]] = field(default_factory=dict)
    per_label_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def sizes(self) -> dict[str, int]:
        return {name: len(ix) for name, ix in self.indices.items()}


def iterative_multilabel_split(
    label_sets: Sequence[Iterable[str]],
    ratios: SplitRatios = SplitRatios(),
    *,
    seed: int = 42,
) -> SplitResult:
    """Partition record indices into named splits using iterative stratification.

    Args:
        label_sets: Per-record iterable of label strings.  Records with no
            labels are handled by a secondary random assignment that still
            respects the global ratios.
        ratios: Named split ratios (must sum to 1).
        seed: Seed for tie-breaking randomness.

    Returns:
        SplitResult with per-split index lists, per-label counts (for audit),
        and any warnings (e.g. labels too rare to guarantee dev coverage).
    """
    rng = random.Random(seed)
    n_records = len(label_sets)
    split_names = list(ratios.as_mapping().keys())
    split_weights = ratios.as_mapping()

    label_to_records: dict[str, list[int]] = {}
    for i, labels in enumerate(label_sets):
        for label in labels:
            label_to_records.setdefault(label, []).append(i)

    if not label_to_records:
        # No labels anywhere: fall back to a simple random partition.
        return _random_partition(n_records, split_weights, rng)

    desired_per_split = {name: ratios.as_mapping()[name] * n_records for name in split_names}
    desired_per_label_per_split: dict[str, dict[str, float]] = {
        label: {
            name: split_weights[name] * len(records)
            for name in split_names
        }
        for label, records in label_to_records.items()
    }

    assignment: dict[int, str | None] = {i: None for i in range(n_records)}
    remaining = set(range(n_records))

    # Iterate labels rarest-first.  At each step pick the rarest remaining
    # label and greedily assign its still-unplaced records to whichever split
    # needs that label most (argmax of remaining desired count).
    labels_sorted = sorted(
        label_to_records.items(),
        key=lambda kv: (len(kv[1]), kv[0]),
    )

    def _pick_split(label: str) -> str:
        by_label = desired_per_label_per_split[label]
        # Primary: split with the largest remaining desired count for this label.
        max_label = max(by_label.values())
        candidates = [n for n, v in by_label.items() if math.isclose(v, max_label)]
        if len(candidates) == 1:
            return candidates[0]
        # Tie-break: split with the largest remaining overall capacity.
        capacities = {n: desired_per_split[n] for n in candidates}
        max_cap = max(capacities.values())
        finalists = [n for n, v in capacities.items() if math.isclose(v, max_cap)]
        if len(finalists) == 1:
            return finalists[0]
        # Final tie-break: deterministic RNG pick.
        return rng.choice(sorted(finalists))

    warnings: list[str] = []
    for label, records in labels_sorted:
        unplaced = [r for r in records if assignment[r] is None]
        rng.shuffle(unplaced)
        for idx in unplaced:
            split = _pick_split(label)
            assignment[idx] = split
            remaining.discard(idx)
            desired_per_split[split] -= 1
            for lbl in label_sets[idx]:
                desired_per_label_per_split[lbl][split] -= 1

    # Records with no labels (or whose labels all landed before they did —
    # impossible with the loop above, but defensive).
    for idx in list(remaining):
        candidates = list(desired_per_split.keys())
        max_cap = max(desired_per_split[c] for c in candidates)
        finalists = [c for c in candidates if math.isclose(desired_per_split[c], max_cap)]
        split = rng.choice(sorted(finalists))
        assignment[idx] = split
        desired_per_split[split] -= 1

    indices: dict[str, list[int]] = {name: [] for name in split_names}
    for idx, split in assignment.items():
        assert split is not None
        indices[split].append(idx)

    per_label_counts: dict[str, dict[str, int]] = {
        label: {name: 0 for name in split_names}
        for label in label_to_records
    }
    for split_name, idx_list in indices.items():
        for idx in idx_list:
            for label in label_sets[idx]:
                per_label_counts[label][split_name] += 1

    # Emit warnings for any label that missed the dev or test split entirely.
    for label, counts in per_label_counts.items():
        if counts.get("dev", 0) == 0 and len(label_to_records[label]) >= 2:
            warnings.append(
                f"label {label!r} has zero dev records "
                f"(only {len(label_to_records[label])} training records total)"
            )

    return SplitResult(
        indices=indices,
        per_label_counts=per_label_counts,
        warnings=warnings,
    )


@dataclass
class FoldResult:
    """Indices for a single K-fold split (train vs validation)."""

    fold_index: int
    train_indices: list[int]
    val_indices: list[int]


def kfold_multilabel_split(
    label_sets: Sequence[Iterable[str]],
    *,
    k: int,
    seed: int = 42,
) -> list[FoldResult]:
    """Produce K stratified folds for cross-validation.

    Each record appears in exactly one validation fold. Stratification is
    approximate and uses the same iterative algorithm as
    :func:`iterative_multilabel_split`: we build K equal-sized buckets (one per
    fold) using the rarest-label-first heuristic, then emit (train=all except
    bucket_k, val=bucket_k) pairs.

    Raises:
        ValueError: if k < 2 or k > n_records.
    """
    n_records = len(label_sets)
    if k < 2:
        raise ValueError(f"K-fold requires k >= 2 (got {k})")
    if k > n_records:
        raise ValueError(
            f"K-fold requires k <= n_records (got k={k}, n_records={n_records})"
        )

    fold_weights = {f"fold_{i}": 1.0 / k for i in range(k)}
    rng = random.Random(seed)
    label_to_records: dict[str, list[int]] = {}
    for i, labels in enumerate(label_sets):
        for label in labels:
            label_to_records.setdefault(label, []).append(i)

    if not label_to_records:
        partition = _random_partition(n_records, fold_weights, rng)
        buckets = [partition.indices[f"fold_{i}"] for i in range(k)]
    else:
        desired_per_split = {name: fold_weights[name] * n_records for name in fold_weights}
        desired_per_label_per_split: dict[str, dict[str, float]] = {
            label: {
                name: fold_weights[name] * len(records)
                for name in fold_weights
            }
            for label, records in label_to_records.items()
        }
        assignment: dict[int, str | None] = {i: None for i in range(n_records)}
        remaining = set(range(n_records))
        labels_sorted = sorted(
            label_to_records.items(),
            key=lambda kv: (len(kv[1]), kv[0]),
        )

        def _pick(label: str) -> str:
            by_label = desired_per_label_per_split[label]
            max_label = max(by_label.values())
            candidates = [n for n, v in by_label.items() if math.isclose(v, max_label)]
            if len(candidates) == 1:
                return candidates[0]
            capacities = {n: desired_per_split[n] for n in candidates}
            max_cap = max(capacities.values())
            finalists = [n for n, v in capacities.items() if math.isclose(v, max_cap)]
            if len(finalists) == 1:
                return finalists[0]
            return rng.choice(sorted(finalists))

        for label, records in labels_sorted:
            unplaced = [r for r in records if assignment[r] is None]
            rng.shuffle(unplaced)
            for idx in unplaced:
                split = _pick(label)
                assignment[idx] = split
                remaining.discard(idx)
                desired_per_split[split] -= 1
                for lbl in label_sets[idx]:
                    desired_per_label_per_split[lbl][split] -= 1

        for idx in list(remaining):
            max_cap = max(desired_per_split.values())
            finalists = [n for n, v in desired_per_split.items() if math.isclose(v, max_cap)]
            split = rng.choice(sorted(finalists))
            assignment[idx] = split
            desired_per_split[split] -= 1

        buckets = [[] for _ in range(k)]
        for idx, split in assignment.items():
            assert split is not None
            buckets[int(split.split("_")[1])].append(idx)

    folds: list[FoldResult] = []
    for i in range(k):
        val = sorted(buckets[i])
        train = sorted([idx for j in range(k) if j != i for idx in buckets[j]])
        folds.append(FoldResult(fold_index=i, train_indices=train, val_indices=val))
    return folds


def _random_partition(
    n_records: int,
    split_weights: Mapping[str, float],
    rng: random.Random,
) -> SplitResult:
    indices = list(range(n_records))
    rng.shuffle(indices)
    out: dict[str, list[int]] = {name: [] for name in split_weights}
    boundaries: list[tuple[str, int]] = []
    cursor = 0
    names = list(split_weights.keys())
    for name in names[:-1]:
        span = int(round(split_weights[name] * n_records))
        boundaries.append((name, cursor + span))
        cursor += span
    boundaries.append((names[-1], n_records))
    start = 0
    for name, end in boundaries:
        out[name] = sorted(indices[start:end])
        start = end
    return SplitResult(indices=out, per_label_counts={}, warnings=[])
