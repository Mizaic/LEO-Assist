"""Recognition outcomes applied to a referral bundle's chunks.

There is no fallback by letter hash, by organisation and service, or by
whole bundle. Each recognised form is applied only to its own document.
A failed lookup is a failed recognition, never "not taught".

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6. Fail-closed boundary: UN-89E2AE36 / DI-B7A69F26.
"""

from __future__ import annotations

import re

import pytest

from libs.form_recognition.recogniser import (
    NotAForm,
    RecognitionFailed,
    Recognised,
    Unrecognised,
)
from libs.pipeline.form_recognition_apply import (
    bundle_match,
    document_scoped_text,
    primary_schema,
    recognise_texts,
    recognition_fields,
    rewrite_chunks,
)
from libs.pipeline.form_schema_store import (
    FormSchemaLookupError,
    has_taught_form_schema,
    reset_schema_cache,
)
from tests.form_recognition_corpus import bundle_chunks, load_manifest, load_schemas

_BUNDLES = {b["id"]: b for b in load_manifest()["bundles"]}
_UBRN = "ubrn-shaped-untaught-lower-gi-plus-ers"
_LETTER = "letter-plus-ers"
_TAUGHT = "taught-gynae-plus-ers"
_ERS = "nhs-ers-clinical-information-v1"
_MARKER = re.compile(r"--- Document:")


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_schema_cache()
    yield
    reset_schema_cache()


@pytest.fixture(scope="module")
def schemas():
    return load_schemas()


def _recognise(bundle_id: str, schemas) -> tuple[list[str], list]:
    chunks = bundle_chunks(_BUNDLES[bundle_id])
    return chunks, recognise_texts(chunks, lambda: schemas)


def _raise() -> list:
    raise FormSchemaLookupError("We could not check the taught forms.")


def test_untaught_form_plus_ers_is_unrecognised(schemas) -> None:
    _chunks, outcomes = _recognise(_UBRN, schemas)
    assert [type(o) for o in outcomes] == [Unrecognised, Recognised]
    assert bundle_match(outcomes) == "unrecognised"


def test_taught_form_plus_ers_is_recognised(schemas) -> None:
    _chunks, outcomes = _recognise(_TAUGHT, schemas)
    assert bundle_match(outcomes) == "recognised"
    assert primary_schema(outcomes).fingerprint == "sfh-gynae-2ww-v1"


def test_letter_plus_ers_is_recognised_on_the_ers_form(schemas) -> None:
    _chunks, outcomes = _recognise(_LETTER, schemas)
    assert isinstance(outcomes[0], NotAForm)
    assert bundle_match(outcomes) == "recognised"
    assert primary_schema(outcomes).fingerprint == _ERS


def test_a_failed_lookup_fails_every_document(schemas) -> None:
    chunks = bundle_chunks(_BUNDLES[_UBRN])
    outcomes = recognise_texts(chunks, _raise)
    assert [type(o) for o in outcomes] == [RecognitionFailed, RecognitionFailed]
    assert "could not" in outcomes[0].error
    assert bundle_match(outcomes) == "failed"


def test_no_documents_is_none() -> None:
    assert bundle_match([]) == "none"


def test_state_fields_never_use_the_old_match_values(schemas) -> None:
    for bundle_id in (_UBRN, _LETTER, _TAUGHT):
        chunks, outcomes = _recognise(bundle_id, schemas)
        fields = recognition_fields(chunks, outcomes)
        assert fields["form_schema_match"] in {
            "recognised",
            "unrecognised",
            "not_a_form",
            "failed",
        }
        kinds = [row["outcome"] for row in fields["form_recognition"]]
        assert kinds == [o.kind for o in outcomes]


def test_only_a_fully_recognised_bundle_counts_as_taught(schemas) -> None:
    chunks, outcomes = _recognise(_TAUGHT, schemas)
    assert has_taught_form_schema(recognition_fields(chunks, outcomes))
    chunks, outcomes = _recognise(_UBRN, schemas)
    unrecognised = recognition_fields(chunks, outcomes)
    assert not has_taught_form_schema(unrecognised)
    assert "completeness_groups" not in unrecognised
    assert unrecognised["form_layout_matched"] is False


def test_failed_lookup_fields_are_not_taught(schemas) -> None:
    chunks = bundle_chunks(_BUNDLES[_UBRN])
    outcomes = recognise_texts(chunks, _raise)
    fields = recognition_fields(chunks, outcomes)
    assert fields["form_schema_match"] == "failed"
    assert fields["form_schema_fingerprint"] == "none"
    assert not has_taught_form_schema(fields)


def test_ers_schema_does_not_touch_the_untaught_form(schemas) -> None:
    chunks, outcomes = _recognise(_UBRN, schemas)
    generic = rewrite_chunks(chunks, [NotAForm(), NotAForm()])
    rewritten = rewrite_chunks(chunks, outcomes)
    assert rewritten[0] == generic[0]


def test_taught_schema_is_applied_to_its_own_document(schemas) -> None:
    chunks, outcomes = _recognise(_TAUGHT, schemas)
    generic = rewrite_chunks(chunks, [NotAForm(), NotAForm()])
    assert rewrite_chunks(chunks, outcomes)[0] != generic[0]


def test_hits_come_only_from_recognised_documents(schemas) -> None:
    chunks, outcomes = _recognise(_UBRN, schemas)
    fields = recognition_fields(chunks, outcomes)
    ers_sections = {s.section_id for s in outcomes[1].schema.sections}
    hit_sections = {row["section_id"] for row in fields.get("section_hits") or []}
    assert hit_sections <= ers_sections


def test_seeding_text_keeps_only_the_recognised_document(schemas) -> None:
    chunks, outcomes = _recognise(_TAUGHT, schemas)
    text = "\n\n".join(chunks)
    rows = [outcome.to_dict() for outcome in outcomes]
    scoped = document_scoped_text(text, rows, "sfh-gynae-2ww-v1")
    assert len(scoped) == len(text)
    ers_start = text.index("--- Document:", 1)
    assert scoped[:ers_start] == text[:ers_start]
    assert not scoped[ers_start:].strip()
    assert scoped.count("\n") == text.count("\n")


def test_seeding_text_is_unchanged_when_documents_do_not_line_up() -> None:
    text = "--- Document: a.doc ---\nfirst"
    assert document_scoped_text(text, [], "x") == text


def test_document_markers_still_start_a_line(schemas) -> None:
    chunk = "\n".join(bundle_chunks(_BUNDLES[_TAUGHT]))
    outcomes = recognise_texts([chunk], lambda: schemas)
    (rewritten,) = rewrite_chunks([chunk], outcomes)
    assert len(_MARKER.findall(rewritten)) == 2
    for found in _MARKER.finditer(rewritten):
        assert found.start() == 0 or rewritten[found.start() - 1] == "\n"
