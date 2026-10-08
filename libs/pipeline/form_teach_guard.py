"""Teach-time clash check for a new taught form.

Before an active form is saved it must:
  1. recognise the letter it was taught from;
  2. not clash with another active form for the organisation (the letter
     must still be recognised as the new form when they compete);
  3. not take over a labelled letter, or a labelled document of another
     form, in ``tests/fixtures/form_recognition``.

The check fails closed. A failed candidate lookup raises
``FormSchemaLookupError`` and a missing labelled set raises
``TeachCheckUnavailable``; neither is a pass.

When the letter has headings or tick boxes the form does not cover, the
refusal names the first few, so the teacher knows what to add.

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1 (named lines).
Risk R-B88CCFD6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from libs.form_recognition.labelled_set import (
    LabelledDocument,
    LabelledSetUnavailable,
    labelled_documents,
)
from libs.form_recognition.normalise import segments
from libs.form_recognition.recogniser import (
    Outcome,
    Recognised,
    explains_layout,
    recognise_bundle,
    recognise_document,
)
from libs.pipeline.form_schema_candidates import load_candidate_schemas
from libs.pipeline.form_schema_normalizer import FormSchema
from libs.pipeline.form_skip_boxes import printed_label

_NOTHING_SAVED = "Nothing was saved."
_NO_LETTER = (
    "Load the letter you taught this form from, then save again. " + _NOTHING_SAVED
)
_OWN_LETTER = (
    "This form does not match the letter it was taught from. Check the "
    "section headings, then save again."
)
_LEFTOVER = (
    "This form does not match the letter it was taught from. These lines on "
    "the letter are not in the form: {names}. Add them to a section, then "
    "save again."
)
_MAX_LEFTOVERS = 3
_CLASH = (
    'This form looks too like the taught form "{name}". Add the headings '
    "that make it different, then save again."
)
_TAKEOVER = (
    "This form would also match a document that is not this form ({doc_id}). "
    "Make the section headings more specific, then save again."
)
CHECK_UNAVAILABLE = (
    "We could not run the safety check for new forms, so nothing was saved. "
    "Please try again, and tell support if it keeps happening."
)
_MAX_TAKEOVERS = 3


class TeachRefused(ValueError):
    """The new form would not be recognised safely. Nothing was saved."""


class TeachCheckUnavailable(RuntimeError):
    """The check could not run, so the form was not saved."""


@dataclass(frozen=True)
class TeachCheckRequest:
    schema: FormSchema
    source_text: str
    organization_id: str


def _is_new_form(outcome: Outcome, fingerprint: str) -> bool:
    return (
        isinstance(outcome, Recognised)
        and outcome.schema is not None
        and outcome.schema.fingerprint == fingerprint
    )


def _clashing_name(outcome: Outcome, fingerprint: str) -> str:
    if isinstance(outcome, Recognised) and outcome.schema is not None:
        return outcome.schema.form_name or outcome.schema.fingerprint
    for score in (getattr(outcome, "best", None), getattr(outcome, "runner_up", None)):
        if score is not None and score.fingerprint != fingerprint:
            return score.form_name or score.fingerprint
    return "another form"


def _leftover_names(source_text: str, unexplained: Iterable[str]) -> list[str]:
    wanted = set(unexplained)
    names: list[str] = []
    for segment in segments(source_text):
        if segment.words not in wanted:
            continue
        name = printed_label(segment.raw).encode("ascii", "ignore").decode().strip()
        if name and name not in names:
            names.append(name)
    return names[:_MAX_LEFTOVERS]


def _own_letter_problem(alone: list[Outcome], source_text: str) -> str:
    for outcome in alone:
        best = getattr(outcome, "best", None)
        if best is None or explains_layout(best):
            continue
        names = _leftover_names(source_text, best.unexplained)
        if names:
            return _LEFTOVER.format(names=", ".join(names))
    return _OWN_LETTER


def _clash_problems(
    schema: FormSchema, source_text: str, others: list[FormSchema]
) -> list[str]:
    alone = recognise_bundle([source_text], [schema])
    own = [i for i, o in enumerate(alone) if _is_new_form(o, schema.fingerprint)]
    if not own:
        return [_own_letter_problem(alone, source_text)]
    together = recognise_bundle([source_text], [schema, *others])
    for index in own:
        if not _is_new_form(together[index], schema.fingerprint):
            name = _clashing_name(together[index], schema.fingerprint)
            return [_CLASH.format(name=name)]
    return []


def _guards(doc: LabelledDocument, fingerprint: str) -> bool:
    if doc.expect == "not_a_form":
        return True
    return doc.expect == "recognised" and doc.schema != fingerprint


def _takeover_problems(
    schema: FormSchema, labelled: Iterable[LabelledDocument]
) -> list[str]:
    taken = [
        doc.doc_id
        for doc in labelled
        if _guards(doc, schema.fingerprint)
        and isinstance(recognise_document(doc.text, [schema]), Recognised)
    ]
    return [_TAKEOVER.format(doc_id=doc_id) for doc_id in taken[:_MAX_TAKEOVERS]]


def teach_problems(
    schema: FormSchema,
    source_text: str,
    others: list[FormSchema],
    labelled: Iterable[LabelledDocument] | None = None,
) -> list[str]:
    """Return every reason not to save *schema*, in plain English."""
    rows = labelled_documents() if labelled is None else labelled
    others = [o for o in others if o.fingerprint != schema.fingerprint]
    return _clash_problems(schema, source_text, others) + _takeover_problems(
        schema, rows
    )


def check_new_form(client: object, req: TeachCheckRequest) -> None:
    """Raise unless the new form is safe to save. Returns None on a pass."""
    if not (req.source_text or "").strip():
        raise TeachRefused(_NO_LETTER)
    try:
        labelled = labelled_documents()
    except LabelledSetUnavailable as exc:
        raise TeachCheckUnavailable(CHECK_UNAVAILABLE) from exc
    others = load_candidate_schemas(client, req.organization_id)
    problems = teach_problems(req.schema, req.source_text, others, labelled)
    if problems:
        raise TeachRefused(f"{problems[0]} {_NOTHING_SAVED}")
