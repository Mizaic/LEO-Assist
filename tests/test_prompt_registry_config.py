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
    def _fake_fetch(name: str, version: int):
        if name == "annotation_guidelines" and version == 1:
            return {
                "id": "pc-guidelines",
                "name": "annotation_guidelines",
                "version": 1,
                "systemPrompt": "Shared rules block",
                "outputSchema": "{}",
                "fewShotExamples": "[]",
                "maxFewShot": 0,
            }
        return row

    with patch.object(registry, "_neo4j_fetch", side_effect=_fake_fetch):
        cfg = registry.get_prompt_config("extraction", version=2)

    assert cfg["id"] == "pc-1"
    assert cfg["name"] == "extraction"
    assert cfg["version"] == 2
    assert cfg["systemPrompt"] == "System prompt body\n\nShared rules block"
    assert cfg["outputSchema"] == '{"type":"object"}'
    assert cfg["fewShotExamples"][0]["id"] == "ex-1"
    assert cfg["maxFewShot"] == 12


def test_compose_prompt_with_annotation_guidelines_target_and_non_target():
    from libs.prompts import registry

    with patch.object(
        registry,
        "_load_annotation_guidelines_text",
        return_value="Shared guide",
    ):
        target = registry.compose_prompt_with_annotation_guidelines(
            "label_verification", "Base prompt"
        )
        non_target = registry.compose_prompt_with_annotation_guidelines(
            "verification", "Base prompt"
        )

    assert target == "Base prompt\n\nShared guide"
    assert non_target == "Base prompt"
