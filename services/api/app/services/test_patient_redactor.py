"""Free-text redactor for the clone-from-real-patient flow.

Wraps :func:`libs.utils.deidentify.deidentify_text` (the production
clinical-text redactor used elsewhere in the codebase) into a small
class that the clone service can inject. Two responsibilities:

1. ``redact(text)`` -- replace every PII pattern (NHS number, postcode,
   phone, email, dates, names via SystmOne / honorific / all-caps
   regexes, and -- when a spaCy model is configured -- free-narrative
   first names) with safe placeholder tokens.

2. ``residual_phi(text)`` -- audit helper that returns the list of PII
   type tags still detectable AFTER ``redact``. The clone tests assert
   this is empty for the cloned subgraph; if it ever returns non-empty
   the clone is rejected and a clear error is raised so partial /
   silently-incorrect clones cannot land in the knowledge graph.

Why a thin wrapper?
-------------------
Callers don't need to know whether the underlying implementation is
regex, spaCy, presidio, or a remote service. Tests substitute a
no-op or aggressive stub. The clone service depends on the abstract
``redact(text)`` contract via duck typing.
"""

from __future__ import annotations

import logging
from typing import Protocol

from libs.utils.deidentify import deidentify_text, detect_phi

logger = logging.getLogger(__name__)


class TextRedactor(Protocol):
    """Minimal interface the clone service expects."""

    def redact(self, text: str) -> str: ...


class ResidualPhiError(ValueError):
    """Raised when the redacted text still contains detectable PII.

    The clone service catches this and refuses to write the encounter
    or document to the knowledge graph -- this is the loud-failure
    half of the "free text never carries PHI to the knowledge graph"
    invariant.
    """


class ClinicalTextRedactor:
    """Default redactor backed by :func:`deidentify_text`.

    Set the env var ``DEIDENTIFY_NER_MODEL`` (e.g. ``en_core_web_lg``)
    in the API service to enable the spaCy PERSON-NER second pass for
    free-narrative first names. When unset, regex patterns alone run.
    """

    def __init__(self, *, ner: bool | None = None) -> None:
        self._ner = ner

    def redact(self, text: str) -> str:
        if not text:
            return ""
        return deidentify_text(text, ner=self._ner)

    def residual_phi(self, redacted_text: str) -> list[str]:
        if not redacted_text:
            return []
        return detect_phi(redacted_text)

    def assert_clean(self, redacted_text: str) -> None:
        residual = self.residual_phi(redacted_text)
        if residual:
            raise ResidualPhiError(
                "redacted text still contains PII tags: "
                + ", ".join(sorted(set(residual)))
            )


class NoopRedactor:
    """Test-only redactor that returns text unchanged.

    Used by unit tests that want to exercise the clone wiring without
    pulling in spaCy. NEVER inject this in production code paths -- the
    router uses :class:`ClinicalTextRedactor` by default.
    """

    def redact(self, text: str) -> str:
        return text or ""

    def residual_phi(self, redacted_text: str) -> list[str]:
        return []

    def assert_clean(self, redacted_text: str) -> None:
        return None


def get_default_redactor() -> ClinicalTextRedactor:
    """Singleton accessor used by FastAPI dependencies."""
    return ClinicalTextRedactor()
