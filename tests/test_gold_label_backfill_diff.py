"""Unit tests for the gold-label backfill diff helpers.

Covers the diff_entities + merge_into_existing logic that the
backfill script uses to decide which proposed entities should be
added to a GoldLabel and which should be flagged as extensions or
overlaps.

Critical invariants:
- Existing entities are never modified or deleted.
- A proposal whose normalized (text, label) matches an existing
  entity goes into 'overlaps' and is never added.
- A proposal whose label matches an existing entity AND whose text
  is a strict superset of the existing text goes into 'extensions'
  (e.g. existing 'Reticulocyte count' procedure plus proposed
  'Reticulocyte count - observation' procedure).
- Proposals annotating disorder, procedure or finding entities that
  the previous backfill missed go into 'additions'.
"""

from __future__ import annotations

from scripts.lib.gold_label_backfill import (
    diff_entities,
    merge_into_existing,
    normalize_label,
    normalize_text,
)


def _ent(text: str, label: str, **extra) -> dict:
    base = {"text": text, "label": label, "semantic_tag": label, "assertion": "present"}
    base.update(extra)
    return base


def test_normalize_text_collapses_whitespace_and_case() -> None:
    assert normalize_text("  Reticulocyte  Count  ") == "reticulocyte count"


def test_normalize_text_strips_surrounding_punctuation() -> None:
    assert normalize_text(",- Atypical Lymphocytes :") == "atypical lymphocytes"


def test_normalize_label_canonicalises_whitespace_case() -> None:
    assert normalize_label("Observable Entity") == "observable_entity"
    assert normalize_label(" PROCEDURE ") == "procedure"


def test_diff_treats_text_label_match_as_overlap() -> None:
    existing = [_ent("Anaemia", "disorder")]
    proposed = [_ent("anaemia", "disorder"), _ent("Anaemia", "disorder")]
    out = diff_entities("L1", "Patient has anaemia.", existing, proposed)
    assert out.additions == []
    assert out.extensions == []
    assert len(out.overlaps) == 1
    assert out.overlaps[0]["text"] == "anaemia"


def test_diff_classifies_strict_superset_text_as_extension() -> None:
    """When the proposed text contains the existing text, it's an extension."""
    existing = [_ent("Reticulocyte count", "procedure")]
    proposed = [_ent("Reticulocyte count - observation", "procedure")]
    out = diff_entities("L2", "Reticulocyte count - observation", existing, proposed)
    assert out.additions == []
    assert len(out.extensions) == 1
    assert out.extensions[0]["text"] == "Reticulocyte count - observation"


def test_diff_adds_disorder_missed_by_previous_backfill() -> None:
    """The previous backfill added an observable but missed a disorder.

    This is the user's exact complaint: the same text contains a lab
    observable AND a disorder, but only the observable was added.
    The diff must propose the disorder as a fresh addition.
    """
    text = (
        "Mean cell volume (42A..) 100 fL [80 - 99] - Outside reference range\n"
        "Iron deficiency anaemia"
    )
    existing = [
        _ent("Mean cell volume (42A..) 100 fL [80 - 99]", "observable_entity"),
    ]
    proposed = [
        _ent("Mean cell volume (42A..) 100 fL [80 - 99]", "observable_entity"),
        _ent("Iron deficiency anaemia", "disorder"),
        _ent("Outside reference range", "finding"),
    ]
    out = diff_entities("L3", text, existing, proposed)
    addition_keys = sorted((e["text"], e["label"]) for e in out.additions)
    assert ("Iron deficiency anaemia", "disorder") in addition_keys
    assert ("Outside reference range", "finding") in addition_keys
    assert len(out.overlaps) == 1


def test_diff_dedupes_proposals_by_normalized_key() -> None:
    proposed = [
        _ent("Anaemia", "disorder"),
        _ent("anaemia", "disorder"),
        _ent("ANAEMIA", "disorder"),
    ]
    out = diff_entities("L4", "Anaemia.", [], proposed)
    assert len(out.additions) == 1


