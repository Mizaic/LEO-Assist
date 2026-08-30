"""ConText must not judge an entity by text that is not the entity.

``SpanResolver.resolve`` returns ``(0, len(term))`` when it cannot find a
surface form in the text it was given. Offsets are resolved against the
extraction text and consumed against the post-processing text, and those
are not the same string, so that fallback fires often: in the Sherwood
referral run 64bf2111 it fired for 17 of 19 entities.

Character 0 is the top of the letter, so every one of those entities was
judged against the document header. A header carries no negation cue, so
ConText left each assertion at ``present`` and the layer became inert.
One fact reached the graph as "On examination - abdominal pain on
palpation" at 0.988 confidence from the sentence "abdo full soft, non
tender, nil palp masses" -- a finding the letter denies. The model itself
had normalised that text to "abdomen soft non-tender", so only the
assertion was wrong, and ConText is the layer meant to catch exactly
that.

The rule under test: ConText locates an entity by its own text. When the
offsets it is handed do not contain that text it re-finds it, and when
the text is not in the document at all the entity is flagged unresolved
rather than silently passing as present.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
"""

from __future__ import annotations

from libs.ner.context_engine import apply_context_detection_to_dicts

# The shape of a real referral letter: a header, then the narrative.
DOC = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n\n"
    "| Sherwood Forest Hospitals (NHS) Trust URGENT SUSPECTED CANCER REFERRAL |\n\n"
    "Section C: Further Clinical details\n"
    "abdo full soft, non tender, nil palp masses. no pv bleeding.\n"
)

NEGATED = "abdo full soft, non tender, nil palp masses"


def _entity(text: str, start: int, end: int) -> dict:
    return {
        "text": text,
        "start": start,
        "end": end,
        "entity_type": "finding",
        "assertion": "present",
    }


def test_the_zero_offset_fallback_does_not_blind_context() -> None:
    """The exact signature seen in run 64bf2111: start 0, end len(text)."""
    ent = _entity(NEGATED, 0, len(NEGATED))
    assert DOC[0 : len(NEGATED)] != NEGATED, "fixture must reproduce the mismatch"
    apply_context_detection_to_dicts(DOC, [ent])
    assert ent["assertion"] == "absent", (
        "ConText judged the entity by the document header instead of "
        "re-finding its own text, so a denied finding stayed present"
    )


def test_correct_offsets_still_work() -> None:
    """The change must not disturb the entities that resolve properly."""
    start = DOC.index(NEGATED)
    ent = _entity(NEGATED, start, start + len(NEGATED))
    apply_context_detection_to_dicts(DOC, [ent])
    assert ent["assertion"] == "absent"


def test_text_absent_from_the_document_is_flagged_not_asserted() -> None:
    """An entity we cannot place must not pass silently as present.

    Leaving it present is the fail-open outcome: nothing in the record
    shows that the negation layer never got to see this fact.
    """
    ent = _entity("hallucinated finding not in the letter", 0, 37)
    apply_context_detection_to_dicts(DOC, [ent])
    assert ent.get("context_span_unresolved") is True, (
        "an entity that cannot be located must be flagged so the run can "
        "degrade rather than silently trusting the model's assertion"
    )
    assert ent["assertion"] == "assertion_unverified"


def test_a_present_finding_stays_present() -> None:
    """Re-finding text must not invent negation where there is none."""
    doc = "Section C\npatient reports dyspareunia for 1 year.\n"
    ent = _entity("dyspareunia for 1 year", 0, 22)
    apply_context_detection_to_dicts(doc, [ent])
    assert ent["assertion"] == "present"
    assert not ent.get("context_span_unresolved")


def test_deid_date_token_still_locates_raw_letter_span() -> None:
    """LLM entity text uses [DATE]; ConText searches the raw letter.

    Atlas: DI-B7A69F26 / VT-AA8ED00F
    """
    doc = (
        "Section C: Further Clinical details\n"
        "vaginal discharge- 10/7 yellowish in colour. no pv bleeding.\n"
    )
    ent = _entity("vaginal discharge- [DATE] yellowish in colour", 0, 44)
    apply_context_detection_to_dicts(doc, [ent])
    assert not ent.get(
        "context_span_unresolved"
    ), "a de-identified date token must still find the raw letter span"
    assert ent["assertion"] == "present"


def test_placeholder_without_surrounding_words_stays_unresolved() -> None:
    """A [DATE] token is not enough when the finding words are absent."""
    doc = "Section C\nlast smear November 2025. no pv bleeding.\n"
    ent = _entity("hepatosplenomegaly [DATE] with ascites", 0, 36)
    apply_context_detection_to_dicts(doc, [ent])
    assert ent.get("context_span_unresolved") is True
    assert ent["assertion"] == "assertion_unverified"
