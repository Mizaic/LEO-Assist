"""LEO-local concept identifiers for guidance triggers and narrative actions.

Atlas trace:
  UN: UN-13601C35
  DI: DI-624F8D75
  DO: DO-AB0E235F
  VT: VT-ADF21FA9
  Risk: R-F2D0CDA7

Local concepts live as ``:Concept`` nodes with ``code_system='leo_local'``.
They are never emitted to GP EPR writeback as pretended SNOMED codes.
"""

from __future__ import annotations

import re
from typing import Literal

CODE_SYSTEM_LEO_LOCAL = "leo_local"

ConceptKind = Literal[
    "finding",
    "procedure",
    "narrative_action",
    "both",
]

VALID_CONCEPT_KINDS: frozenset[str] = frozenset(
    {"finding", "procedure", "narrative_action", "both"}
)

ActionKind = Literal["snomed_procedure", "narrative"]

VALID_ACTION_KINDS: frozenset[str] = frozenset({"snomed_procedure", "narrative"})

# Finding / trigger ids: LEO-LOCAL-<SLUG>
# Shared narrative action templates: LEO-ACT-<SLUG>
_LOCAL_ID_RE = re.compile(r"^LEO-(?:LOCAL|ACT)-[A-Z0-9]+(?:-[A-Z0-9]+)*$")

RESERVED_ACTION_TEMPLATES: dict[str, str] = {
    "LEO-ACT-ADVISE": "Advise (LEO narrative action)",
    "LEO-ACT-SAFETY-NET": "Safety-net advice (LEO narrative action)",
    "LEO-ACT-REFER-NARRATIVE": "Refer - narrative (LEO narrative action)",
}


def is_local_concept_id(concept_id: str) -> bool:
    """Return True when *concept_id* is in the LEO-local namespace."""
    return bool(_LOCAL_ID_RE.match((concept_id or "").strip()))


def validate_local_concept_id(concept_id: str) -> str:
    """Normalise and validate a local concept id.

    Raises:
        ValueError: When the id is empty or outside the allowed namespace.
    """
    normalised = (concept_id or "").strip().upper()
    if not normalised:
        raise ValueError("Local concept id is required.")
    if not is_local_concept_id(normalised):
        raise ValueError(
            "Local concept id must match LEO-LOCAL-* or LEO-ACT-* "
            "(uppercase letters, digits, hyphens)."
        )
    return normalised


def slugify_local_label(label: str, *, prefix: str = "LEO-LOCAL") -> str:
    """Build a candidate local concept id from a display label."""
    raw = re.sub(r"[^A-Za-z0-9]+", "-", (label or "").strip().upper())
    slug = re.sub(r"-+", "-", raw).strip("-")
    if not slug:
        raise ValueError("Cannot build a local concept id from an empty label.")
    if len(slug) > 48:
        slug = slug[:48].rstrip("-")
    candidate = f"{prefix}-{slug}"
    return validate_local_concept_id(candidate)


def validate_concept_kind(kind: str) -> str:
    """Validate concept_kind; raise ValueError when invalid."""
    value = (kind or "").strip().lower()
    if value not in VALID_CONCEPT_KINDS:
        raise ValueError(
            f"Invalid concept_kind {kind!r}. "
            f"Expected one of: {sorted(VALID_CONCEPT_KINDS)}."
        )
    return value


def validate_action_kind(kind: str | None) -> str:
    """Validate action_kind; default snomed_procedure when blank."""
    if kind is None or not str(kind).strip():
        return "snomed_procedure"
    value = str(kind).strip().lower()
    if value not in VALID_ACTION_KINDS:
        raise ValueError(
            f"Invalid action_kind {kind!r}. "
            f"Expected one of: {sorted(VALID_ACTION_KINDS)}."
        )
    return value


def is_narrative_action(action_kind: str | None) -> bool:
    """Return True when the action must not drive procedure-compliance checks."""
    return validate_action_kind(action_kind) == "narrative"


def force_exact_match_for_local(concept_id: str, include_descendants: bool) -> bool:
    """Local criteria never expand via IS_A; force exact match."""
    if is_local_concept_id(concept_id):
        return False
    return bool(include_descendants)
