"""Tests for ``libs.training_ext.corpus_balancer``.

Covers the four guards the balancer is responsible for:
  - text dedupe (collapse exact-duplicate sentence records)
  - per-source surface dedupe (kill 100x duplicate (source, label, surface))
  - iterative source-share cap (no single source > max_source_share)
  - tier-1 label minimum (raise when safety-critical labels under-represented)

Plus determinism: re-running with the same seed gives identical output.
"""

from __future__ import annotations

import os
import unittest
from collections import Counter
from unittest.mock import patch

from libs.training_ext.corpus_balancer import (
    BalanceConfig,
    TierOneLabelStarvationError,
    balance_corpus,
)


def _record(
    label_id: str,
    text: str,
    source: str,
    entities: list[dict],
) -> dict:
    return {
        "label_id": label_id,
        "text": text,
        "source": source,
        "entities": entities,
    }


def _ent(surface: str, label: str, start: int = 0, end: int | None = None) -> dict:
    return {
        "text": surface,
        "label": label,
        "start": start,
        "end": end if end is not None else len(surface),
        "assertion": "present",
    }


_TIER1 = frozenset({"DISORDER", "FINDING", "MEDICINAL_PRODUCT", "PROCEDURE"})


def _balanced_corpus_with_tier1(records: list[dict]) -> list[dict]:
    """Add enough tier-1 records so the balancer never aborts during dedup tests."""

    seeded: list[dict] = list(records)
    for label in _TIER1:
        for i in range(35):
            surface = f"{label.lower()}_filler_{i}"
            seeded.append(
                _record(
                    label_id=f"GL-{label}-{i:03d}",
                    text=f"Filler text {label} {i}",
                    source="manual_gold_editor",
                    entities=[_ent(surface, label)],
                )
            )
    return seeded


class TestTextDedupe(unittest.TestCase):
    """Records sharing the exact same ``text`` collapse to ``max_records_per_text``."""

    def test_duplicate_text_records_collapse(self):
        dup = [
            _record(
                "GL-001", "Patient has diabetes", "lab_coder_v1",
                [_ent("diabetes", "DISORDER")],
            ),
            _record(
                "GL-002", "Patient has diabetes", "lab_coder_v1",
                [_ent("diabetes", "DISORDER")],
            ),
        ]
        records = _balanced_corpus_with_tier1(dup)
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
        )
        out, report = balance_corpus(records, cfg)
        diabetes_records = [
            r for r in out if r["text"] == "Patient has diabetes"
        ]
        self.assertEqual(len(diabetes_records), 1)
        self.assertEqual(report.text_dedupe_dropped, 1)

    def test_unique_texts_pass_through(self):
        unique = [
            _record(
                "GL-001", "Patient has diabetes", "manual_gold_editor",
                [_ent("diabetes", "DISORDER")],
            ),
            _record(
                "GL-002", "Patient has hypertension", "manual_gold_editor",
                [_ent("hypertension", "DISORDER")],
            ),
        ]
        records = _balanced_corpus_with_tier1(unique)
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
        )
        out, report = balance_corpus(records, cfg)
        self.assertEqual(report.text_dedupe_dropped, 0)
        self.assertEqual(len(out), len(records))


class TestSurfaceDedupePerSource(unittest.TestCase):
    """Same (source, label, surface) capped to N copies."""

    def test_surface_capped_per_source(self):
        repeated = [
            _record(
                f"GL-{i:03d}",
                f"Sentence {i} containing Serum total protein level marker",
                "lab_coder_v1",
                [_ent("Serum total protein level", "PROCEDURE")],
            )
            for i in range(10)
        ]
        records = _balanced_corpus_with_tier1(repeated)
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=3,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
        )
        out, report = balance_corpus(records, cfg)
        kept_surface = sum(
            1
            for r in out
            for ent in r["entities"]
            if str(ent.get("text", "")).strip().lower()
            == "serum total protein level"
            and r["source"] == "lab_coder_v1"
        )
        self.assertEqual(kept_surface, 3)
        self.assertEqual(report.surface_dedupe_dropped, 7)

    def test_surface_cap_independent_per_source(self):
        same_surface_two_sources = [
            _record(
                f"GL-A-{i}",
                f"a_{i} Serum total protein level data",
                "lab_coder_v1",
                [_ent("Serum total protein level", "PROCEDURE")],
            )
            for i in range(5)
        ] + [
            _record(
                f"GL-B-{i}",
                f"b_{i} Serum total protein level data",
                "manual_gold_editor",
                [_ent("Serum total protein level", "PROCEDURE")],
            )
            for i in range(5)
        ]
        records = _balanced_corpus_with_tier1(same_surface_two_sources)
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=2,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
        )
        out, _ = balance_corpus(records, cfg)
        per_source = Counter(
            r["source"]
            for r in out
            for ent in r["entities"]
            if str(ent.get("text", "")).strip().lower()
            == "serum total protein level"
        )
        self.assertEqual(per_source["lab_coder_v1"], 2)
        self.assertEqual(per_source["manual_gold_editor"], 2)