def test_diff_skips_proposals_with_empty_text() -> None:
    out = diff_entities("L5", "x", [], [_ent("", "disorder"), _ent("   ", "finding")])
    assert out.additions == []


def test_diff_does_not_mutate_inputs() -> None:
    existing = [_ent("a", "disorder")]
    proposed = [_ent("b", "finding")]
    snap_existing = [dict(e) for e in existing]
    snap_proposed = [dict(e) for e in proposed]
    diff_entities("L6", "a b", existing, proposed)
    assert existing == snap_existing
    assert proposed == snap_proposed


def test_merge_appends_additions_with_provenance_and_review_status() -> None:
    existing = [_ent("a", "disorder")]
    text = "a b"
    proposed = [_ent("b", "finding")]
    diff = diff_entities("L7", text, existing, proposed)
    merged = merge_into_existing(existing, diff, apply_extensions=False)
    assert len(merged) == 2
    new_one = merged[1]
    assert new_one["text"] == "b"
    assert new_one["provenance"] == "auto_backfill_v1"
    assert new_one["review_status"] == "pending"
    assert merged[0] == existing[0]


def test_merge_includes_extensions_only_when_flag_is_set() -> None:
    existing = [_ent("Reticulocyte count", "procedure")]
    proposed = [_ent("Reticulocyte count - observation", "procedure")]
    diff = diff_entities("L8", "Reticulocyte count - observation", existing, proposed)
    no_ext = merge_into_existing(existing, diff, apply_extensions=False)
    assert len(no_ext) == 1
    with_ext = merge_into_existing(existing, diff, apply_extensions=True)
    assert len(with_ext) == 2
    assert with_ext[1]["text"] == "Reticulocyte count - observation"


def test_diff_subset_of_existing_same_label_span_is_overlap_not_addition() -> None:
    """Avoid proposing a short observable when a longer one already exists.

    The deterministic post-processing stack often emits both a long and
    a short observable for the same lab line (the spancat trains on the
    long span, the runtime contract carries a short span + structured
    value/unit fields). When backfilling an existing GoldLabel that
    already has the long observable, the short version must NOT be
    proposed as a new addition -- it would silently duplicate the
    semantic.
    """
    existing = [
        _ent("Serum bilirubin level (44E..) 9 umol/L [< 21]", "observable_entity"),
        _ent("Serum bilirubin level", "procedure"),
    ]
    proposed = [
        _ent("Serum bilirubin level", "observable_entity"),
        _ent("Serum bilirubin level", "procedure"),
    ]
    text = "Serum bilirubin level (44E..) 9 umol/L [< 21]"
    out = diff_entities("L_subset", text, existing, proposed)
    assert out.additions == []
    assert out.extensions == []
    assert len(out.overlaps) == 2


def test_diff_drops_proposals_with_label_outside_gold_whitelist() -> None:
    """qualifier_value etc. extracted by the runtime are dropped."""
    existing = [_ent("Serum bilirubin level", "procedure")]
    proposed = [
        _ent("9 umol/L", "qualifier_value"),
        _ent("not_a_real_class", "garbage"),
        _ent("Iron deficiency anaemia", "disorder"),
    ]
    out = diff_entities("L_white", "x", existing, proposed)
    add_labels = sorted(a["label"] for a in out.additions)
    assert add_labels == ["disorder", "qualifier_value"]
    assert all(a["label"] != "garbage" for a in out.additions)


def test_diff_overlaps_count_is_reported_separately_from_additions() -> None:
    existing = [_ent("Anaemia", "disorder")]
    proposed = [
        _ent("Anaemia", "disorder"),
        _ent("Type 2 diabetes mellitus", "disorder"),
    ]
    text = "Anaemia and Type 2 diabetes mellitus"
    diff = diff_entities("L9", text, existing, proposed)
    assert len(diff.overlaps) == 1
    assert len(diff.additions) == 1
    assert diff.additions[0]["text"] == "Type 2 diabetes mellitus"
