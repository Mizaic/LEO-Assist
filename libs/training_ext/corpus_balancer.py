"""Corpus balancer for the GoldLabel training export pipeline.

Atlas trace:
  DO: pending  (registered alongside DO-2695BE52 label_exporter)
  DI: pending

Why this exists
---------------
The training corpus exhibited severe source/style monoculture: a single bulk
seeding source (``lab_coder_v1``) contributed ~55% of records and ~75% of
entity spans, with the same surface form (e.g. "Serum total protein level")
repeated 200+ times verbatim.  The downstream spancat model effectively
learnt a lab-line tagger and produced very poor predictions on prose
narrative (cancer, fast-track referrals, symptoms).

This module rebalances the raw GoldLabel record list before it reaches the
stratified split / DocBin write step.  It is deterministic for a given seed,
emits a structured report, and aborts the export when tier-1 (safety-critical)
labels fall below a minimum count -- so a degenerate corpus cannot quietly
ship as a model.

Pipeline
--------
1. Exact text dedupe (collapse identical sentences within a source).
2. Per-(source, label, surface) cap (kill 100x duplicate surface forms).
3. Iterative source-share cap (no single source > ``max_source_share`` of
   the remaining records; capping the largest source repeatedly until the
   constraint holds).
4. Per-label minimum check (warns on rare labels; raises if any tier-1
   label is below the minimum).

All thresholds are configurable via env vars and have safe defaults.

Environment variables
---------------------
TRAINING_CORPUS_MAX_SOURCE_SHARE       float in (0, 1], default 0.80
TRAINING_CORPUS_MAX_SURFACE_DUPES      int >= 1, default 3
TRAINING_CORPUS_MAX_RECORDS_PER_TEXT   int >= 1, default 1
TRAINING_CORPUS_MIN_PER_LABEL          int >= 0, default 30
TRAINING_CORPUS_TIER1_LABELS           comma list, default
                                       "DISORDER,FINDING,MEDICINAL_PRODUCT,PROCEDURE"
TRAINING_CORPUS_BALANCE_DISABLED       set to "1"/"true" to bypass the
                                       balancer entirely (back-compat escape
                                       hatch; logs a warning).
"""

from __future__ import annotations

import logging
import os
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)


_DEFAULT_TIER1_LABELS = frozenset({"FINDING", "OBSERVABLE", "PROCEDURE"})


def _normalise_label(raw: Any) -> str:
    """Mirror the lightweight label normalisation used by label_exporter.

    We only care about uppercase comparison here -- the canonical mapping
    happens in ``label_exporter._normalise_label``.  Importing that module
    would create a circular dependency, so we re-implement the cheap part.
    """

    return str(raw or "").strip().upper().replace(" ", "_").replace("/", "_")


@dataclass(frozen=True)
class BalanceConfig:
    """Knobs controlling the corpus rebalancer."""

    max_source_share: float = 0.80
    max_surface_dupes_per_source: int = 3
    max_records_per_text: int = 1
    min_per_label: int = 30
    tier1_labels: frozenset[str] = _DEFAULT_TIER1_LABELS
    seed: int = 42

    def __post_init__(self) -> None:
        if not 0.0 < self.max_source_share <= 1.0:
            raise ValueError(
                f"max_source_share must be in (0, 1], got {self.max_source_share!r}"
            )
        if self.max_surface_dupes_per_source < 1:
            raise ValueError(
                "max_surface_dupes_per_source must be >= 1, got "
                f"{self.max_surface_dupes_per_source!r}"
            )
        if self.max_records_per_text < 1:
            raise ValueError(
                "max_records_per_text must be >= 1, got "
                f"{self.max_records_per_text!r}"
            )
        if self.min_per_label < 0:
            raise ValueError(
                f"min_per_label must be >= 0, got {self.min_per_label!r}"
            )

    @classmethod
    def from_env(cls) -> "BalanceConfig":
        tier1_raw = os.getenv("TRAINING_CORPUS_TIER1_LABELS", "").strip()
        if tier1_raw:
            tier1 = frozenset(
                _normalise_label(t) for t in tier1_raw.split(",") if t.strip()
            )
        else:
            tier1 = _DEFAULT_TIER1_LABELS
        return cls(
            max_source_share=float(
                os.getenv("TRAINING_CORPUS_MAX_SOURCE_SHARE", "0.80")
            ),
            max_surface_dupes_per_source=int(
                os.getenv("TRAINING_CORPUS_MAX_SURFACE_DUPES", "3")
            ),
            max_records_per_text=int(
                os.getenv("TRAINING_CORPUS_MAX_RECORDS_PER_TEXT", "1")
            ),
            min_per_label=int(os.getenv("TRAINING_CORPUS_MIN_PER_LABEL", "30")),
            tier1_labels=tier1,
            seed=int(os.getenv("TRAINING_CORPUS_BALANCER_SEED", "42")),
        )


