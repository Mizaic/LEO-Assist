"""Every model's real limit, and a loud stop before we reach it.

Nothing in the platform knew how much a model could read. ModelConfig in
Neo4j carried prices and a model id, never a context window, so every
budget was a number somebody typed: 16,000 characters here, 50,000 tokens
there, 200,000 somewhere else. The only check on the real limit ran after
a call had already failed, by reading the provider's error message.

Two things go wrong with that. Budgets set far under the limit throw away
clinical text nobody was told was missing -- the referral that lost its
FIT and CA 125 results was cut at 16,000 characters against a 272,000
token input window. And a budget set over the limit fails in the
provider, late, on a patient's referral.

Rule: .cursor/rules/fail-closed-boundary.mdc rule 2 -- a lookup has three
answers. An undeclared window is "we could not ask", never "it fits".
"""

from __future__ import annotations

import pytest

from libs.llm_client.context_budget import (
    HEADROOM_FRACTION,
    ContextBudgetExceeded,
    ModelWindowUnknown,
    check_output_request,
    check_prompt_fits,
    fleet_safe_char_budget,
    window_for_model,
)
from libs.pipeline.llm_clinical_input import DEFAULT_USER_TEXT_MAX_CHARS

# The models the platform is configured to use, and the limits their
# vendors publish. Sources: Microsoft Foundry model catalogue and the AWS
# Bedrock model cards, read 2026-09-18; gpt-5.6-sol read 2026-10-09.
CONFIGURED_MODELS = {
    "gpt-5-mini": (400_000, 272_000, 128_000),
    "gpt-5.4": (1_050_000, 922_000, 128_000),
    "gpt-5.6-sol": (1_050_000, 922_000, 128_000),
    "gpt-5.6-luna": (1_050_000, 922_000, 128_000),
    "arn:aws:bedrock:eu-west-2:204065380870:inference-profile/"
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0": (200_000, 200_000, 64_000),
    "arn:aws:bedrock:eu-west-2:204065380870:inference-profile/"
    "eu.anthropic.claude-sonnet-4-6": (1_000_000, 1_000_000, 64_000),
    "arn:aws:bedrock:eu-west-2:204065380870:inference-profile/"
    "eu.anthropic.claude-opus-4-6-v1": (1_000_000, 1_000_000, 128_000),
}


# What the production container apps are actually pointed at, read from
# the leo-ai-prod app settings on 2026-09-18. These are the ids that reach
# create_llm, and they do not all match the ModelConfig rows: ModelConfig
# still says gpt-5-mini where the apps say gpt-5.4-mini. A window missing
# from here stops every call on that tier, so the deployed set is pinned.
DEPLOYED_MODEL_IDS = (
    "gpt-5.4",  # pipeline-worker AZURE_OPENAI_BIG_MODEL
    "gpt-5.4-mini",  # pipeline-worker AZURE_OPENAI_SMALL_MODEL
    "gpt-5.6-sol",  # core-api AZURE_OPENAI_BIG_MODEL from 2026-10-09
    "gpt-5.6-luna",  # core-api AZURE_OPENAI_SMALL_MODEL from 2026-10-09
)


def test_every_model_the_apps_are_pointed_at_has_a_window() -> None:
    """The guard refuses an undeclared model, so anything deployed must be
    declared or that tier stops working."""
    for model_id in DEPLOYED_MODEL_IDS:
        assert window_for_model(model_id).context_window_tokens > 0, model_id


def test_the_smallest_deployed_model_is_the_chat_preview() -> None:
    """gpt-5.2-chat is a fraction of the others at 128,000. core-api ran it
    as its big model until 2026-10-09, and the fleet budget is still sized
    to it. A budget sized for gpt-5.4 overruns it."""
    window = window_for_model("gpt-5.2-chat")
    assert window.context_window_tokens == 128_000
    assert window.max_input_tokens == 111_616
    assert window.max_output_tokens == 16_384


