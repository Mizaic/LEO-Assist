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

    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm", lambda tier="small": fake_llm
    )
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
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm", lambda tier="small": fake_llm
    )

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


def test_taught_form_keeps_examples_marked_safe(monkeypatch) -> None:
    """A taught bundle still carries free text, so content examples must survive.

    The form filter exists to stop generic checkbox and negation examples
    fighting the taught contract. It must not blind the model to the
    radiology reports and lab tables attached behind the form.
    """
    _mock_compose_prompt(monkeypatch)
    fake_llm = _FakeLLM()
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm", lambda tier="small": fake_llm
    )

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
                "category": "disorder:imaging",
                "description": "pelvic ultrasound core",
                "input": "[s0] Right adnexal cyst measuring 6cm.",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": True,
                "taught_form_safe": True,
            },
            {
                "category": "precision:referral_scope",
                "description": "scope core",
                "input": "[s0] Referred under 2WW.",
                "output": '{"terms":[]}',
                "model_scope": "any",
                "core": True,
            },
        ],
        max_few_shot=5,
        provider="aws",
        known_form_schema=True,
    )

    kept = {ex["description"] for ex in adapter._core_examples}
    assert kept == {"checkbox core", "pelvic ultrasound core"}
    assert "pelvic ultrasound core" in adapter._system_prompt
    assert "scope core" not in adapter._system_prompt


def test_library_teaches_pelvic_ultrasound_on_a_taught_form() -> None:
    """The gynae 2WW bundle attaches pelvic scans, so the library must cover them."""
    from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES

    survivors = [
        ex
        for ex in EXTRACTION_EXAMPLES
        if ex.get("core")
        and (ex.get("category") == "form:checkbox" or ex.get("taught_form_safe"))
    ]
    blob = " ".join(
        f"{ex.get('description', '')} {ex.get('input', '')}" for ex in survivors
    ).lower()
    assert "adnexal" in blob or "ovarian" in blob
    assert "ultrasound" in blob


def _surviving_examples() -> list[dict]:
    """Core examples that still reach the model once a form is taught."""
    from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES

    return [
        ex
        for ex in EXTRACTION_EXAMPLES
        if ex.get("core")
        and (ex.get("category") == "form:checkbox" or ex.get("taught_form_safe"))
    ]


class TestTheInvestigationLog:
    """A dated list of completed scans must read as scans that happened.

    NHS 4568668417 listed three finished studies in the referral's
    investigation log::

        | 30 May 2026: Standard chest X-ray (535..) |
        | 24 Jun 2026: US PELVIS |
        | 24 Jun 2026: US PELVIS TRANSVAGINAL |

    The model was shown every one of those lines and returned nothing for
    them, so a pelvic ultrasound the patient had already had was requested
    again. "US PELVIS" was already taught in SurfaceForm at the time, so
    the gap was never the vocabulary -- the model simply never produced a
    span to look up. Only an example of this shape closes that.
    """

    def test_the_library_shows_a_dated_investigation_line(self) -> None:
        blob = " ".join(str(ex.get("input", "")) for ex in _surviving_examples())
        assert "US PELVIS" in blob or "US Pelvis" in blob

    def test_the_library_shows_a_scan_being_coded_as_a_procedure(self) -> None:
        for ex in _surviving_examples():
            if "US PELVIS" in str(ex.get("input", "")):
                assert '"semantic_tag": "procedure"' in str(ex.get("output", ""))
                return
        raise AssertionError("no investigation-log example in the library")

    def test_the_library_covers_plain_film_as_well_as_ultrasound(self) -> None:
        """A chest X-ray is on the same log and was missed the same way."""
        blob = " ".join(str(ex.get("input", "")) for ex in _surviving_examples())
        assert "chest x-ray" in blob.lower()


def test_seeded_payload_carries_the_taught_form_flag() -> None:
    """The flag is only useful if it survives the trip into Neo4j.

    The extractor reads examples from PromptConfig at run time, not from
    the Python module, and the seeder rebuilds each example from a fixed
    key list. A flag missing from that list is dropped in silence and the
    taught-form filter never sees it.
    """
    from scripts.seed_prompt_configs import SEED_PROMPTS

    extraction = next(
        p for p in SEED_PROMPTS if p["name"] == "extraction" and p["version"] == 1
    )
    examples = extraction["few_shot_examples"]
    survivors = [
        ex
        for ex in examples
        if ex.get("core")
        and (ex.get("category") == "form:checkbox" or ex.get("taught_form_safe"))
    ]
    assert any(ex.get("taught_form_safe") for ex in examples)
    assert any("adnexal" in str(ex.get("input", "")).lower() for ex in survivors)


def test_seeding_can_be_narrowed_to_named_prompts() -> None:
    """Seeding everything rewrites prompts the repo and graph disagree on.

    The SBAR prompts had drifted from the graph when the few-shot fix
    needed seeding, so the extraction prompt must be seedable alone.
    """
    from scripts.seed_prompt_configs import SEED_PROMPTS, select_prompts

    chosen = select_prompts(SEED_PROMPTS, ["extraction"])
    assert [p["name"] for p in chosen] == ["extraction"]
    assert select_prompts(SEED_PROMPTS, None) == SEED_PROMPTS
    assert select_prompts(SEED_PROMPTS, []) == SEED_PROMPTS


def test_seeding_refuses_a_name_it_cannot_find() -> None:
    """A typo must fail loudly, not seed nothing and report success."""
    import pytest

    from scripts.seed_prompt_configs import SEED_PROMPTS, select_prompts

    with pytest.raises(SystemExit):
        select_prompts(SEED_PROMPTS, ["extracton"])


def test_known_form_schema_adds_taught_form_hint(monkeypatch) -> None:
    _mock_compose_prompt(monkeypatch)
    fake_llm = _FakeLLM()
    monkeypatch.setattr(
        "libs.llm_client.factory.create_llm", lambda tier="small": fake_llm
    )

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
