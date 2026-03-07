from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline_graph.subgraphs.persist import write_gold_training


def test_write_gold_training_writes_candidate_and_gold() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    with patch("libs.pipeline_graph.subgraphs.persist._get_patient_graph_client", return_value=client):
        out = write_gold_training(
            {
                "encounter_text": "chest pain for 3 days",
                "entities": [{"text": "chest pain", "label": "finding", "start": 0, "end": 10}],
                "verification_result": {"confidence": 0.95},
                "errors": [],
            }
        )
    assert out["training_labels_written"] == 1
    assert session.run.call_count >= 3

