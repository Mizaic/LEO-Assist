"""Drift maths for the daily Azure spend check.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations


def drift_ratio(ours: float, theirs: float) -> float:
    """abs(theirs - ours) / ours. Ours is the baseline."""
    if ours <= 0 and theirs <= 0:
        return 0.0
    if ours <= 0:
        return 1.0
    return abs(float(theirs) - float(ours)) / float(ours)


def classify_status(
    token_drift: float,
    cost_drift: float,
    *,
    provisional: bool,
    failed: bool,
    token_warn: float = 0.15,
    cost_warn: float = 0.25,
) -> str:
    if failed:
        return "failed"
    if token_drift > token_warn:
        return "warn"
    if not provisional and cost_drift > cost_warn:
        return "warn"
    return "ok"


def our_total_tokens(input_tokens: int, output_tokens: int) -> int:
    return max(0, int(input_tokens)) + max(0, int(output_tokens))


def azure_total_tokens(prompt_tokens: int, completion_tokens: int) -> int:
    return max(0, int(prompt_tokens)) + max(0, int(completion_tokens))
