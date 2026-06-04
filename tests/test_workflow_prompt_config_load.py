from __future__ import annotations

from unittest.mock import MagicMock

from libs.workflow.engine import WorkflowEngine


def test_load_prompt_config_by_id_matches_registry_normalisation(monkeypatch):
    row = {
        "id": "prompt-uuid-1",
        "name": "extraction",
        "version": 2,
        "systemPrompt": "Extract clinical terms.",
        "outputSchema": '{"type":"object"}',
        "fewShotExamples": '[{"input":"[s0] No fever.","output":"{}","category":"assertion:absent"}]',
        "maxFewShot": 7,
    }

    session = MagicMock()
    session.run.return_value.single.return_value = row
    client = MagicMock()
    client.session.return_value.__enter__.return_value = session

    monkeypatch.setattr(
        "libs.neo4j_client.client.KnowledgeGraphClient",
        lambda: client,
    )

    from libs.prompts import registry

    expected = registry._normalise_prompt_config_row("extraction", 2, dict(row))

    engine = WorkflowEngine()
    loaded = engine._load_prompt_config("prompt-uuid-1")

    assert loaded == expected
    assert loaded["maxFewShot"] == 7
    assert loaded["fewShotExamples"]
