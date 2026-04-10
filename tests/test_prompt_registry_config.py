from __future__ import annotations

from unittest.mock import patch


def test_get_prompt_config_normalises_examples_and_schema():
    from libs.prompts import registry

    row = {
        "id": "pc-1",
        "name": "extraction",
        "version": 2,
        "systemPrompt": "System prompt body",
        "outputSchema": '{"type":"object"}',
        "fewShotExamples": '[{"id":"ex-1","category":"labs"}]',
        "maxFewShot": 12,
    }
    with patch.object(registry, "_neo4j_fetch", return_value=row):
        cfg = registry.get_prompt_config("extraction", version=2)

    assert cfg["id"] == "pc-1"
    assert cfg["name"] == "extraction"
    assert cfg["version"] == 2
    assert cfg["systemPrompt"] == "System prompt body"
    assert cfg["outputSchema"] == '{"type":"object"}'
    assert cfg["fewShotExamples"][0]["id"] == "ex-1"
    assert cfg["maxFewShot"] == 12
