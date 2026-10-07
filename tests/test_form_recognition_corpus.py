"""Labelled-set accuracy for the per-document form recogniser.

Every positive is recognised as its own form, every negative is
unrecognised, every letter is not a form, and nothing is ever matched to
the wrong form -- in each Word format, filled in, and flattened.

Atlas trace: DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48. Risk R-B88CCFD6.
"""

from __future__ import annotations

import pytest

from libs.form_recognition.recogniser import (
    NotAForm,
    Recognised,
    Unrecognised,
    recognise_document,
)
from tests.form_recognition_corpus import (
    documents,
    fill_in,
    flatten,
    load_manifest,
    load_schemas,
)

_DOCS = documents()
_POSITIVES = [d for d in _DOCS if d[2]["expect"] == "recognised"]
_IDS = [d[0] for d in _DOCS]
_POS_IDS = [d[0] for d in _POSITIVES]
_KINDS = {
    "recognised": Recognised,
    "unrecognised": Unrecognised,
    "not_a_form": NotAForm,
}


@pytest.fixture(scope="module")
def schemas():
    return load_schemas()


def test_manifest_covers_every_outcome_and_word_format() -> None:
    expects = {d[2]["expect"] for d in _DOCS}
    assert expects == {"recognised", "unrecognised", "not_a_form"}
    formats = {i.rsplit("-", 1)[-1] for i in _POS_IDS}
    assert {"docx", "doc", "rtf"} <= formats


@pytest.mark.parametrize(("doc_id", "text", "entry"), _DOCS, ids=_IDS)
def test_each_labelled_document_gets_its_expected_outcome(
    schemas, doc_id: str, text: str, entry: dict
) -> None:
    outcome = recognise_document(text, schemas)
    assert isinstance(outcome, _KINDS[entry["expect"]]), outcome.summary()
    if entry["expect"] == "recognised":
        assert outcome.schema.fingerprint == entry["schema"]


@pytest.mark.parametrize(("doc_id", "text", "entry"), _POSITIVES, ids=_POS_IDS)
def test_filled_in_positive_is_still_recognised(
    schemas, doc_id: str, text: str, entry: dict
) -> None:
    outcome = recognise_document(fill_in(text), schemas)
    assert isinstance(outcome, Recognised), outcome.summary()
    assert outcome.schema.fingerprint == entry["schema"]


@pytest.mark.parametrize(("doc_id", "text", "entry"), _POSITIVES, ids=_POS_IDS)
def test_flattened_positive_is_still_recognised(
    schemas, doc_id: str, text: str, entry: dict
) -> None:
    outcome = recognise_document(flatten(text), schemas)
    assert isinstance(outcome, Recognised), outcome.summary()
    assert outcome.schema.fingerprint == entry["schema"]


def test_zero_wrong_matches_across_every_variant(schemas) -> None:
    wrong: list[str] = []
    for doc_id, text, entry in _DOCS:
        for variant in (text, fill_in(text), flatten(text)):
            outcome = recognise_document(variant, schemas)
            if not isinstance(outcome, Recognised):
                continue
            if outcome.schema.fingerprint != entry.get("schema"):
                wrong.append(f"{doc_id} -> {outcome.schema.fingerprint}")
    assert wrong == []


def test_recognised_result_carries_its_evidence(schemas) -> None:
    text = dict((d[0], d[1]) for d in _DOCS)["devon-breast-docx"]
    outcome = recognise_document(text, schemas)
    assert isinstance(outcome, Recognised)
    best = outcome.best
    assert best.fingerprint == "devon-breast-s1-v3-5"
    assert best.matched and best.recall > 0.0 and best.precision > 0.0
    assert 0.0 <= best.order <= 1.0
    assert outcome.runner_up is not None
    assert outcome.runner_up.fingerprint != best.fingerprint
    evidence = outcome.to_dict()
    assert evidence["outcome"] == "recognised"
    assert evidence["best"]["matched_count"] == len(best.matched)
    assert evidence["best"]["missing"] == list(best.missing)


def test_unrecognised_result_names_the_closest_form(schemas) -> None:
    text = dict((d[0], d[1]) for d in _DOCS)["eoe-gynae-lookalike"]
    outcome = recognise_document(text, schemas)
    assert isinstance(outcome, Unrecognised)
    assert outcome.best is not None
    assert outcome.best.missing
    assert outcome.to_dict()["outcome"] == "unrecognised"


def test_manifest_records_its_known_gaps() -> None:
    assert load_manifest()["gaps"]
