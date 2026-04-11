from __future__ import annotations

from scripts.migrate_training_labels import _gold_label_id, _sha


def test_content_only_hash_is_stable() -> None:
    assert _sha("abc") == _sha("abc")
    assert _sha("abc") != _sha("abcd")


def test_gold_label_id_uses_text_and_entities() -> None:
    e1 = '[{"text":"chest pain"}]'
    e2 = '[{"text":"chest discomfort"}]'
    assert _gold_label_id("note", e1) != _gold_label_id("note", e2)
