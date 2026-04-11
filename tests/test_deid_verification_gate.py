from __future__ import annotations

from unittest.mock import MagicMock, patch

from libs.pipeline_graph.subgraphs.persist import write_gold_training


def _state(text: str) -> dict:
    return {
        "encounter_text": text,
        "entities": [
            {
                "text": "chest pain",
                "label": "finding",
                "start": 0,
                "end": 10,
                "_llm_check_source": "llm_added",
            }
        ],
        "verification_result": {"confidence": 0.95},
        "errors": [],
    }


def test_deid_gate_blocks_nhs_number() -> None:
    result = write_gold_training(_state("NHS number 123 456 7890 with chest pain"))
    assert result.get("status") == "deid_failed"
    assert result.get("training_labels_written") == 0


def test_deid_gate_allows_placeholder_text() -> None:
    # No blocked patterns: should not return deid_failed.
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = False
    mock_client = MagicMock()
    mock_client.session.return_value = mock_session
    with patch(
        "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
        return_value=mock_client,
    ):
        result = write_gold_training(_state("Patient has chest pain and no dyspnoea."))
    assert result.get("status") != "deid_failed"


def test_deid_gate_validates_deidentified_payload() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    client = MagicMock()
    client.session.return_value = session
    with (
        patch(
            "libs.pipeline_graph.subgraphs.persist._get_patient_graph_client",
            return_value=client,
        ),
        patch(
            "libs.pipeline_graph.subgraphs.persist.deidentify_text",
            side_effect=lambda text, ner=True: text.replace("GOPEE, Dinesha", "[PERSON]"),
        ),
    ):
        result = write_gold_training(
            _state("Review done by GOPEE, Dinesha (Dr) - 15 May 2024")
        )
    assert result.get("status") != "deid_failed"