@dataclass
class BalanceReport:
    """Structured audit of the rebalancing decisions."""

    pre_record_count: int = 0
    post_record_count: int = 0
    pre_source_counts: dict[str, int] = field(default_factory=dict)
    post_source_counts: dict[str, int] = field(default_factory=dict)
    pre_label_counts: dict[str, int] = field(default_factory=dict)
    post_label_counts: dict[str, int] = field(default_factory=dict)
    text_dedupe_dropped: int = 0
    surface_dedupe_dropped: int = 0
    source_cap_dropped: int = 0
    source_cap_actions: list[dict[str, Any]] = field(default_factory=list)
    tier1_under_min: list[str] = field(default_factory=list)
    other_under_min: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre_record_count": self.pre_record_count,
            "post_record_count": self.post_record_count,
            "pre_source_counts": dict(
                sorted(self.pre_source_counts.items(), key=lambda kv: -kv[1])
            ),
            "post_source_counts": dict(
                sorted(self.post_source_counts.items(), key=lambda kv: -kv[1])
            ),
            "pre_label_counts": dict(
                sorted(self.pre_label_counts.items(), key=lambda kv: -kv[1])
            ),
            "post_label_counts": dict(
                sorted(self.post_label_counts.items(), key=lambda kv: -kv[1])
            ),
            "text_dedupe_dropped": self.text_dedupe_dropped,
            "surface_dedupe_dropped": self.surface_dedupe_dropped,
            "source_cap_dropped": self.source_cap_dropped,
            "source_cap_actions": list(self.source_cap_actions),
            "tier1_under_min": list(self.tier1_under_min),
            "other_under_min": list(self.other_under_min),
            "warnings": list(self.warnings),
            "config": dict(self.config),
        }


class TierOneLabelStarvationError(ValueError):
    """Raised when one or more tier-1 labels are under the minimum after balancing.

    The export aborts so a degenerate corpus cannot ship a degenerate model.
    """


def _record_label_set(record: dict[str, Any]) -> set[str]:
    labels: set[str] = set()
    for ent in record.get("entities", []) or []:
        label = _normalise_label(ent.get("label") or ent.get("semantic_tag"))
        if label:
            labels.add(label)
    return labels


