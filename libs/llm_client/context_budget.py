"""How much each model can read, and a stop before we get there.

Every token and character budget in the platform used to be a number
somebody typed. ModelConfig in Neo4j carried prices and a model id but no
context window, so nothing could tell whether 16,000 characters was
cautious or reckless for the model actually answering. It was both: far
under the limit on the extraction path, where it silently cut clinical
letters, and unchecked on the agent paths, where the only thing that
noticed a breach was the provider's own error message after the call had
already failed.

This module holds the published limit for every model the platform is
configured to use, and refuses work that would come within ten percent of
it. The headroom matters: a prompt that exactly fills the window is
accepted by the provider and leaves nothing to answer with.

An undeclared model raises. That is deliberate. Pointing at a new
deployment is a change somebody has to make on purpose, and guessing a
limit for it would put the guess on a patient's referral.

Rule: .cursor/rules/fail-closed-boundary.mdc rule 2 -- a lookup has three
answers, and "we could not ask" is never "it fits".

Atlas trace:
  DI: DI-B7A69F26
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B7A69F26")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Work stops ten percent short of the published limit, so a prompt sized
# right up to the edge still leaves the model room to answer.
HEADROOM_FRACTION = 0.10

# Roughly four characters to a token for English clinical prose. Only ever
# used to decide whether to ask; never to decide what to cut.
_CHARS_PER_TOKEN = 4


class ContextBudgetError(RuntimeError):
    """Base for anything that stops a call on context grounds."""


class ModelWindowUnknown(ContextBudgetError):
    """Nobody has declared how much this model can read."""


class ContextBudgetExceeded(ContextBudgetError):
    """This call would come within the headroom of the model's limit."""


@dataclass(frozen=True)
class ModelWindow:
    """One model's published limits, and the budget we work to.

    ``context_window_tokens`` is the total shared by input, output and any
    reasoning. ``max_input_tokens`` and ``max_output_tokens`` are the
    separate ceilings; they usually do not add up to the total, because the
    vendor lets you spend the budget either way.
    """

    model_id: str
    context_window_tokens: int
    max_input_tokens: int
    max_output_tokens: int

    @property
    def usable_input_tokens(self) -> int:
        return int(self.max_input_tokens * (1 - HEADROOM_FRACTION))

    @property
    def usable_output_tokens(self) -> int:
        return int(self.max_output_tokens * (1 - HEADROOM_FRACTION))


# Vendor-published limits. Sources read 2026-09-18: the Microsoft Foundry
# model catalogue for the Azure models, the AWS Bedrock model cards for the
# Claude models. Adding a model here is how you make it usable.
PUBLISHED_WINDOWS: dict[str, ModelWindow] = {
    window.model_id: window
    for window in (
        ModelWindow("gpt-5-mini", 400_000, 272_000, 128_000),
        ModelWindow("gpt-5.4", 1_050_000, 922_000, 128_000),
        # The GPT-5.4 and 5.2 reasoning line. gpt-5.4-mini is what the
        # container apps actually run as the small model, where ModelConfig
        # still says gpt-5-mini.
        ModelWindow("gpt-5.4-mini", 400_000, 272_000, 128_000),
        ModelWindow("gpt-5.4-nano", 400_000, 272_000, 128_000),
        ModelWindow("gpt-5.4-pro", 1_050_000, 922_000, 128_000),
        ModelWindow("gpt-5.2", 400_000, 272_000, 128_000),
        # core-api's big model from 2026-10-09 (catalogue read that day).
        ModelWindow("gpt-5.6-sol", 1_050_000, 922_000, 128_000),
        # The chat preview is a fraction of the rest. Its 16,384 output
        # ceiling is below what Azure's reasoning expansion will ask for, so
        # it is the one that trips, and the fleet budget stays sized to it.
        ModelWindow("gpt-5.2-chat", 128_000, 111_616, 16_384),
        ModelWindow("claude-haiku-4-5-20251001-v1:0", 200_000, 200_000, 64_000),
        ModelWindow("claude-sonnet-4-6", 1_000_000, 1_000_000, 64_000),
        ModelWindow("claude-opus-4-6-v1", 1_000_000, 1_000_000, 128_000),
    )
}

