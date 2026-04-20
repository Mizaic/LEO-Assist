"""Tests for the reconcile -> :GoldLabel promoter (DI-C424BB44).

Covers:

  - The promoter calls write_audit_verified_to_kg with
    source=RECONCILE_PATHWAY_SOURCE and verified_by=lock.locked_by
  - Coded-link / assertion locks demand exactly one encounter context
  - Episode locks fan out to one promotion call per IS_PART_OF
    encounter
  - Writeback failures and DE-ID failures degrade to skipped, never raise
  - Unsupported entity_types (encounter, is_part_of_edge) are skipped
  - The new RECONCILE_PATHWAY_SOURCE constant is wired through the
    writeback so a custom source overrides AUDIT_VERIFIED_SOURCE
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from libs.audit.kg_verified_writeback import (
    AUDIT_VERIFIED_SOURCE,
    RECONCILE_PATHWAY_SOURCE,
    write_audit_verified_to_kg,
)
from libs.locks import VerificationLock
from libs.training_data import EncounterContext, promote_lock_to_gold


def _lock(
    entity_type: str = "coded_link",
    entity_id: str = "enc-1:111",
    locked_by: str = "alice@example.org",
) -> VerificationLock:
    return VerificationLock(
        lock_id="lock-aaaaaaaa1",
        entity_type=entity_type,
        entity_id=entity_id,
        locked_by=locked_by,
        locked_by_role="clinician",
        lock_reason="confirmed",
        source="reconcile_pathway",
        locked_at="2026-04-20T00:00:00Z",
        updated_at="2026-04-20T00:00:00Z",
    )


def _ctx(encounter_id: str = "enc-1") -> EncounterContext:
    return EncounterContext(
        encounter_id=encounter_id,
        raw_encounter_text="cough settled",
        coded_rows=[
            {"evidence": "cough", "semantic_tag": "Finding"},
        ],
    )


# ---------------------------------------------------------------------------
# write_audit_verified_to_kg source-override (the underlying primitive)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_kg_session():
    with patch("libs.audit.kg_verified_writeback.KnowledgeGraphClient") as cls:
        inst = MagicMock()
        cls.return_value = inst
        session = MagicMock()
        inst.session.return_value.__enter__ = MagicMock(return_value=session)
        inst.session.return_value.__exit__ = MagicMock(return_value=False)
        yield inst, session


def test_write_audit_verified_propagates_custom_source(mock_kg_session):
    inst, session = mock_kg_session
    with patch("libs.audit.kg_verified_writeback.DeIdValidator") as vcls:
        vcls.return_value.check_record.return_value = []
        out = write_audit_verified_to_kg(
            raw_encounter_text="cough today",
            coded_rows=[],
            quality_score=0.9,
            verified_by="alice@example.org",
            assessment="reconcile",
            source=RECONCILE_PATHWAY_SOURCE,
        )
    assert out["written"] is True
    sources = []
    for c in session.run.call_args_list:
        kw = getattr(c, "kwargs", {}) or {}
        if "source" in kw:
            sources.append(kw["source"])
    assert sources, "expected at least one source kwarg on Cypher writes"
    assert all(s == RECONCILE_PATHWAY_SOURCE for s in sources)
    assert AUDIT_VERIFIED_SOURCE not in sources


# ---------------------------------------------------------------------------
# promote_lock_to_gold
# ---------------------------------------------------------------------------


def test_promote_coded_link_writes_one_gold_label():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg",
        return_value={"written": True, "errors": [], "deid_failed": False},
    ) as wb:
        out = promote_lock_to_gold(
            lock=_lock(entity_type="coded_link"),
            encounter_contexts=[_ctx()],
        )
    assert out["promoted"] == 1
    assert out["skipped"] == 0
    wb.assert_called_once()
    kwargs = wb.call_args.kwargs
    assert kwargs["source"] == RECONCILE_PATHWAY_SOURCE
    assert kwargs["verified_by"] == "alice@example.org"
    assert kwargs["assessment"].startswith("reconcile_pathway:")


def test_promote_assertion_lock_writes_one_gold_label():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg",
        return_value={"written": True, "errors": [], "deid_failed": False},
    ) as wb:
        out = promote_lock_to_gold(
            lock=_lock(entity_type="assertion", entity_id="enc-1:abc"),
            encounter_contexts=[_ctx()],
        )
    assert out["promoted"] == 1
    wb.assert_called_once()


def test_episode_lock_fans_out_to_every_encounter():
    contexts = [_ctx("enc-1"), _ctx("enc-2"), _ctx("enc-3")]
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg",
        return_value={"written": True, "errors": [], "deid_failed": False},
    ) as wb:
        out = promote_lock_to_gold(
            lock=_lock(entity_type="episode", entity_id="ep-7"),
            encounter_contexts=contexts,
        )
    assert out["promoted"] == 3
    assert wb.call_count == 3


def test_coded_link_lock_with_zero_or_many_contexts_is_skipped():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg"
    ) as wb:
        out = promote_lock_to_gold(
            lock=_lock(entity_type="coded_link"),
            encounter_contexts=[_ctx("a"), _ctx("b")],
        )
    assert out["promoted"] == 0
    assert out["skipped"] == 1
    assert any("requires exactly one" in e for e in out["errors"])
    wb.assert_not_called()


def test_unsupported_entity_type_is_skipped():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg"
    ) as wb:
        out = promote_lock_to_gold(
            lock=_lock(entity_type="encounter", entity_id="enc-1"),
            encounter_contexts=[_ctx()],
        )
    assert out["promoted"] == 0
    assert out["skipped"] == 1
    assert any("not promotable" in e for e in out["errors"])
    wb.assert_not_called()


def test_writeback_exception_degrades_to_skipped():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg",
        side_effect=RuntimeError("kg down"),
    ):
        out = promote_lock_to_gold(
            lock=_lock(entity_type="coded_link"),
            encounter_contexts=[_ctx()],
        )
    assert out["promoted"] == 0
    assert out["skipped"] == 1
    assert any("RuntimeError" in e for e in out["errors"])


def test_deid_failure_recorded_as_skipped_with_error():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg",
        return_value={
            "written": False,
            "errors": ["deid_failed: nhs_number"],
            "deid_failed": True,
        },
    ):
        out = promote_lock_to_gold(
            lock=_lock(entity_type="coded_link"),
            encounter_contexts=[_ctx()],
        )
    assert out["promoted"] == 0
    assert out["skipped"] == 1
    assert any("deid_failed" in e for e in out["errors"])


def test_episode_lock_with_some_failures_partially_promoted():
    contexts = [_ctx("enc-1"), _ctx("enc-2")]
    results = [
        {"written": True, "errors": [], "deid_failed": False},
        {"written": False, "errors": ["deid_failed"], "deid_failed": True},
    ]
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg",
        side_effect=results,
    ):
        out = promote_lock_to_gold(
            lock=_lock(entity_type="episode", entity_id="ep-7"),
            encounter_contexts=contexts,
        )
    assert out["promoted"] == 1
    assert out["skipped"] == 1


def test_encounter_context_without_id_is_skipped():
    with patch(
        "libs.training_data.reconcile_promoter.write_audit_verified_to_kg"
    ) as wb:
        out = promote_lock_to_gold(
            lock=_lock(entity_type="episode", entity_id="ep-7"),
            encounter_contexts=[
                EncounterContext(encounter_id="", raw_encounter_text="")
            ],
        )
    assert out["promoted"] == 0
    assert out["skipped"] == 1
    wb.assert_not_called()
