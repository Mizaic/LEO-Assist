"""Tests: ModelRegistry lifecycle and CompatibilityGate.

Covers:
- Register, offline validate, canary, promote, rollback transitions.
- Promotion rejected when canary KPIs not met.
- Promotion rejected when no rollback target.
- CompatibilityGate passes when all versions match.
- CompatibilityGate fails on version mismatch.
- TrainingAdapter converts records and rejects unsupported versions.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from libs.model_registry.registry import ModelRecord, ModelRegistry, ModelStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(**kwargs) -> ModelRecord:
    defaults = dict(
        model_name="medspacy_clinical_ner",
        model_version="1.0",
        model_path="/models/v1.0",
        training_dataset_version="20260101",
        schema_version="1.0",
        deid_version="1.0",
    )
    defaults.update(kwargs)
    return ModelRecord(**defaults)


# ---------------------------------------------------------------------------
# Registry lifecycle
# ---------------------------------------------------------------------------


def test_register_and_get():
    reg = ModelRegistry()
    rec = _make_record()
    reg.register(rec)
    fetched = reg.get("1.0")
    assert fetched is not None
    assert fetched.model_version == "1.0"
    assert fetched.status == ModelStatus.REGISTERED


def test_register_duplicate_raises():
    reg = ModelRegistry()
    reg.register(_make_record())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_make_record())


def test_offline_validate_pass():
    reg = ModelRegistry()
    reg.register(_make_record())
    reg.validate_offline("1.0", precision=0.85, recall=0.80)
    assert reg.get("1.0").status == ModelStatus.OFFLINE_VALIDATED


def test_offline_validate_fail():
    reg = ModelRegistry()
    reg.register(_make_record())
    reg.validate_offline("1.0", precision=0.50, recall=0.50)
    assert reg.get("1.0").status == ModelStatus.DEPRECATED


def test_canary_requires_offline_validation():
    reg = ModelRegistry()
    reg.register(_make_record())
    with pytest.raises(RuntimeError, match="cannot start canary"):
        reg.start_canary("1.0")


def test_promote_happy_path():
    reg = ModelRegistry()
    # Register rollback v0.9 and promote it first
    reg.register(_make_record(model_version="0.9"))
    reg.validate_offline("0.9", precision=0.82, recall=0.78)
    reg.start_canary("0.9")
    reg.record_canary_result("0.9", precision=0.81, recall=0.76)
    reg.promote("0.9")

    # Now register v1.0 and go through full lifecycle
    reg.register(_make_record(model_version="1.0"))
    reg.validate_offline("1.0", precision=0.88, recall=0.82)
    reg.start_canary("1.0")
    reg.record_canary_result("1.0", precision=0.86, recall=0.80)
    reg.promote("1.0", rollback_target_version="0.9")

    active = reg.get_active()
    assert active is not None
    assert active.model_version == "1.0"
    assert active.status == ModelStatus.PROMOTED
    assert active.rollback_target_version == "0.9"


def test_promote_fails_without_canary_kpis():
    reg = ModelRegistry()
    reg.register(_make_record())
    reg.validate_offline("1.0", precision=0.88, recall=0.82)
    reg.start_canary("1.0")
    with pytest.raises(RuntimeError, match="canary KPIs not recorded"):
        reg.promote("1.0")


def test_promote_fails_low_canary_kpi():
    reg = ModelRegistry()
    reg.register(_make_record())
    reg.validate_offline("1.0", precision=0.88, recall=0.82)
    reg.start_canary("1.0")
    reg.record_canary_result("1.0", precision=0.50, recall=0.50)
    with pytest.raises(RuntimeError, match="canary KPI thresholds not met"):
        reg.promote("1.0")


def test_rollback():
    reg = ModelRegistry()
    reg.register(_make_record(model_version="0.9"))
    reg.validate_offline("0.9", precision=0.82, recall=0.78)
    reg.start_canary("0.9")
    reg.record_canary_result("0.9", precision=0.81, recall=0.76)
    reg.promote("0.9")

    reg.register(_make_record(model_version="1.0"))
    reg.validate_offline("1.0", precision=0.88, recall=0.82)
    reg.start_canary("1.0")
    reg.record_canary_result("1.0", precision=0.85, recall=0.79)
    reg.promote("1.0", rollback_target_version="0.9")

    assert reg.get_active().model_version == "1.0"

    rolled_back = reg.rollback()
    assert rolled_back.model_version == "0.9"
    assert reg.get_active().model_version == "0.9"
    assert reg.get("1.0").status == ModelStatus.ROLLBACK


# ---------------------------------------------------------------------------
# CompatibilityGate
# ---------------------------------------------------------------------------


def _write_manifest(path: Path, **overrides) -> None:
    manifest = {
        "schema_version": "1.0",
        "deid_version": "1.0",
        "label_mapping_version": "1.0",
        "dataset_version": "20260101",
        "split": {"train": 0.8, "dev": 0.1, "test": 0.1},
        "entity_counts": {"finding": 500},
        "created_at": "2026-01-01T00:00:00Z",
    }
    manifest.update(overrides)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_compatibility_gate_passes():
    from libs.model_registry.manifest_reader import CompatibilityGate

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(manifest_path)

        gate = CompatibilityGate(
            required_schema_version="1.0",
            required_deid_version="1.0",
            required_label_version="1.0",
        )
        result = gate.check(
            manifest_path=manifest_path,
            model_schema_version="1.0",
            model_deid_version="1.0",
            model_label_mapping_version="1.0",
            model_dataset_version="20260101",
        )
    assert result.passed
    assert not result.failures


def test_compatibility_gate_fails_schema_mismatch():
    from libs.model_registry.manifest_reader import CompatibilityGate

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(manifest_path, schema_version="1.0")

        gate = CompatibilityGate()
        result = gate.check(
            manifest_path=manifest_path,
            model_schema_version="2.0",  # mismatch
            model_deid_version="1.0",
            model_label_mapping_version="1.0",
            model_dataset_version="20260101",
        )
    assert not result.passed
    assert any("schema_version" in f for f in result.failures)


def test_compatibility_gate_raises_on_fail():
    from libs.model_registry.manifest_reader import CompatibilityGate

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "manifest.json"
        _write_manifest(manifest_path)

        gate = CompatibilityGate()
        result = gate.check(
            manifest_path=manifest_path,
            model_schema_version="9.0",
            model_deid_version="1.0",
            model_label_mapping_version="1.0",
            model_dataset_version="20260101",
        )
    with pytest.raises(RuntimeError, match="promotion blocked"):
        result.raise_if_failed()


def test_compatibility_gate_missing_manifest():
    from libs.model_registry.manifest_reader import CompatibilityGate

    gate = CompatibilityGate()
    result = gate.check(
        manifest_path="/nonexistent/manifest.json",
        model_schema_version="1.0",
        model_deid_version="1.0",
        model_label_mapping_version="1.0",
        model_dataset_version="20260101",
    )
    assert not result.passed
    assert any("manifest_read_error" in f for f in result.failures)


# ---------------------------------------------------------------------------
# TrainingAdapter
# ---------------------------------------------------------------------------


def test_training_adapter_converts_record():
    from libs.model_registry.training_adapter import TrainingAdapter, TrainingRecord

    record = TrainingRecord(
        text="Referred for suspected colorectal cancer",
        entities=[
            {
                "start": 12,
                "end": 40,
                "label": "FAST_TRACK_REFERRAL",
                "text": "suspected colorectal cancer",
                "assertion": "present",
                "normalized": "Fast track referral",
                "confidence": 1.0,
            }
        ],
        sentence_id="s001",
        schema_version="1.0",
        deid_version="1.0",
        label_mapping_version="1.0",
    )

    adapter = TrainingAdapter(model_name="training_corpus", model_version="1.0")
    items = adapter.to_extraction_items(record)

    assert len(items) == 1
    assert items[0].text == "suspected colorectal cancer"
    assert items[0].semantic_tag == "finding"
    assert items[0].assertion == "present"
    assert items[0].source == "training_label"


def test_training_adapter_rejects_unsupported_schema():
    from libs.model_registry.training_adapter import (
        AdapterError,
        TrainingAdapter,
        TrainingRecord,
    )

    record = TrainingRecord(
        text="cancer text",
        entities=[],
        sentence_id="s1",
        schema_version="99.0",  # unsupported
        deid_version="1.0",
        label_mapping_version="1.0",
    )

    adapter = TrainingAdapter()
    with pytest.raises(AdapterError, match="schema_version"):
        adapter.to_extraction_items(record)
