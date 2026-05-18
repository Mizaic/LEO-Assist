"""Validation for clinical extraction scenario fixtures."""

from __future__ import annotations

import pathlib

from tests.helpers.clinical_extraction_scenario_loader import (
    fixture_dir,
    iter_cases,
    load_expected_strings,
    score_extraction_cases,
)

_EXPECTED_FORMATS = {
    "email_request",
    "referral_form_markdown",
    "referral_letter",
    "semi_structured_note",
}
_EXPECTED_SITES = {
    "brain_cns",
    "breast",
    "gynaecology",
    "haematology",
    "head_and_neck",
    "lower_gi",
    "lung",
    "non_site_specific",
    "prostate",
    "sarcoma",
    "skin",
    "upper_gi",
    "urology",
}
_HARD_DIFFICULTIES = {
    "abbreviation",
    "ambiguous_phrase",
    "boilerplate_footer",
    "checkbox_field_label",
    "fit_surface_form_variant",
    "incomplete_form",
    "lab_vitals_row",
    "negative_phrase",
    "placeholder_noise",
    "repeated_phrase",
    "surface_form_gap",
    "template_dense_form",
}
_TEMPLATE_RENDER_STATUSES = {
    "manual_transcription_required",
    "rendered_from_ooxml_fallback",
    "rendered_from_word_template",
}
_SYNTHETIC_PATIENT_KEYS = {
    "synthetic",
    "given_name",
    "family_name",
    "date_of_birth",
    "gender",
    "synthetic_nhs_number",
    "address",
    "home_phone",
    "gp_name",
    "practice_name",
    "practice_email",
    "decision_to_refer_date",
    "case_reference",
}
_BLOOD_RESULT_KEYS = {
    "concept_id",
    "display_name",
    "flag",
    "reference_high",
    "reference_low",
    "source",
    "test_name",
    "unit",
    "value",
}
_OBSERVABLE_KEYS = {"flag", "text", "unit", "value"}
_DOCUMENT_STYLE_MARKERS = {
    "Dear ",
    "Subject:",
    "SystmOne consultation entry",
    "## Referral criteria and clinical information",
}


def _read_fixture_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_expected_strings_contract_is_locked() -> None:
    """Gold fixture declares traceability, scope, normalisation, and threshold."""
    doc = load_expected_strings()
    assert doc["schema_version"] == 1
    assert doc["traceability"] == {
        "user_need": "UN-89E2AE36",
        "validation_test": "VAL-87173594",
        "verification_test": "VT-29880CC8",
    }
    assert doc["validation_scope"] == "extraction_only_terms_text_before_coding"
    assert doc["pass_threshold"]["overall_phrase_f1"] == 0.95
    assert doc["normalisation"] == {
        "casefold": True,
        "trim": True,
        "collapse_whitespace": True,
        "strip_terminal_punctuation": True,
    }


def test_cases_have_required_schema_and_markdown_files() -> None:
    """Each JSON case has the required keys and a matching Markdown source."""
    base = fixture_dir().parent.parent.parent
    seen: set[str] = set()
    for case in iter_cases():
        case_id = case["case_id"]
        source_path = base / case["source_markdown"]
        assert case_id not in seen
        assert source_path.exists(), case_id
        assert source_path.name == f"{case_id}.md"
        assert source_path.parent.name == "markdown"
        assert case["format"] in _EXPECTED_FORMATS
        assert case["site"] in _EXPECTED_SITES
        assert case["expected_strings"]
        assert case["review_status"] == "draft_for_clinician_approval"
        template_path = base / case["source_template_markdown"]
        assert template_path.exists(), case_id
        assert template_path.parent.name == "template_markdown"
        assert set(case["synthetic_patient"]) == _SYNTHETIC_PATIENT_KEYS
        assert case["synthetic_patient"]["synthetic"] is True
        assert case["blood_results"]["source_reference"] == (
            "configs/reference_ranges/nhs_haematology_defaults.json"
        )
        seen.add(case_id)


def test_template_sources_have_markdown_renderings() -> None:
    """Every referral template has a Markdown rendering or explicit PDF placeholder."""
    base = fixture_dir().parent.parent.parent
    doc = load_expected_strings()
    rendered_templates = doc["rendered_templates"]
    assert len(rendered_templates) == 20
    for row in rendered_templates:
        source_path = base / row["source_template"]
        rendered_path = base / row["rendered_markdown"]
        assert source_path.exists()
        assert rendered_path.exists()
        assert rendered_path.parent.name == "template_markdown"
        assert row["status"] in _TEMPLATE_RENDER_STATUSES


def test_scenarios_are_template_backed_documents() -> None:
    """Scenario Markdown is the completed document, not scenario metadata."""
    base = fixture_dir().parent.parent.parent
    for case in iter_cases():
        text = _read_fixture_text(base / case["source_markdown"])
        assert "## Template Source" not in text
        assert "## Synthetic Patient Details" not in text
        assert "## Template Excerpt Used" not in text
        assert "## Completed Template Fields For This Scenario" not in text
        assert "## Clinician Review Notes" not in text
        assert case["case_id"] not in text.splitlines()[0]
        assert "Template field" not in text
        assert "Scenario entry" not in text
        assert "extraction scenario" not in text.lower()
        assert "| Field | Value |" not in text
        assert any(marker in text for marker in _DOCUMENT_STYLE_MARKERS)