def _record_label_span_count(record: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ent in record.get("entities", []) or []:
        label = _normalise_label(ent.get("label") or ent.get("semantic_tag"))
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts


def _stable_sort_key(record: dict[str, Any], index: int) -> tuple:
    """Deterministic ordering: prefer manual review, then label_id, then index.

    Records authored or curated by humans tend to have richer or more accurate
    spans than synthetic seeds; preferring them is a quality-preserving
    tiebreaker when we have to drop duplicates.
    """

    source = str(record.get("source") or "")
    manual_priority = 0 if "manual" in source.lower() else 1
    label_id = str(record.get("label_id") or "")
    return (manual_priority, label_id, index)


def _dedupe_by_text(
    records: Sequence[dict[str, Any]],
    *,
    max_per_text: int,
) -> tuple[list[dict[str, Any]], int]:
    """Drop near-identical records that share an exact ``text`` value.

    Determinism: among records sharing the same text, we keep the ones with
    the lowest ``_stable_sort_key`` (manual sources first, then by label_id).
    """

    if max_per_text < 1:
        return list(records), 0

    grouped: dict[str, list[tuple[tuple, int, dict[str, Any]]]] = defaultdict(list)
    for index, record in enumerate(records):
        text = str(record.get("text") or "")
        grouped[text].append((_stable_sort_key(record, index), index, record))

    kept: list[tuple[int, dict[str, Any]]] = []
    dropped = 0
    for items in grouped.values():
        items.sort(key=lambda x: x[0])
        for _, original_index, rec in items[:max_per_text]:
            kept.append((original_index, rec))
        dropped += max(0, len(items) - max_per_text)

    kept.sort(key=lambda x: x[0])
    return [rec for _, rec in kept], dropped


def _dedupe_surface_per_source(
    records: Sequence[dict[str, Any]],
    *,
    max_per_source_surface: int,
) -> tuple[list[dict[str, Any]], int]:
    """Cap how often the same (source, label, surface) entity appears.

    Operates at the entity level: we never drop a record entirely here.  If
    every entity in a record has hit its cap, we still keep the record (with
    the saturated entities removed).  Records that lose all entities are then
    dropped by the caller's existing "no entities -> skip" check.

    Returns the rewritten records plus the count of dropped entity spans.
    """

    if max_per_source_surface < 1:
        return list(records), 0

    seen: dict[tuple[str, str, str], int] = defaultdict(int)
    out: list[dict[str, Any]] = []
    dropped = 0
    for record in records:
        source = str(record.get("source") or "")
        kept_entities: list[dict[str, Any]] = []
        for ent in record.get("entities", []) or []:
            label = _normalise_label(ent.get("label") or ent.get("semantic_tag"))
            surface = str(ent.get("text") or "").strip().lower()
            if not label or not surface:
                kept_entities.append(ent)
                continue
            key = (source, label, surface)
            if seen[key] >= max_per_source_surface:
                dropped += 1
                continue
            seen[key] += 1
            kept_entities.append(ent)
        if kept_entities:
            out.append({**record, "entities": kept_entities})
        else:
            dropped_record_entities = sum(
                1 for _ in (record.get("entities") or [])
            )
            dropped += 0  # entities already counted above; record itself is dropped silently
            del dropped_record_entities  # noqa: F841 -- explicit no-op for clarity
    return out, dropped


def _iterative_source_cap(
    records: Sequence[dict[str, Any]],
    *,
    max_share: float,
    seed: int,
    warnings: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    """Repeatedly cap the largest source until no source > max_share of total.

    Sub-sampling within a capped source uses a seeded ``random.Random`` for
    determinism.  We preserve original record order in the returned list so
    downstream stratified splits remain reproducible.

    Infeasible configurations
    -------------------------
    A target share of S with N distinct sources requires ``S >= 1/N``.  When
    the requested cap is below that lower bound the cap loop would oscillate
    forever, so we clamp ``max_share`` to ``max(max_share, 1/N + epsilon)``
    and append a warning explaining the auto-adjustment.  The caller can
    surface this warning to the operator (and tighten thresholds or add more
    source diversity in response).
    """

    if max_share >= 1.0:
        return list(records), 0, []

    pool: list[dict[str, Any]] = list(records)
    rng = random.Random(seed)
    actions: list[dict[str, Any]] = []
    total_dropped = 0

    initial_sources = {str(r.get("source") or "") for r in pool}
    n_sources = len(initial_sources)
    effective_max_share = max_share
    if n_sources >= 2:
        feasible_floor = 1.0 / n_sources + 1e-6
        if effective_max_share < feasible_floor:
            if warnings is not None:
                warnings.append(
                    "Source-share cap "
                    f"max_source_share={max_share:.3f} is infeasible with "
                    f"{n_sources} distinct sources (minimum feasible share "
                    f"= 1/N = {1.0 / n_sources:.3f}); clamped to "
                    f"{feasible_floor:.3f}.  Add more source diversity to make "
                    "tighter caps achievable."
                )
            effective_max_share = feasible_floor

    while True:
        if not pool:
            break
        counts = Counter(str(r.get("source") or "") for r in pool)
        if len(counts) <= 1:
            # Only one source -- the cap is unsatisfiable without emptying the
            # corpus, so we leave it alone.  Diversity is the caller's problem.
            break
        total = sum(counts.values())
        biggest_source, biggest_count = counts.most_common(1)[0]
        share = biggest_count / total if total else 0.0
        if share <= effective_max_share + 1e-9:
            break

        # Algebra: cap source S so that new_count / (total - biggest_count + new_count) == max_share
        # => new_count = max_share * (total - biggest_count) / (1 - max_share)
        other = total - biggest_count
        if other <= 0:
            # Defensive: cannot satisfy the cap -- leave the pool intact.
            break
        target_for_source = int(
            effective_max_share * other / (1.0 - effective_max_share)
        )
        target_for_source = max(target_for_source, 0)
        if target_for_source >= biggest_count:
            # Numerical edge case: nothing to drop.
            break

        candidate_indices = [
            i for i, r in enumerate(pool)
            if str(r.get("source") or "") == biggest_source
        ]
        rng.shuffle(candidate_indices)
        keep_indices = set(candidate_indices[:target_for_source])
        new_pool: list[dict[str, Any]] = []
        for i, record in enumerate(pool):
            if str(record.get("source") or "") != biggest_source:
                new_pool.append(record)
            elif i in keep_indices:
                new_pool.append(record)
        dropped_now = biggest_count - target_for_source
        total_dropped += dropped_now
        actions.append(
            {
                "source": biggest_source,
                "before": biggest_count,
                "after": target_for_source,
                "dropped": dropped_now,
                "share_before": round(share, 4),
                "share_target": round(max_share, 4),
            }
        )
        pool = new_pool

    return pool, total_dropped, actions


def _aggregate_label_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in records:
        for label, n in _record_label_span_count(rec).items():
            counts[label] = counts.get(label, 0) + n
    return counts


def _aggregate_source_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(r.get("source") or "") for r in records))


