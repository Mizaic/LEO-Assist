from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "training_worker"))

from app import label_exporter


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def run(self, _query):
        return self._rows


class _FakePatientClient:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def session(self):
        return _FakeSession(self._rows)

    def close(self):
        self.closed = True


class _FakeKnowledgeClient:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def session(self):
        return _FakeSession(self._rows)

    def close(self):
        self.closed = True


def _patch_clients(monkeypatch, *, patient_rows, kg_rows):
    patient_client = _FakePatientClient(patient_rows)
    kg_client = _FakeKnowledgeClient(kg_rows)

    class _ClientModule:
        @staticmethod
        def PatientGraphClient():
            return patient_client

        @staticmethod
        def KnowledgeGraphClient():
            return kg_client

    monkeypatch.setattr(
        "libs.neo4j_client.client.PatientGraphClient", _ClientModule.PatientGraphClient
    )
    monkeypatch.setattr(
        "libs.neo4j_client.client.KnowledgeGraphClient",
        _ClientModule.KnowledgeGraphClient,
    )
    monkeypatch.setattr("libs.ner.post_processor_rules.parse_rules", lambda rows: [])
    monkeypatch.setattr(
        "libs.ner.post_processor_rules.apply_rules_to_entities",
        lambda text, entities, rules: entities,
    )
    return patient_client, kg_client


def test_export_labels_reads_gold_label_source(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        label_exporter.os,
        "getenv",
        lambda key, default=None: (
            "1" if key == "TRAINING_MIN_LABEL_COUNT" else os.environ.get(key, default)
        ),
    )
    patient_rows = []
    kg_rows = [
        {
            "label_id": "a",
            "text": "Patient has chest pain",
            "entities_json": '[{"start": 12, "end": 22, "label": "finding"}]',
            "source": "manual_gold_editor",
            "quality_score": 0.9,
            "verified_at": "2026-01-01T00:00:00",
        },
        {
            "label_id": "b",
            "text": "Biopsy planned tomorrow",
            "entities_json": '[{"start": 0, "end": 6, "label": "procedure"}]',
            "source": "migrated_from_training_label",
            "quality_score": 0.95,
            "verified_at": "2026-01-01T00:00:00",
        },
    ]
    patient_client, kg_client = _patch_clients(
        monkeypatch, patient_rows=patient_rows, kg_rows=kg_rows
    )

    result = label_exporter.export_labels(tmp_path, train_ratio=0.5, seed=7)

    assert result["total"] == 2
    assert result["train_count"] >= 1
    assert result["dev_count"] >= 1
    assert (tmp_path / "train.spacy").exists()
    assert (tmp_path / "dev.spacy").exists()
    assert patient_client.closed is True
    assert kg_client.closed is True


def test_export_labels_blocks_when_gold_count_below_min(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        label_exporter.os,
        "getenv",
        lambda key, default=None: (
            "3" if key == "TRAINING_MIN_LABEL_COUNT" else os.environ.get(key, default)
        ),
    )
    _patch_clients(
        monkeypatch,
        patient_rows=[],
        kg_rows=[
            {
                "label_id": "a",
                "text": "Only one record",
                "entities_json": '[{"start": 0, "end": 4, "label": "finding"}]',
                "source": "manual_gold_editor",
                "quality_score": 0.9,
                "verified_at": "2026-01-01T00:00:00",
            }
        ],
    )

    try:
        label_exporter.export_labels(tmp_path, train_ratio=0.8, seed=1)
        raise AssertionError("Expected ValueError for below-minimum GoldLabel count")
    except ValueError as exc:
        assert "Only 1 GoldLabel records" in str(exc)
