"""
Combined abbreviation detector: Schwartz-Hearst in-text detection + GP dictionary.

Adapted from scispaCy ``abbreviation.py`` (Schwartz & Hearst 2003) and extended
with a pre-built dictionary of UK GP abbreviations loaded from JSON.

Sets ``Doc._.abbreviations``, ``Span._.long_form``, ``Span._.is_abbreviation``,
and ``Token._.expanded_form``.
"""


import json
import re
from collections import defaultdict
from os import path
from pathlib import Path
from typing import Iterable, Optional

from spacy.language import Language
from spacy.matcher import Matcher
from spacy.tokens import Doc, Span, Token

def _looks_like_clinical_code(text: str) -> bool:
    """Detect Read v2, CTV3, or similar clinical codes in parenthetical text."""
    text = text.strip()
    if len(text) < 4 or len(text) > 7:
        return False
    if not text[0].isalpha():
        return False
    has_digit = any(c.isdigit() for c in text)
    has_dot = "." in text
    if text[0] in ("X", "Y") and len(text.rstrip(".")) == 5:
        return True
    return has_digit or has_dot


def _find_abbreviation(
    long_form_candidate: Span, short_form_candidate: Span
) -> tuple[Span, Span] | None:
    """Schwartz-Hearst character-alignment algorithm."""
    long = " ".join([t.text for t in long_form_candidate])
    short = short_form_candidate.text

    long_idx = len(long) - 1
    short_idx = len(short) - 1

    while short_idx >= 0:
        short_char = short[short_idx].lower()
        if not short_char.isalnum():
            short_idx -= 1
            continue

        while long_idx >= 0 and long[long_idx].lower() != short_char:
            long_idx -= 1

        if long_idx < 0:
            return None

        if short_idx == 0:
            # First char of abbreviation must be start of a word in the long form
            if long_idx > 0 and long[long_idx - 1].isalnum():
                return None

        long_idx -= 1
        short_idx -= 1

    # Walk back to find the token boundary
    char_offset = len(long) - long_idx - 1
    cumulative = 0
    for i, token in enumerate(long_form_candidate):
        cumulative += len(token.text_with_ws)
        if cumulative > char_offset:
            start_idx = long_form_candidate.start + i
            return (
                long_form_candidate.doc[start_idx : long_form_candidate.end],
                short_form_candidate,
            )

    return None


def _is_plausible_abbreviation(text: str) -> bool:
    """Reject common English words / GP structural markers as abbreviation candidates."""
    if len(text) < 2 or len(text) > 6:
        return False
    if not text[0].isalpha():
        return False
    # Title-case single words (First, Episode, Mrs, New) are not abbreviations
    if text[0].isupper() and text[1:].islower():
        return False
    # All-lowercase words > 3 chars are not abbreviations
    if text.islower() and len(text) > 3:
        return False
    return True


def _filter_matches(
    matcher_output: list[tuple[int, int, int]], doc: Doc
) -> Iterable[tuple[Span, Span]]:
    """Classify parenthetical matches into (long, short) or (short, long) pairs."""
    candidates = []
    for _, start, end in matcher_output:
        if start >= len(doc) or end > len(doc):
            continue
        inner = doc[start + 1 : end - 1] if end - start > 2 else None
        if inner is None or len(inner) == 0:
            continue

        # Skip spans that bridge multiple parenthetical groups
        if any(t.text in ("(", ")") for t in inner):
            continue

        # Skip parentheticals that look like Read/CTV3 code annotations
        if _looks_like_clinical_code(inner.text):
            continue

        if len(inner) > 3:
            short_candidate = doc[max(0, start - 1) : start]
            if (
                len(short_candidate) == 1
                and 2 <= len(short_candidate.text) <= 10
                and sum(c.isalpha() for c in short_candidate.text)
                >= 0.5 * len(short_candidate.text)
            ):
                candidates.append((_find_abbreviation(inner, short_candidate)))
        else:
            short_text = inner.text
            if not _is_plausible_abbreviation(short_text):
                continue
            max_look = min(len(short_text) + 5, len(short_text) * 2)
            long_start = max(0, start - max_look)
            long_candidate = doc[long_start:start]
            candidates.append(_find_abbreviation(long_candidate, inner))

    return [c for c in candidates if c is not None]


@Language.factory(
    "abbreviation_detector",
    default_config={
        "abbreviations_path": None,
        "language_code": "en_gb",
    },
)
class AbbreviationDetector:
    """Schwartz-Hearst in-text abbreviation detection + GP dictionary lookup."""

    def __init__(
        self,
        nlp: Language,
        name: str = "abbreviation_detector",
        abbreviations_path: str | None = None,
        language_code: str = "en_gb",
    ):
        self.nlp = nlp
        self.name = name

        self._paren_matcher = Matcher(nlp.vocab)
        self._paren_matcher.add(
            "PARENS",
            [[{"TEXT": "("}, {"OP": "+"}, {"TEXT": ")"}]],
        )

        self._abbreviation_dict: dict[str, dict] = {}
        rules_path = abbreviations_path
        if rules_path is None:
            rules_path = str(
                Path(__file__).resolve().parents[1]
                / "resources"
                / language_code
                / "gp_abbreviations.json"
            )
        if path.exists(rules_path):
            with open(rules_path) as f:
                data = json.load(f)
            for entry in data.get("abbreviations", []):
                key = entry["abbrev"].lower()
                self._abbreviation_dict[key] = entry

    def __call__(self, doc: Doc) -> Doc:
        abbreviations: list[Span] = []
        long_form_map: dict[int, Span] = {}

        # --- Part 1: Schwartz-Hearst (in-text parenthetical definitions) ---
        matches = self._paren_matcher(doc)
        pairs = _filter_matches(matches, doc)

        global_matcher = Matcher(self.nlp.vocab)
        for long_form, short_form in pairs:
            long_form_map[short_form.start] = long_form
            global_matcher.add(
                f"ABBREV_{short_form.text}",
                [[{"TEXT": short_form.text}]],
            )
            abbreviations.append(short_form)

        # Find all other occurrences of detected abbreviations
        if len(global_matcher) > 0:
            global_matches = global_matcher(doc)
            for match_id, gstart, gend in global_matches:
                if gstart not in long_form_map:
                    rule_name = doc.vocab.strings[match_id]
                    abbrev_text = rule_name.replace("ABBREV_", "")
                    for lf_start, lf_span in long_form_map.items():
                        short_ref = doc[lf_start : lf_start + 1]
                        if short_ref.text == abbrev_text:
                            span = doc[gstart:gend]
                            span._.long_form = lf_span
                            span._.is_abbreviation = True
                            abbreviations.append(span)
                            break

        for short_form_span in [
            s for s in abbreviations if s.start in long_form_map
        ]:
            short_form_span._.long_form = long_form_map[short_form_span.start]
            short_form_span._.is_abbreviation = True

        # --- Part 2: GP dictionary lookup (pre-built abbreviations) ---
        for token in doc:
            lower = token.text.lower()
            if lower not in self._abbreviation_dict:
                continue
            entry = self._abbreviation_dict[lower]
            # Short ambiguous abbreviations (<=2 chars) must be all-uppercase
            # to avoid matching titles (Ms, Mr) and common words
            if len(token.text) <= 2 and not token.text.isupper():
                continue
            token._.expanded_form = entry["expansion"]
            span = doc[token.i : token.i + 1]
            if span._.long_form is None:
                span._.is_abbreviation = True
                abbreviations.append(span)

        doc._.abbreviations = abbreviations
        return doc
