"""Sanity checks for NCDA ethnicity SNOMED mapping config."""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_MAPPING = _REPO / "configs" / "snomed" / "snomed_ncda_ethnicity_mapping.json"


def test_ncda_ethnicity_mapping_has_twenty_one_buckets() -> None:
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    assert len(data["mappings"]) == 21


def test_ncda_ethnicity_mapping_required_labels() -> None:
    data = json.loads(_MAPPING.read_text(encoding="utf-8"))
    keys = set(data["mappings"].keys())
    must = {
        "English / Welsh / Scottish / Northern Irish / British",
        "Gypsy or Irish Traveller",
        "Asian or Asian British group",
        "Any other Asian background",
        "Not Known",
        "Unspecified (including transgender)",
    }
    assert must <= keys


def test_ncda_ethnicity_snomed_loader_matches_mapping_row_count() -> None:
    from libs.analytics.ncda_ethnicity_snomed import (
        load_ncda_ethnicity_benchmark_table,
        load_ncda_ethnicity_snomed_ids,
    )

    ids = load_ncda_ethnicity_snomed_ids()
    rows = load_ncda_ethnicity_benchmark_table()
    assert len(ids) == 21
    assert len(rows) == 21
    assert all(len(str(i)) >= 6 for i in ids)

