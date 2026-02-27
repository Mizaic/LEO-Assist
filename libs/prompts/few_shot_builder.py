"""Build a few-shot example section from human-reviewed classification votes.

Called at classify time to inject verified examples into the encounter
classification system prompt.  Examples are drawn from disagreement cases
where at least one model was incorrect — the hardest decision-boundary cases
that teach the models most about *this* dataset's quirks.

Examples are fetched from Neo4j once and cached in-process for
``CACHE_TTL_SECONDS`` (default 30 min) so that classification runs don't
hammer the database.  The cache is bypassed when ``force_refresh=True`` is
passed, e.g. immediately after a new batch of votes is submitted.

Caching strategy:
    module-level dict  →  cheap, no Redis dependency
    TTL reset on force_refresh  →  fresh examples propagate within one run
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from libs.utils.deidentify import deidentify_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONTENT_TYPES = ["admin_only", "document_transfer", "clinical"]

CONTENT_TYPE_LABELS = {
    "admin_only": "admin_only",
    "document_transfer": "document_transfer",
    "clinical": "clinical",
}

#: Max characters from each encounter to include in the prompt.
#: Keeps prompts manageable; the full text can be long.
MAX_EXAMPLE_CHARS = 500

#: How many examples to pull per class.
DEFAULT_N_PER_CLASS = 2

#: How long (seconds) to keep the in-process example cache before re-fetching.
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes

# ---------------------------------------------------------------------------
# In-process cache
# ---------------------------------------------------------------------------

@dataclass
class _Cache:
    examples: dict[str, list[dict]] = field(default_factory=dict)
    fetched_at: float = 0.0
    count: int = 0

_cache = _Cache()
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_from_neo4j(n_per_class: int) -> dict[str, list[dict]]:
    """Pull voted examples from Neo4j, grouped by correct class."""
    from libs.neo4j_client.client import PatientGraphClient
    from libs.cypher.classification_vote_queries import GET_FEW_SHOT_EXAMPLES

    examples: dict[str, list[dict]] = {ct: [] for ct in CONTENT_TYPES}
    client = PatientGraphClient()
    try:
        with client.session() as session:
            for content_type in CONTENT_TYPES:
                rows = session.run(
                    GET_FEW_SHOT_EXAMPLES,
                    content_type=content_type,
                    limit=n_per_class,
                )
                for row in rows:
                    raw = (row["text"] or "").strip()
                    if not raw:
                        continue
                    # De-identify before the text enters the prompt or the UI
                    clean = deidentify_text(raw)
                    examples[content_type].append({
                        "text": clean[:MAX_EXAMPLE_CHARS],
                        "truncated": len(clean) > MAX_EXAMPLE_CHARS,
                        "notes": row.get("notes") or "",
                    })
    finally:
        client.close()
    return examples


def _get_examples(n_per_class: int, force_refresh: bool) -> dict[str, list[dict]]:
    """Return examples from cache or Neo4j, respecting TTL."""
    with _cache_lock:
        age = time.monotonic() - _cache.fetched_at
        if not force_refresh and _cache.examples and age < CACHE_TTL_SECONDS:
            return _cache.examples

    try:
        fresh = _fetch_from_neo4j(n_per_class)
    except Exception:
        logger.warning("Could not load few-shot examples from Neo4j", exc_info=True)
        return {ct: [] for ct in CONTENT_TYPES}

    total = sum(len(v) for v in fresh.values())
    with _cache_lock:
        _cache.examples = fresh
        _cache.fetched_at = time.monotonic()
        _cache.count = total

    logger.info("few_shot_builder: loaded %d example(s) from Neo4j", total)
    return fresh


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_few_shot_section(
    n_per_class: int = DEFAULT_N_PER_CLASS,
    force_refresh: bool = False,
) -> str:
    """Return a formatted Markdown section ready to append to the system prompt.

    Returns an empty string when fewer than ``n_per_class`` examples exist
    for any class, so the classifier degrades gracefully to zero-shot until
    enough votes have been collected.

    Args:
        n_per_class:    How many examples to include per content_type class.
        force_refresh:  Bypass the in-process cache and re-query Neo4j now.
    """
    examples = _get_examples(n_per_class, force_refresh)
    total = sum(len(v) for v in examples.values())

    if total == 0:
        return ""

    lines: list[str] = [
        "",
        "## Verified Examples",
        "",
        "The following examples were confirmed by human clinical reviewers from",
        "cases where the two classification models disagreed.  Use them to",
        "calibrate borderline cases specific to this GP dataset.",
        "",
    ]

    for ct in CONTENT_TYPES:
        ct_examples = examples[ct]
        if not ct_examples:
            continue
        lines.append(f"### {ct}")
        lines.append("")
        for i, ex in enumerate(ct_examples, 1):
            display = ex["text"]
            if ex["truncated"]:
                display += "…"
            lines.append(f"**Example {i}**")
            lines.append(f'Encounter text: "{display}"')
            if ex.get("notes"):
                lines.append(f"Reviewer note: {ex['notes']}")
            lines.append(f'→ {{"content_type": "{ct}"}}')
            lines.append("")

    return "\n".join(lines)


def example_counts(force_refresh: bool = False) -> dict[str, int]:
    """Return {content_type: n_examples} from the cache (or Neo4j if stale)."""
    examples = _get_examples(DEFAULT_N_PER_CLASS, force_refresh)
    return {ct: len(v) for ct, v in examples.items()}


def get_cached_examples(force_refresh: bool = False) -> dict[str, list[dict]]:
    """Return the raw example dicts (for the preview API endpoint)."""
    return _get_examples(DEFAULT_N_PER_CLASS, force_refresh)


def invalidate_cache() -> None:
    """Force the next classify call to re-fetch examples from Neo4j.

    Call this immediately after submitting a batch of new votes so the
    classifier picks them up without waiting for the TTL to expire.
    """
    with _cache_lock:
        _cache.fetched_at = 0.0
