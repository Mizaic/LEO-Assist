"""Worked examples in the Pipeline Guards UI must match real guard tests.

The JSON is the same file the Knowledge UI renders. Each example.note is a
sentence (or span) from an existing pytest. This module re-runs the guard so
the UI cannot drift from proven behaviour.

Run:
    pytest tests/libs/pipeline/test_guard_worked_examples.py -v --no-coverage
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_JSON_PATH = (
    Path(__file__).resolve().parents[3]
    / "services/ui/src/app/admin/guard-rules/guard_worked_examples.json"
)


def _load_catalog() -> dict[str, Any]:
    return json.loads(_JSON_PATH.read_text(encoding="utf-8"))


def _examples() -> list[tuple[str, dict[str, Any]]]:
    data = _load_catalog()
    rows: list[tuple[str, dict[str, Any]]] = []
    for key, example in data["families"].items():
        rows.append((f"family:{key}", example))
    for key, example in data["types"].items():
        rows.append((f"type:{key}", example))
    for key, example in data["rules"].items():
        rows.append((f"rule:{key}", example))
    return rows


def _check_scope_suppressed(example: dict[str, Any]) -> None:
    from libs.ner.scope_guard import SUPPRESSED, reclassify_assertion

    tag = example["check"].get("semantic_tag", "disorder")
    result = reclassify_assertion(
        entity_semantic_tag=tag,
        entity_assertion="present",
        sentence_text=example["note"],
    )
    assert result == SUPPRESSED


def _check_scope_hypothetical(example: dict[str, Any]) -> None:
    from libs.ner.scope_guard import reclassify_assertion

    tag = example["check"].get("semantic_tag", "substance")
    result = reclassify_assertion(
        entity_semantic_tag=tag,
        entity_assertion="present",
        sentence_text=example["note"],
    )
    assert result == "hypothetical"


def _check_lab_result(example: dict[str, Any]) -> None:
    import libs.ner.lab_value_guard as guard

    with patch.object(guard, "_fetch_neo4j_lab_rules", return_value=[]):
        guard.reload_lab_value_guard()
        assert guard.is_lab_result_sentence(example["note"])


def _check_referral_keep(example: dict[str, Any]) -> None:
    import libs.ner.referral_routing_guard as guard

    with patch.object(guard, "_fetch_neo4j_routing_rules", return_value=[]):
        guard.reload_referral_routing_guard()
        drop_note = example["check"]["drop_note"]
        assert guard.is_informational_referral_routing(drop_note)
        assert not guard.is_informational_referral_routing(example["note"])


def _check_assertion_present(example: dict[str, Any]) -> None:
    from libs.pipeline.post_processing import fix_lifestyle_status_assertions

    check = example["check"]
    ent = {
        "concept_id": check["concept_id"],
        "term": check["term"],
        "assertion": "absent",
        "semantic_tag": "finding",
    }
    fix_lifestyle_status_assertions([ent])
    assert ent["assertion"] == "present"


def _check_entity_relabel(example: dict[str, Any]) -> None:
    from libs.pipeline.post_processing import normalise_entity_types

    start = example["check"]["start_label"]
    ent = {"label": start, "text": example["note"]}
    normalise_entity_types([ent])
    assert ent["label"] == "qualifier_value"


def _check_checkbox_suppress(example: dict[str, Any]) -> None:
    from libs.ner.form_checkbox_normalizer import normalize_form_checkbox_text

    result = normalize_form_checkbox_text(example["note"])
    assert "[NON_EXTRACTABLE]" in result or "Has the patient" not in result


def _check_situation_rewrite(example: dict[str, Any]) -> None:
    with patch(
        "libs.ner.context_detector._fetch_neo4j_rules",
        return_value=[],
    ):
        from libs.ner import context_detector

        context_detector._reload_singleton()
        result = context_detector.normalize_situation_lookup(example["note"])
    assert result == example["check"]["expected"]


def _check_blocklist(example: dict[str, Any]) -> None:
    check = example["check"]
    with patch(
        "libs.pipeline_graph.subgraphs.terminology._fetch_neo4j_blocklist",
        return_value=[],
    ):
        from libs.pipeline_graph.subgraphs import terminology as term_mod

        term_mod._reload_blocklist_singleton()
        assert term_mod._is_blocked_mapping(check["text"], check["concept_id"])


_HANDLERS = {
    "scope_suppressed": _check_scope_suppressed,
    "scope_hypothetical": _check_scope_hypothetical,
    "lab_result": _check_lab_result,
    "referral_keep": _check_referral_keep,
    "assertion_present": _check_assertion_present,
    "entity_relabel": _check_entity_relabel,
    "checkbox_suppress": _check_checkbox_suppress,
    "situation_rewrite": _check_situation_rewrite,
    "blocklist": _check_blocklist,
}


@pytest.mark.parametrize("label,example", _examples())
def test_ui_worked_example_matches_guard(
    label: str,
    example: dict[str, Any],
) -> None:
    kind = example["check"]["kind"]
    handler = _HANDLERS.get(kind)
    assert handler is not None, f"{label}: unknown check kind {kind}"
    handler(example)


def test_catalog_covers_every_guard_family() -> None:
    data = _load_catalog()
    expected = {
        "scope_guard",
        "lab_value_guard",
        "referral_routing_guard",
        "assertion_guard",
        "entity_type_norm",
        "checkbox_norm",
        "situation_lookup",
        "term_concept_blocklist",
    }
    assert expected <= set(data["families"])
