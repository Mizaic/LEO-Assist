"""Text-channel signal extractor (rulebook-driven regex catalogue).

Atlas trace:
  DI: DI-8A5FCF4F (12-component detector)
  DI: DI-FA3CE229 (RulebookBundle-backed runtime)

Reads each installed site's ``signals.text_channel.regex_catalogue``
and emits a ``Signal(channel="text")`` for every encounter whose
``text_snippet`` matches a site pattern. Patterns are compiled with
``re.IGNORECASE`` and are cached per-call so the inner loop stays
allocation-free across encounters.

Design notes:

* The text channel is deliberately low-confidence (0.55). A plain-text
  mention of "breast" on a GP consultation is weaker evidence than a
  SNOMED-coded breast investigation. The voting/aggregator layer is
  the place that decides whether the text signal alone is enough to
  activate an episode.
* Intent is always ``suspected``. Distinguishing confirmed vs ruled-out
  from free text requires LLM-grade parsing (negation scope, temporal
  qualifiers, hypothetical framing) and is deferred until we promote
  the text channel from "coding-triage hint" to "autonomous decision
  input". The ConText assertion layer already does that job for coded
  entities; the text channel stays conservative.
* Malformed regex strings are skipped with a warning so a single bad
  pattern cannot take the detector down.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from .._rulebook_adapter import text_channel_regex
from ..site_keys import ALL_SITES
from ..types import Signal, TimelineEvent

logger = logging.getLogger(__name__)

_TEXT_CONFIDENCE = 0.55


def _compile_site_catalogues() -> dict[str, tuple[re.Pattern[str], ...]]:
    """Compile every installed site's regex catalogue once per call."""
    out: dict[str, tuple[re.Pattern[str], ...]] = {}
    for site in ALL_SITES:
        patterns: list[re.Pattern[str]] = []
        for raw in text_channel_regex(site):
            if not raw or not isinstance(raw, str):
                continue
            try:
                patterns.append(re.compile(raw, re.IGNORECASE))
            except re.error as exc:
                logger.warning(
                    "text_channel: skipping invalid regex %r for site %s: %s",
                    raw,
                    site,
                    exc,
                )
        if patterns:
            out[site] = tuple(patterns)
    return out


def _first_match_citation(
    text: str, patterns: tuple[re.Pattern[str], ...]
) -> str | None:
    """Return a short citation of the first matching pattern, or None."""
    for pat in patterns:
        m = pat.search(text)
        if m:
            matched = m.group(0)
            if len(matched) > 60:
                matched = matched[:57] + "..."
            return f"Text mention: '{matched}'"
    return None


def extract_text_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """Emit one ``Signal(channel="text")`` per (encounter, site) when
    the encounter's ``text_snippet`` matches any of the site's regex
    patterns. Returns ``[]`` when no rulebook has a text catalogue.

    The signal's role is ``diagnosis`` and intent is ``suspected``
    because free-text alone cannot distinguish confirmed cancer from
    a ruled-out suspicion without assertion parsing. Downstream
    consensus logic still requires corroborating evidence from one of
    the coded channels before an episode reaches the ``auto`` tier.
    """

    site_patterns = _compile_site_catalogues()
    if not site_patterns:
        return []

    out: list[Signal] = []
    for event in events:
        text = event.text_snippet or ""
        if not text:
            continue
        for site_key, patterns in site_patterns.items():
            citation = _first_match_citation(text, patterns)
            if citation is None:
                continue
            out.append(
                Signal(
                    channel="text",
                    encounter_id=event.encounter_id,
                    site_key=site_key,
                    role="diagnosis",
                    intent="suspected",
                    confidence=_TEXT_CONFIDENCE,
                    citation=citation,
                )
            )
    return out
