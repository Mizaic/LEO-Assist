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

from .._rulebook_adapter import (
    text_channel_context_catalogue,
    text_channel_exclusion_catalogue,
    text_channel_regex,
)
from ..site_keys import ALL_SITES
from ..types import Signal, TimelineEvent

logger = logging.getLogger(__name__)

_TEXT_CONFIDENCE = 0.55
# Context-milestone signals are treated as supporting evidence, never
# as a diagnostic anchor. The consensus layer never promotes an
# episode to "auto" on the strength of a context signal alone -- the
# voting.assign_confidence_tier pinning enforces that regardless, but
# we keep the raw confidence modest so the aggregator does not
# overweight them either.
_CONTEXT_CONFIDENCE = 0.55


def _compile_patterns(
    raw_patterns: Iterable[str],
    *,
    site: str,
    label: str,
) -> tuple[re.Pattern[str], ...]:
    """Compile a list of regex strings, skipping malformed entries."""
    compiled: list[re.Pattern[str]] = []
    for raw in raw_patterns:
        if not raw or not isinstance(raw, str):
            continue
        try:
            compiled.append(re.compile(raw, re.IGNORECASE))
        except re.error as exc:
            logger.warning(
                "text_channel: skipping invalid regex %r for %s/%s: %s",
                raw,
                site,
                label,
                exc,
            )
    return tuple(compiled)


def _compile_site_catalogues() -> dict[str, tuple[re.Pattern[str], ...]]:
    """Compile every installed site's diagnosis-channel catalogue."""
    out: dict[str, tuple[re.Pattern[str], ...]] = {}
    for site in ALL_SITES:
        patterns = _compile_patterns(
            text_channel_regex(site),
            site=site,
            label="diagnosis",
        )
        if patterns:
            out[site] = patterns
    return out


def _compile_site_exclusion_catalogues() -> dict[str, tuple[re.Pattern[str], ...]]:
    """Compile every installed site's text-channel exclusion catalogue.

    An exclusion pattern suppresses the diagnosis signal for the
    matching (encounter, site) pair. Sites with no exclusion entries
    are omitted so the inner loop stays cheap.
    """
    out: dict[str, tuple[re.Pattern[str], ...]] = {}
    for site in ALL_SITES:
        patterns = _compile_patterns(
            text_channel_exclusion_catalogue(site),
            site=site,
            label="exclusion",
        )
        if patterns:
            out[site] = patterns
    return out


def _compile_site_context_catalogues() -> (
    dict[str, dict[str, tuple[re.Pattern[str], ...]]]
):
    """Compile every installed site's per-context-tag catalogues.

    Returns ``{site_key: {context_tag: (compiled,...)}}``. Sites with
    no context entries are omitted.
    """
    out: dict[str, dict[str, tuple[re.Pattern[str], ...]]] = {}
    for site in ALL_SITES:
        per_tag: dict[str, tuple[re.Pattern[str], ...]] = {}
        for tag, patterns in text_channel_context_catalogue(site).items():
            compiled = _compile_patterns(
                patterns,
                site=site,
                label=f"context/{tag}",
            )
            if compiled:
                per_tag[tag] = compiled
        if per_tag:
            out[site] = per_tag
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


def _context_citation(text: str, patterns: tuple[re.Pattern[str], ...]) -> str | None:
    """Return a short citation for a context-milestone match, or None."""
    for pat in patterns:
        m = pat.search(text)
        if m:
            matched = m.group(0)
            if len(matched) > 60:
                matched = matched[:57] + "..."
            return f"Context mention: '{matched}'"
    return None


def extract_text_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    """Emit text-channel signals from encounter free text.

    Two signal shapes are produced, both at channel="text":

    1. ``role="diagnosis"`` -- one per (encounter, site) when the
       encounter's ``text_snippet`` matches any of the site's
       ``regex_catalogue`` patterns. Intent ``suspected``; free text
       alone cannot distinguish confirmed from ruled-out.
       If the text matches the site's ``exclusion_catalogue``, **no**
       text-channel breast signals of any role are emitted for that
       encounter (diagnosis and context) -- a routine "breast neoplasm
       screening normal" letter must not seed referral_sent context
       from the same "NHS Breast Screening Programme" line that a true
       recall uses. A later encounter with recall/malignant codes is
       unaffected.

    2. ``role="context_milestone"`` -- one per (encounter, site,
       context_tag) when the text matches any of the site's
       ``context_role_catalogue[tag]`` patterns. The
       ``context_tag`` field names the canonical tag (one of
       ``CONTEXT_MILESTONE_TAGS``). DI-2C015ADE: these join the
       episode_engine LLM's own context milestones in the writer;
       their presence forces the owning EpisodeOfCare's
       confidence_tier off ``"auto"`` via
       voting.assign_confidence_tier.

    Returns ``[]`` when no rulebook has any catalogue. Downstream
    consensus logic still requires corroborating evidence from one
    of the coded channels before an episode reaches the ``auto``
    tier.
    """

    diagnosis_patterns = _compile_site_catalogues()
    exclusion_patterns = _compile_site_exclusion_catalogues()
    context_patterns = _compile_site_context_catalogues()
    if not diagnosis_patterns and not context_patterns:
        return []

    out: list[Signal] = []
    for event in events:
        text = event.text_snippet or ""
        if not text:
            continue
        for site_key, patterns in diagnosis_patterns.items():
            excl = exclusion_patterns.get(site_key, ())
            if excl and _first_match_citation(text, excl) is not None:
                continue
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
        for site_key, per_tag in context_patterns.items():
            excl = exclusion_patterns.get(site_key, ())
            if excl and _first_match_citation(text, excl) is not None:
                continue
            for tag, patterns in per_tag.items():
                citation = _context_citation(text, patterns)
                if citation is None:
                    continue
                out.append(
                    Signal(
                        channel="text",
                        encounter_id=event.encounter_id,
                        site_key=site_key,
                        role="context_milestone",
                        intent="suggested",
                        confidence=_CONTEXT_CONFIDENCE,
                        citation=citation,
                        context_tag=tag,
                    )
                )
    return out
