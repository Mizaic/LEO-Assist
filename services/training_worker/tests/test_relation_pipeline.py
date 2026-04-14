from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.relation_evaluator import evaluate_relation_model
from app.relation_exporter import export_relation_dataset
from app.relation_trainer import train_relation_model


def test_relation_exporter_writes_train_dev(tmp_path: Path):
    rows = [
        {
            "text": "lump in right breast",
            "entities_json": json.dumps(
                [
                    {
                        "text": "lump",
                        "label": "finding",
                        "relations": [{"type": "finding_site", "target_idx": 1}],
                    },
                    {
                        "text": "right breast",
                        "label": "body_structure",
                        "snomed_term": "Right breast structure",
                    },
                ]
            ),
        }
    ]
    with patch("app.relation_exporter.KnowledgeGraphClient") as mock_client:
        inner = MagicMock()
        inner.run.return_value = rows
        mock_client.return_value.session.return_value.__enter__ = lambda s: inner
        mock_client.return_value.session.return_value.__exit__ = MagicMock(
            return_value=False
        )
        summary = export_relation_dataset(tmp_path, train_ratio=0.8, seed=1)

    assert summary["total"] == 1
    assert (tmp_path / "relation_train.jsonl").exists()
    assert (tmp_path / "relation_dev.jsonl").exists()


def test_relation_train_and_eval_round_trip(tmp_path: Path):
    train_path = tmp_path / "relation_train.jsonl"
    dev_path = tmp_path / "relation_dev.jsonl"
    row = {
        "text": "lump in right breast",
        "entities": [
            {"text": "lump", "label": "finding"},
            {"text": "right breast", "label": "body_structure"},
        ],
        "relations": [{"source_idx": 0, "target_idx": 1, "type": "finding_site"}],
    }
    train_path.write_text(json.dumps(row), encoding="utf-8")
    dev_path.write_text(json.dumps(row), encoding="utf-8")
    model_path = tmp_path / "relation_model.json"
    train_summary = train_relation_model(train_path, model_path)
    assert train_summary["sample_count"] == 1
    metrics = evaluate_relation_model(model_path, dev_path)
    assert metrics["sample_count"] == 1
    assert metrics["f1"] >= 0.99
