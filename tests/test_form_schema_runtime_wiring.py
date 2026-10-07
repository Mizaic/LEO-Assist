"""Runtime wiring for taught FormSchema items in the extraction pipeline.

Atlas trace: DI-5C9CA57B, DI-0C766F85
"""

from __future__ import annotations

import textwrap
from dataclasses import replace

import pytest

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.document_quality import form_fingerprint
from libs.pipeline.form_schema_normalizer import (
    FormSchema,
    FormSchemaItem,
    FormSection,
    apply_schema_to_text,
)
from libs.pipeline.form_schema_seeding import seed_ordered_tests_entities
from libs.pipeline.form_schema_store import _SCHEMA_CACHE, reset_schema_cache
from libs.pipeline.post_processing import run_post_processing

FBC_ITEM = FormSchemaItem(
    pattern="FBC",
    entity_text="Full blood count",
    semantic_tag="procedure",
    assertion="present",
    procedure_snomed="26604007",
    procedure_display="Full blood count",
    analytes=[
        {"label": "Hb", "snomed_code": "1022280009", "display": "Haemoglobin"},
        {"label": "WCC", "snomed_code": "413892002", "display": "White cell count"},
    ],
    value_placeholder="{{NUMERIC_VALUE}} {{UNIT}}",
)

ORDERED_TESTS_TEXT = textwrap.dedent("""\
    Section D: Investigations performed
    MANDATORY the following tests must be undertaken
    FBC | 124 g/L | 12.5 |
    BLOODS DONE TODAY
    """)

ORDERED_TESTS_SCHEMA = FormSchema(
    schema_id="test-ordered-tests",
    fingerprint=form_fingerprint(ORDERED_TESTS_TEXT),
    form_name="Ordered Tests Form",
    created_by="test",
    sections=[
        FormSection(
            section_id="D",
            section_type="ordered_tests",
            label="Section D",
            start_pattern=r"(?i)section\s+d:",
            items=[FBC_ITEM],
        ),
    ],
    chunk_section_map=[{"chunk_idx": 0, "section_id": "D"}],
)


# The same section with each value beside the analyte it belongs to.
# GGT is taught but is not one of the abbreviations the deterministic
# blood-panel extractor knows, so only schema seeding can produce it.
RESULTED_TESTS_TEXT = textwrap.dedent("""\
    Section D: Investigations performed
    MANDATORY the following tests must be undertaken
    FBC | 23.06.26 | Hb 124 g/L , WCC 12.5 x10^9/L , GGT 30 U/L |
    BLOODS DONE TODAY
    """)

RESULTED_FBC_ITEM = replace(
    FBC_ITEM,
    analytes=[
        *FBC_ITEM.analytes,
        {"label": "GGT", "snomed_code": "1000861000000106", "display": "Gamma GT"},
    ],
)

RESULTED_TESTS_SCHEMA = FormSchema(
    schema_id="test-resulted-tests",
    fingerprint=form_fingerprint(RESULTED_TESTS_TEXT),
    form_name="Ordered Tests Form",
    created_by="test",
    sections=[
        FormSection(
            section_id="D",
            section_type="ordered_tests",
            label="Section D",
            start_pattern=r"(?i)section\s+d:",
            items=[RESULTED_FBC_ITEM],
        ),
    ],
    chunk_section_map=[{"chunk_idx": 0, "section_id": "D"}],
)


def _cache_schema(schema: FormSchema) -> None:
    _SCHEMA_CACHE[schema.fingerprint] = schema


@pytest.fixture(autouse=True)
def _clear_schema_cache() -> None:
    reset_schema_cache()
    yield
    reset_schema_cache()


def test_a_cached_schema_alone_does_not_bypass_the_quality_gate() -> None:
    """The letter-hash cache no longer binds a form (DI-E21DF9EF).

    With no taught candidate recognised from the text, the quality gate
    still scores the letter.
    """
    from unittest.mock import patch

    from libs.pipeline_graph.subgraphs.extraction import merge_results

    _cache_schema(ORDERED_TESTS_SCHEMA)
    with patch(
        "libs.pipeline.document_chunk_loader._candidate_schemas", return_value=[]
    ):
        out = merge_results(
            {
                "encounter_text": ORDERED_TESTS_TEXT,
                "entities": [],
                "few_shot_max_similarity": 0.05,
            }
        )
    assert out["form_schema_match"] != "recognised"
    assert out["document_quality"]["document_quality_score"] < 1.0


