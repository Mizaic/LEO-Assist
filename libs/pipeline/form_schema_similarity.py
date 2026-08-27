"""Cross-form section borrowing via fuzzy start_pattern similarity.

When auto-detecting sections for an unknown form, this module compares
each chunk of the new form against start_pattern strings from all known
FormSchema nodes. A strong match pre-populates the section from the
existing schema, saving an LLM call and re-using clinician-taught data.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

_SKIP_TYPES: frozenset[str] = frozenset({"admin", "template_noise"})

# Patterns shorter than this are too generic to borrow reliably.
_MIN_PATTERN_LEN = 4


@dataclass
class SectionMatch:
    """A known section that closely matches a chunk of a new form."""

    section: dict[str, Any]
    source_fingerprint: str
    source_org: str
    source_service: str
    source_form_name: str
    confidence: float


def find_similar_sections(
    chunks: list[str],
    known_schemas: list[dict[str, Any]],
    threshold: float = 0.85,
) -> list[SectionMatch]:
    """Return sections from known schemas that match chunks of a new form.

    For each section in each known schema, the best similarity score
    against any line in any chunk is computed. Sections whose best score
    meets or exceeds *threshold* are returned, deduplicated by
    start_pattern (highest confidence wins).

    Admin and template_noise sections are never borrowed.

    Args:
        chunks: Text chunks from the new form (one paragraph per entry).
        known_schemas: Dicts with keys ``fingerprint``, ``organization_id``,
            ``service_id``, ``form_name``, and ``sections`` (list of dicts
            matching FormSection structure).
        threshold: Minimum SequenceMatcher ratio to accept (0-1).

    Returns:
        Deduplicated list of SectionMatch objects, sorted by confidence desc.
    """
    if not chunks or not known_schemas:
        return []

    lines = _extract_lines(chunks)
    # key: normalised start_pattern -> best SectionMatch so far
    best: dict[str, SectionMatch] = {}

    for schema in known_schemas:
        for section in schema.get("sections") or []:
            match = _score_section(section, schema, lines, threshold)
            if match is None:
                continue
            key = section["start_pattern"].lower().strip()
            existing = best.get(key)
            if existing is None or match.confidence > existing.confidence:
                best[key] = match

    return sorted(best.values(), key=lambda m: m.confidence, reverse=True)


def merge_borrowed_and_detected(
    borrowed: list[SectionMatch],
    detected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge borrowed sections with LLM-detected sections.

    Borrowed sections take priority when both cover the same start_pattern.
    Borrowed sections gain a ``borrowed_from`` metadata key so the UI can
    show provenance and let the clinician override or skip.

    Args:
        borrowed: Matches returned by find_similar_sections().
        detected: Sections returned by the LLM detector.

    Returns:
        Combined list with borrowed sections first, remaining detected
        sections appended.
    """
    borrowed_patterns: dict[str, dict[str, Any]] = {}
    for match in borrowed:
        enriched = _enrich_with_provenance(match)
        key = match.section.get("start_pattern", "").lower().strip()
        borrowed_patterns[key] = enriched

    result: list[dict[str, Any]] = list(borrowed_patterns.values())
    for section in detected:
        key = section.get("start_pattern", "").lower().strip()
        if key not in borrowed_patterns:
            result.append(section)

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_lines(chunks: list[str]) -> list[str]:
    """Return all non-blank lines from chunks, stripped."""
    lines: list[str] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
    return lines


def _score_section(
    section: dict[str, Any],
    schema: dict[str, Any],
    lines: list[str],
    threshold: float,
) -> SectionMatch | None:
    """Return a SectionMatch if the section's pattern matches any line."""
    stype = section.get("section_type", "")
    if stype in _SKIP_TYPES:
        return None

    pattern = section.get("start_pattern", "").strip()
    if len(pattern) < _MIN_PATTERN_LEN:
        return None

    best_score = _best_line_score(pattern, lines)
    if best_score < threshold:
        return None

    return SectionMatch(
        section=section,
        source_fingerprint=schema.get("fingerprint", ""),
        source_org=schema.get("organization_id", ""),
        source_service=schema.get("service_id", ""),
        source_form_name=schema.get("form_name", ""),
        confidence=round(best_score, 4),
    )


def _best_line_score(pattern: str, lines: list[str]) -> float:
    """Return the highest SequenceMatcher ratio between pattern and any line."""
    pattern_lower = pattern.lower()
    best = 0.0
    for line in lines:
        score = _ratio(pattern_lower, _strip_pipes(line).lower())
        if score > best:
            best = score
        if best >= 1.0:
            break
    return best


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _strip_pipes(line: str) -> str:
    """Remove Markdown table pipes and excess whitespace."""
    return line.strip("|").strip()


def _enrich_with_provenance(match: SectionMatch) -> dict[str, Any]:
    """Return a copy of the section dict with borrowed_from metadata added."""
    enriched = dict(match.section)
    enriched["borrowed_from"] = {
        "fingerprint": match.source_fingerprint,
        "org": match.source_org,
        "service": match.source_service,
        "form_name": match.source_form_name,
        "confidence": match.confidence,
    }
    return enriched
