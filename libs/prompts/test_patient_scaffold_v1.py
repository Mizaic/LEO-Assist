"""Prompt for scaffolding a test patient from a single guideline rule.

The Knowledge > Test Patients tab calls this when a reviewer clicks
"Scaffold from rule" and picks one AppropriatenessRule. The scaffolder
gives Haiku:
  - the verbatim NICE recommendation,
  - the SNOMED criteria that must trigger the rule,
  - the action priority (2ww / urgent / routine),
  - any APPLIES_TO demographics constraints (age, sex).

Haiku returns a small JSON proposal that we map onto the existing
test-patient editor shape:
  - one or two short consultation notes that mention every trigger
    SNOMED in natural clinician phrasing,
  - a plausible age / sex within the constraints,
  - a short reviewer focus sentence that names the rule.

The expected SBAR is filled in deterministically by the service
afterwards (recommendation_text -> Recommendation, action_priority
-> expected_action_priority, picked rule -> matched_rule_ids), so
Haiku never has to invent the "ground truth" answer it is supposed
to be a test for.

Rules of the road:
  - The output must be JSON, exactly matching the schema below. Anything
    else fails the JSON parser and we surface the error.
  - The notes must be PLAIN ENGLISH a UK GP would write, NOT marketing
    copy. Short sentences, real abbreviations (PMHx, OE, HbA1c).
  - The notes MUST mention every trigger SNOMED preferred term verbatim
    or as a near-synonym (so the production NER pipeline can find them).
  - No identifying details ever -- no names, no addresses, no real DOB.
"""

from __future__ import annotations

import json
from typing import Iterable


_SCHEMA_HINT = """\
Return ONLY a JSON object that matches this schema:
{
  "demographics": {
    "age": <int between 18 and 95>,
    "sex": "male" | "female",
    "display_hint": "<one short phrase, e.g. 'retired postman with COPD'>"
  },
  "encounters": [
    {
      "source_label": "GP consultation" | "Hospital letter" | "Telephone triage" | "A&E note",
      "date_offset_days": <negative integer, days before today, e.g. -7>,
      "text": "<2-5 short sentences. UK GP style. PMHx, OE, plan abbreviations are fine.>"
    },
    ...  // 1 or 2 encounters total
  ],
  "reviewer_focus": "<one short sentence: what should the reviewer check?>"
}

Hard rules:
  - Every trigger term in the input MUST appear in at least one encounter's text
    (verbatim or as a clear clinical synonym, e.g. "blood in the urine" for
    "haematuria"). The production NER pipeline will be run against this text and
    is expected to recover every SNOMED id; missing terms break the test.
  - Demographics MUST satisfy every constraint in the input (e.g. age >= 60).
  - Plain English at UK reading age 11-13 wherever the audience is the patient,
    clinician shorthand is fine inside the note text itself.
  - NEVER include real names, addresses, dates of birth, NHS numbers, postcodes
    or phone numbers. Ages in years are fine.
  - Encounters must be in order, oldest first. date_offset_days is the offset
    from today (today = 0, last week = -7).
"""


def _format_constraints(constraints: list[dict] | None) -> str:
    """Render the APPLIES_TO constraints as plain English for the prompt."""
    if not constraints:
        return "(none -- pick any plausible adult)"
    parts: list[str] = []
    for c in constraints:
        field = (c.get("field") or "").strip()
        op = (c.get("operator") or "").strip()
        value = c.get("value")
        unit = (c.get("unit") or "").strip()
        if not field:
            continue
        bits = [field, op, str(value) if value is not None else ""]
        if unit:
            bits.append(unit)
        parts.append(" ".join(b for b in bits if b))
    return "; ".join(parts) if parts else "(none -- pick any plausible adult)"


def _format_triggers(triggers: Iterable[dict]) -> str:
    rows: list[str] = []
    for t in triggers or []:
        cid = (t.get("concept_id") or "").strip()
        term = (t.get("preferred_term") or "").strip()
        if not cid or not term:
            continue
        rows.append(f"  - {term} (SNOMED {cid})")
    if not rows:
        return "  (no specific triggers -- write notes consistent with the recommendation)"
    return "\n".join(rows)


SYSTEM_PROMPT = (
    "You are a UK clinical test-data assistant. Your job is to scaffold a "
    "synthetic test patient that should make a specific NICE-derived rule "
    "fire. You are NOT making a clinical decision -- you are writing a "
    "plausible record so QA can verify the rule engine. Treat every output "
    "as test data: never invent identifying details. "
    "Always return strictly valid JSON matching the user-supplied schema."
)


def build_user_prompt(
    *,
    rule_id: str,
    rule_label: str,
    recommendation_text: str | None,
    chapter_title: str | None,
    guideline_title: str | None,
    action_priority: str | None,
    triggers: list[dict],
    demographic_constraints: list[dict] | None = None,
) -> str:
    """Compose the user message Haiku sees.

    `triggers` is a list of {concept_id, preferred_term} dicts. They are
    rendered verbatim into the prompt so Haiku can echo each preferred
    term back into the encounter text.
    """
    return (
        "Scaffold a test patient that should fire this rule.\n"
        "\n"
        f"Rule id: {rule_id}\n"
        f"Rule label: {rule_label}\n"
        f"Guideline: {guideline_title or '(unknown)'}\n"
        f"Section: {chapter_title or '(unknown)'}\n"
        f"Recommendation: {recommendation_text or '(none on file)'}\n"
        f"Expected action priority: {action_priority or '(unspecified)'}\n"
        "Trigger SNOMED concepts (each MUST appear in at least one note):\n"
        f"{_format_triggers(triggers)}\n"
        "Demographic constraints from APPLIES_TO:\n"
        f"  {_format_constraints(demographic_constraints)}\n"
        "\n"
        f"{_SCHEMA_HINT}\n"
    )


def expected_field_set() -> set[str]:
    """The top-level keys the scaffolder service relies on.

    Used by the validator -- if Haiku omits any of these we treat the
    response as a hard failure rather than silently writing a half-baked
    test patient.
    """
    return {"demographics", "encounters", "reviewer_focus"}


def schema_example() -> str:
    """Round-tripped schema example for tests / docs."""
    example = {
        "demographics": {"age": 67, "sex": "female", "display_hint": "Retired teacher"},
        "encounters": [
            {
                "source_label": "GP consultation",
                "date_offset_days": -3,
                "text": (
                    "67yo female. C/O 2/52 painless visible haematuria. "
                    "No dysuria, no fever. PMHx: HTN. OE: abdo soft, no mass. "
                    "Urine dip: blood +++. Plan: 2WW urology referral."
                ),
            }
        ],
        "reviewer_focus": (
            "Confirm the 2WW urology rule fires on the haematuria mention."
        ),
    }
    return json.dumps(example, indent=2)
