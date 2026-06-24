"""Wave 5 tests for drift monitor, review queue, strided spans aggregator."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path

from libs.training_ext.drift_monitor import (
    CONFIDENCE_DROP_THRESHOLD,
    DriftAlert,
    DriftRecord,
    DriftSink,
    _baseline_means,
    _load_day_records,
    _weighted_label_means,
    check_confidence_drift,
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


# ---------------------------------------------------------------------------
# DriftAlert / check_confidence_drift tests
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 6, 11)


def _write_day(base: Path, day: datetime.date, records: list[dict]) -> None:
    path = base / f"drift-{day.isoformat()}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _record(label: str, confidence: float, count: int = 10) -> dict:
    return {
        "model_version": "v1",
        "timestamp": "2026-06-11T00:00:00Z",
        "total_spans": count,
        "below_threshold_spans": 0,
        "per_label_counts": {label: count},
        "per_label_confidence_mean": {label: confidence},
    }


def test_load_day_records_missing_file_returns_empty(tmp_path):
    assert _load_day_records(tmp_path, _TODAY) == []


def test_load_day_records_reads_jsonl(tmp_path):
    _write_day(tmp_path, _TODAY, [_record("DISORDER", 0.9)])
    records = _load_day_records(tmp_path, _TODAY)
    assert len(records) == 1
    assert records[0]["per_label_confidence_mean"]["DISORDER"] == 0.9


def test_load_day_records_skips_malformed_lines(tmp_path):
    path = tmp_path / f"drift-{_TODAY.isoformat()}.jsonl"
    path.write_text('{"valid": 1}\nnot-json\n{"valid": 2}\n', encoding="utf-8")
    records = _load_day_records(tmp_path, _TODAY)
    assert len(records) == 2


def test_weighted_label_means_single_record():
    records = [_record("DISORDER", 0.8, count=5)]
    means = _weighted_label_means(records)
    assert abs(means["DISORDER"] - 0.8) < 1e-9


def test_weighted_label_means_weights_by_count():
    # 10 spans at 0.9 and 10 spans at 0.7 => weighted mean 0.8
    records = [_record("DISORDER", 0.9, count=10), _record("DISORDER", 0.7, count=10)]
    means = _weighted_label_means(records)
    assert abs(means["DISORDER"] - 0.8) < 1e-9


def test_baseline_means_averages_days():
    daily = [{"DISORDER": 0.9}, {"DISORDER": 0.7}]
    result = _baseline_means(daily)
    assert abs(result["DISORDER"] - 0.8) < 1e-9


def test_check_confidence_drift_no_today_data_returns_empty(tmp_path):
    alerts = check_confidence_drift(tmp_path, today=_TODAY)
    assert alerts == []


def test_check_confidence_drift_no_baseline_returns_empty(tmp_path):
    _write_day(tmp_path, _TODAY, [_record("DISORDER", 0.8)])
    alerts = check_confidence_drift(tmp_path, today=_TODAY)
    assert alerts == []


def test_check_confidence_drift_no_alert_when_stable(tmp_path):
    for offset in range(1, 8):
        day = _TODAY - datetime.timedelta(days=offset)
        _write_day(tmp_path, day, [_record("DISORDER", 0.85)])
    _write_day(tmp_path, _TODAY, [_record("DISORDER", 0.84)])  # <10% drop
    alerts = check_confidence_drift(tmp_path, today=_TODAY)
    assert alerts == []


def test_check_confidence_drift_alert_on_drop_above_threshold(tmp_path):
    # baseline mean = 0.85; today = 0.70 => drop = 15/85 ~ 17.6% > 10%
    for offset in range(1, 8):
        day = _TODAY - datetime.timedelta(days=offset)
        _write_day(tmp_path, day, [_record("DISORDER", 0.85)])
    _write_day(tmp_path, _TODAY, [_record("DISORDER", 0.70)])
    alerts = check_confidence_drift(tmp_path, today=_TODAY)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.label == "DISORDER"
    assert alert.relative_drop > CONFIDENCE_DROP_THRESHOLD
    assert alert.today_mean < alert.baseline_mean


def test_check_confidence_drift_only_alerts_breaching_labels(tmp_path):
    # DISORDER drops; FINDING is stable
    for offset in range(1, 8):
        day = _TODAY - datetime.timedelta(days=offset)
        _write_day(
            tmp_path,
            day,
            [_record("DISORDER", 0.85), _record("FINDING", 0.80)],
        )
    disorder_today = _record("DISORDER", 0.70)
    finding_today = _record("FINDING", 0.79)
    _write_day(tmp_path, _TODAY, [disorder_today, finding_today])
    alerts = check_confidence_drift(tmp_path, today=_TODAY)
    labels = {a.label for a in alerts}
    assert "DISORDER" in labels
    assert "FINDING" not in labels


def test_check_confidence_drift_respects_custom_threshold(tmp_path):
    for offset in range(1, 8):
        day = _TODAY - datetime.timedelta(days=offset)
        _write_day(tmp_path, day, [_record("DISORDER", 0.85)])
    # ~5.9% drop -- below 10% default but above 5% custom threshold
    _write_day(tmp_path, _TODAY, [_record("DISORDER", 0.80)])
    assert check_confidence_drift(tmp_path, today=_TODAY) == []
    alerts = check_confidence_drift(tmp_path, today=_TODAY, threshold=0.05)
    assert len(alerts) == 1