def test_merge_results_loads_taught_schema_from_neo4j_when_cache_empty() -> None:
    """Worker merge_results must load :FormSchema from Neo4j, not only cache."""
    import json
    from unittest.mock import MagicMock, patch

    from libs.pipeline.form_schema_store import _schema_to_sections_json
    from libs.pipeline_graph.subgraphs.extraction import merge_results

    client = MagicMock()
    client.run.return_value = [
        {
            "schema_id": ORDERED_TESTS_SCHEMA.schema_id,
            "fingerprint": ORDERED_TESTS_SCHEMA.fingerprint,
            "form_name": ORDERED_TESTS_SCHEMA.form_name,
            "sections_json": _schema_to_sections_json(ORDERED_TESTS_SCHEMA),
            "chunk_section_map": json.dumps(ORDERED_TESTS_SCHEMA.chunk_section_map),
            "created_by": "test",
            "version": 1,
            "status": "active",
        }
    ]

    with patch(
        "libs.neo4j_client.client.PatientGraphClient",
        return_value=client,
    ):
        out = merge_results(
            {
                "encounter_text": ORDERED_TESTS_TEXT,
                "entities": [],
                "few_shot_max_similarity": 0.05,
            }
        )

    quality = out["document_quality"]
    assert quality["document_quality_score"] == 1.0
    assert quality["quality_reasons"] == []
    client.close.assert_called_once()


def test_ordered_tests_with_analytes_not_fully_suppressed() -> None:
    """A resulted row keeps its values while boilerplate stays suppressed."""
    result = apply_schema_to_text(ORDERED_TESTS_TEXT, ORDERED_TESTS_SCHEMA)
    assert "124 g/L" in result
    assert "{{NUMERIC_VALUE}}" not in result
    # FBC row with taught analytes must stay extractable
    fbc_lines = [ln for ln in result.splitlines() if "FBC" in ln]
    assert fbc_lines, "Expected an FBC row in normalised output"
    assert all(NON_EXTRACTABLE_MARKER not in ln for ln in fbc_lines)
    # Admin boilerplate in the same section stays suppressed
    assert any(NON_EXTRACTABLE_MARKER in ln for ln in result.splitlines())


def test_post_processing_applies_taught_analyte_codes() -> None:
    """Entities get taught snomed_code after run_post_processing."""
    _cache_schema(ORDERED_TESTS_SCHEMA)
    entities = [
        {
            "text": "Hb",
            "label": "Hb",
            "snomed_code": "INFERRED-999",
            "start": 0,
            "end": 2,
        },
        {
            "text": "WCC",
            "label": "WCC",
            "snomed_code": "INFERRED-888",
            "start": 10,
            "end": 13,
        },
    ]
    result = run_post_processing(
        ORDERED_TESTS_TEXT, entities, enable_disorder_gate=False
    )
    hb = next(e for e in result if e.get("label") == "Hb")
    wcc = next(e for e in result if e.get("label") == "WCC")
    assert hb["snomed_code"] == "1022280009"
    assert wcc["snomed_code"] == "413892002"


def test_enrichment_seeds_taught_analytes_from_schema() -> None:
    """Extraction enrichment injects taught analytes when battery rows match."""
    from libs.pipeline_graph.subgraphs.extraction import (
        _enrich_with_blood_panel_entities,
    )

    result = _enrich_with_blood_panel_entities(
        {"entities": [], "extraction_route": "llm"},
        RESULTED_TESTS_TEXT,
        [],
        schema=RESULTED_TESTS_SCHEMA,
    )
    texts = {e.get("text") for e in result["entities"]}
    labels = {e.get("label") for e in result["entities"]}
    assert {"Hb", "WCC"} <= texts
    assert "GGT" in labels
    assert "schema-seed" in result["extraction_route"]


def test_enrichment_does_not_seed_from_a_cached_schema_alone() -> None:
    """Only the recognised schema seeds; the hash cache is not a bind."""
    from libs.pipeline_graph.subgraphs.extraction import (
        _enrich_with_blood_panel_entities,
    )

    _cache_schema(RESULTED_TESTS_SCHEMA)
    result = _enrich_with_blood_panel_entities(
        {"entities": [], "extraction_route": "llm"}, RESULTED_TESTS_TEXT, []
    )
    labels = {e.get("label") for e in result["entities"]}
    assert "GGT" not in labels


def test_seed_ordered_tests_entities_for_cached_schema() -> None:
    _cache_schema(ORDERED_TESTS_SCHEMA)
    text = "Section D\nFBC | Hb 124 g/L, WCC 6.1 x10^9/L"
    seeded = seed_ordered_tests_entities(text, ORDERED_TESTS_SCHEMA)
    assert any(e.get("label") == "Hb" for e in seeded)


def test_seeding_skips_an_unresulted_battery_row() -> None:
    """A battery row with no result seeds nothing for the cached schema."""
    _cache_schema(ORDERED_TESTS_SCHEMA)
    seeded = seed_ordered_tests_entities(
        "Section D\nFBC | Hb, WCC", ORDERED_TESTS_SCHEMA
    )
    assert seeded == []
