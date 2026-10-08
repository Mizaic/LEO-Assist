#!/usr/bin/env python3
"""Local Teach-this-form probe. No Neo4j write.

It fills skipped sections with their tick boxes and runs the save check,
as the product save does, so a green probe will not be refused on save.

Usage:
    .venv/bin/python .cursor/skills/teach-paused-form/scripts/probe_form_schema.py \\
        --letter tmp/teach-form/UBRN-letter.txt \\
        --schema tmp/teach-form/UBRN-schema.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.form_recognition.labelled_set import LabelledSetUnavailable
from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_checkbox_seed import seed_checkbox_entities
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    _yes_no_answer,
    apply_schema_to_text,
)
from libs.pipeline.form_schema_request import build_sections_from_request
from libs.pipeline.form_skip_boxes import fill_skip_section_boxes
from libs.pipeline.form_teach_guard import CHECK_UNAVAILABLE, teach_problems

_TICKED_LINE = re.compile(r"\[(?:X|x|\*|YES|yes)\]|\((?:X|x)\)")
_GUIDANCE = re.compile(
    r"points to remember|mastalgia|nice guideline|must not be rejected|"
    r"jess'?s rule|standard contract",
    re.IGNORECASE,
)


def _load_schema_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("schema"), dict):
        return raw["schema"]
    return raw


def schema_from_payload(payload: dict[str, Any]) -> FormSchema:
    body = _load_schema_payload(payload)
    sections = build_sections_from_request(list(body.get("sections") or []))
    return FormSchema(
        schema_id=str(body.get("schema_id") or "probe"),
        fingerprint=str(body.get("fingerprint") or "probe"),
        form_name=str(body.get("form_name") or "Probe"),
        sections=sections,
        created_by="probe_form_schema",
        completeness_groups=list(body.get("completeness_groups") or []),
    )


def vacant_completeness(groups: list[dict[str, Any]]) -> list[str]:
    vacant: list[str] = []
    for group in groups:
        name = str(group.get("name") or "unnamed")
        ids = group.get("concept_ids") or []
        cats = group.get("semantic_categories") or []
        members = group.get("members") or []
        if members:
            if all(
                not (m.get("concept_ids") or m.get("semantic_categories"))
                for m in members
                if isinstance(m, dict)
            ):
                vacant.append(name)
            continue
        if not ids and not cats:
            vacant.append(name)
    return vacant


def unmatched_ticks(letter: str, seeded_labels: set[str]) -> list[str]:
    misses: list[str] = []
    for line in letter.splitlines():
        if not _TICKED_LINE.search(line):
            continue
        if _GUIDANCE.search(line):
            continue
        # A ticked No on a Yes/No row is not a present clinical fact.
        if _yes_no_answer(line) == "no":
            continue
        # Table Yes/No columns without the words: empty then ticked is No.
        if re.search(r"\[\s*\]\s*\|\s*\[(?:X|x|\*)\]", line):
            continue
        # Stray tick pair with no clinical label.
        if re.match(r"^\|\s*\[(?:X|x|\*)\]\s*\|\s*\[\s*\]\s*\|", line.strip()):
            continue
        text = line.strip()
        if any(label.lower() in text.lower() for label in seeded_labels):
            continue
        misses.append(text[:160])
    return misses


def leaked_guidance(normalised: str) -> list[str]:
    leaks: list[str] = []
    for line in normalised.splitlines():
        if NON_EXTRACTABLE_MARKER in line:
            continue
        if _GUIDANCE.search(line):
            leaks.append(line.strip()[:160])
    return leaks


def clinical_sections(schema: FormSchema) -> int:
    skip = {"admin", "template_noise"}
    return sum(1 for section in schema.sections if section.section_type not in skip)


def save_check_problems(schema: FormSchema, letter: str) -> list[str]:
    """Run the product save check, without the graph clash part.

    The clash with other active forms for the organisation needs the
    graph, so only the product save (PUT) checks it.
    """
    try:
        return teach_problems(schema, letter, [])
    except LabelledSetUnavailable:
        return [CHECK_UNAVAILABLE]


def _seeded_rows(seeded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "pattern": row.get("text"),
            "entity_text": row.get("entity_text"),
            "assertion": row.get("assertion"),
        }
        for row in seeded
    ]


def probe(letter: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = _load_schema_payload(payload)
    filled = fill_skip_section_boxes(list(body.get("sections") or []), letter)
    schema = schema_from_payload({**body, "sections": filled})
    leaks = leaked_guidance(apply_schema_to_text(letter, schema))
    seeded = seed_checkbox_entities(letter, schema)
    misses = unmatched_ticks(letter, {str(row.get("text") or "") for row in seeded})
    clinical = clinical_sections(schema)
    problems = save_check_problems(schema, letter)
    green = bool(seeded) and not misses and not leaks and clinical > 0
    if not seeded and not _TICKED_LINE.search(letter):
        green = not leaks and clinical > 0
    return {
        "green": green and not problems,
        "form_name": schema.form_name,
        "fingerprint": schema.fingerprint,
        "section_count": len(schema.sections),
        "clinical_sections": clinical,
        "seeded": _seeded_rows(seeded),
        "unmatched_ticks": misses,
        "guidance_leaks": leaks,
        "vacant_completeness": vacant_completeness(schema.completeness_groups),
        "teach_problems": problems,
        "filled_sections": filled,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--letter", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    args = parser.parse_args()
    letter = args.letter.read_text(encoding="utf-8")
    payload = json.loads(args.schema.read_text(encoding="utf-8"))
    report = probe(letter, payload)
    json.dump(report, sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0 if report["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