# Bedrock is configured with inference-profile ARNs, and the profile is
# prefixed with the geography it runs in.
_GEO_PREFIX = re.compile(r"^(?:us|eu|au|jp|apac|global)\.")


def normalise_model_id(model_id: str) -> str:
    """Reduce a configured model id to the name the limits are filed under.

    Turns an ARN such as ``arn:aws:bedrock:eu-west-2:...:inference-profile/
    eu.anthropic.claude-haiku-4-5-20251001-v1:0`` into
    ``claude-haiku-4-5-20251001-v1:0``. An Azure deployment name is already
    in that shape and comes back unchanged.
    """
    name = str(model_id or "").strip().rsplit("/", 1)[-1].lower()
    name = _GEO_PREFIX.sub("", name)
    return name.removeprefix("anthropic.")


def window_for_model(model_id: str) -> ModelWindow:
    """The published window for this model.

    Raises:
        ModelWindowUnknown: No window is on file. The caller must stop: a
            guessed limit is the thing this module exists to prevent.
    """
    key = normalise_model_id(model_id)
    window = PUBLISHED_WINDOWS.get(key)
    if window is None:
        logger.error(
            "no context window declared for model %r (normalised to %r). "
            "Declare it in libs/llm_client/context_budget.py and seed it "
            "onto the matching ModelConfig before using this model.",
            model_id,
            key,
        )
        raise ModelWindowUnknown(
            f"No context window is declared for model {model_id!r}. "
            f"Add it to PUBLISHED_WINDOWS and seed it onto ModelConfig "
            f"before pointing the platform at this model."
        )
    return window


def fleet_safe_char_budget(reserve_tokens: int = 32_000) -> int:
    """Characters of clinical text that are safe whichever model answers.

    Sized to the tightest window on file, so a letter that passes here fits
    any model the platform can be pointed at. ``reserve_tokens`` leaves room
    for the system prompt, the few-shot library, and the answer.

    This replaces a hand-typed 16,000-character cap that cut referrals to
    roughly 1.5% of what the smallest model can read, and did it quietly.
    """
    smallest = min(w.usable_input_tokens for w in PUBLISHED_WINDOWS.values())
    return max(0, smallest - reserve_tokens) * _CHARS_PER_TOKEN


def estimate_tokens(text: str) -> int:
    """Rough token count for a prompt, rounding up."""
    if not text:
        return 0
    return -(-len(text) // _CHARS_PER_TOKEN)


def check_prompt_fits(
    model_id: str,
    *,
    estimated_tokens: int,
    what: str = "prompt",
) -> None:
    """Stop a call whose input would come within the headroom of the limit.

    Raises:
        ModelWindowUnknown: The model has no declared window.
        ContextBudgetExceeded: The input is over the working budget.
    """
    window = window_for_model(model_id)
    budget = window.usable_input_tokens
    if estimated_tokens <= budget:
        return
    message = (
        f"{what} is too big for {model_id}: about {estimated_tokens:,} input "
        f"tokens against a working budget of {budget:,} "
        f"({window.max_input_tokens:,} published, held "
        f"{int(HEADROOM_FRACTION * 100)}% back for the answer). "
        f"Split the work or shorten the input. Nothing was sent."
    )
    logger.error(message)
    raise ContextBudgetExceeded(message)


def check_output_request(
    model_id: str,
    *,
    requested_tokens: int,
    what: str = "requested answer",
) -> None:
    """Stop a call that asks for more output than the model can give.

    Raises:
        ModelWindowUnknown: The model has no declared window.
        ContextBudgetExceeded: The request is over the working budget.
    """
    window = window_for_model(model_id)
    budget = window.usable_output_tokens
    if requested_tokens <= budget:
        return
    message = (
        f"{what} is too big for {model_id}: {requested_tokens:,} output "
        f"tokens against a working budget of {budget:,} "
        f"({window.max_output_tokens:,} published, held "
        f"{int(HEADROOM_FRACTION * 100)}% back). Nothing was sent."
    )
    logger.error(message)
    raise ContextBudgetExceeded(message)