def test_corpus_uses_mixed_real_world_document_shapes() -> None:
    """Corpus must not collapse to one generated table shape."""
    base = fixture_dir().parent.parent.parent
    texts = {
        case["case_id"]: _read_fixture_text(base / case["source_markdown"])
        for case in iter_cases()
    }
    assert sum(text.startswith("| Field | Value |") for text in texts.values()) == 0
    assert sum("Dear " in text for text in texts.values()) >= 10
    assert sum("Subject:" in text for text in texts.values()) >= 5
    assert sum("SystmOne consultation entry" in text for text in texts.values()) >= 10
    assert sum("## Referral criteria and clinical information" in text for text in texts.values()) >= 20


def test_scenarios_include_synthetic_patient_details() -> None:
    """Scenario Markdown must include fake patient details, not metadata."""
    base = fixture_dir().parent.parent.parent
    for case in iter_cases():
        patient = case["synthetic_patient"]
        text = _read_fixture_text(base / case["source_markdown"])
        assert patient["given_name"].startswith("Synthetic Given ")
        assert patient["family_name"].startswith("Synthetic Family ")
        assert patient["synthetic_nhs_number"].startswith("SYN-NHS-")
        assert patient["practice_email"].endswith("@example.invalid")
        assert patient["given_name"] in text
        assert patient["family_name"] in text
        assert patient["synthetic_nhs_number"] in text
        assert "<Patient Name>" not in text


def test_expected_clinical_phrases_are_present_in_documents() -> None:
    """Expected clinical strings must appear in the authored document text."""
    base = fixture_dir().parent.parent.parent
    for case in iter_cases():
        observable_names = {item["text"] for item in case["expected_observables"]}
        clinical_phrases = [
            phrase
            for phrase in case["expected_strings"]
            if phrase not in observable_names
        ]
        text = _read_fixture_text(base / case["source_markdown"]).casefold()
        for phrase in clinical_phrases:
            assert phrase.casefold() in text, f"{case['case_id']}: {phrase}"


def test_scenarios_include_blood_results_with_values_and_units() -> None:
    """Markdown shows result values only; JSON keeps ranges and flags."""
    base = fixture_dir().parent.parent.parent
    for case in iter_cases():
        blood_results = case["blood_results"]
        results = blood_results["results"]
        observables = case["expected_observables"]
        text = _read_fixture_text(base / case["source_markdown"])
        assert "## Blood Results (Last 2m)" in text
        assert "| Panel | Date | Result |" in text
        assert "Reference range" not in text
        assert "| Flag |" not in text
        assert len(results) >= 16
        assert len(results) == len(observables)
        for result, observable in zip(results, observables):
            assert set(result) == _BLOOD_RESULT_KEYS
            assert set(observable) == _OBSERVABLE_KEYS
            assert result["test_name"] == observable["text"]
            assert str(result["value"]) == observable["value"]
            assert result["unit"] == observable["unit"]
            assert result["flag"] in {"high", "low", "normal"}
            assert result["unit"]
            assert result["test_name"] in case["expected_strings"]
            rendered = f"{result['display_name']} {result['value']} {result['unit']}"
            assert rendered in text


def test_markdown_does_not_embed_answer_key() -> None:
    """Scenario Markdown is the document only; JSON stores the answer key."""
    base = fixture_dir().parent.parent.parent
    for case in iter_cases():
        text = _read_fixture_text(base / case["source_markdown"])
        assert "## Expected Extracted Strings" not in text
        assert "## Must Not Extract" not in text
        assert "expected extraction strings" not in text.lower()
        for phrase in case.get("must_not_extract", []):
            assert f"- {phrase}" not in text


def test_v1_corpus_balances_pathways_formats_and_hard_cases() -> None:
    """The first corpus covers all planned sites, formats, and hard cases."""
    cases = iter_cases()
    formats = {case["format"] for case in cases}
    sites = {case["site"] for case in cases}
    hard_cases = [
        case
        for case in cases
        if _HARD_DIFFICULTIES.intersection(case.get("difficulty", []))
    ]
    assert len(cases) == 97
    assert _EXPECTED_SITES <= sites
    assert _EXPECTED_FORMATS <= formats
    for fmt in _EXPECTED_FORMATS:
        assert sum(case["format"] == fmt for case in cases) >= 5
    assert len(hard_cases) >= 8


def test_fixture_text_is_ascii_only() -> None:
    """Committed clinical extraction fixture text must stay ASCII."""
    paths = [
        fixture_dir() / "SCENARIO_SOURCE_MAP.md",
        fixture_dir() / "SCENARIO_MATRIX.md",
        fixture_dir() / "expected_strings.json",
        fixture_dir() / "reports" / "latest_extraction_f1_report.json",
        *sorted((fixture_dir() / "markdown").glob("*.md")),
        *sorted((fixture_dir() / "template_markdown").glob("*.md")),
    ]
    for path in paths:
        _read_fixture_text(path).encode("ascii")


def test_phrase_f1_scorer_matches_terms_text_contract() -> None:
    """Scorer compares extraction ``terms[].text`` strings before coding."""
    doc = load_expected_strings()
    cases = doc["cases"][:2]
    extracted = {case["case_id"]: list(case["expected_strings"]) for case in cases}
    result = score_extraction_cases(cases, extracted, doc["normalisation"])
    assert result["overall"]["precision"] == 1.0
    assert result["overall"]["recall"] == 1.0
    assert result["overall"]["f1"] == 1.0


def test_phrase_f1_scorer_reports_misses_and_extras() -> None:
    """Scorer records false positives and false negatives for reports."""
    doc = load_expected_strings()
    case = doc["cases"][0]
    extracted = {case["case_id"]: ["rectal bleeding", "extra phrase"]}
    result = score_extraction_cases([case], extracted, doc["normalisation"])
    row = result["by_case"][0]
    assert row["false_positive"] == 1
    assert row["false_negative"] == len(case["expected_strings"]) - 1
    assert row["extra_strings"] == ["extra phrase"]
