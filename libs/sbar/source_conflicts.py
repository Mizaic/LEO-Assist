"""Generic two-source clashes for SBAR, completeness, and appropriateness.

Atlas trace:
  DI: DI-C6D01509
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-C6D01509")

A conflict is two documented sides of the same question. The pipeline
does not pick a winner. Specialty, guideline, and form names stay out
of this module.
"""

from __future__ import annotations

from typing import Any

_PLEASE_CHECK = "Please check."


def conflicts_from_excluded_facts(
    rules: list[dict[str, Any]] | None,
) -> list[dict[str, str | list[str]]]:
    """Name a clash when a match also has a code that leaf excludes."""
    rows: list[dict[str, str | list[str]]] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        codes = [
            str(item).strip()
            for item in (rule.get("excluded_present") or [])
            if str(item).strip()
        ]
        if not codes:
            continue
        rows.append(
            {
                "description": (
                    "This match used one finding. Another record names a "
                    "finding this rule asks us to set aside."
                ),
                "sources": codes,
            }
        )
    return rows


def merge_source_conflicts(
    batches: list[list[dict[str, Any]] | None],
) -> list[dict[str, str | list[str]]]:
    """Deduplicate conflict rows by description, first batch first."""
    seen: set[str] = set()
    out: list[dict[str, str | list[str]]] = []
    for batch in batches:
        for row in _normalise_rows(batch):
            key = str(row["description"])
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def attach_conflicts(markdown: str, conflicts: list[dict[str, Any]] | None) -> str:
    """Append a Conflicts block when any rows exist."""
    extra = render_source_conflicts(conflicts)
    if not extra:
        return markdown
    return markdown.rstrip() + "\n" + "\n".join(extra)


def render_source_conflicts(
    conflicts: list[dict[str, Any]] | None,
) -> list[str]:
    """Markdown lines for a Conflicts block. Empty when there are none."""
    rows = _normalise_rows(conflicts)
    if not rows:
        return []
    lines = ["", f"### Conflicts ({len(rows)})"]
    for row in rows:
        desc = str(row["description"])
        if _PLEASE_CHECK.lower() not in desc.lower():
            desc = f"{desc.rstrip('.')} {_PLEASE_CHECK}"
        lines.append(f"- {desc}")
    return lines


def _normalise_rows(
    conflicts: list[dict[str, Any]] | None,
) -> list[dict[str, str | list[str]]]:
    rows: list[dict[str, str | list[str]]] = []
    for raw in conflicts or []:
        if not isinstance(raw, dict):
            continue
        description = str(raw.get("description") or "").strip()
        if not description:
            continue
        sources = [
            str(item).strip()
            for item in (raw.get("sources") or [])
            if str(item).strip()
        ]
        rows.append({"description": description, "sources": sources})
    return rows
