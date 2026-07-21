"""Tests for Validation Lab equity taxonomy tables.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ETHNICITY_CFG = ROOT / "configs/snomed/snomed_ncda_ethnicity_mapping.json"
PS_CFG = ROOT / "configs/snomed/snomed_ncda_who_performance_status_mapping.json"


def test_ethnicity_options_match_config_count() -> None:
    from libs.validation_lab.equity_taxonomy import ethnicity_options

    cfg = json.loads(ETHNICITY_CFG.read_text(encoding="utf-8"))
    expected = int(cfg["metadata"]["total_terms"])
    rows = ethnicity_options()
    assert len(rows) == expected
    for row in rows:
        assert row["concept_id"]
        assert row["preferred_term"]
        assert row["key"]


def test_performance_status_options_match_config_ids() -> None:
    from libs.validation_lab.equity_taxonomy import performance_status_options

    cfg = json.loads(PS_CFG.read_text(encoding="utf-8"))
    by_grade = {
        int(str(k).rsplit(" ", 1)[-1]): str(v["concept_id"])
        for k, v in cfg["mappings"].items()
    }
    rows = performance_status_options()
    assert len(rows) == 5
    for row in rows:
        grade = int(row["grade"])
        assert 0 <= grade <= 4
        assert str(row["concept_id"]) == by_grade[grade]


def test_comorbidity_band_options() -> None:
    from libs.validation_lab.equity_taxonomy import comorbidity_band_options

    assert comorbidity_band_options() == ("none", "low", "moderate", "high")


def test_plus_group_options() -> None:
    from libs.validation_lab.equity_taxonomy import plus_group_options

    assert plus_group_options() == (
        "ethnic_minority_community",
        "coastal_deprivation_community",
        "learning_disability_or_autism",
        "inclusion_health_group",
        "none",
    )


@pytest.mark.parametrize("decile,ok", [(0, False), (1, True), (10, True), (11, False)])
def test_core20_decile_bounds(decile: int, ok: bool) -> None:
    from libs.validation_lab.equity_taxonomy import is_valid_core20_decile

    assert is_valid_core20_decile(decile) is ok
