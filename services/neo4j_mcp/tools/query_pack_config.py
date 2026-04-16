"""Thresholds, ownership, and SLA metadata for DQ/variation query pack."""

from __future__ import annotations

from typing import Any

QUERY_POLICY: dict[str, dict[str, Any]] = {
    "dq_shell_patients": {
        "owner": "ops_data_ingestion",
        "sla_hours": 24,
        "thresholds": {"max_shell_patients": 0},
        "action": "Quarantine shell patients from KPI denominators and open ingestion remediation case.",
    },
    "dq_patients_with_encounters_no_documents": {
        "owner": "coding_qa",
        "sla_hours": 24,
        "thresholds": {"max_patients": 0},
        "action": "Enqueue recode workflow and inspect extractor/writeback failures.",
    },
    "dq_coding_completeness_by_site_month": {
        "owner": "ops_data_quality",
        "sla_hours": 24,
        "thresholds": {"coverage_floor_pct": 95.0, "min_encounters_per_bucket": 25},
        "action": "Raise incident when coverage floor is breached for any org-month bucket.",
    },
    "dq_assertion_contradictions_same_concept": {
        "owner": "clinical_coding_governance",
        "sla_hours": 8,
        "thresholds": {"max_conflicts": 0},
        "action": "Route contradictions to review queue and suspend shortcut propagation for affected concepts.",
    },
    "dq_high_risk_low_confidence_codes": {
        "owner": "clinical_safety_lead",
        "sla_hours": 4,
        "thresholds": {"confidence_floor": 0.7, "min_case_count": 1},
        "action": "Force human review for high-risk low-confidence coding events.",
    },
    "dq_stale_unactioned_safety_alerts": {
        "owner": "pathway_coordinator",
        "sla_hours": 8,
        "thresholds": {"stale_days": 14},
        "action": "Escalate stale unactioned alerts to service owner worklist.",
    },
    "dq_missing_milestone_chains": {
        "owner": "pathway_analytics",
        "sla_hours": 24,
        "thresholds": {"required_milestones": 3},
        "action": "Trigger episode rebuild and open data quality case for broken chains.",
    },
    "dq_outlier_stage_delays": {
        "owner": "capacity_planning",
        "sla_hours": 48,
        "thresholds": {"max_referral_to_diagnosis_days": 62, "max_diagnosis_to_treatment_days": 31},
        "action": "Review service bottlenecks and capacity constraints for outlier pathways.",
    },
    "dq_looping_pathways": {
        "owner": "pathway_coordinator",
        "sla_hours": 24,
        "thresholds": {"max_repeat_milestone_count": 3},
        "action": "Prioritize cases with repeated milestone loops for senior review.",
    },
    "dq_orphan_coded_encounters": {
        "owner": "pathway_analytics",
        "sla_hours": 24,
        "thresholds": {"max_orphans": 0},
        "action": "Run episode linking rebuild for coded encounters not attached to episodes.",
    },
    "dq_escalation_yield_by_rule": {
        "owner": "clinical_governance",
        "sla_hours": 72,
        "thresholds": {"min_action_rate_pct": 20.0, "min_alerts": 20},
        "action": "Retune or downgrade low-yield rules with high alert burden.",
    },
    "dq_repeat_escalations_no_state_change": {
        "owner": "ops_data_quality",
        "sla_hours": 24,
        "thresholds": {"repeat_alert_threshold": 3},
        "action": "Deduplicate repeat escalation events until state changes.",
    },
    "dq_false_positive_proxy_by_rule": {
        "owner": "clinical_governance",
        "sla_hours": 72,
        "thresholds": {"max_dismissed_rate_pct": 60.0, "min_alerts": 15},
        "action": "Tighten criteria for rules with high dismissed/ignored rates.",
    },
    "dq_escalation_parity_by_site": {
        "owner": "clinical_governance",
        "sla_hours": 72,
        "thresholds": {"max_rate_ratio_vs_median": 2.0, "min_encounters": 50},
        "action": "Investigate unwarranted escalation variation across sites after case-mix review.",
    },
    "dq_training_candidate_pipeline_health": {
        "owner": "ml_ops",
        "sla_hours": 24,
        "thresholds": {"max_failed_pct": 5.0, "max_pending_age_days": 14},
        "action": "Prioritize queue burn-down and investigate generator failures.",
    },
    "dq_gold_label_conflicts": {
        "owner": "coding_qa",
        "sla_hours": 48,
        "thresholds": {"max_conflicts": 0},
        "action": "Send conflicting gold labels to phrase consistency adjudication.",
    },
    "dq_gold_label_span_payload_issues": {
        "owner": "ml_ops",
        "sla_hours": 24,
        "thresholds": {"max_invalid_payloads": 0},
        "action": "Repair malformed entity payloads or quarantine examples from training export.",
    },
    "dq_writeback_effectiveness_drift": {
        "owner": "terminology_admin",
        "sla_hours": 72,
        "thresholds": {"min_surface_form_mapping_rate_pct": 95.0, "min_use_count": 5},
        "action": "Create/update surface-form mappings for recurring unresolved terms.",
    },
}

