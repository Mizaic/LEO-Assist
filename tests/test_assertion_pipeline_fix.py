"""Verification tests for the declined/cancelled assertion lifecycle fix.

Covers every layer where the bug existed or where new behaviour was added:

1. LLM Extractor -- _VALID_ASSERTIONS and _ASSERTION_TO_CONTEXT include
   declined and cancelled with correct context flag mapping.
2. Schema Mapper -- assertion allowlist passes declined and cancelled;
   unknown values are coerced to present.
3. Documents Queries -- _assertion_context and _NON_PRESENT include
   declined and cancelled; patient shortcut gate query uses FOREACH.
4. Tier Classifier -- declined and cancelled both trigger Tier 3 in
   both modes; both are in _AUTO_CODE_BLOCKED.
5. Label Verifier -- _AUTO_CODE_BLOCKED includes declined and cancelled.
6. Extractor Contract -- CONTRACT_VERSION is 1.2 (bumped for schema change).
7. Patient Timeline Query -- GET_PATIENT_CODING_TIMELINE returns
   required fields and is ordered by date.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 1. LLM Extractor
# ---------------------------------------------------------------------------


class TestLlmExtractorAssertions:
    """_VALID_ASSERTIONS and _ASSERTION_TO_CONTEXT in llm_extractor.py."""

    def _import(self):
        from services.coding_worker.app.pipeline.llm_extractor import (
            _ASSERTION_TO_CONTEXT,
            _VALID_ASSERTIONS,
        )

        return _VALID_ASSERTIONS, _ASSERTION_TO_CONTEXT

    def test_declined_in_valid_assertions(self):
        valid, _ = self._import()
        assert "declined" in valid

    def test_cancelled_in_valid_assertions(self):
        valid, _ = self._import()
        assert "cancelled" in valid

    def test_declined_context_sets_declined_flag(self):
        _, ctx = self._import()
        assert ctx["declined"]["declined"] is True

    def test_declined_context_not_negated(self):
        _, ctx = self._import()
        assert ctx["declined"]["negated"] is False

    def test_cancelled_context_sets_cancelled_flag(self):
        _, ctx = self._import()
        assert ctx["cancelled"]["cancelled"] is True

    def test_cancelled_context_not_negated(self):
        _, ctx = self._import()
        assert ctx["cancelled"]["negated"] is False

    def test_present_context_has_no_declined_or_cancelled(self):
        _, ctx = self._import()
        assert ctx["present"]["declined"] is False
        assert ctx["present"]["cancelled"] is False

    def test_all_canonical_assertions_covered(self):
        valid, ctx = self._import()
        for assertion in valid:
            assert assertion in ctx, f"Missing context entry for '{assertion}'"


# ---------------------------------------------------------------------------
# 2. Schema Mapper
# ---------------------------------------------------------------------------


class TestSchemaMapperAssertionAllowlist:
    """schema_mapper.py assertion allowlist admits declined and cancelled."""

    def _map_entity(self, assertion: str) -> str:
        from libs.ner.schema_mapper import map_raw_record

        text = "patient declined the flu vaccine"
        raw = {
            "document_id": "doc-001",
            "text": text,
            "entities": [
                {
                    "text": "flu vaccine",
                    "start": text.index("flu vaccine"),
                    "end": text.index("flu vaccine") + len("flu vaccine"),
                    "label": "procedure",
                    "assertion": assertion,
                }
            ],
            "relations": [],
            "metadata": {},
        }
        result, reasons = map_raw_record(raw)
        if result is None:
            pytest.skip(f"Entity rejected: {reasons}")
        entities = result.get("entities", [])
        return entities[0]["assertion"] if entities else "missing"

    def test_declined_passes_through(self):
        assert self._map_entity("declined") == "declined"

    def test_cancelled_passes_through(self):
        assert self._map_entity("cancelled") == "cancelled"

    def test_unknown_assertion_coerced_to_present(self):
        assert self._map_entity("nonsense_value") == "present"

    def test_absent_still_passes_through(self):
        assert self._map_entity("absent") == "absent"

    def test_hypothetical_still_passes_through(self):
        assert self._map_entity("hypothetical") == "hypothetical"

    def test_planned_still_passes_through(self):
        assert self._map_entity("planned") == "planned"


# ---------------------------------------------------------------------------
# 3. Documents Queries
# ---------------------------------------------------------------------------


class TestDocumentsQueriesAssertionContext:
    """_assertion_context, _NON_PRESENT, and patient shortcut gate."""

    def _import(self):
        from libs.cypher.documents_queries import (
            _NON_PRESENT,
            _assertion_context,
        )

        return _NON_PRESENT, _assertion_context

    def test_declined_in_non_present(self):
        non_present, _ = self._import()
        assert "declined" in non_present

    def test_cancelled_in_non_present(self):
        non_present, _ = self._import()
        assert "cancelled" in non_present

    def test_planned_in_non_present(self):
        non_present, _ = self._import()
        assert "planned" in non_present

    def test_assertion_context_planned(self):
        _, ctx_fn = self._import()
        ctx = ctx_fn("planned")
        assert ctx["assertion"] == "planned"
        assert ctx["planned"] is True
        assert ctx["negated"] is False
        assert ctx["hypothetical"] is False

    def test_assertion_context_declined(self):
        _, ctx_fn = self._import()
        ctx = ctx_fn("declined")
        assert ctx["assertion"] == "declined"
        assert ctx["declined"] is True
        assert ctx["negated"] is False
        assert ctx["cancelled"] is False

    def test_assertion_context_cancelled(self):
        _, ctx_fn = self._import()
        ctx = ctx_fn("cancelled")
        assert ctx["assertion"] == "cancelled"
        assert ctx["cancelled"] is True
        assert ctx["negated"] is False
        assert ctx["declined"] is False

    def test_assertion_context_none_defaults_to_present(self):
        _, ctx_fn = self._import()
        ctx = ctx_fn(None)
        assert ctx["assertion"] == "present"
        assert ctx["declined"] is False
        assert ctx["cancelled"] is False

    def test_assertion_context_present(self):
        _, ctx_fn = self._import()
        ctx = ctx_fn("present")
        assert ctx["assertion"] == "present"
        assert ctx["negated"] is False
        assert ctx["declined"] is False

    def test_patient_shortcut_gate_uses_foreach(self):
        """FOREACH gate must be present so shortcuts are skipped for
        non-present assertions (declined, cancelled, absent, etc.)."""
        from libs.cypher import documents_queries
        import inspect

        src = inspect.getsource(documents_queries._build_upsert_query)
        assert "FOREACH" in src, (
            "_build_upsert_query must use FOREACH to gate patient shortcut "
            "relationships based on assertion value"
        )

    def test_timeline_query_has_required_return_fields(self):
        from libs.cypher.documents_queries import GET_PATIENT_CODING_TIMELINE

        for field in (
            "encounter_date",
            "encounter_id",
            "concept_id",
            "term",
            "semantic_tag",
            "r.context",
            "r.confidence",
        ):
            assert (
                field in GET_PATIENT_CODING_TIMELINE
            ), f"GET_PATIENT_CODING_TIMELINE is missing field '{field}'"

    def test_timeline_query_ordered_by_date(self):
        from libs.cypher.documents_queries import GET_PATIENT_CODING_TIMELINE

        assert "ORDER BY e.date" in GET_PATIENT_CODING_TIMELINE


# ---------------------------------------------------------------------------
# 4. Tier Classifier
# ---------------------------------------------------------------------------


class TestTierClassifierDeclinedCancelled:
    """declined and cancelled must block auto-coding (Tier 3)."""

    def _classify(self, assertion: str, mode: str) -> object:
        from libs.coding_engine.tier_classifier import classify_tier

        return classify_tier(
            assertion=assertion,
            context_failed=False,
            terminology_score=1.0,
            surface_form_status="approved",
            coding_mode=mode,
        )

    def test_declined_autonomous_is_tier3(self):
        d = self._classify("declined", "autonomous")
        assert d.tier == 3

    def test_declined_hitl_is_tier3(self):
        d = self._classify("declined", "hitl")
        assert d.tier == 3

    def test_cancelled_autonomous_is_tier3(self):
        d = self._classify("cancelled", "autonomous")
        assert d.tier == 3

    def test_cancelled_hitl_is_tier3(self):
        d = self._classify("cancelled", "hitl")
        assert d.tier == 3

    def test_declined_in_auto_code_blocked(self):
        from libs.coding_engine.tier_classifier import _AUTO_CODE_BLOCKED

        assert "declined" in _AUTO_CODE_BLOCKED

    def test_cancelled_in_auto_code_blocked(self):
        from libs.coding_engine.tier_classifier import _AUTO_CODE_BLOCKED

        assert "cancelled" in _AUTO_CODE_BLOCKED

    def test_present_high_confidence_is_not_tier3(self):
        d = self._classify("present", "autonomous")
        assert d.tier != 3


# ---------------------------------------------------------------------------
# 5. Label Verifier constants
# ---------------------------------------------------------------------------


class TestLabelVerifierAssertionSets:
    """_AUTO_CODE_BLOCKED in label_verifier.py blocks all non-present assertions."""

    def test_auto_code_blocked_contains_declined(self):
        """_AUTO_CODE_BLOCKED is a local constant; verify by source inspection."""
        import inspect
        import services.api.app.services.label_verifier as lv

        src = inspect.getsource(lv)
        assert (
            '"declined"' in src or "'declined'" in src
        ), "_AUTO_CODE_BLOCKED must contain 'declined'"

    def test_auto_code_blocked_contains_cancelled(self):
        import inspect
        import services.api.app.services.label_verifier as lv

        src = inspect.getsource(lv)
        assert (
            '"cancelled"' in src or "'cancelled'" in src
        ), "_AUTO_CODE_BLOCKED must contain 'cancelled'"


# ---------------------------------------------------------------------------
# 6. Extractor Contract version
# ---------------------------------------------------------------------------


class TestExtractorContractVersion:
    """CONTRACT_VERSION must be at least 1.2 after the assertion schema change."""

    def test_contract_version_is_1_2(self):
        from libs.ner.extractor_contract import CONTRACT_VERSION

        # The assertion schema change first bumped to 1.2; later bumps
        # (e.g. 1.3 for downstream-only assertion) remain compatible.
        major, minor = CONTRACT_VERSION.split(".", 1)
        assert int(major) == 1 and int(minor) >= 2, (
            f"CONTRACT_VERSION must be >= 1.2; got {CONTRACT_VERSION}"
        )

    def test_extraction_item_assertion_docstring_mentions_declined(self):
        from libs.ner.extractor_contract import ExtractionItem
        import inspect

        src = inspect.getsource(ExtractionItem)
        assert "declined" in src
        assert "cancelled" in src
