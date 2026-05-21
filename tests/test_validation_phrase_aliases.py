"""API validation term aliases for phrase-level F1."""

from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[1] / "services" / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from app.routers.extraction_scenarios import (  # noqa: E402
    _build_case_alias_map,
    _normalise_validation_term,
    _normalise_validation_terms,
)


def test_phrase_alias_mri_and_ca125() -> None:
    case = {"expected_observables": []}
    out_entities = _normalise_validation_terms(
        [
            {"text": "MRI scan of the brain", "semantic_tag": "procedure"},
            {"text": "CA125 level is raised at 92 U/mL", "semantic_tag": "observable_entity"},
            {"text": "Glycated haemoglobin", "semantic_tag": "observable_entity"},
            {"text": "Plasma viscosity", "semantic_tag": "observable_entity"},
        ],
        case,
    )
    out = [e["text"] for e in out_entities]
    assert "urgent MRI scan of the brain" in out
    assert "CA125 raised" in out
    assert "HbA1c" in out
    assert "PV" in out


def test_routing_phrase_dropped_by_noise_markers() -> None:
    alias_map = _build_case_alias_map(None)
    assert _normalise_validation_term("referral criteria and clinical information", alias_map) == ""
