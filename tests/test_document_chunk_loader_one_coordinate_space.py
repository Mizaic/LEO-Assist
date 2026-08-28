"""The model and the span resolver must read the same text.

``sentences`` is what the windowed extractor shows the model.
``encounter_text`` is where ``SpanResolver`` looks the quote up again, where
ConText decides the assertion, and where lab-value recovery scans for
results. When those two disagree the model can quote a phrase that cannot
then be found, and ``SpanResolver`` fails open to ``(0, len(term))`` -- which
lands on the bundle's first line, a ``--- Document: ... ---`` banner. ConText
then reads that banner instead of the clinical sentence and the persisted
assertion is decided by the wrong text.

Stripping still belongs in ``bundle_fingerprint``: the attachment differs
between referrals of the same form, so fingerprinting it would stop the
taught :FormSchema ever binding. That is a separate boundary and these tests
pin it in place.

Atlas trace:
  DO: DO-728930A1
  DI: DI-16CE412B, DI-B5C78811
"""

from __future__ import annotations

from libs.pipeline.document_chunk_loader import (
    bundle_fingerprint,
    build_document_chunk_state,
)

_GP_FORM_CHUNK = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n"
    "Section A: cancer type suspected\nCervix [X] Ovary [ ]"
)

# Two of the five production referrals carry clinical content here that
# appears nowhere else in the bundle: a blood panel with reference-range
# flags, and a current medication list naming an anticoagulant.
_ATTACHMENT_CHUNK = (
    "--- Document: Clinical Information.pdf ---\n"
    "Findings\nInvestigations and Results\n"
    "05/06/2026 Serum iron level\n8.8 umol/l\nBelow low reference limit\n"
    "Current Medication\nApixaban 5mg tablets\n"
    "Dosage: Take one tablet twice a day. This is an anticoagulant"
)


def _rows(*texts: str) -> list[dict]:
    return [
        {
            "chunk_id": f"chunk-{i}",
            "text": text,
            "ordinal": i,
            "char_start": None,
            "char_end": None,
        }
        for i, text in enumerate(texts)
    ]


def _state() -> dict:
    return build_document_chunk_state(_rows(_GP_FORM_CHUNK, _ATTACHMENT_CHUNK))


def test_every_sentence_is_findable_in_encounter_text() -> None:
    """The resolver can locate anything the model was shown.

    This is the invariant the whole coordinate space rests on. Asserting it
    per sentence rather than on total length means a failure names the chunk
    that diverged.
    """
    state = _state()
    encounter_text = state["encounter_text"]
    for sentence in state["sentences"]:
        raw = sentence["text_raw"]
        assert raw in encounter_text, (
            f"sentence {sentence['sentence_id']} was shown to the model but "
            f"cannot be found in encounter_text, so any term the model quotes "
            f"from it resolves to offset 0 -- the document banner. "
            f"Missing text starts: {raw[:60]!r}"
        )


def test_attachment_results_reach_the_resolver() -> None:
    """A result only the attachment carries survives into encounter_text."""
    encounter_text = _state()["encounter_text"]
    for fragment in ("Serum iron level", "8.8 umol/l", "Below low reference limit"):
        assert fragment in encounter_text, (
            f"{fragment!r} is in the referral but not in encounter_text, so "
            f"lab-value recovery and ConText cannot see it"
        )


def test_attachment_medication_reaches_the_resolver() -> None:
    """An anticoagulant changes what happens next; it must not be dropped."""
    encounter_text = _state()["encounter_text"]
    assert "Apixaban 5mg tablets" in encounter_text
    assert "anticoagulant" in encounter_text


def test_fingerprint_still_ignores_the_attachment() -> None:
    """Schema binding is unaffected: the attachment stays out of the hash.

    The attachment differs between referrals of the same form. If it reached
    the fingerprint, each referral would hash differently and the taught
    schema would never be found.
    """
    with_attachment = bundle_fingerprint([_GP_FORM_CHUNK, _ATTACHMENT_CHUNK])
    form_only = bundle_fingerprint([_GP_FORM_CHUNK])
    assert with_attachment == form_only


def test_fingerprint_ignores_which_attachment_arrived() -> None:
    """Two referrals of one form hash alike however their attachments differ."""
    other_attachment = (
        "--- Document: Clinical Information.pdf ---\n"
        "Findings\nNo Information Provided\nUBRN: 0004 8182 7411"
    )
    assert bundle_fingerprint(
        [_GP_FORM_CHUNK, _ATTACHMENT_CHUNK]
    ) == bundle_fingerprint([_GP_FORM_CHUNK, other_attachment])
