"""Teach-time clash check: a new form must earn its place before it is saved.

A taught form is refused, in plain English, unless:
  1. it recognises the letter it was taught from;
  2. it does not clash with another active form for the organisation;
  3. it does not take over a labelled letter or another form's document.

A missing labelled set or a failed candidate lookup refuses the save too,
so the check can never be skipped silently.

Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
Risk R-B88CCFD6.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from libs.form_recognition.labelled_set import LabelledSetUnavailable
from libs.pipeline.form_schema_normalizer import FormSchema, FormSection
from libs.pipeline.form_schema_store import FormSchemaLookupError
from libs.pipeline.form_teach_guard import (
    TeachCheckRequest,
    TeachCheckUnavailable,
    TeachRefused,
    check_new_form,
    teach_problems,
)
from tests.form_recognition_corpus import (
    REPO,
    document_by_id,
    load_manifest,
    load_schemas,
)


def _schema(fingerprint: str) -> FormSchema:
    (schema,) = [s for s in load_schemas() if s.fingerprint == fingerprint]
    return schema


def _others(*exclude: str) -> list[FormSchema]:
    return [s for s in load_schemas() if s.fingerprint not in exclude]


def _blood_results_only() -> FormSchema:
    return FormSchema(
        schema_id="blood",
        fingerprint="blood-results-only",
        form_name="Blood results only",
        sections=[
            FormSection(
                section_id="bloods",
                section_type="free_text",
                label="Blood Results",
                start_pattern="Blood Results",
                items=[],
            )
        ],
        created_by="test",
    )


def test_a_well_taught_form_passes() -> None:
    schema = _schema("devon-uscp-gynae-v8")
    problems = teach_problems(
        schema, document_by_id("devon-gynae-docx"), _others("devon-uscp-gynae-v8")
    )
    assert problems == []


_POSITIVES = {
    "devon-uscp-gynae-v8": "devon-gynae-docx",
    "devon-breast-s1-v3-5": "devon-breast-docx",
    "sfh-gynae-2ww-v1": "sfh-gynae-production-deid",
    "nhs-ers-clinical-information-v1": "ers-production-deid",
}


@pytest.mark.parametrize("fingerprint", sorted(_POSITIVES))
def test_re_saving_every_taught_form_from_its_own_document_passes(
    fingerprint: str,
) -> None:
    problems = teach_problems(
        _schema(fingerprint),
        document_by_id(_POSITIVES[fingerprint]),
        _others(fingerprint),
    )
    assert problems == []


def test_a_form_that_does_not_match_its_own_letter_is_refused() -> None:
    schema = _schema("devon-breast-s1-v3-5")
    problems = teach_problems(schema, document_by_id("lung"), _others())
    assert problems and "does not match the letter it was taught from" in problems[0]


def test_a_copy_of_an_active_form_clashes_with_it() -> None:
    gynae = _schema("sfh-gynae-2ww-v1")
    copy = replace(gynae, fingerprint="sfh-gynae-copy", schema_id="copy")
    problems = teach_problems(
        copy, document_by_id("sfh-gynae-production-deid"), _others()
    )
    assert problems and "looks too like" in problems[0]
    assert gynae.form_name in problems[0]


def test_a_form_that_takes_over_a_labelled_letter_is_refused() -> None:
    letter_like = "Notes\n\n## Blood Results (Last 2m)\n\n| FBC | Hb 120 |\n"
    problems = teach_problems(_blood_results_only(), letter_like, _others())
    assert any("letter-gynae" in problem for problem in problems)


def test_problems_are_plain_ascii() -> None:
    problems = teach_problems(
        _schema("devon-breast-s1-v3-5"), document_by_id("lung"), _others()
    )
    assert problems
    for problem in problems:
        assert problem.isascii()


def _request(schema: FormSchema, text: str) -> TeachCheckRequest:
    return TeachCheckRequest(schema=schema, source_text=text, organization_id="RK5")


def test_check_new_form_refuses_with_a_plain_message() -> None:
    client = MagicMock()
    client.run.return_value = []
    with pytest.raises(TeachRefused) as refused:
        check_new_form(
            client, _request(_schema("devon-breast-s1-v3-5"), document_by_id("lung"))
        )
    assert "Nothing was saved." in str(refused.value)


def test_check_new_form_passes_a_good_form() -> None:
    client = MagicMock()
    client.run.return_value = []
    schema = _schema("devon-uscp-gynae-v8")
    check_new_form(client, _request(schema, document_by_id("devon-gynae-docx")))


def test_a_failed_candidate_lookup_is_not_a_pass() -> None:
    client = MagicMock()
    client.run.side_effect = RuntimeError("graph down")
    schema = _schema("devon-uscp-gynae-v8")
    with pytest.raises(FormSchemaLookupError):
        check_new_form(client, _request(schema, document_by_id("devon-gynae-docx")))


def test_a_missing_labelled_set_is_not_a_pass() -> None:
    client = MagicMock()
    client.run.return_value = []
    schema = _schema("devon-uscp-gynae-v8")
    with patch(
        "libs.pipeline.form_teach_guard.labelled_documents",
        side_effect=LabelledSetUnavailable("gone"),
    ):
        with pytest.raises(TeachCheckUnavailable):
            check_new_form(client, _request(schema, document_by_id("devon-gynae-docx")))


def _fixture_dirs() -> set[str]:
    manifest = load_manifest()
    paths = [row["path"] for row in manifest["schemas"]]
    paths += [row["source"]["path"] for row in manifest["documents"]]
    paths.append("tests/fixtures/form_recognition/expected.json")
    return {"/".join(p.split("/")[:3]) for p in paths}


def test_the_core_api_image_ships_every_labelled_set_folder() -> None:
    dockerfile = (REPO / "infra/dockerfiles/Dockerfile.core-api").read_text()
    ignore = (REPO / ".dockerignore").read_text().splitlines()
    for folder in sorted(_fixture_dirs()):
        assert f"COPY {folder}/ /app/{folder}/" in dockerfile, folder
        assert f"!{folder}/**" in ignore, folder


def test_an_empty_source_letter_is_refused() -> None:
    with pytest.raises(TeachRefused) as refused:
        check_new_form(MagicMock(), _request(_schema("devon-uscp-gynae-v8"), "  "))
    assert "letter" in str(refused.value)
