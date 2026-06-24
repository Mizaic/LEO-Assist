"""Tests for the Comprehensive Audit Builder changes.

Covers:
  - libs/cypher/audit_metric_queries.py  (registry refactor, 32 metrics)
  - libs/cypher/_audit_metrics_extended.py (18 new metrics, all tiers)
  - libs/cypher/sbar_assessment_queries.py (completeness_failed_count field)
  - services/pipeline_worker/.../referral_durable_steps.py (_count_completeness_failures)
  - services/analytics_api/app/models/audit_template.py (global scope_type)
  - services/analytics_api/app/routers/audit_draft.py (tool config, routes)

Atlas trace: VT-32FBAA69 / DI-64CA7740 / DO-3775670C
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------


class TestMetricRegistry:
    def setup_method(self):
        from libs.cypher.audit_metric_queries import (
            METRIC_REGISTRY,
            get_catalogue,
            get_metric,
            _ORG_GUARD,
            _EPISODE_ACTIVE,
        )
        self.METRIC_REGISTRY = METRIC_REGISTRY
        self.get_catalogue = get_catalogue
        self.get_metric = get_metric
        self._ORG_GUARD = _ORG_GUARD
        self._EPISODE_ACTIVE = _EPISODE_ACTIVE

    def test_total_metric_count(self):
        assert len(self.METRIC_REGISTRY) == 32

    def test_original_14_metrics_still_present(self):
        original_ids = {
            "patient_count", "episode_count_by_status", "episode_count_by_condition",
            "referral_route_distribution", "referral_site_distribution",
            "place_of_presentation", "primary_care_interval", "diagnostic_interval",
            "episodes_over_time", "coding_completeness", "top_coded_conditions",
            "safety_net_alerts_by_type", "cancer_type_distribution",
            "cancer_stage_distribution",
        }
        ids = {m["metric_id"] for m in self.METRIC_REGISTRY}
        assert original_ids.issubset(ids)

    def test_18_new_metrics_present(self):
        new_ids = {
            # Tier A
            "referral_stt_rate", "referral_guideline_compliance_rate",
            "referral_alternative_pathway_rate", "referral_completeness_rate",
            # Tier B
            "patient_gender_distribution", "patient_age_band_distribution",
            "imd_distribution", "conditions_by_deprivation",
            # Tier C
            "early_stage_detection_rate", "cancer_conversion_rate",
            "emergency_presentation_rate", "outcome_distribution",
            # Tier D
            "unactioned_alerts_by_age", "alert_escalation_rate",
            "repeat_referral_patients",
            # Tier E
            "episode_open_age_distribution", "referral_completion_rate",
            "coding_backlog_by_site",
        }
        ids = {m["metric_id"] for m in self.METRIC_REGISTRY}
        assert new_ids.issubset(ids)

    def test_all_metrics_have_required_fields(self):
        required = {"metric_id", "title", "description", "output_type",
                    "param_schema", "output_schema", "cypher"}
        for m in self.METRIC_REGISTRY:
            missing = required - set(m.keys())
            assert not missing, f"{m['metric_id']} missing fields: {missing}"

    def test_get_metric_returns_cypher(self):
        m = self.get_metric("referral_stt_rate")
        assert m is not None
        assert "cypher" in m
        assert "$scope_org_ids" in m["cypher"]

    def test_get_metric_unknown_returns_none(self):
        assert self.get_metric("does_not_exist") is None

    def test_catalogue_excludes_cypher(self):
        cat = self.get_catalogue()
        assert len(cat) == 32
        for item in cat:
            assert "cypher" not in item

    def test_back_compat_aliases_exist(self):
        assert self._ORG_GUARD
        assert self._EPISODE_ACTIVE

    def test_all_metrics_use_org_guard(self):
        """Every metric cypher must enforce tenant isolation."""
        for m in self.METRIC_REGISTRY:
            cypher = m["cypher"]
            assert "scope_org_ids" in cypher, (
                f"{m['metric_id']} does not reference $scope_org_ids"
            )

    def test_output_types_are_valid(self):
        valid = {"kpi_strip", "bar_chart", "line_chart", "table", "interval_plot", "text"}
        for m in self.METRIC_REGISTRY:
            assert m["output_type"] in valid, (
                f"{m['metric_id']} has invalid output_type: {m['output_type']}"
            )

    def test_no_duplicate_metric_ids(self):
        ids = [m["metric_id"] for m in self.METRIC_REGISTRY]
        assert len(ids) == len(set(ids)), "Duplicate metric_id detected"


# ---------------------------------------------------------------------------
# Completeness count helper
# ---------------------------------------------------------------------------


class TestCountCompletnesFailures:
    def setup_method(self):
        from services.pipeline_worker.app.services.referral_durable_steps import (
            _count_completeness_failures,
        )
        self.fn = _count_completeness_failures

    def test_empty_result_returns_zero(self):
        assert self.fn({}) == 0

    def test_no_missing_groups_returns_zero(self):
        assert self.fn({"missing_groups": []}) == 0

    def test_counts_only_required_fields(self):
        result = self.fn({
            "missing_groups": [
                {"name": "reason", "required": True},
                {"name": "history", "required": True},
                {"name": "optional_note", "required": False},
            ]
        })
        assert result == 2

    def test_none_missing_groups_returns_zero(self):
        assert self.fn({"missing_groups": None}) == 0

    def test_all_optional_returns_zero(self):
        result = self.fn({
            "missing_groups": [{"name": "x", "required": False}]
        })
        assert result == 0

    def test_missing_required_key_treated_as_not_required(self):
        result = self.fn({
            "missing_groups": [{"name": "x"}]  # no 'required' key
        })
        assert result == 0


# ---------------------------------------------------------------------------
# SET_ASSESSMENT_COMPLETENESS Cypher
# ---------------------------------------------------------------------------


class TestSetAssessmentCompleteness:
    def setup_method(self):
        from libs.cypher.sbar_assessment_queries import SET_ASSESSMENT_COMPLETENESS
        self.query = SET_ASSESSMENT_COMPLETENESS

    def test_sets_completeness_result_json(self):
        assert "completeness_result_json" in self.query

    def test_sets_completeness_failed_count(self):
        assert "completeness_failed_count" in self.query
        assert "$completeness_failed_count" in self.query

    def test_sets_updated_at(self):
        assert "updated_at" in self.query


# ---------------------------------------------------------------------------
# TemplateAssignment global scope_type
# ---------------------------------------------------------------------------


class TestTemplateAssignmentGlobalScope:
    def test_global_scope_type_is_valid(self):
        from services.analytics_api.app.models.audit_template import (
            TemplateAssignmentCreate,
        )
        ta = TemplateAssignmentCreate(
            template_id="t1", scope_type="global", scope_id="__global__"
        )
        assert ta.scope_type == "global"
        assert ta.scope_id == "__global__"

    def test_org_and_group_still_valid(self):
        from services.analytics_api.app.models.audit_template import (
            TemplateAssignmentCreate,
        )
        for st in ("org", "group", "global"):
            TemplateAssignmentCreate(template_id="t1", scope_type=st, scope_id="x")

    def test_invalid_scope_type_raises(self):
        from pydantic import ValidationError
        from services.analytics_api.app.models.audit_template import (
            TemplateAssignmentCreate,
        )
        with pytest.raises(ValidationError):
            TemplateAssignmentCreate(
                template_id="t1", scope_type="universe", scope_id="x"
            )


# ---------------------------------------------------------------------------
# audit_draft router
# ---------------------------------------------------------------------------


class TestAuditDraftRouter:
    def setup_method(self):
        from services.analytics_api.app.routers.audit_draft import (
            router, DraftRequest, DraftMessage,
            _TOOL_CONFIG, _DESIGN_REPORT_TOOL,
        )
        self.router = router
        self.DraftRequest = DraftRequest
        self.DraftMessage = DraftMessage
        self.TOOL_CONFIG = _TOOL_CONFIG
        self.DESIGN_REPORT_TOOL = _DESIGN_REPORT_TOOL

    def test_router_has_draft_route(self):
        paths = [r.path for r in self.router.routes]
        assert "/audit-templates/draft" in paths

    def test_tool_config_forces_design_report(self):
        assert self.TOOL_CONFIG["toolChoice"]["tool"]["name"] == "design_report"
        assert len(self.TOOL_CONFIG["tools"]) == 1

    def test_tool_spec_has_required_fields(self):
        spec = self.DESIGN_REPORT_TOOL["toolSpec"]
        assert spec["name"] == "design_report"
        schema = spec["inputSchema"]["json"]
        assert "rationale" in schema["properties"]
        assert "tiles" in schema["properties"]
        assert set(schema["required"]) == {"rationale", "tiles"}

    def test_tile_item_has_required_fields(self):
        tiles_schema = self.DESIGN_REPORT_TOOL["toolSpec"]["inputSchema"]["json"]
        tile_item = tiles_schema["properties"]["tiles"]["items"]
        assert set(tile_item["required"]) == {"metric_id", "label", "tile_type"}

    def test_draft_request_model(self):
        msg = self.DraftMessage(role="user", content="hello")
        req = self.DraftRequest(
            messages=[msg],
            current_tiles=[{"metric_id": "patient_count", "label": "Patients"}],
        )
        assert len(req.messages) == 1
        assert req.existing_metric_ids == []
        assert req.current_tiles[0]["metric_id"] == "patient_count"

    def test_draft_message_role_validation(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self.DraftMessage(role="system", content="x")
