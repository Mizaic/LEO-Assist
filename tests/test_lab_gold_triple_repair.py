from __future__ import annotations

from libs.training.lab_concept_lookup import lab_lookup_texts
from libs.training.gold_label_snomed_check import ValidationResult
from scripts.repair_lab_gold_triples import RowPlan, _finalise_plan


def test_procedure_lookup_variants_include_label_consistent_measurement() -> None:
    entity = {"text": "Prostate-specific antigen level", "label": "procedure"}

    lookups = lab_lookup_texts(entity)

    assert lookups[0] == "Prostate-specific antigen level"
    assert "Prostate-specific antigen measurement" in lookups


def test_observable_lookup_keeps_full_value_bearing_span_first() -> None:
    text = "Eosinophil count - observation (42K..) 0.23 10^9/L [0.04 - 0.4]"
    entity = {"text": text, "label": "observable_entity"}

    lookups = lab_lookup_texts(entity)

    assert lookups[0] == text
    assert "Eosinophil count - observation" in lookups


def test_egfr_procedure_lookup_uses_label_consistent_formal_term() -> None:
    entity = {
        "text": "eGFR using creatinine (CKD-EPI) per 1.73 square metres",
        "label": "procedure",
    }

    lookups = lab_lookup_texts(entity)

    assert lookups[0] == "eGFR using creatinine (CKD-EPI) per 1.73 square metres"
    assert any("glomerular filtration" in lookup.lower() for lookup in lookups)


def test_adjusted_calcium_procedure_lookup_uses_corrected_measurement() -> None:
    entity = {
        "text": "Serum adjusted calcium concentration",
        "label": "procedure",
    }

    lookups = lab_lookup_texts(entity)

    assert lookups[0] == "Serum adjusted calcium concentration"
    assert "Corrected serum calcium measurement" in lookups


def test_finding_lookup_simplifies_serum_level_wrapper() -> None:
    text = (
        "Serum alanine aminotransferase level (XaLJx) 63 iu/L [10 - 49] "
        "- Outside reference range"
    )
    entity = {"text": text, "label": "finding"}

    lookups = lab_lookup_texts(entity)

    assert "Serum alanine aminotransferase level outside reference range" in lookups
    assert "alanine aminotransferase outside reference range" in [
        lookup.lower() for lookup in lookups
    ]


def test_repair_plan_rejects_label_inconsistent_concept() -> None:
    entity = {
        "text": "Pulse rate",
        "label": "procedure",
        "semantic_tag": "procedure",
        "start": 0,
        "end": 10,
    }
    plan = RowPlan(
        label_id="GL-test",
        source="lab_coder_v1",
        candidate_id="candidate",
        text="Pulse rate (X773s) 80 bpm",
        existing_entities=[],
        generated_entities=[entity],
        kept_entities=[],
    )
    validations = {
        ("Pulse rate", "procedure"): ValidationResult(
            accepted=False,
            reason="tag_mismatch_all",
            surface_text="Pulse rate",
            proposed_label="procedure",
        )
    }

    item = _finalise_plan(plan, validations)

    assert item["status"] == "concept_unresolved"
    assert item["unresolved"][0]["entity"]["text"] == "Pulse rate"
