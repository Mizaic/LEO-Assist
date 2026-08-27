"""Few-shot policy when a taught FormSchema is already bound."""

from __future__ import annotations

from libs.nlp.sentence_splitter import SentenceChunk
from libs.pipeline_graph.subgraphs._extractor import LLMExtractorAdapter


def _mock_compose_prompt(monkeypatch) -> None:
    monkeypatch.setattr(
        "libs.prompts.registry.compose_prompt_with_annotation_guidelines",
        lambda _name, instructions: instructions,
    )


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

    def converse(self, system, messages, **kwargs):  # noqa: ANN001
        _ = kwargs
        self.system = system
        self.messages = messages
        return _FakeResp('{"terms": []}')


def test_known_form_schema_skips_dynamic_few_shot(monkeypatch) -> None:
    _mock_compose_prompt(monkeypatch)
    fake_llm = _FakeLLM()
    select_called: list[int] = []

    def _track_select(self, query_text, k):  # noqa: ANN001, ARG001
        select_called.append(k)
        return [], 0.0

    monkeypatch.setattr("libs.llm_client.factory.create_llm", lambda tier="small": fake_llm)
    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs._extractor.FewShotSelector.select_with_scores",
        _track_select,
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
        known_form_schema=True,
    )

    assert adapter._dynamic_budget == 0
    adapter.extract_batch("Encounter text", [SentenceChunk("s0", "No fever.", 0, 9)])

    assert select_called == []
    assert "## Relevant examples" not in fake_llm.messages[0]["content"]


def test_known_form_schema_keeps_only_form_checkbox_core(monkeypatch) -> None:
    _mock_compose_prompt(monkeypatch)
    fake_llm = _FakeLLM()
    monkeypatch.setattr("libs.llm_client.factory.create_llm", lambda tier="small": fake_llm)

    adapter = LLMExtractorAdapter(
        system_prompt="Base instructions",
        output_schema_json='{"type":"object","properties":{"terms":{"type":"array"}}}',
        few_shot_examples=[
            {
                "category": "form:checkbox",
                "description": "checkbox core",
                "input": "[s0] [X] Breast lump",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": True,
            },
            {
                "category": "observable",
                "description": "lab core",
                "input": "[s0] eGFR 42",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": True,
            },
        ],
        max_few_shot=5,
        provider="aws",
        known_form_schema=True,
    )

    assert len(adapter._core_examples) == 1
    assert adapter._core_examples[0]["category"] == "form:checkbox"
    assert "checkbox core" in adapter._system_prompt
    assert "lab core" not in adapter._system_prompt


def test_run_llm_extraction_passes_known_form_schema(monkeypatch) -> None:
    from libs.pipeline_graph.subgraphs.extraction import _run_llm_extraction

    _mock_compose_prompt(monkeypatch)
    captured: dict[str, bool] = {}

    class _StubAdapter:
        def extract_batch_with_usage(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return [], {"few_shot_max_similarity": 0.0}

    def _fake_build_extractor(**kwargs):
        captured["known_form_schema"] = bool(kwargs.get("known_form_schema"))
        return _StubAdapter()

    monkeypatch.setattr(
        "libs.pipeline_graph.subgraphs._extractor.build_extractor",
        _fake_build_extractor,
    )

    prompt_state = {"prompt_config": {"systemPrompt": "Extract clinical terms."}}

    _run_llm_extraction(
        "letter text",
        [SentenceChunk("s0", "line", 0, 4)],
        {
            **prompt_state,
            "form_schema_match": "org_service",
            "form_schema_fingerprint": "sfh-gynae-2ww-v1",
        },
    )
    assert captured["known_form_schema"] is True

    _run_llm_extraction(
        "letter text",
        [SentenceChunk("s0", "line", 0, 4)],
        {**prompt_state, "form_schema_match": "none"},
    )
    assert captured["known_form_schema"] is False


def test_known_form_schema_adds_taught_form_hint(monkeypatch) -> None:
    _mock_compose_prompt(monkeypatch)
    fake_llm = _FakeLLM()
    monkeypatch.setattr("libs.llm_client.factory.create_llm", lambda tier="small": fake_llm)

    adapter = LLMExtractorAdapter(
        system_prompt="Base instructions",
        output_schema_json='{"type":"object","properties":{"terms":{"type":"array"}}}',
        few_shot_examples=[],
        provider="aws",
        known_form_schema=True,
        taught_form_fingerprint="sfh-gynae-2ww-v1",
    )
    adapter.extract_batch("Encounter text", [SentenceChunk("s0", "line", 0, 4)])

    assert "Input was normalized from taught form sfh-gynae-2ww-v1." in (
        fake_llm.messages[0]["content"]
    )
