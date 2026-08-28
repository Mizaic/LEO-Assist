"""Recognising a form must not depend on which attachment arrived with it.

``form_fingerprint`` answers one question: which printed form is this? The
e-RS attachment is not part of that form. It differs between referrals of
the same form, and since the coordinate-space fix it now reaches every
caller that passes ``encounter_text``:

  extraction seeding, the post-processing schema cache, the extraction
  quality gate, the review store, and the form-schema fallback lookup.

If the attachment reached the hash, one form would produce a different
fingerprint per referral, the taught :FormSchema would stop being found,
and ``score_document_quality`` would additionally brand every referral
``unknown_form_template`` and dock it the wrapper penalty for phrases
("Clinical Information Summary", "No Information Provided") that belong to
the attachment rather than the GP's form.

Stripping inside ``form_fingerprint`` keeps all of those callers correct
without any of them having to remember.

Atlas trace:
  DI: DI-0C766F85
"""

from __future__ import annotations

from libs.pipeline.document_quality import form_fingerprint, score_document_quality

_GP_FORM = (
    "--- Document: 23 Jun 2026 Two Week Wait Referral to Gynaecology .doc ---\n"
    "Section A: Gynaecological Cancer type suspected\n"
    "(Please put a X in appropriate boxes)\n"
    "Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
    "Section B: Signs/symptoms for 14-day rule criteria\n"
    "B1. Lesion suspicious of cancer of cervix Yes [X] No [ ]\n"
)

# Real shape: three of five production referrals carry only boilerplate
# here, two carry a blood panel or a medication list.
_ATTACHMENT_EMPTY = (
    "--- Document: Clinical Information.pdf ---\n"
    "NHS Confidential\nClinical Information Summary\n"
    "UBRN: 0004 8191 4514\n"
    "Past medical history\nNo Information Provided\n"
)

_ATTACHMENT_WITH_RESULTS = (
    "--- Document: Clinical Information.pdf ---\n"
    "NHS Confidential\nClinical Information Summary\n"
    "UBRN: 0004 8185 8468\n"
    "Findings\nInvestigations and Results\n"
    "05/06/2026 Serum iron level\n8.8 umol/l\nBelow low reference limit\n"
)


def test_fingerprint_ignores_the_attachment() -> None:
    """The taught schema is found whether or not an attachment came along."""
    assert form_fingerprint(_GP_FORM + "\n\n" + _ATTACHMENT_EMPTY) == form_fingerprint(
        _GP_FORM
    )


def test_fingerprint_is_the_same_for_two_referrals_of_one_form() -> None:
    """One form, two different attachments, one hash."""
    first = form_fingerprint(_GP_FORM + "\n\n" + _ATTACHMENT_EMPTY)
    second = form_fingerprint(_GP_FORM + "\n\n" + _ATTACHMENT_WITH_RESULTS)
    assert first == second


def test_fingerprint_unchanged_for_text_with_no_attachment() -> None:
    """Stripping is a no-op on anything that is not a referral bundle."""
    letter = "Dear colleague\n\nThank you for seeing this patient.\n"
    assert form_fingerprint(letter) == form_fingerprint(letter)
    assert form_fingerprint(letter) != form_fingerprint(_GP_FORM)


def test_quality_score_not_docked_for_attachment_boilerplate() -> None:
    """The wrapper penalty judges the GP's form, not the e-RS envelope.

    ``known_schema=False`` because a taught form bypasses the gate at 1.0
    and would hide the regression this test exists to catch.
    """
    bundle = score_document_quality(
        _GP_FORM + "\n\n" + _ATTACHMENT_EMPTY,
        few_shot_max_similarity=0.9,
        known_schema=False,
    )
    form_only = score_document_quality(
        _GP_FORM,
        few_shot_max_similarity=0.9,
        known_schema=False,
    )
    assert bundle.document_quality_score == form_only.document_quality_score
    assert "wrapper_admin_only" not in bundle.quality_reasons


def test_quality_reasons_identical_with_and_without_attachment() -> None:
    """Same form, same verdict, whatever envelope it arrived in."""
    bundle = score_document_quality(
        _GP_FORM + "\n\n" + _ATTACHMENT_WITH_RESULTS,
        few_shot_max_similarity=0.9,
        known_schema=False,
    )
    form_only = score_document_quality(
        _GP_FORM,
        few_shot_max_similarity=0.9,
        known_schema=False,
    )
    assert bundle.quality_reasons == form_only.quality_reasons
    assert bundle.form_fingerprint_id == form_only.form_fingerprint_id


def test_wrapper_penalty_still_fires_on_a_genuinely_empty_referral() -> None:
    """An admin-only referral must still be caught.

    The penalty is not being deleted, only aimed at the right text. A
    bundle whose primary document says nothing keeps its penalty.
    """
    admin_only = (
        "--- Document: 23 Jun 2026 Referral.doc ---\n"
        "Section A: reason for referral\n"
        "See attachment\n"
        "Section B: history\n"
        "No Information Provided\n"
    )
    quality = score_document_quality(
        admin_only,
        few_shot_max_similarity=0.9,
        known_schema=False,
    )
    assert "wrapper_admin_only" in quality.quality_reasons
