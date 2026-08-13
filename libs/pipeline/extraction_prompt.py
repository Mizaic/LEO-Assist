"""Shared extraction user-prompt builder (window-local + dual-path parity).

Atlas trace:
  DO: DO-292D7D75
  DI: DI-452DA083
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-292D7D75")
"""

from __future__ import annotations

CONTEXT_MODE_WINDOW_LOCAL = "window_local"
CONTEXT_MODE_FULL_DOCUMENT = "full_document"
_VALID_CONTEXT_MODES = frozenset(
    {CONTEXT_MODE_WINDOW_LOCAL, CONTEXT_MODE_FULL_DOCUMENT}
)


def normalise_context_mode(raw: str | None) -> str:
    """Return a supported context mode; default window_local."""
    mode = str(raw or CONTEXT_MODE_WINDOW_LOCAL).strip().lower()
    if mode not in _VALID_CONTEXT_MODES:
        return CONTEXT_MODE_WINDOW_LOCAL
    return mode


def context_label(context_mode: str) -> str:
    """User-message heading for the clinical context block."""
    if normalise_context_mode(context_mode) == CONTEXT_MODE_WINDOW_LOCAL:
        return "Window context"
    return "Encounter text"


def build_sentence_block(sentences: list[tuple[str, str]]) -> str:
    """Format ``[(sentence_id, text), ...]`` for the extractor user message."""
    return "\n".join(f"[{sid}] {text}" for sid, text in sentences)


def build_extraction_user_message(
    context_text: str,
    sentence_block: str,
    *,
    context_mode: str = CONTEXT_MODE_WINDOW_LOCAL,
    relevant_examples_block: str = "",
) -> str:
    """Build the extractor user message shared by pipeline and coding_worker."""
    label = context_label(context_mode)
    user_msg = (
        f"{label}:\n{context_text}\n\n" f"Sentences to process:\n{sentence_block}"
    )
    if relevant_examples_block:
        return f"{relevant_examples_block}\n\n{user_msg}"
    return user_msg
