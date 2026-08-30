"""VT-LEO-AI-104 -- Polarity-encoded finding guard.

Verifies that fix_polarity_encoded_findings() corrects assertion inversion
on SNOMED finding/observable entity concepts whose preferred term ends with a
polarity suffix word (absent, not detected, not found, not present, negative).

Companion to test_double_negation_guard.py (VT-LEO-AI-101) which covers
situation prefix-negated concepts.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from libs.pipeline.post_processing import (
    fix_double_negated_situations,
    fix_polarity_encoded_findings,
)


def _ent(
    assertion: str,
    semantic_tag: str,
    term: str = "",
    concept_id: str = "",
) -> dict[str, Any]:
    return {
        "assertion": assertion,
        "semantic_tag": semantic_tag,
        "term": term,
        "concept_id": concept_id,
    }


# ---------------------------------------------------------------------------
# TC-001 -- Perineural invasion absent finding corrected
# ---------------------------------------------------------------------------
def test_perineural_invasion_absent_corrected():
    ent = _ent(
        "absent",
        "finding",
        "Perineural invasion by tumor absent (finding)",
        "370051000",
    )
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "polarity_encoded_finding"


# ---------------------------------------------------------------------------
# TC-002 -- "not detected" suffix
# ---------------------------------------------------------------------------
def test_not_detected_suffix_corrected():
    ent = _ent("absent", "finding", "Bacteria not detected (finding)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "polarity_encoded_finding"


# ---------------------------------------------------------------------------
# TC-003 -- "not found" suffix
# ---------------------------------------------------------------------------
def test_not_found_suffix_corrected():
    ent = _ent("absent", "finding", "Malignant cells not found (finding)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"


# ---------------------------------------------------------------------------
# TC-004 -- "negative" suffix
# ---------------------------------------------------------------------------
def test_negative_suffix_corrected():
    ent = _ent("absent", "finding", "Staining result negative (finding)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"


# ---------------------------------------------------------------------------
# TC-005 -- positive PT "present (finding)" NOT changed
# (the regex matches absent/not-detected words, not 'present')
# ---------------------------------------------------------------------------
def test_positive_pt_not_changed():
    ent = _ent("absent", "finding", "Perineural invasion by tumor present (finding)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "absent"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# TC-006 -- situation entity NOT changed (handled by other guard)
# ---------------------------------------------------------------------------
def test_situation_entity_not_changed():
    ent = _ent("absent", "situation", "No suicidal thoughts (situation)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "absent"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# TC-007 -- disorder entity NOT changed
# ---------------------------------------------------------------------------
def test_disorder_entity_not_changed():
    ent = _ent("absent", "disorder", "Breast carcinoma absent (disorder)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "absent"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# TC-008 -- present assertion NOT changed
# ---------------------------------------------------------------------------
def test_present_assertion_not_changed():
    ent = _ent("present", "finding", "Bacteria not detected (finding)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"
    assert "_assertion_guard" not in ent


# ---------------------------------------------------------------------------
# TC-009 -- idempotency
# ---------------------------------------------------------------------------
def test_idempotent():
    ent = _ent(
        "absent",
        "finding",
        "Perineural invasion by tumor absent (finding)",
        "370051000",
    )
    fix_polarity_encoded_findings([ent])
    state_after_first = dict(ent)
    fix_polarity_encoded_findings([ent])
    assert ent == state_after_first


# ---------------------------------------------------------------------------
# TC-010 -- observable entity tag corrected
# ---------------------------------------------------------------------------
def test_observable_entity_corrected():
    ent = _ent("absent", "observable entity", "Tumor marker absent (observable entity)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "polarity_encoded_finding"


# ---------------------------------------------------------------------------
# TC-011 -- terminology.py calls fix_polarity_encoded_findings (source check)
# (langgraph not installed in local env; verified via source inspection)
# ---------------------------------------------------------------------------
def test_terminology_subgraph_calls_polarity_guard():
    """Verify terminology.py imports and calls fix_polarity_encoded_findings."""
    import os

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(
        os.path.join(repo_root, "libs/pipeline_graph/subgraphs/terminology.py")
    ).read()
    assert (
        "fix_polarity_encoded_findings" in src
    ), "terminology.py must import and call fix_polarity_encoded_findings"
    assert (
        "apply_false_absent_assertion_guards" in src
    ), "terminology.py must call apply_false_absent_assertion_guards"
    # Verify call order after fix_double_negated_situations
    idx_double = src.find("fix_double_negated_situations(resolved)")
    idx_polarity = src.find("fix_polarity_encoded_findings(resolved)")
    idx_false_absent = src.find("apply_false_absent_assertion_guards(resolved")
    assert (
        idx_polarity > idx_double
    ), "fix_polarity_encoded_findings must be called after fix_double_negated_situations"
    assert (
        idx_false_absent > idx_polarity
    ), "apply_false_absent_assertion_guards must run after polarity guard"


# ---------------------------------------------------------------------------
# Guards do not interfere with each other
# ---------------------------------------------------------------------------
def test_both_guards_independent():
    """fix_double_negated_situations and fix_polarity_encoded_findings
    each correct their own class of entity without affecting the other."""
    entities = [
        _ent("absent", "situation", "No suicidal thoughts (situation)", "134420004"),
        _ent(
            "absent",
            "finding",
            "Perineural invasion by tumor absent (finding)",
            "370051000",
        ),
        _ent("absent", "finding", "Chest pain (finding)"),
        _ent("present", "finding", "Bacteria not detected (finding)"),
    ]
    fix_double_negated_situations(entities)
    fix_polarity_encoded_findings(entities)

    assert entities[0]["assertion"] == "present"  # situation guard
    assert entities[0]["_assertion_guard"] == "double_negated_situation"
    assert entities[1]["assertion"] == "present"  # polarity guard
    assert entities[1]["_assertion_guard"] == "polarity_encoded_finding"
    assert entities[2]["assertion"] == "absent"  # no suffix match
    assert entities[3]["assertion"] == "present"  # was already present


# ---------------------------------------------------------------------------
# "not present" suffix
# ---------------------------------------------------------------------------
def test_not_present_suffix_corrected():
    ent = _ent("absent", "finding", "Lymphovascular invasion not present (finding)")
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"
