"""VT-LEO-AI-509 -- seed_prompt_configs SBAR context entries.

Verifies DI-LEO-AI-507 acceptance criteria for the seed script:

- One ``sbar_situation_context_<value>`` entry exists per
  SummarisationContext member.
- Each entry seeds at version 1 with the matching framing snippet
  from libs.sbar.events.SUMMARISATION_CONTEXT_PROMPTS.
- Each entry's description begins with one of the four allowed
  ``[<Group>]`` prefixes (Primary care / Secondary care / Statutory
  and social / Quality assurance) so the AI Instructions list groups
  the rows by clinical setting.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from libs.sbar.events import (  # noqa: E402
    SUMMARISATION_CONTEXT_GROUPS,
    SUMMARISATION_CONTEXT_PROMPTS,
    SummarisationContext,
)
from scripts.seed_prompt_configs import SEED_PROMPTS  # noqa: E402


SBAR_PREFIX = "sbar_situation_context_"
ALLOWED_GROUPS = {
    "Primary care",
    "Secondary care",
    "Statutory and social",
    "Quality assurance",
}


def _sbar_entries() -> list[dict]:
    return [p for p in SEED_PROMPTS if p["name"].startswith(SBAR_PREFIX)]


def test_one_seed_entry_per_summarisation_context() -> None:
    entries = _sbar_entries()
    assert len(entries) == len(list(SummarisationContext))
    names = {p["name"] for p in entries}
    expected = {f"{SBAR_PREFIX}{c.value}" for c in SummarisationContext}
    assert names == expected


def test_seed_entries_use_version_1() -> None:
    for p in _sbar_entries():
        assert p["version"] == 1, f"{p['name']} not at version 1"


def test_seed_system_prompt_matches_hardcoded_dict() -> None:
    by_name = {p["name"]: p for p in _sbar_entries()}
    for ctx in SummarisationContext:
        entry = by_name[f"{SBAR_PREFIX}{ctx.value}"]
        assert entry["system_prompt"] == SUMMARISATION_CONTEXT_PROMPTS[ctx]


def test_seed_descriptions_carry_group_prefix() -> None:
    """Each seeded SBAR-context PromptConfig must start its description
    with [<Group>] using one of the four allowed group labels so the
    AI Instructions categoriser routes it correctly."""
    pattern = re.compile(r"^\[([^\]]+)\]\s")
    by_name = {p["name"]: p for p in _sbar_entries()}
    for ctx in SummarisationContext:
        entry = by_name[f"{SBAR_PREFIX}{ctx.value}"]
        match = pattern.match(entry["description"])
        assert match is not None, (
            f"{entry['name']} description has no [<Group>] prefix: "
            f"{entry['description']!r}"
        )
        group = match.group(1).strip()
        assert group in ALLOWED_GROUPS, (
            f"{entry['name']} group {group!r} not in {ALLOWED_GROUPS}"
        )
        assert group == SUMMARISATION_CONTEXT_GROUPS[ctx], (
            f"{entry['name']} group {group!r} does not match "
            f"SUMMARISATION_CONTEXT_GROUPS[{ctx.value}]="
            f"{SUMMARISATION_CONTEXT_GROUPS[ctx]!r}"
        )


def test_seed_entries_carry_no_few_shot_or_schema() -> None:
    """SBAR context snippets are pure text framing - they don't drive
    a structured-output schema or have few-shot examples."""
    for entry in _sbar_entries():
        assert entry["output_schema"] == "{}"
        assert entry["few_shot_examples"] == []
        assert entry["max_few_shot"] == 0
        assert entry["verification"] is False
