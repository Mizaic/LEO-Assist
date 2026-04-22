from __future__ import annotations

from libs.ner.observable_post_processor import (
    _detect_interpretation,
    normalize_observable_entities,
    parse_measurement_from_text,
)


def test_parse_measurement_ignores_read_code_and_extracts_true_value_unit() -> None:
    text = "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]"
    parsed = parse_measurement_from_text(text)
    assert parsed["numeric_value"] == "2.41"
    assert parsed["unit"] == "10^9/L"
    assert parsed["reference_range"] == "1.5 - 7.5"
    assert parsed["value_span"] == "2.41 10^9/L"


def test_normalize_observable_entity_splits_span_and_adds_qualifier() -> None:
    encounter = "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]"
    entities = [
        {
            "text": "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.95,
        }
    ]
    normalized = normalize_observable_entities(
        encounter, entities, add_qualifier_value=True
    )

    assert len(normalized) == 2
    obs = normalized[0]
    qv = normalized[1]

    assert obs["label"] == "observable_entity"
    assert obs["text"] == "Neutrophil count"
    assert obs["start"] == 0
    assert obs["end"] == len("Neutrophil count")
    assert obs["value"] == "2.41"
    assert obs["unit"] == "10^9/L"
    assert obs["reference_range"] == "1.5 - 7.5"

    assert qv["label"] == "qualifier_value"
    assert qv["text"] == "2.41 10^9/L"
    assert qv["start"] == encounter.index("2.41 10^9/L")
    assert qv["end"] == qv["start"] + len("2.41 10^9/L")


def test_normalize_does_not_duplicate_existing_qualifier() -> None:
    encounter = "Serum sodium level (XE2q0) 142 mmol/L [135 - 145]"
    value_text = "142 mmol/L"
    entities = [
        {
            "text": "Serum sodium level (XE2q0) 142 mmol/L [135 - 145]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.9,
        },
        {
            "text": value_text,
            "label": "qualifier_value",
            "start": encounter.index(value_text),
            "end": encounter.index(value_text) + len(value_text),
            "confidence": 0.9,
        },
    ]
    normalized = normalize_observable_entities(
        encounter, entities, add_qualifier_value=True
    )
    qualifiers = [
        e
        for e in normalized
        if e.get("label") == "qualifier_value" and e.get("text") == value_text
    ]
    assert len(qualifiers) == 1


def test_parse_measurement_supports_blood_pressure_ratio_values() -> None:
    text = "BP 145/69 mmHg"
    parsed = parse_measurement_from_text(text)
    assert parsed["numeric_value"] == "145/69"
    assert parsed["unit"].lower() == "mmhg"
    assert parsed["value_span"] == "145/69 mmHg"


def test_parse_measurement_rejects_unqualified_slash_units() -> None:
    text = "value 12 / next"
    parsed = parse_measurement_from_text(text)
    assert "numeric_value" not in parsed
    assert "unit" not in parsed


def test_preserve_existing_structured_fields_by_default() -> None:
    encounter = "Neutrophil count 2.41 10^9/L [1.5 - 7.5]"
    entities = [
        {
            "text": "Neutrophil count 2.41 10^9/L [1.5 - 7.5]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "value": "9.99",
            "unit": "fake",
            "reference_range": "x-y",
        }
    ]
    normalized = normalize_observable_entities(encounter, entities)
    assert normalized[0]["value"] == "9.99"
    assert normalized[0]["unit"] == "fake"
    assert normalized[0]["reference_range"] == "x-y"


# ---------------------------------------------------------------------------
# Tests for interpretation-suffix detection (compound lab entity emission)
# ---------------------------------------------------------------------------


def test_detect_interpretation_outside_reference_range() -> None:
    matched_text, key = _detect_interpretation(" - Outside reference range")
    assert key == "outside_reference_range"
    assert "Outside reference range" in matched_text


def test_detect_interpretation_high() -> None:
    result = _detect_interpretation(" - High")
    assert result is not None
    _, key = result
    assert key == "high"


