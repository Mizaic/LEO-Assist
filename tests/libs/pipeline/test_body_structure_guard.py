"""Body-part guard keep and drop rules.

Atlas trace:
  VT: VT-A514931C
  DI: DI-6ACD24D2
  DO: DO-8E641A9E

Run:
    pytest tests/libs/pipeline/test_body_structure_guard.py -v --no-coverage
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _reload(custom: list[dict] | None = None):
    import libs.ner.body_structure_guard as guard

    with patch.object(guard, "_fetch_neo4j_rules", return_value=custom or []):
        guard.reload_body_structure_guard()
    return guard


def test_always_keep_cervix() -> None:
    guard = _reload()
    by_id = {"concept_id": "71252005", "text": "cervix", "label": "body_structure"}
    by_name = {"text": "cervix", "label": "body_structure"}
    assert guard.should_keep_body_structure(by_id)
    assert guard.should_keep_body_structure(by_name)
    assert guard.is_always_keep_body_structure(by_name)


def test_keep_as_site_arm() -> None:
    guard = _reload()
    ent = {"text": "arm", "label": "body_structure"}
    assert guard.should_keep_body_structure(ent)
    assert not guard.is_always_keep_body_structure(ent)


def test_unknown_body_part_dropped() -> None:
    guard = _reload()
    ent = {"text": "xiphoid", "label": "body_structure"}
    assert not guard.should_keep_body_structure(ent)


def test_custom_keep_as_site_after_reload() -> None:
    guard = _reload(
        [
            {
                "rule_id": "bs-custom-earlobe",
                "rule_type": "keep_as_site",
                "pattern": "earlobe",
                "active": True,
            }
        ]
    )
    assert guard.should_keep_body_structure(
        {"text": "earlobe", "label": "body_structure"}
    )


def test_orphan_site_suppressed_after_link() -> None:
    guard = _reload()
    entities = [
        {"text": "numbness", "label": "finding", "__relations": []},
        {"text": "arm", "label": "body_structure"},
        {"text": "cervix", "label": "body_structure", "concept_id": "71252005"},
    ]
    guard.suppress_orphan_body_structures(entities)
    assert entities[1].get("_relation_suppressed") is True
    assert not entities[2].get("_relation_suppressed")

    entities[0]["__relations"] = [{"type": "finding_site", "target_idx": 1}]
    entities[1].pop("_relation_suppressed", None)
    guard.suppress_orphan_body_structures(entities)
    assert not entities[1].get("_relation_suppressed")


@pytest.mark.parametrize(
    "organ",
    ["uterus", "ovary", "prostate", "testis", "fallopian tube"],
)
def test_reproductive_organ_names_kept(organ: str) -> None:
    guard = _reload()
    assert guard.should_keep_body_structure({"text": organ, "label": "body_structure"})


def test_post_processing_drops_unknown_keeps_site() -> None:
    guard = _reload()
    from libs.pipeline.post_processing import normalise_entity_types

    entities = [
        {"text": "arm", "label": "body_structure", "start": 0, "end": 3},
        {"text": "xiphoid", "label": "body_structure", "start": 4, "end": 11},
        {
            "text": "cervix",
            "label": "body_structure",
            "concept_id": "71252005",
            "start": 12,
            "end": 18,
        },
    ]
    normalise_entity_types(entities)
    texts = {e["text"] for e in entities}
    assert "arm" in texts
    assert "cervix" in texts
    assert "xiphoid" not in texts
    assert guard.should_keep_body_structure({"text": "arm", "label": "body_structure"})