class TestIterativeSourceCap(unittest.TestCase):
    """No source can exceed ``max_source_share`` of the post-balanced corpus."""

    def test_dominant_source_capped(self):
        # 3 sources so max_share=0.40 is mathematically feasible
        # (the lower bound is 1/N = 0.33).
        dominant = [
            _record(
                f"GL-D-{i}",
                f"unique_text_dominant_{i}",
                "lab_coder_v1",
                [_ent(f"surface_{i}", "PROCEDURE")],
            )
            for i in range(80)
        ]
        minor_a = [
            _record(
                f"GL-MA-{i}",
                f"unique_text_minor_a_{i}",
                "manual_gold_editor",
                [_ent(f"surface_a_{i}", "FINDING")],
            )
            for i in range(20)
        ]
        minor_b = [
            _record(
                f"GL-MB-{i}",
                f"unique_text_minor_b_{i}",
                "synthetic_seed",
                [_ent(f"surface_b_{i}", "DISORDER")],
            )
            for i in range(20)
        ]
        cfg = BalanceConfig(
            max_source_share=0.40,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=frozenset(),
        )
        out, report = balance_corpus(dominant + minor_a + minor_b, cfg)
        post_counts = Counter(r["source"] for r in out)
        total = sum(post_counts.values())
        for source, count in post_counts.items():
            with self.subTest(source=source):
                self.assertLessEqual(
                    count / total,
                    cfg.max_source_share + 1e-6,
                    msg=f"{source} share={count / total:.3f}",
                )
        actions = [a["source"] for a in report.source_cap_actions]
        self.assertIn("lab_coder_v1", actions)

    def test_infeasible_max_share_clamped_with_warning(self):
        # Two sources can never both be <= 0.40 share -- the lower bound is 0.5.
        records = [
            _record(
                f"GL-A-{i}", f"text_a_{i}", "manual_gold_editor",
                [_ent(f"a_{i}", "DISORDER")],
            )
            for i in range(40)
        ] + [
            _record(
                f"GL-B-{i}", f"text_b_{i}", "lab_coder_v1",
                [_ent(f"b_{i}", "PROCEDURE")],
            )
            for i in range(80)
        ]
        cfg = BalanceConfig(
            max_source_share=0.40,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=frozenset(),
        )
        out, report = balance_corpus(records, cfg)
        self.assertTrue(
            any("infeasible" in w.lower() for w in report.warnings),
            msg=f"warnings={report.warnings}",
        )
        # After clamping to 1/N + eps the corpus is balanced.
        post_counts = Counter(r["source"] for r in out)
        total = sum(post_counts.values())
        for source, count in post_counts.items():
            with self.subTest(source=source):
                self.assertLessEqual(count / total, 0.5 + 1e-6)

    def test_balanced_corpus_no_capping(self):
        # No tier-1 enforcement (min_per_label=0) so we can keep the source
        # mix exactly even and verify the cap stays out of the way.
        even = [
            _record(
                f"GL-A-{i}", f"text_a_{i}", "manual_gold_editor",
                [_ent(f"a_{i}", "DISORDER")],
            )
            for i in range(40)
        ] + [
            _record(
                f"GL-B-{i}", f"text_b_{i}", "lab_coder_v1",
                [_ent(f"b_{i}", "PROCEDURE")],
            )
            for i in range(40)
        ]
        cfg = BalanceConfig(
            max_source_share=0.60,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=frozenset(),
        )
        out, report = balance_corpus(even, cfg)
        self.assertEqual(report.source_cap_dropped, 0)
        self.assertEqual(report.source_cap_actions, [])
        self.assertEqual(len(out), len(even))


class TestTierOneStarvation(unittest.TestCase):
    """Tier-1 labels under the minimum abort the export."""

    def test_missing_tier1_label_aborts(self):
        records = [
            _record(
                f"GL-{i}", f"text_{i}", "manual_gold_editor",
                [_ent(f"surf_{i}", "DISORDER")],
            )
            for i in range(50)
        ]
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=30,
            tier1_labels=frozenset({"DISORDER", "FINDING", "PROCEDURE"}),
        )
        with self.assertRaises(TierOneLabelStarvationError) as ctx:
            balance_corpus(records, cfg)
        message = str(ctx.exception)
        self.assertIn("FINDING", message)
        self.assertIn("PROCEDURE", message)
        self.assertNotIn("DISORDER:", message)

    def test_under_min_tier1_aborts_with_count(self):
        records = (
            [
                _record(
                    f"GL-D-{i}", f"text_d_{i}", "manual_gold_editor",
                    [_ent(f"d_{i}", "DISORDER")],
                )
                for i in range(40)
            ]
            + [
                _record(
                    f"GL-F-{i}", f"text_f_{i}", "manual_gold_editor",
                    [_ent(f"f_{i}", "FINDING")],
                )
                for i in range(5)
            ]
        )
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=30,
            tier1_labels=frozenset({"DISORDER", "FINDING"}),
        )
        with self.assertRaises(TierOneLabelStarvationError) as ctx:
            balance_corpus(records, cfg)
        self.assertIn("FINDING: 5 < 30", str(ctx.exception))

    def test_other_labels_under_min_only_warn(self):
        records = (
            [
                _record(
                    f"GL-D-{i}", f"text_d_{i}", "manual_gold_editor",
                    [_ent(f"d_{i}", "DISORDER")],
                )
                for i in range(40)
            ]
            + [
                _record(
                    f"GL-Q-{i}", f"text_q_{i}", "manual_gold_editor",
                    [_ent(f"q_{i}", "QUALIFIER")],
                )
                for i in range(2)
            ]
        )
        cfg = BalanceConfig(
            max_source_share=0.99,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=30,
            tier1_labels=frozenset({"DISORDER"}),
        )
        out, report = balance_corpus(records, cfg)
        self.assertEqual(len(out), 42)
        self.assertEqual(report.tier1_under_min, [])
        self.assertTrue(any("QUALIFIER" in entry for entry in report.other_under_min))


