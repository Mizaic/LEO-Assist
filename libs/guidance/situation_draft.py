"""Situation-aligned draft contract for NICE rule generation.

Atlas trace:
  DO: DO-BEFC4C67
  DI: DI-85AB13D7
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEFC4C67")

Compiles Always-true / Situations / Conditions drafts into schema_version 2
``logic_tree`` JSON so the bitmap compiler and Highlight Wizard stay stable.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, Literal

from pydantic import BaseModel, Field

SituationSource = Literal["structure", "heuristic", "tree", "single"]

_PATHWAY_KEY_RE = re.compile(r"^pw_[a-z0-9]+$")


def mint_pathway_key() -> str:
    """Mint a wizard-compatible pathway_key (pw_ + random suffix)."""
    return f"pw_{secrets.token_hex(4)}"


class LeafDraft(BaseModel):
    """One condition leaf as emitted by the LLM (pre-SNOMED resolve)."""

    model_config = {"extra": "allow"}

    kind: str
    term: dict[str, Any] | None = None
    field: str | None = None
    operator: str | None = None
    value: Any = None
    unit: str | None = None
    within_days: int | None = None
    children: list[dict[str, Any]] | None = None
    min: int | None = None
    source_row_text: str | None = None


class SituationShell(BaseModel):
    """One situation boundary plus the conditions that belong inside it."""

    text: str = ""
    start: int = 0
    end: int = 0
    source: SituationSource = "single"
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    pathway_key: str | None = None
    structure_children: list[dict[str, Any]] | None = None


class SituationDraft(BaseModel):
    """Wizard-shaped AI draft before compile to schema_version 2 logic_tree."""

    prerequisites: list[dict[str, Any]] = Field(default_factory=list)
    situations: list[SituationShell] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    priority: str | None = None
    schema_version: int = 2


def compile_situation_draft(draft: SituationDraft | dict[str, Any]) -> dict[str, Any]:
    """Compile a SituationDraft into a schema_version 2 logic_tree dict.

    Shape:
      - 0 situations -> AND of prerequisites (may be empty)
      - 1 situation -> AND[prerequisites..., situation.conditions...]
      - 2+ situations -> AND[prerequisites..., OR[AND pathway shells...]]
        or bare OR when there are no prerequisites
    """
    if not isinstance(draft, SituationDraft):
        draft = SituationDraft.model_validate(draft)

    prereqs = [dict(p) for p in draft.prerequisites]
    situations = list(draft.situations)

    if not situations:
        return {"kind": "AND", "children": prereqs}

    if len(situations) == 1:
        return {
            "kind": "AND",
            "children": prereqs + [dict(c) for c in situations[0].conditions],
        }

    pathway_children: list[dict[str, Any]] = []
    for situation in situations:
        key = situation.pathway_key or mint_pathway_key()
        if not _PATHWAY_KEY_RE.match(key):
            key = mint_pathway_key()
        situation.pathway_key = key
        pathway_children.append(
            {
                "kind": "AND",
                "pathway_key": key,
                "children": [dict(c) for c in situation.conditions],
            }
        )

    or_node: dict[str, Any] = {"kind": "OR", "children": pathway_children}
    if not prereqs:
        return or_node
    return {"kind": "AND", "children": prereqs + [or_node]}


def empty_situation_shells(
    shells: list[SituationShell] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Compile empty pathway AND shells for failed-extract stubs."""
    situations: list[SituationShell] = []
    for shell in shells:
        if isinstance(shell, SituationShell):
            situations.append(
                shell.model_copy(
                    update={"conditions": [], "pathway_key": shell.pathway_key}
                )
            )
        else:
            situations.append(
                SituationShell(
                    text=str(shell.get("text") or ""),
                    start=int(shell.get("start") or 0),
                    end=int(shell.get("end") or 0),
                    source=shell.get("source") or "single",  # type: ignore[arg-type]
                    conditions=[],
                    pathway_key=shell.get("pathway_key"),
                )
            )
    return compile_situation_draft(
        SituationDraft(prerequisites=[], situations=situations, actions=[])
    )


def draft_from_llm_payload(data: dict[str, Any]) -> SituationDraft | None:
    """Parse a SituationDraft from LLM JSON, or None if not that shape."""
    if not isinstance(data, dict):
        return None
    if "situations" not in data and "prerequisites" not in data:
        return None
    try:
        return SituationDraft.model_validate(data)
    except Exception:
        return None


def align_draft_to_skeleton(
    draft: SituationDraft,
    shells: list[SituationShell] | list[dict[str, Any]],
) -> SituationDraft:
    """Force situation arity/offsets to match the pre-built skeleton shells.

    Conditions are kept by index when the LLM returns a different count.
    Extra LLM situations are dropped; missing shells get empty conditions.
    """
    skeleton: list[SituationShell] = []
    for shell in shells:
        if isinstance(shell, SituationShell):
            skeleton.append(shell)
        else:
            skeleton.append(SituationShell.model_validate(shell))

    if not skeleton:
        return draft

    aligned: list[SituationShell] = []
    for i, shell in enumerate(skeleton):
        conditions: list[dict[str, Any]] = []
        if i < len(draft.situations):
            conditions = [dict(c) for c in draft.situations[i].conditions]
        aligned.append(
            SituationShell(
                text=shell.text,
                start=shell.start,
                end=shell.end,
                source=shell.source,
                conditions=conditions,
                pathway_key=shell.pathway_key
                or (
                    draft.situations[i].pathway_key
                    if i < len(draft.situations)
                    else None
                ),
                structure_children=shell.structure_children,
            )
        )
    return SituationDraft(
        prerequisites=[dict(p) for p in draft.prerequisites],
        situations=aligned,
        actions=[dict(a) for a in draft.actions],
        priority=draft.priority,
        schema_version=2,
    )


def tree_shells_from_threshold_rows(
    rows: list[str] | list[dict[str, Any]],
) -> list[SituationShell]:
    """Build ``source=\"tree\"`` situation shells from extracted table rows.

    Used when a recommendation points at an external threshold table and a
    dedicated extract step (or reviewer) supplies one row label per situation.
    Without rows, callers should keep a single tree/single shell instead.
    """
    shells: list[SituationShell] = []
    cursor = 0
    for row in rows:
        if isinstance(row, dict):
            text = str(row.get("text") or row.get("label") or "").strip()
        else:
            text = str(row).strip()
        if not text:
            continue
        start = cursor
        end = start + len(text)
        shells.append(
            SituationShell(
                text=text,
                start=start,
                end=end,
                source="tree",
                pathway_key=mint_pathway_key(),
            )
        )
        cursor = end + 1
    return shells
