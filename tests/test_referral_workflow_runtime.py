from __future__ import annotations


class _EmptyGlobalReport:
    def to_dict(self) -> dict:
        return {"total_checked": 0, "compliant_count": 0, "issues": []}


def test_quality_check_uses_configured_completeness(monkeypatch):
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(
        quality_check,
        "_load_completeness_schema",
        lambda domain, subdomain: [
            {
                "name": "FIT result",
                "required": True,
                "semantic_categories": [],
                "concept_ids": [71711000112103],
            },
            {
                "name": "Presenting symptom",
                "required": True,
                "semantic_categories": ["finding"],
                "concept_ids": [],
            },
        ],
    )

    result = quality_check.run_quality_checks(
        {
            "patient_id": "p1",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "lower_gi",
            "entities": [{"concept_id": "71711000112103", "semantic_tag": "finding"}],
            "episodes": [{}],
        }
    )

    completeness = result["completeness_result"]
    assert completeness["configured"] is True
    assert completeness["complete"] is True
    assert result["quality_report"]["completeness"] == completeness


def test_quality_check_skips_completeness_when_domain_or_subdomain_missing(
    monkeypatch,
):
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)

    for state in (
        {"patient_id": "p1", "entities": [], "episodes": [{}]},
        {
            "patient_id": "p1",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "",
            "entities": [],
            "episodes": [{}],
        },
    ):
        result = quality_check.run_quality_checks(state)
        assert "completeness_result" not in result
        assert not any(
            issue["issue_type"] == "minimum_dataset_incomplete"
            for issue in result["quality_issues"]
        )


def test_quality_check_reports_unconfigured_completeness(monkeypatch):
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(
        quality_check, "_load_completeness_schema", lambda domain, subdomain: []
    )

    result = quality_check.run_quality_checks(
        {
            "patient_id": "p1",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "lower_gi",
            "entities": [{"concept_id": "71711000112103"}],
            "episodes": [{}],
        }
    )

    completeness = result["completeness_result"]
    assert completeness["configured"] is False
    assert completeness["complete"] is False
    assert any(
        issue["issue_type"] == "minimum_dataset_incomplete"
        for issue in result["quality_issues"]
    )


def test_quality_check_normalises_entity_semantic_tags(monkeypatch):
    from libs.pipeline_graph.subgraphs import quality_check

    monkeypatch.setattr(quality_check, "run_global_quality_checks", _EmptyGlobalReport)
    monkeypatch.setattr(
        quality_check,
        "_load_completeness_schema",
        lambda domain, subdomain: [
            {
                "name": "Lab result",
                "required": True,
                "semantic_categories": ["observable_entity"],
                "concept_ids": [],
            }
        ],
    )
    monkeypatch.setattr(quality_check, "_load_isa_expansion", lambda required_ids: {})

    result = quality_check.run_quality_checks(
        {
            "patient_id": "p1",
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": "lower_gi",
            "entities": [{"semantic_tag": "observable entity"}],
            "episodes": [{}],
        }
    )

    assert result["completeness_result"]["complete"] is True


def test_compliance_uses_guideline_evaluator_when_scope_configured(monkeypatch):
    from libs.pipeline_graph.subgraphs import compliance

    captured = {}

    def fake_guideline(state, codes):
        captured["codes"] = codes
        captured["scope"] = state["guideline_scope_id"]
        return {"matched_rules": [{"id": "rule-1"}], "is_compliant": True}

    monkeypatch.setattr(compliance, "_evaluate_guideline", fake_guideline)

    result = compliance.evaluate_compliance(
        {
            "patient_id": "p1",
            "guideline_scope_id": "NG12",
            "entities": [{"concept_id": "71711000112103"}],
        }
    )

    assert captured == {"codes": ["71711000112103"], "scope": "NG12"}
    assert result["guideline_result"]["is_compliant"] is True
