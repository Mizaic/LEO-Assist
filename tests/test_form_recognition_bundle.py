"""Per-document bundle recognition and the fail-closed outcomes.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48. Risk R-B88CCFD6.
Fail-closed boundary: an error is RecognitionFailed, never "not a form".
"""

from __future__ import annotations

import pytest

from libs.form_recognition import recogniser as recogniser_module
from libs.form_recognition.bundle import split_documents
from libs.form_recognition.recogniser import (
    NotAForm,
    RecognitionFailed,
    Recognised,
    Unrecognised,
    bundle_needs_review,
    recognise_bundle,
    recognise_document,
)
from tests.form_recognition_corpus import (
    bundle_chunks,
    document_by_id,
    load_manifest,
    load_schemas,
)

_KINDS = {
    "recognised": Recognised,
    "unrecognised": Unrecognised,
    "not_a_form": NotAForm,
}
_BUNDLES = load_manifest()["bundles"]


@pytest.fixture(scope="module")
def schemas():
    return load_schemas()


def test_split_documents_uses_bundle_markers() -> None:
    text = "--- Document: a.doc ---\n\nfirst\n\n--- Document: b.pdf ---\n\nsecond"
    docs = split_documents(text)
    assert [(d.title, d.text.strip()) for d in docs] == [
        ("a.doc", "first"),
        ("b.pdf", "second"),
    ]


def test_split_documents_without_markers_is_one_document() -> None:
    assert [d.title for d in split_documents("just text")] == [""]


@pytest.mark.parametrize("bundle", _BUNDLES, ids=[b["id"] for b in _BUNDLES])
def test_bundle_gets_one_outcome_per_document(schemas, bundle: dict) -> None:
    results = recognise_bundle(bundle_chunks(bundle), schemas)
    assert [r.title for r in results] == [d["title"] for d in bundle["documents"]]
    for result, expected in zip(results, bundle["expect"]):
        assert isinstance(result, _KINDS[expected]), result.summary()
    assert bundle_needs_review(results) is bundle["expect_pause"]


def test_ers_schema_is_only_applied_to_the_ers_document(schemas) -> None:
    bundle = next(b for b in _BUNDLES if b["id"].startswith("ubrn-shaped"))
    specialty, ers = recognise_bundle(bundle_chunks(bundle), schemas)
    assert isinstance(specialty, Unrecognised)
    assert isinstance(ers, Recognised)
    assert ers.schema.fingerprint == "nhs-ers-clinical-information-v1"


def test_chunks_of_one_document_are_scored_together(schemas) -> None:
    text = document_by_id("sfh-gynae-synthetic")
    parts = text.split("\n\n")
    half = len(parts) // 2
    chunks = [
        "--- Document: gynae.doc ---\n\n" + "\n\n".join(parts[:half]),
        "\n\n".join(parts[half:]),
    ]
    (result,) = recognise_bundle(chunks, schemas)
    assert isinstance(result, Recognised)
    assert result.chunk_indexes == (0, 1)


def test_no_taught_forms_means_a_form_is_unrecognised() -> None:
    outcome = recognise_document(document_by_id("devon-gynae-docx"), [])
    assert isinstance(outcome, Unrecognised)
    assert outcome.best is None


def test_scoring_error_is_recognition_failed_not_a_letter(
    schemas, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("scorer exploded")

    monkeypatch.setattr(recogniser_module, "score_schema", boom)
    (result,) = recognise_bundle(
        ["--- Document: x.doc ---\n\n" + document_by_id("devon-gynae-docx")],
        schemas,
    )
    assert isinstance(result, RecognitionFailed)
    assert "scorer exploded" in result.error
    assert bundle_needs_review([result]) is True


def test_malformed_schema_is_recognition_failed(schemas) -> None:
    broken = [*schemas, object()]
    (result,) = recognise_bundle(
        ["--- Document: x.doc ---\n\n" + document_by_id("devon-gynae-docx")],
        broken,
    )
    assert isinstance(result, RecognitionFailed)


def test_only_recognised_and_letters_skip_review(schemas) -> None:
    letter = recognise_document(document_by_id("letter-gynae"), schemas)
    form = recognise_document(document_by_id("devon-gynae-docx"), schemas)
    assert bundle_needs_review([letter, form]) is False
    assert bundle_needs_review([]) is False
