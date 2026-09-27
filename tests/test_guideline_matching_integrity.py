"""VT -- guideline matching uses present facts and an honest scope.

Atlas:
  DI: DI-D260D249
  DO: DO-C9F7BFC8
  VT: VT-76A1816F
  Risk: R-A414D626
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from libs.guidelines.action_already_done import action_already_done
from libs.guidelines.organ_gate import rule_requires_absent_organ
from libs.guidelines.service_rulesets import (
    BREAST_SERVICE_ID,
    GYNAE_SERVICE_ID,
    guideline_ids_for_service,
)
from libs.pipeline_graph.subgraphs.compliance import (
    _entity_codes,
    _evaluate_dual_compliance,
    _evaluate_guideline,
    evaluate_compliance,
)
from libs.sbar.assessment_formatter import format_assessment


def test_absent_and_family_codes_are_excluded_from_guideline_matching() -> None:
    codes = _entity_codes(
        [
            {"concept_id": "254837009", "assertion": "absent"},
            {"concept_id": "275937001", "assertion": "family"},
            {"concept_id": "363346000", "assertion": "refuted"},
            {"concept_id": "161505003", "assertion": "negated"},
            {"concept_id": "22298006", "assertion": "present"},
        ]
    )
    assert codes == ["22298006"]


@patch("libs.pipeline_graph.subgraphs.compliance.GuidelineEvaluator", create=True)
@patch("services.terminology_api.app.services.guideline_evaluator.GuidelineEvaluator")
def test_pipeline_evaluator_is_built_with_a_neo4j_session(
    mock_evaluator_cls: MagicMock,
    _unused: MagicMock,
) -> None:
    evaluator = MagicMock()
    evaluator.evaluate_patient.return_value = {"matched_rules": []}
    mock_evaluator_cls.return_value = evaluator
    session = MagicMock()
    client = MagicMock()
    client.session.return_value.__enter__.return_value = session
    client.session.return_value.__exit__.return_value = False

    with patch(
        "libs.neo4j_client.client.KnowledgeGraphClient",
        return_value=client,
    ):
        _evaluate_guideline({"guideline_scope_id": "NG12"}, ["22298006"])

    mock_evaluator_cls.assert_called()
    kwargs = mock_evaluator_cls.call_args.kwargs
    assert kwargs.get("neo4j_session") is session


def test_resulted_observable_counts_as_already_done() -> None:
    action = {"concept_id": "241390007", "name": "pelvic ultrasound"}
    observations = [{"observable_id": "399034003", "value": 5.7, "unit": "mm"}]

    def _lookup(concept_id: str) -> dict[str, Any]:
        if concept_id == "399034003":
            return {
                "component_of_procedures": [
                    {"id": "241390007", "rel": "component_of_procedures"}
                ]
            }
        return {}

    assert action_already_done(action, [], observations, related_lookup=_lookup)


def test_prostate_rule_does_not_fire_for_a_woman_without_male_anatomy() -> None:
    rule = {
        "rule_id": "ng12-prostate",
        "logic_tree": {
            "type": "CONCEPT",
            "concept_id": "41216001",
        },
    }
    assert rule_requires_absent_organ(rule, "female", []) is True


def test_global_fallback_keeps_scope_id_none() -> None:
    captured: dict[str, Any] = {}

    class _Eval:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def evaluate_patient(self, codes: list[str], **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"matched_rules": [], "not_compiled": True}

    with (
        patch(
            "services.terminology_api.app.services.guideline_evaluator.GuidelineEvaluator",
            _Eval,
        ),
        patch(
            "libs.neo4j_client.client.KnowledgeGraphClient",
            side_effect=RuntimeError("no graph"),
        ),
    ):
        _evaluate_dual_compliance(
            {
                "guideline_scope_id": "val-gardena-defaults",
                "guideline_id": "val-gardena-defaults",
                "healthcare_service_id": "unbound-service",
            },
            ["22298006"],
        )

    assert captured.get("scope_type") == "global"
    assert captured.get("scope_id") is None


def test_missing_ruleset_degrades_and_is_not_called_unsupported() -> None:
    with patch(
        "libs.pipeline_graph.subgraphs.compliance._evaluate_guideline",
        return_value={
            "matched_rules": [],
            "not_compiled": True,
            "scope_type": "guideline",
            "scope_id": "NG12",
        },
    ):
        result = evaluate_compliance(
            {
                "patient_id": "p1",
                "primary_guideline_ids": ["NG12"],
                "healthcare_service_id": BREAST_SERVICE_ID,
                "healthcare_service_name": "Breast Clinic",
                "referral_reason": "Suspected breast cancer",
                "entities": [{"concept_id": "22298006", "assertion": "present"}],
            }
        )

    payload = result["compliance_result"]
    assert payload.get("degraded") is True
    assert payload["primary"].get("ruleset_missing") is True
    narrative = format_assessment(
        matched_rules=[],
        patient_codes=["22298006"],
        guideline_ids=["NG12"],
        compliance_context=payload,
        spoa_disposition=None,
        spoa_disposition_evidence=None,
    )
    text = narrative.markdown.lower()
    assert "could not check" in text or "ruleset" in text
    assert "supported by receiving service? no." not in text


def test_breast_service_117038_is_bound_to_ng12() -> None:
    assert guideline_ids_for_service("117038") == ("NG12",)


def test_gynae_service_7980224_is_bound_to_ng12() -> None:
    assert guideline_ids_for_service(GYNAE_SERVICE_ID) == ("NG12",)


def test_catalogue_ng12_uses_the_full_published_ruleset() -> None:
    calls: list[dict[str, Any]] = []

    class _Eval:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def evaluate_patient(self, codes: list[str], **kwargs: Any) -> dict[str, Any]:
            calls.append(dict(kwargs))
            return {"matched_rules": []}

    with (
        patch(
            "services.terminology_api.app.services.guideline_evaluator.GuidelineEvaluator",
            _Eval,
        ),
        patch(
            "libs.neo4j_client.client.KnowledgeGraphClient",
            side_effect=RuntimeError("no graph"),
        ),
    ):
        _evaluate_dual_compliance(
            {
                "healthcare_service_id": BREAST_SERVICE_ID,
                "primary_guideline_ids": ["NG12"],
            },
            ["89164003"],
        )

    assert calls
    primary = calls[0]
    assert primary.get("pathway_filter") == "NG12"
    assert primary.get("scope_type") == "global"
    assert primary.get("scope_id") is None


def test_placeholder_primary_ids_yield_to_compiled_catalogue() -> None:
    from libs.pipeline_graph.subgraphs.compliance import _primary_guideline_ids

    ids = _primary_guideline_ids(
        {
            "primary_guideline_ids": ["val-gardena-defaults"],
            "healthcare_service_id": BREAST_SERVICE_ID,
        }
    )
    assert ids == ["NG12"]
