"""VT-24D1E4F6 -- assertion restore must use the letter, not the concept label.

Atlas:
  DI: DI-0B907354
  DO: DO-AC2014F7
  VT: VT-24D1E4F6
  Risk: R-3926E48D
"""

from __future__ import annotations

from typing import Any

from libs.pipeline.post_processing import apply_false_absent_assertion_guards
from libs.pipeline_graph.subgraphs.compliance import _entity_codes


def test_post_terminology_restore_does_not_flip_context_settled() -> None:
    """A ConText-settled absent must stand after terminology restore.

    Atlas: DI-0B907354 / VT-24D1E4F6
    """
    ent: dict[str, Any] = {
        "assertion": "absent",
        "_assertion_source": "context",
        "text": "GORD",
        "evidence_sentence": "background of GORD",
    }
    apply_false_absent_assertion_guards([ent], respect_context=True)
    assert ent["assertion"] == "absent"


def test_unverified_assertion_is_excluded_from_guideline_codes() -> None:
    """Unresolved facts must not feed guideline matching.

    Atlas: DI-0B907354 / VT-24D1E4F6
    """
    codes = _entity_codes(
        [
            {
                "concept_id": "254838004",
                "assertion": "assertion_unverified",
                "context_span_unresolved": True,
            },
            {"concept_id": "22298006", "assertion": "present"},
        ]
    )
    assert codes == ["22298006"]