class TestDeterminism(unittest.TestCase):
    """Same input + same seed -> bit-identical kept records."""

    def _build_dataset(self) -> list[dict]:
        many = [
            _record(
                f"GL-D-{i}",
                f"text_d_{i}",
                "lab_coder_v1",
                [_ent(f"surf_d_{i}", "PROCEDURE")],
            )
            for i in range(60)
        ]
        few = [
            _record(
                f"GL-M-{i}",
                f"text_m_{i}",
                "manual_gold_editor",
                [_ent(f"surf_m_{i}", "FINDING")],
            )
            for i in range(20)
        ]
        return _balanced_corpus_with_tier1(many + few)

    def test_same_seed_produces_same_kept_records(self):
        records = self._build_dataset()
        cfg = BalanceConfig(
            max_source_share=0.40,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
            seed=2026,
        )
        out_a, _ = balance_corpus(records, cfg)
        out_b, _ = balance_corpus(records, cfg)
        ids_a = [r["label_id"] for r in out_a]
        ids_b = [r["label_id"] for r in out_b]
        self.assertEqual(ids_a, ids_b)

    def test_different_seed_can_change_membership(self):
        records = self._build_dataset()
        cfg_a = BalanceConfig(
            max_source_share=0.40,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
            seed=1,
        )
        cfg_b = BalanceConfig(
            max_source_share=0.40,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=_TIER1,
            seed=2,
        )
        out_a, _ = balance_corpus(records, cfg_a)
        out_b, _ = balance_corpus(records, cfg_b)
        self.assertEqual(len(out_a), len(out_b))
        self.assertNotEqual(
            [r["label_id"] for r in out_a],
            [r["label_id"] for r in out_b],
            msg="Different seeds should have re-rolled the down-sample",
        )


class TestEnvOverrides(unittest.TestCase):
    """``BalanceConfig.from_env`` honours the documented env vars."""

    def test_env_overrides_applied(self):
        with patch.dict(
            os.environ,
            {
                "TRAINING_CORPUS_MAX_SOURCE_SHARE": "0.25",
                "TRAINING_CORPUS_MAX_SURFACE_DUPES": "5",
                "TRAINING_CORPUS_MAX_RECORDS_PER_TEXT": "2",
                "TRAINING_CORPUS_MIN_PER_LABEL": "10",
                "TRAINING_CORPUS_TIER1_LABELS": "disorder,finding",
                "TRAINING_CORPUS_BALANCER_SEED": "7",
            },
            clear=False,
        ):
            cfg = BalanceConfig.from_env()
        self.assertEqual(cfg.max_source_share, 0.25)
        self.assertEqual(cfg.max_surface_dupes_per_source, 5)
        self.assertEqual(cfg.max_records_per_text, 2)
        self.assertEqual(cfg.min_per_label, 10)
        self.assertEqual(cfg.tier1_labels, frozenset({"DISORDER", "FINDING"}))
        self.assertEqual(cfg.seed, 7)

    def test_disable_flag_bypasses_balancer(self):
        records = [
            _record(
                f"GL-{i}", f"text_{i}", "lab_coder_v1",
                [_ent(f"s_{i}", "PROCEDURE")],
            )
            for i in range(50)
        ]
        cfg = BalanceConfig(
            max_source_share=0.10,
            max_surface_dupes_per_source=999,
            max_records_per_text=1,
            min_per_label=0,
            tier1_labels=frozenset(),
        )
        with patch.dict(
            os.environ,
            {"TRAINING_CORPUS_BALANCE_DISABLED": "true"},
            clear=False,
        ):
            out, report = balance_corpus(records, cfg)
        self.assertEqual(len(out), 50)
        self.assertTrue(
            any("BALANCE_DISABLED" in w for w in report.warnings),
            msg=f"warnings={report.warnings}",
        )


if __name__ == "__main__":
    unittest.main()
