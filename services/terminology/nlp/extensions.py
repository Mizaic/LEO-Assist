"""
Register custom spaCy extensions for the UK GP clinical NLP pipeline.

Extends medspaCy's default extensions (is_negated, is_historical, etc.) with
terminology linking, abbreviation handling, measurement extraction, and
additional context attributes specific to UK primary care.

Call ``set_extensions()`` once before building the pipeline.
"""

from spacy.tokens import Doc, Span, Token


def set_extensions() -> None:
    _set_token_extensions()
    _set_span_extensions()
    _set_doc_extensions()


# ── Token extensions ────────────────────────────────────────────────

_token_extensions: dict[str, dict] = {
    "expanded_form": {"default": None},
}


def _set_token_extensions() -> None:
    for attr, kwargs in _token_extensions.items():
        if not Token.has_extension(attr):
            Token.set_extension(attr, **kwargs)


# ── Span extensions ─────────────────────────────────────────────────

_span_extensions: dict[str, dict] = {
    # Entity linking (scispaCy pattern)
    "kb_ents": {"default": []},
    "long_form": {"default": None},
    # Terminology codes
    "cui": {"default": None},
    "snomed_code": {"default": None},
    "snomed_term": {"default": None},
    "icd10_codes": {"default": []},
    "read_code": {"default": None},
    # Linking metadata
    "linker_score": {"default": 0.0},
    "confidence": {"default": 0.0},
    "source": {"default": None},
    # Context: resolved (supplements medspaCy's is_negated, is_historical, etc.)
    "is_resolved": {"default": False},
    # Abbreviation flag
    "is_abbreviation": {"default": False},
    # Clinical measurements
    "value": {"default": None},
    "unit": {"default": None},
    "measurement_type": {"default": None},
    # Temporal
    "date_value": {"default": None},
    "temporal_type": {"default": None},
}


def _set_span_extensions() -> None:
    for attr, kwargs in _span_extensions.items():
        if not Span.has_extension(attr):
            Span.set_extension(attr, **kwargs)


# ── Doc extensions ──────────────────────────────────────────────────

_doc_extensions: dict[str, dict] = {
    "abbreviations": {"default": []},
}


def _set_doc_extensions() -> None:
    for attr, kwargs in _doc_extensions.items():
        if not Doc.has_extension(attr):
            Doc.set_extension(attr, **kwargs)
