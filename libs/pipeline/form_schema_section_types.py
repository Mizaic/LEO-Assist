"""Guard the ``section_type`` vocabulary at every form-schema write boundary.

``_process_section_lines`` in :mod:`libs.pipeline.form_schema_normalizer`
dispatches on ``section_type``. A value outside the ``SectionType``
vocabulary falls through to a bare pass-through, so the deterministic
checkbox control does nothing at all and unticked criteria reach the LLM
as plain text. That is the false-positive hazard R-687E8027 is accepted
against, so an unrecognised value must never be stored.

The valid set is derived from ``SectionType`` rather than copied, so the
two can never drift apart.

Two behaviours, deliberately different:

* :func:`validate_section_type` raises. Use it where a value is about to
  be trusted -- the API request boundary, and conversion of a stored
  record back into a :class:`FormSection`.
* :func:`coerce_section_type` logs and substitutes. Use it only where the
  value is a *proposal* a clinician will review before it is saved, such
  as the LLM form-schema detector.

Atlas trace: DI-5C9CA57B, DO-D0C19842
"""

from __future__ import annotations

import logging
from typing import get_args

from libs.pipeline.form_schema_normalizer import SectionType

logger = logging.getLogger(__name__)

VALID_SECTION_TYPES: frozenset[str] = frozenset(get_args(SectionType))

# Free text is the only substitute that can neither fabricate a finding
# nor suppress one: it hands the lines to the LLM untouched.
SAFE_SECTION_TYPE = "free_text"

# Values seen in the wild that map cleanly onto the vocabulary. Keep this
# to observed evidence only -- a guessed alias is a silent wrong answer.
SECTION_TYPE_ALIASES: dict[str, str] = {
    "checkbox": "checkbox_multi",
}


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def is_valid_section_type(value: object) -> bool:
    """Return True when *value* is a section type the normaliser handles."""
    return _as_text(value) in VALID_SECTION_TYPES


def section_type_message(value: object) -> str:
    """Return a plain-English error naming the bad value and the choices."""
    options = ", ".join(sorted(VALID_SECTION_TYPES))
    shown = _as_text(value) or "(empty)"
    return (
        f"We do not recognise the section type {shown!r}, so we cannot read "
        "the tick boxes in that section safely. Choose one of: "
        f"{options}."
    )


def validate_section_type(value: object) -> str:
    """Return *value* when it is recognised, otherwise raise ``ValueError``."""
    text = _as_text(value)
    if text in VALID_SECTION_TYPES:
        return text
    raise ValueError(section_type_message(value))


def coerce_section_type(value: object, *, source: str) -> str:
    """Return the nearest recognised section type, logging any substitution.

    Args:
        value: The proposed section type.
        source: Where the proposal came from, for the warning log.

    Returns:
        A member of :data:`VALID_SECTION_TYPES`.
    """
    text = _as_text(value)
    if text in VALID_SECTION_TYPES:
        return text
    replacement = SECTION_TYPE_ALIASES.get(text.lower(), SAFE_SECTION_TYPE)
    logger.warning(
        "form_schema section_type %r from %s is not recognised; using %r",
        text or value,
        source,
        replacement,
    )
    return replacement


__all__ = [
    "SAFE_SECTION_TYPE",
    "SECTION_TYPE_ALIASES",
    "VALID_SECTION_TYPES",
    "coerce_section_type",
    "is_valid_section_type",
    "section_type_message",
    "validate_section_type",
]
