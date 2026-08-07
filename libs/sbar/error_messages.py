"""Plain-English translator for SBAR LLM / API failures.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

The Bedrock Converse API surfaces failures as long, vendor-specific
exception strings such as:

    An error occurred (ValidationException) when calling the Converse
    operation: The model returned the following errors: Input is too
    long for requested model.

A QA reviewer or platform admin scanning the SBAR Playground cannot
act on that. This module maps the four known failure modes to plain
English at reading age 9-11, with a generic fallback for anything we
do not recognise so vendor strings never reach the UI.

See DI-LEO-AI-513 and DI-LEO-AI-516.
"""

from __future__ import annotations

from typing import TypedDict

# Stages a reviewer would recognise on the SBAR Playground.
StageName = str  # one of: situation, background, assessment, recommendation


class FriendlyError(TypedDict):
    """Wire-friendly error detail surfaced via SSE."""

    stage: StageName
    code: str
    message: str


# Known failure-mode codes. Keep this list in sync with VT-LEO-AI-514 TC-005.
KNOWN_ERROR_CODES: frozenset[str] = frozenset(
    {
        "input_too_long",
        "throttled",
        "access_denied",
        "network",
        "missing_section",
        "too_many_parts",
        "reduce_failed",
        "background_part_failed",
        "unknown",
    }
)


# Stage-aware suffixes so the same friendly text reads naturally for
# each SBAR section. Health-literacy rule: short, active, actionable,
# explain the term in everyday words first.
_STAGE_NOUNS: dict[str, str] = {
    "situation": "the Situation section",
    "background": "the Background section",
    "assessment": "the Assessment section",
    "recommendation": "the Recommendation section",
}


def _stage_noun(stage: str) -> str:
    return _STAGE_NOUNS.get(stage, "this section")


def _is_input_too_long(raw: str) -> bool:
    text = raw.lower()
    return (
        "input is too long" in text
        or "input too long" in text
        or "context length" in text
        or "max_tokens" in text
        and "exceed" in text
    )


def _is_throttled(raw: str) -> bool:
    text = raw.lower()
    return (
        "throttling" in text
        or "throttled" in text
        or "too many requests" in text
        or "rate limit" in text
        or "429" in text
    )


def _is_access_denied(raw: str) -> bool:
    text = raw.lower()
    return (
        "accessdenied" in text
        or "access denied" in text
        or "not authorized" in text
        or "unauthorizedoperation" in text
        or "expiredtoken" in text
        or "credentialerror" in text
        or "unrecognizedclientexception" in text
        or "invalid security token" in text
        or "security token included in the request is invalid" in text
    )


def _is_network(raw: str) -> bool:
    text = raw.lower()
    return (
        "endpointconnectionerror" in text
        or "connection" in text
        and ("refused" in text or "reset" in text or "timeout" in text)
        or "timed out" in text
        or "name resolution" in text
        or "ssl" in text
        and "error" in text
    )


def _is_missing_section(raw: str) -> bool:
    return raw.startswith("missing_")


_DIRECT_CODES: frozenset[str] = frozenset(
    {"too_many_parts", "reduce_failed", "background_part_failed"}
)


def _classify(raw: str) -> str:
    """Map a raw error string to one of KNOWN_ERROR_CODES."""
    if not raw:
        return "unknown"
    if raw in _DIRECT_CODES:
        return raw
    if _is_missing_section(raw):
        return "missing_section"
    if _is_input_too_long(raw):
        return "input_too_long"
    if _is_throttled(raw):
        return "throttled"
    if _is_access_denied(raw):
        return "access_denied"
    if _is_network(raw):
        return "network"
    return "unknown"


def _message_for(code: str, stage: str) -> str:
    noun = _stage_noun(stage)
    if code == "input_too_long":
        return (
            f"There was too much information for the model to read for {noun}. "
            "Try picking fewer records, or shorter ones, and run it again."
        )
    if code == "throttled":
        return (
            f"The AI service was busy when we tried to write {noun}. "
            "Wait a moment and run it again."
        )
    if code == "access_denied":
        return (
            f"We could not reach the AI service to write {noun} "
            "because the connection was refused. The team has been told."
        )
    if code == "network":
        return (
            f"We could not reach the AI service to write {noun} "
            "because of a network problem. Try again in a moment."
        )
    if code == "missing_section":
        return (
            f"The model did not return any text for {noun}. "
            "Try running it again, or pick different records."
        )
    if code == "too_many_parts":
        return (
            "This patient has too many records to summarise in one go. "
            "We can only split the work into 8 parts at most. "
            "Pick fewer records and run it again."
        )
    if code == "reduce_failed":
        return (
            f"We summarised the records in parts but could not merge "
            f"them into one {noun}. The parts are shown side by side "
            "below. Try running it again to get a single, joined-up "
            "version."
        )
    if code == "background_part_failed":
        return (
            f"One part of {noun} did not finish. The other parts are "
            "shown below. Try running it again."
        )
    return (
        f"Something went wrong while writing {noun}. "
        "Try running it again. If it keeps happening, tell the team."
    )


def translate_error(stage: str, raw: str) -> FriendlyError:
    """Translate a raw LLM / API error into a friendly wire payload.

    Args:
        stage: One of "situation", "background", "assessment",
            "recommendation".
        raw: The raw error string from invoke_llm_json or an
            uncaught exception's str(). May be vendor-specific.

    Returns:
        A FriendlyError dict suitable for the SSE wire and for
        persisting on the :Assessment node. The "message" field is
        plain English at reading age 9-11 and never echoes the raw
        vendor string for known failure modes.
    """
    code = _classify(raw or "")
    return {"stage": stage, "code": code, "message": _message_for(code, stage)}


class FriendlyNotice(TypedDict):
    """Wire-friendly notice (informational, not a failure)."""

    stage: StageName
    code: str
    message: str


def background_split_notice(message: str) -> FriendlyNotice:
    """Build a notice for the background_split code.

    Used when the partitioner has split the patient's records
    into multiple parts so the LLM can read all of them across
    several calls. No clinical detail is dropped.
    """
    return {"stage": "background", "code": "background_split", "message": message}


def background_record_split_notice(message: str) -> FriendlyNotice:
    """Build a notice for the background_record_split code.

    Used when one individual record was so long that the
    partitioner had to split it across two or more parts.
    """
    return {
        "stage": "background",
        "code": "background_record_split",
        "message": message,
    }


def background_part_failed_error(
    part_index: int,
    part_total: int,
    message: str,
) -> FriendlyError:
    """Build a per-part error for the background_part_failed code.

    Surfaced once per failed part so the reviewer can see which
    parts of a multi-part Background did not finish (e.g. "part 3
    of 5"), in addition to the aggregated "Background" stage error.
    The stage label is intentionally enriched with the part index
    so the playground groups it under Background without inflating
    the per-stage error count.
    """
    return {
        "stage": f"background:part {part_index} of {part_total}",
        "code": "background_part_failed",
        "message": (f"Background (part {part_index} of {part_total}): {message}"),
    }


def background_partition_overflow_error(parts_needed: int) -> FriendlyError:
    """Build the friendly overflow error when bin-packing > 8 parts.

    Returned when a patient is so record-rich that fitting every
    record inside the per-part token budget would need more than
    the 8-part hard cap. No LLM calls are made -- the reviewer is
    asked to pick fewer records and re-run.
    """
    return {
        "stage": "background",
        "code": "too_many_parts",
        "message": (
            "This patient has too many records to summarise in one go "
            f"(would need {parts_needed} parts; max is 8). Pick fewer "
            "records and run it again."
        ),
    }
