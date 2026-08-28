"""A blank row of a blood panel is not evidence that the test was done.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996

A taught referral form prints its blood panel whether or not the bloods were
taken, so a battery label sitting on an otherwise empty row says nothing
about this patient. Measured on five production referrals, eight facts on one
patient came from that panel: the bare labels "FBC", "LFT", "UE", "CRP",
"Bone", "Lipids", "Iron" and "Random Glucose" each landed as a procedure
asserted ``present``.

The result-gated normalisation in :mod:`libs.pipeline.form_schema_normalizer`
cannot catch these. It only fires for chunks a taught schema maps to an
``ordered_tests`` section, and a schema whose ``chunk_section_map`` is empty
leaves the panel chunk untouched. Forms differ per organisation and service,
so that map is the wrong place to carry a safety property. This guard works
from the letter text instead, so it holds for any form.

Two things it deliberately leaves alone:

  - **Conditions.** A problem-list row such as
    ``| Diastolic dysfunction (XaYYs) | [DATE] - Ongoing |`` reports no
    number, but the condition is real. Only test and measurement concepts
    are considered.
  - **Requested tests.** A blank row does support "this test is being asked
    for", so a ``planned`` assertion stands. It is ``present`` -- "this was
    done" -- that a blank row contradicts.

It also fails open on suppression: an entity we cannot locate in the text is
kept, because dropping a fact we cannot reason about would lose clinical
content silently. Over-keeping is visible to the reviewer; over-dropping is
not.
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.lab_result_evidence import row_reports_a_result

#: Labels that name a test or a measurement rather than a condition.
TEST_LABELS = frozenset(
    {
        "procedure",
        "observable_entity",
        "lab_test",
        "laboratory_procedure",
    }
)

#: Assertions that claim the test was actually performed.
_CLAIMS_PERFORMED = frozenset({"present", "historical", ""})

SUPPRESSED_REASON = (
    "The row this was read from does not show a result, so the letter does "
    "not say the test was done."
)


def line_containing(text: str, start: int, end: int) -> str:
    """Return the single line of *text* that the span ``[start, end)`` sits on.

    Returns an empty string when the span is outside the text, so callers can
    tell "no line" from "a blank line".
    """
    if not text:
        return ""
    try:
        begin = int(start)
        finish = int(end)
    except (TypeError, ValueError):
        return ""
    if begin < 0 or begin >= len(text):
        return ""
    finish = max(finish, begin)

    line_start = text.rfind("\n", 0, begin) + 1
    line_end = text.find("\n", min(finish, len(text)))
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end]


def _has_own_value(ent: dict[str, Any]) -> bool:
    """True when the entity carries a measurement of its own."""
    for key in ("value", "unit"):
        if str(ent.get(key) or "").strip():
            return True
    return False


def _is_test_mention(ent: dict[str, Any]) -> bool:
    label = str(ent.get("label") or ent.get("semantic_tag") or "").strip().lower()
    return label in TEST_LABELS


def _claims_performed(ent: dict[str, Any]) -> bool:
    assertion = str(ent.get("assertion") or "").strip().lower()
    return assertion in _CLAIMS_PERFORMED


def is_unresulted_test_mention(ent: dict[str, Any], encounter_text: str) -> bool:
    """True when *ent* is a test the letter does not show a result for."""
    if not _is_test_mention(ent):
        return False
    if not _claims_performed(ent):
        return False
    if _has_own_value(ent):
        return False

    if ent.get("start") is None or ent.get("end") is None:
        return False
    line = line_containing(encounter_text, ent["start"], ent["end"])
    if "|" not in line:
        # Prose. A blank table row is the only thing this guard judges.
        return False
    return not row_reports_a_result(line, [])


def suppress_unresulted_test_mentions(
    entities: list[dict[str, Any]], encounter_text: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split *entities* into the ones to keep and the ones to drop.

    Dropped entities are returned with a ``suppressed_reason`` so the run can
    say what it removed and why, rather than a fact quietly vanishing.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for ent in entities:
        if is_unresulted_test_mention(ent, encounter_text):
            marked = dict(ent)
            marked["suppressed_reason"] = SUPPRESSED_REASON
            dropped.append(marked)
        else:
            kept.append(ent)
    return kept, dropped
