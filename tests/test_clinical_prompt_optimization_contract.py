"""Focused contracts for provider-neutral clinical prompt optimisation."""

from __future__ import annotations

import json
from pathlib import Path

from libs.llm_client import coding_verifier, disorder_verifier, escalation
from libs.llm_client.prompt_safety import INJECTION_GUARD
from libs.prompts import episode_engine
from libs.prompts.episode_engine import (
    audit_relevance_filter_v1,
    classifier_v1,
    milestone_extractor_v1,
    reconciler_v1,
    segmenter_v1,
)
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.prompts.referral_extraction_v1 import REFERRAL_EXTRACTION_SYSTEM_V1
from libs.prompts.sbar_background_reduce_v1 import (
    SBAR_BACKGROUND_REDUCE_SYSTEM_V1,
)
from libs.prompts.sbar_background_v1 import SBAR_BACKGROUND_SYSTEM_V1
from libs.prompts.sbar_recall_v1 import SBAR_RECALL_SYSTEM_V1
from libs.prompts.sbar_recommendation_v1 import SBAR_RECOMMENDATION_SYSTEM_V1
from libs.prompts.sbar_rollup_recommendation_v1 import (
    SBAR_ROLLUP_RECOMMENDATION_SYSTEM_V1,
)
from libs.prompts.sbar_situation_v1 import SBAR_SITUATION_SYSTEM_V1


def test_extraction_body_structure_assertions_match_examples() -> None:
    assert 'Use assertion="present" for all body structure' not in EXTRACTION_SYSTEM_V1
    assert "Assign assertion from explicit cues" in EXTRACTION_SYSTEM_V1


def test_referral_prompt_preserves_assertion_schema() -> None:
    assert "Include assertion on every entity" in REFERRAL_EXTRACTION_SYSTEM_V1
    assert "Do not output assertion" not in REFERRAL_EXTRACTION_SYSTEM_V1
    assert "OUTPUT CONTRACT" in REFERRAL_EXTRACTION_SYSTEM_V1


def test_out_of_range_lab_example_contains_value_and_interpretation() -> None:
    example = next(
        item
        for item in EXTRACTION_EXAMPLES
        if item.get("description", "").startswith("Compound lab result")
    )
    terms = json.loads(example["output"])["terms"]
    assert [term["semantic_tag"] for term in terms] == [
        "observable entity",
        "finding",
    ]


def test_sbar_prompts_state_priorities_and_json_contract() -> None:
    prompts = (
        SBAR_SITUATION_SYSTEM_V1,
        SBAR_BACKGROUND_SYSTEM_V1,
        SBAR_BACKGROUND_REDUCE_SYSTEM_V1,
        SBAR_RECOMMENDATION_SYSTEM_V1,
        SBAR_ROLLUP_RECOMMENDATION_SYSTEM_V1,
    )
    for prompt in prompts:
        assert "PRIORITY ORDER" in prompt
        assert "HARD RULES" in prompt
        assert "Output MUST be a single JSON object" in prompt
    assert "PRIORITY ORDER" in SBAR_RECALL_SYSTEM_V1
    assert "submit_recall_result" in SBAR_RECALL_SYSTEM_V1


def test_episode_prompts_keep_safety_and_structured_contracts() -> None:
    prompts = (
        segmenter_v1.SYSTEM,
        classifier_v1.SYSTEM,
        milestone_extractor_v1.SYSTEM,
        reconciler_v1.SYSTEM,
        audit_relevance_filter_v1.SYSTEM,
    )
    for prompt in prompts:
        assert prompt.startswith(INJECTION_GUARD)
        assert "OBJECTIVE" in prompt
        assert "PRIORITY ORDER" in prompt
        assert "HARD REQUIREMENTS" in prompt
        assert "OUTPUT CONTRACT" in prompt
    assert "needs_human_review=true" in milestone_extractor_v1.SYSTEM
    assert "human review" in reconciler_v1.SYSTEM


def test_verifier_prompts_keep_injection_guard_and_conservative_priority() -> None:
    prompts = (
        escalation._CANDIDATES_SYSTEM,
        escalation._VERIFY_SYSTEM,
        coding_verifier._SYSTEM_PROMPT,
        disorder_verifier._SYSTEM_PROMPT,
    )
    for prompt in prompts:
        assert prompt.startswith(INJECTION_GUARD)
        assert "OBJECTIVE" in prompt
        assert "PRIORITY ORDER" in prompt
        assert "OUTPUT CONTRACT" in prompt
    assert "Prefer uncertain" in escalation._VERIFY_SYSTEM
    assert "Prefer retry over accept" in coding_verifier._SYSTEM_PROMPT
    assert "Prefer uncertain" in disorder_verifier._SYSTEM_PROMPT


def test_provider_docstrings_describe_current_primary_and_optional_route() -> None:
    modules = (
        episode_engine,
        audit_relevance_filter_v1,
        escalation,
        disorder_verifier,
    )
    for module in modules:
        docstring = " ".join((module.__doc__ or "").split())
        assert "Azure OpenAI GPT-5" in docstring
        assert "AWS Bedrock" in docstring
    assert "Azure is not available" not in (escalation.__doc__ or "")


def test_runtime_and_review_paths_use_managed_shared_contracts() -> None:
    root = Path(__file__).resolve().parents[1]
    candidate_source = (
        root / "services/api/app/services/candidate_ai_first_pass/_extractor.py"
    ).read_text(encoding="utf-8")
    ask_leo_source = (root / "services/api/app/routers/_training_askleo.py").read_text(
        encoding="utf-8"
    )

    assert 'get_prompt_config("extraction"' in candidate_source
    assert "from libs.prompts.extraction_v1 import" not in candidate_source
    rank_block = ask_leo_source.split("def ask_leo_rank_candidates", 1)[1].split(
        "@router.post", 1
    )[0]
    assert "escalate_coding_from_candidates" in rank_block
    assert "create_llm" not in rank_block
