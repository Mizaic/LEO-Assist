"""The outcome of one form-structure detection, with its plain-English notice.

A fallback reader is far weaker than the model. The teacher must be told
when one stood in, so a thin proposal is never mistaken for the model's.

Atlas trace: DI-C1744ED5, DO-1C8E7598, R-98702FED
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DetectionReason = Literal[
    "model",
    "model_failed",
    "model_unreadable",
    "model_no_clinical",
]

_CHECK = "Check every section before you save."

_REASON_TEXT: dict[str, str] = {
    "model_failed": "Ask LEO could not reach the model.",
    "model_unreadable": "Ask LEO could not read the model's answer.",
    "model_no_clinical": "The model found no clinical sections.",
}

_FALLBACK_TEXT = "We used a simpler reader that can miss sections. " + _CHECK
_NOTHING_TEXT = "We could not find any sections. Add them by hand."
_CUT_TEXT = (
    "This letter is too long to read in full. "
    "We only read the first {chars:,} characters. " + _CHECK
)


@dataclass(frozen=True)
class FormDetection:
    """Sections proposed for a form, and how they were found."""

    sections: list[dict[str, Any]] = field(default_factory=list)
    completeness_rules: list[dict[str, Any]] = field(default_factory=list)
    reason: DetectionReason = "model"
    used_fallback: bool = False
    letter_cut: bool = False
    read_chars: int = 0

    @property
    def message(self) -> str:
        """Plain-English notice for the teacher; empty when nothing went wrong."""
        parts: list[str] = []
        if self.reason != "model":
            parts.append(_REASON_TEXT[self.reason])
            parts.append(_FALLBACK_TEXT if self.used_fallback else _NOTHING_TEXT)
        if self.letter_cut:
            parts.append(_CUT_TEXT.format(chars=self.read_chars))
        return " ".join(parts)

    def to_payload(self) -> dict[str, Any]:
        """The detection notice as the API returns it."""
        return {
            "reason": self.reason,
            "used_fallback": self.used_fallback,
            "letter_cut": self.letter_cut,
            "message": self.message,
        }
