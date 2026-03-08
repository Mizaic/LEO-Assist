from __future__ import annotations

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline_graph.subgraphs._extractor import LLMExtractorAdapter


class _FakeResp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.input_tokens = 100
        self.output_tokens = 20
        self.cached_input_tokens = 0


class _FakeLLM:
    def __init__(self) -> None:
        self.system = ""
        self.messages = []

    def converse(self, system, messages, max_tokens=0, temperature=0.0):  # noqa: ANN001
        self.system = system
        self.messages = messages
        return _FakeResp('{"terms": []}')


def test_core_examples_stay_in_system_and_dynamic_go_to_user(monkeypatch) -> None:
    fake_llm = _FakeLLM()

    def _fake_create_llm(tier="small"):  # noqa: ANN001
        return fake_llm

    monkeypatch.setattr("libs.llm_client.factory.create_llm", _fake_create_llm)
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs._extractor.FewShotSelector.select",
        lambda self, query_text, k: [  # noqa: ARG005
            {
                "category": "observable",
                "description": "dynamic example",
                "input": "[s0] eGFR 42",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": False,
            }
        ],
    )

    adapter = LLMExtractorAdapter(
        system_prompt="Base instructions",
        output_schema_json='{"type":"object","properties":{"terms":{"type":"array"}}}',
        few_shot_examples=[
            {
                "category": "assertion:absent",
                "description": "core example",
                "input": "[s0] No fever.",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": True,
            },
            {
                "category": "observable",
                "description": "dynamic candidate",
                "input": "[s0] eGFR 42",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": False,
            },
        ],
        max_few_shot=2,
        provider="aws",
    )

    adapter.extract_batch("Encounter text", [SentenceChunk("s0", "No fever.", 0, 9)])

    assert "core example" in fake_llm.system
    assert "dynamic candidate" not in fake_llm.system
    assert "## Relevant examples" in fake_llm.messages[0]["content"]
    assert "dynamic example" in fake_llm.messages[0]["content"]


def test_invalid_max_few_shot_defaults_to_20() -> None:
    adapter = LLMExtractorAdapter(
        system_prompt="Base instructions",
        output_schema_json='{"type":"object"}',
        few_shot_examples=[],
        max_few_shot="bad-value",  # type: ignore[arg-type]
        provider="aws",
    )
    assert adapter._max_few_shot == 20