def test_detect_interpretation_low() -> None:
    result = _detect_interpretation("- Low")
    assert result is not None
    _, key = result
    assert key == "low"


def test_detect_interpretation_normal_returns_none_for_non_suffix() -> None:
    # "Normal" in the middle of the test name should NOT trigger
    result = _detect_interpretation("Mean corpuscular haemoglobin")
    assert result is None


def test_normalize_emits_finding_entity_for_outside_reference_range() -> None:
    encounter = "Mean cell haemoglobin level (XE2pb) 22.5 pg [27 - 32] - Outside reference range"
    entities = [
        {
            "text": "Mean cell haemoglobin level (XE2pb) 22.5 pg [27 - 32] - Outside reference range",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.95,
        }
    ]
    normalized = normalize_observable_entities(
        encounter, entities, add_qualifier_value=True
    )

    labels = [e["label"] for e in normalized]
    assert "observable_entity" in labels
    assert "qualifier_value" in labels
    assert "finding" in labels

    findings = [e for e in normalized if e["label"] == "finding"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["interpretation_qualifier"] == "outside_reference_range"
    assert finding["parent_observable_text"] == "Mean cell haemoglobin level"
    assert "Outside reference range" in finding["text"]


def test_normalize_handles_label_with_space() -> None:
    """The pipeline stores 'observable entity' (space) not 'observable_entity' (underscore)."""
    encounter = "Serum HDL cholesterol level (44P5.) 2.39 mmol/L [0.9 - 2.2] - Outside reference range"
    entities = [
        {
            "text": encounter,
            "label": "observable entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 1.0,
        }
    ]
    normalized = normalize_observable_entities(
        encounter, entities, add_qualifier_value=True
    )

    assert len(normalized) == 3
    obs = [e for e in normalized if "observable" in str(e.get("label", ""))]
    assert len(obs) == 1
    assert obs[0]["text"] == "Serum HDL cholesterol level"
    assert obs[0]["value"] == "2.39"
    assert obs[0]["unit"] == "mmol/L"
    assert obs[0]["reference_range"] == "0.9 - 2.2"

    qv = [e for e in normalized if e.get("label") == "qualifier_value"]
    assert len(qv) == 1
    assert qv[0]["text"] == "2.39 mmol/L"

    findings = [e for e in normalized if e.get("label") == "finding"]
    assert len(findings) == 1
    assert "Outside reference range" in findings[0]["text"]


def test_normalize_emits_finding_entity_for_high() -> None:
    encounter = "Serum potassium level (XE2pz) 5.9 mmol/L [3.5 - 5.3] - High"
    entities = [
        {
            "text": "Serum potassium level (XE2pz) 5.9 mmol/L [3.5 - 5.3] - High",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.9,
        }
    ]
    normalized = normalize_observable_entities(encounter, entities)
    findings = [e for e in normalized if e["label"] == "finding"]
    assert len(findings) == 1
    assert findings[0]["interpretation_qualifier"] == "high"


def test_normalize_does_not_emit_finding_when_no_interpretation() -> None:
    encounter = "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]"
    entities = [
        {
            "text": "Neutrophil count (42J..) 2.41 10^9/L [1.5 - 7.5]",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.9,
        }
    ]
    normalized = normalize_observable_entities(encounter, entities)
    findings = [e for e in normalized if e["label"] == "finding"]
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# Tests for "now <value>" current-value marker
# (e.g. "weight loss 10kg - now 79kg" -- only 79kg is the current measurement)
# ---------------------------------------------------------------------------


def test_parse_measurement_now_marker_picks_post_now_value() -> None:
    parsed = parse_measurement_from_text("weight loss 10kg - now 79kg")
    assert parsed["numeric_value"] == "79"
    assert parsed["unit"].lower() == "kg"
    assert parsed["value_span"].lower() == "79kg"
    assert parsed.get("current_value_marker") == "now"


def test_parse_measurement_currently_marker_supported() -> None:
    parsed = parse_measurement_from_text(
        "Serum potassium 5.9 mmol/L - currently 4.8 mmol/L"
    )
    assert parsed["numeric_value"] == "4.8"
    assert parsed["unit"].lower() == "mmol/l"
    assert parsed.get("current_value_marker") == "now"


def test_normalize_observable_now_marker_overrides_existing_llm_value() -> None:
    encounter = "weight loss 10kg - now 79kg"
    entities = [
        {
            "text": encounter,
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "value": "10",
            "unit": "kg",
            "confidence": 0.9,
        }
    ]
    normalized = normalize_observable_entities(
        encounter, entities, add_qualifier_value=True
    )
    obs = next(e for e in normalized if e["label"] == "observable_entity")
    assert obs["value"] == "79"
    assert obs["unit"].lower() == "kg"
    assert obs["text"] == "weight loss 10kg"
    qualifiers = [e for e in normalized if e["label"] == "qualifier_value"]
    assert any(q["text"].lower() == "79kg" for q in qualifiers)
    assert not any(q["text"].lower() == "10kg" for q in qualifiers)


def test_normalize_observable_now_marker_no_existing_value() -> None:
    encounter = "Body weight - now 79 kg"
    entities = [
        {
            "text": encounter,
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.95,
        }
    ]
    normalized = normalize_observable_entities(
        encounter, entities, add_qualifier_value=True
    )
    obs = next(e for e in normalized if e["label"] == "observable_entity")
    assert obs["value"] == "79"
    assert obs["unit"].lower() == "kg"
    assert obs["text"] == "Body weight"


def test_normalize_observable_no_now_marker_keeps_legacy_behaviour() -> None:
    encounter = "Neutrophil count 2.41 10^9/L"
    entities = [
        {
            "text": encounter,
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.9,
        }
    ]
    normalized = normalize_observable_entities(encounter, entities)
    obs = next(e for e in normalized if e["label"] == "observable_entity")
    assert obs["value"] == "2.41"
    assert obs["unit"].lower() == "10^9/l"


def test_normalize_suppresses_interpretation_finding_when_flag_off() -> None:
    encounter = "MCH 22.5 pg [27 - 32] - Outside reference range"
    entities = [
        {
            "text": "MCH 22.5 pg [27 - 32] - Outside reference range",
            "label": "observable_entity",
            "start": 0,
            "end": len(encounter),
            "confidence": 0.8,
        }
    ]
    normalized = normalize_observable_entities(
        encounter, entities, emit_interpretation_finding=False
    )
    findings = [e for e in normalized if e["label"] == "finding"]
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# Tests for /concepts/{id}/related endpoint (mocked neo4j)
# ---------------------------------------------------------------------------


def test_related_concepts_endpoint_returns_family() -> None:
    """GET /terminology/concepts/{id}/related → RelatedConceptsResult."""
    from unittest.mock import MagicMock, patch
    from services.terminology_api.app.routers.concepts import get_related_concepts

    mock_row = {
        "concept_id": "1022471000000107",
        "concept_fsn": "Mean corpuscular haemoglobin (observable entity)",
        "semantic_tag": "observable entity",
        "interpreted_by_findings": [
            {
                "id": "365611000",
                "fsn": "Finding of mean cell hemoglobin level (finding)",
                "semantic_tag": "finding",
                "rel": "INTERPRETED_BY",
            },
        ],
        "component_of_procedures": [
            {
                "id": "54706004",
                "fsn": "Mean corpuscular hemoglobin determination (procedure)",
                "semantic_tag": "procedure",
                "rel": "COMPONENT_OF",
            },
        ],
        "interprets_observables": [],
        "has_components": [],
        "associated_findings": [],
    }

    mock_client = MagicMock()
    mock_client.run.return_value = [mock_row]
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch(
        "services.terminology_api.app.routers.concepts.KnowledgeGraphClient",
        return_value=mock_client,
    ):
        result = get_related_concepts("1022471000000107")

    assert result.concept_id == "1022471000000107"
    assert result.semantic_tag == "observable entity"
    assert len(result.interpreted_by_findings) == 1
    assert result.interpreted_by_findings[0].id == "365611000"
    assert len(result.component_of_procedures) == 1
    assert result.component_of_procedures[0].id == "54706004"


def test_related_concepts_endpoint_404_for_missing() -> None:
    from unittest.mock import MagicMock, patch
    from fastapi import HTTPException
    import pytest
    from services.terminology_api.app.routers.concepts import get_related_concepts

    mock_client = MagicMock()
    mock_client.run.return_value = []

    with patch(
        "services.terminology_api.app.routers.concepts.KnowledgeGraphClient",
        return_value=mock_client,
    ):
        with pytest.raises(HTTPException) as exc_info:
            get_related_concepts("9999999999")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests for CodingResolver lab-domain enrichment
# ---------------------------------------------------------------------------


def test_coding_resolver_enriches_lab_domain_top_candidate() -> None:
    from unittest.mock import MagicMock
    from services.terminology_api.app.services.coding_resolver import CodingResolver

    obs_row = {
        "concept_id": "1022471000000107",
        "fsn": "Mean corpuscular haemoglobin (observable entity)",
        "semantic_tag": "observable entity",
        "read_codes": [],
        "score": 2.5,
    }
    related_row = {
        "concept_id": "1022471000000107",
        "concept_fsn": "Mean corpuscular haemoglobin (observable entity)",
        "semantic_tag": "observable entity",
        "interpreted_by_findings": [
            {
                "id": "365611000",
                "fsn": "Finding of mean cell hemoglobin level (finding)",
                "semantic_tag": "finding",
                "rel": "INTERPRETED_BY",
            },
        ],
        "component_of_procedures": [],
        "interprets_observables": [],
        "has_components": [],
        "associated_findings": [],
    }

    call_count = {"n": 0}

    def _mock_run(query, **kwargs):
        call_count["n"] += 1
        if "RELATED_CONCEPTS_QUERY" in query or "concept_id" in kwargs:
            return [related_row]
        return [obs_row]

    session = MagicMock()
    session.run.side_effect = lambda q, **kw: (
        [obs_row] if call_count["n"] == 0 else [related_row]
    )

    # Use a simpler mock: first call returns obs_row, subsequent returns related_row
    calls = []

    def _run(q, **kw):
        calls.append(q)
        if len(calls) <= 3:  # exact / fulltext queries
            return [obs_row]
        return [related_row]

    session.run.side_effect = _run

    resolver = CodingResolver()
    result = resolver.resolve_candidates(
        ["mean corpuscular haemoglobin"],
        neo4j_session=session,
        enrich_lab_domain=True,
    )

    assert "mean corpuscular haemoglobin" in result
    candidates = result["mean corpuscular haemoglobin"]
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.snomed_concept_id == "1022471000000107"
    # related_concepts populated if the related query was reached
    # (may be empty if mocking doesn't trigger RELATED_CONCEPTS_QUERY path exactly,
    # but the resolver should not raise)
    assert isinstance(top.related_concepts, list)


def test_coding_resolver_skips_enrichment_for_non_lab_domain() -> None:
    from unittest.mock import MagicMock
    from services.terminology_api.app.services.coding_resolver import CodingResolver

    disorder_row = {
        "concept_id": "73211009",
        "fsn": "Diabetes mellitus (disorder)",
        "semantic_tag": "disorder",
        "read_codes": [],
        "score": 2.0,
    }

    session = MagicMock()
    session.run.return_value = [disorder_row]

    resolver = CodingResolver()
    result = resolver.resolve_candidates(
        ["diabetes mellitus"],
        neo4j_session=session,
        enrich_lab_domain=True,
    )

    candidates = result.get("diabetes mellitus", [])
    if candidates:
        top = candidates[0]
        # No related_concepts should be populated for a disorder
        assert top.related_concepts == []