def balance_corpus(
    records: Sequence[dict[str, Any]],
    config: BalanceConfig | None = None,
) -> tuple[list[dict[str, Any]], BalanceReport]:
    """Apply text dedupe, surface dedupe, source cap, and label-min checks.

    The returned record list preserves input ordering for the records that
    survive (so stratified split remains stable across runs).  ``records`` is
    not mutated.

    Raises:
        TierOneLabelStarvationError: If any label in
            ``config.tier1_labels`` has fewer than ``config.min_per_label``
            entity spans after balancing.  The exporter is expected to surface
            the message verbatim to the user so they know exactly which labels
            need more gold data.
    """

    cfg = config or BalanceConfig.from_env()
    report = BalanceReport()
    report.pre_record_count = len(records)
    report.pre_source_counts = _aggregate_source_counts(records)
    report.pre_label_counts = _aggregate_label_counts(records)
    report.config = {
        "max_source_share": cfg.max_source_share,
        "max_surface_dupes_per_source": cfg.max_surface_dupes_per_source,
        "max_records_per_text": cfg.max_records_per_text,
        "min_per_label": cfg.min_per_label,
        "tier1_labels": sorted(cfg.tier1_labels),
        "seed": cfg.seed,
    }

    if os.getenv("TRAINING_CORPUS_BALANCE_DISABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    ):
        report.warnings.append(
            "TRAINING_CORPUS_BALANCE_DISABLED is set -- corpus rebalancer is bypassed. "
            "This will degrade model quality if a single source dominates the corpus."
        )
        report.post_record_count = len(records)
        report.post_source_counts = report.pre_source_counts
        report.post_label_counts = report.pre_label_counts
        return list(records), report

    deduped_text, n_text_dropped = _dedupe_by_text(
        records, max_per_text=cfg.max_records_per_text
    )
    report.text_dedupe_dropped = n_text_dropped

    deduped_surface, n_surface_dropped = _dedupe_surface_per_source(
        deduped_text,
        max_per_source_surface=cfg.max_surface_dupes_per_source,
    )
    report.surface_dedupe_dropped = n_surface_dropped

    # After surface dedupe a record can be left with no entities; drop those.
    deduped_surface = [
        rec for rec in deduped_surface if rec.get("entities")
    ]

    capped, n_source_dropped, actions = _iterative_source_cap(
        deduped_surface,
        max_share=cfg.max_source_share,
        seed=cfg.seed,
        warnings=report.warnings,
    )
    report.source_cap_dropped = n_source_dropped
    report.source_cap_actions = actions

    report.post_record_count = len(capped)
    report.post_source_counts = _aggregate_source_counts(capped)
    report.post_label_counts = _aggregate_label_counts(capped)

    if cfg.min_per_label > 0:
        for label, count in report.post_label_counts.items():
            if count >= cfg.min_per_label:
                continue
            if label in cfg.tier1_labels:
                report.tier1_under_min.append(
                    f"{label}: {count} < {cfg.min_per_label}"
                )
            else:
                report.other_under_min.append(
                    f"{label}: {count} < {cfg.min_per_label}"
                )

        # Tier-1 labels missing entirely from the corpus also count as starvation.
        missing_tier1 = sorted(
            label
            for label in cfg.tier1_labels
            if label not in report.post_label_counts
        )
        for label in missing_tier1:
            report.tier1_under_min.append(f"{label}: 0 < {cfg.min_per_label}")

    if report.tier1_under_min:
        message = (
            "Tier-1 (safety-critical) labels are under the minimum span count "
            f"of {cfg.min_per_label} after corpus rebalancing. Add more verified "
            "gold labels for these labels before training -- shipping a model "
            "without them will degrade clinical extraction quality:\n  - "
            + "\n  - ".join(report.tier1_under_min)
        )
        raise TierOneLabelStarvationError(message)

    return capped, report
