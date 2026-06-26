"""Wave 5 tests for drift monitor, review queue, strided spans aggregator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from libs.training_ext.drift_monitor import (
    DriftRecord,
    DriftSink,
    summarise_predictions,
)
from libs.training_ext.review_queue import ReviewItem, ReviewQueue, should_enqueue
from libs.training_ext.strided_spans import aggregate_strided_spans


@dataclass
class _FakeFilteredSpan:
    label: str
    start_char: int
    end_char: int
    calibrated_score: float


def test_summarise_predictions_counts_and_averages():
    spans = [
        _FakeFilteredSpan("DISORDER", 0, 3, 0.9),
        _FakeFilteredSpan("DISORDER", 4, 6, 0.6),
        _FakeFilteredSpan("FINDING", 7, 11, 0.8),
    ]
    record = summarise_predictions("v1", spans, below_threshold_spans=2)
    assert record.total_spans == 3
    assert record.below_threshold_spans == 2
    assert record.per_label_counts == {"DISORDER": 2, "FINDING": 1}
    assert abs(record.per_label_confidence_mean["DISORDER"] - 0.75) < 1e-6
    assert abs(record.per_label_confidence_mean["FINDING"] - 0.8) < 1e-6


def test_drift_sink_appends_to_daily_file(tmp_path):
    sink = DriftSink(tmp_path)
    record = DriftRecord(model_version="v1", total_spans=1)
    sink.write(record)
    sink.write(record)
    files = list(tmp_path.glob("drift-*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        payload = json.loads(line)
        assert payload["model_version"] == "v1"


def test_review_queue_enqueue_writes_jsonl(tmp_path):
    queue = ReviewQueue(tmp_path)
    item = ReviewItem(
        model_version="v1",
        label="DISORDER",
        start_char=0,
        end_char=8,
        surface="diabetes",
        raw_score=0.55,
        calibrated_score=0.58,
    )
    wrote = queue.enqueue([item, item])
    assert wrote == 2


def test_should_enqueue_in_review_band():
    # below bound -> skip (too low-signal to review)
    assert not should_enqueue(0.2, threshold=0.8)
    # in band -> review
    assert should_enqueue(0.5, threshold=0.8)
    # above threshold -> kept as normal prediction, not for review
    assert not should_enqueue(0.85, threshold=0.8)


def test_aggregate_strided_spans_max_wins():
    rows = [
        (10, 20, "DISORDER", 0.4),
        (10, 20, "DISORDER", 0.9),  # winner
        (10, 20, "DISORDER", 0.5),
        (30, 50, "FINDING", 0.7),
    ]
    out = aggregate_strided_spans(rows)
    scores = {(s.start, s.end, s.label): s.score for s in out}
    assert scores[(10, 20, "DISORDER")] == 0.9
    assert scores[(30, 50, "FINDING")] == 0.7
    # Sorted highest first.
    assert out[0].score == 0.9


def test_aggregate_strided_spans_mean_reducer():
    rows = [
        (0, 5, "X", 0.2),
        (0, 5, "X", 0.8),
    ]
    out = aggregate_strided_spans(rows, reducer="mean")
    assert out[0].score == 0.5