def test_every_configured_model_has_a_declared_window() -> None:
    """A model the platform can be pointed at must have a window on file."""
    for model_id, (total, inp, out) in CONFIGURED_MODELS.items():
        window = window_for_model(model_id)
        assert window.context_window_tokens == total, model_id
        assert window.max_input_tokens == inp, model_id
        assert window.max_output_tokens == out, model_id


def test_the_working_budget_sits_ten_percent_under_the_limit() -> None:
    window = window_for_model("gpt-5-mini")
    assert HEADROOM_FRACTION == 0.10
    assert window.usable_input_tokens == 244_800
    assert window.usable_output_tokens == 115_200


def test_a_bedrock_arn_resolves_to_the_model_inside_it() -> None:
    """Config points at inference-profile ARNs, not bare model ids."""
    window = window_for_model(
        "arn:aws:bedrock:eu-west-2:204065380870:inference-profile/"
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    assert window.context_window_tokens == 200_000


def test_a_model_with_no_declared_window_fires_loudly() -> None:
    """The loud stop. Pointing at a new deployment without declaring its
    window must fail, not quietly guess a limit."""
    with pytest.raises(ModelWindowUnknown) as caught:
        window_for_model("gpt-6-turbo-experimental")
    assert "gpt-6-turbo-experimental" in str(caught.value)


def test_a_prompt_inside_the_working_budget_is_allowed() -> None:
    check_prompt_fits("gpt-5-mini", estimated_tokens=200_000)


def test_a_prompt_over_the_working_budget_is_refused() -> None:
    with pytest.raises(ContextBudgetExceeded):
        check_prompt_fits("gpt-5-mini", estimated_tokens=250_000)


def test_the_refusal_says_the_model_the_size_and_the_limit() -> None:
    """A reader has to be able to act on it without opening the code."""
    with pytest.raises(ContextBudgetExceeded) as caught:
        check_prompt_fits("gpt-5-mini", estimated_tokens=250_000)
    message = str(caught.value)
    assert "gpt-5-mini" in message
    assert "250,000" in message
    assert "244,800" in message


def test_a_prompt_between_the_budget_and_the_hard_limit_still_stops() -> None:
    """The headroom is the point. 260,000 would be accepted by the provider
    and leave nothing for the answer."""
    with pytest.raises(ContextBudgetExceeded):
        check_prompt_fits("gpt-5-mini", estimated_tokens=260_000)


def test_an_output_request_over_the_working_budget_is_refused() -> None:
    with pytest.raises(ContextBudgetExceeded):
        check_output_request("gpt-5-mini", requested_tokens=120_000)


def test_an_ordinary_output_request_is_allowed() -> None:
    check_output_request("gpt-5-mini", requested_tokens=4096)


def test_the_clinical_text_budget_is_sized_to_the_tightest_window() -> None:
    """gpt-5.2-chat is the smallest at 111,616 input, so 100,454 usable
    less a 32,000 reserve, at four characters to a token. Still seventeen
    times the 16,000 it replaced."""
    assert fleet_safe_char_budget() == 273_816


def test_the_clinical_text_cap_is_no_longer_a_typed_number() -> None:
    """The cap the extractor applies has to come from the published limits,
    or it drifts away from them again."""
    assert DEFAULT_USER_TEXT_MAX_CHARS == fleet_safe_char_budget()


def test_the_referral_that_lost_its_results_would_not_be_cut_now() -> None:
    """Referral 000482029135 was 26,585 characters and was cut at 16,000,
    which is where its FIT and CA 125 results were lost."""
    assert DEFAULT_USER_TEXT_MAX_CHARS > 26_585


def test_the_haiku_window_is_the_tightest_and_is_enforced() -> None:
    """Haiku is the default small model and has the smallest window of the
    five, so it is the one a budget set for another model overruns."""
    haiku = (
        "arn:aws:bedrock:eu-west-2:204065380870:inference-profile/"
        "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    assert window_for_model(haiku).usable_input_tokens == 180_000
    with pytest.raises(ContextBudgetExceeded):
        check_prompt_fits(haiku, estimated_tokens=190_000)
