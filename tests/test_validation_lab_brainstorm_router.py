"""Tests for POST /validation-lab/brainstorm phases.

Atlas: DI-EB716E68 / DO-A0ADDB38 / VT-C6B93AF0
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest


def test_understand_empty_raises() -> None:
    from libs.validation_lab.brainstorm import run_understand_or_clarify

    with pytest.raises(ValueError):
        run_understand_or_clarify(phase="understand", scenario_text="")


def test_understand_no_rule_short_circuits_without_llm() -> None:
    from libs.validation_lab.brainstorm import run_understand_or_clarify

    with patch("libs.llm_client.factory.create_llm") as create_llm:
        create_llm.side_effect = AssertionError("LLM must not be called")
        out = run_understand_or_clarify(
            phase="understand",
            scenario_text="",
            recommendations=[
                {
                    "recId": "r1",
                    "verbatim": (
                        "Local MDTs should include 2 consultants with "
                        "expertise in managing urinary incontinence."
                    ),
                    "ruleId": "",
                    "ruleStatus": "",
                }
            ],
        )
    assert out["needs_clarification"] is False
    assert out["guidance_message"]
    assert out.get("questions") == []


def test_clarify_round_cap_forces_no_more_questions() -> None:
    from libs.validation_lab.brainstorm import run_understand_or_clarify

    out = run_understand_or_clarify(
        phase="clarify",
        scenario_text="68yo woman with haematuria for 2WW test",
        round=2,
        answers={"q1": "a"},
    )
    assert out["needs_clarification"] is False
    assert out["questions"] == []


def test_propose_strips_unverified_and_caps(monkeypatch) -> None:
    from libs.validation_lab import brainstorm as mod

    def fake_loop(**kwargs: Any) -> dict[str, Any]:
        return {
            "assistant_message": "ok",
            "questions": [],
            "proposed": [
                {
                    "variantId": f"v{i}",
                    "label": f"V{i}",
                    "rationale": "r",
                    "recommended": False,
                    "isControl": False,
                    "triggerConceptIds": ["good"],
                    "pmh": [
                        {
                            "category": "condition",
                            "conceptId": "good",
                            "term": "x",
                        }
                    ],
                    "equity": {"plusGroup": "some_made_up_group"},
                    "expectedTrigger": True,
                }
                for i in range(7)
            ],
            "tool_traces": [],
            "seen_concepts": {"good": {"concept_id": "good"}},
            "seen_observables": set(),
        }

    monkeypatch.setattr(mod, "_run_tool_loop", fake_loop)
    monkeypatch.setattr(
        mod,
        "evaluate_variant_against_rule",
        lambda rule_id, variant: (False, "verified"),
    )
    out = mod.run_propose_variants(scenario_text="haematuria 2WW")
    assert len(out["variants"]) == 5
    assert all(v.get("expectedTrigger") is None for v in out["variants"])
    assert all(
        (v.get("equity") or {}).get("plusGroup") is None for v in out["variants"]
    )


def test_propose_batches_three_per_attached_recommendation(monkeypatch) -> None:
    from libs.validation_lab import brainstorm as mod

    calls: list[dict[str, Any]] = []

    def fake_loop(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        payload = json.loads(kwargs["messages"][0]["content"])
        rec = (payload.get("recommendations") or [{}])[0]
        rec_id = str(rec.get("recId") or "")
        return {
            "assistant_message": "ok",
            "questions": [],
            "proposed": [
                {
                    "variantId": f"{rec_id}-{i}",
                    "targetRecId": rec_id,
                    "label": f"{rec_id} v{i}",
                    "rationale": "r",
                    "recommended": i == 0,
                    "isControl": False,
                    "triggerConceptIds": [],
                    "pmh": [],
                }
                for i in range(3)
            ],
            "tool_traces": [],
            "seen_concepts": {},
            "seen_observables": set(),
        }

    monkeypatch.setattr(mod, "_run_tool_loop", fake_loop)
    monkeypatch.setattr(
        mod,
        "evaluate_variant_against_rule",
        lambda rule_id, variant: (True, "verified"),
    )
    out = mod.run_propose_variants(
        scenario_text="upper GI",
        recommendations=[
            {
                "recId": "rec-a",
                "verbatim": "Refer for oesophageal cancer if dysphagia",
                "ruleId": "R1",
                "ruleStatus": "active",
            },
            {
                "recId": "rec-b",
                "verbatim": "Refer for pancreatic cancer if jaundice",
                "ruleId": "R2",
                "ruleStatus": "active",
            },
        ],
    )
    assert len(calls) == 2
    positives = [v for v in out["variants"] if not v.get("isControl")]
    assert len(positives) == 6
    assert len([v for v in positives if v["targetRecId"] == "rec-a"]) == 3
    assert len([v for v in positives if v["targetRecId"] == "rec-b"]) == 3


def test_propose_retries_when_first_loop_empty(monkeypatch) -> None:
    from libs.validation_lab import brainstorm as mod

    calls: list[dict[str, Any]] = []

    def fake_loop(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "assistant_message": "I will invent patients in prose.",
                "questions": [],
                "proposed": [],
                "tool_traces": [],
                "seen_concepts": {},
                "seen_observables": set(),
            }
        return {
            "assistant_message": "ok",
            "questions": [],
            "proposed": [
                {
                    "variantId": "v1",
                    "label": "Upper GI jaundice",
                    "rationale": "fires UGIB pathway",
                    "recommended": True,
                    "isControl": False,
                    "triggerConceptIds": [],
                    "pmh": [],
                }
            ],
            "tool_traces": [{"tool": "propose_variants", "ok": True}],
            "seen_concepts": {},
            "seen_observables": set(),
        }

    monkeypatch.setattr(mod, "_run_tool_loop", fake_loop)
    out = mod.run_propose_variants(scenario_text="jaundice age 40+")
    assert len(calls) == 2
    assert "toolChoice" in (calls[1].get("tool_config") or {})
    assert len(out["variants"]) == 1


def test_propose_empty_sets_guidance(monkeypatch) -> None:
    from libs.validation_lab import brainstorm as mod

    monkeypatch.setattr(
        mod,
        "_run_tool_loop",
        lambda **kwargs: {
            "assistant_message": "",
            "questions": [],
            "proposed": [],
            "tool_traces": [],
            "seen_concepts": {},
            "seen_observables": set(),
        },
    )
    out = mod.run_propose_variants(scenario_text="jaundice")
    assert out["variants"] == []
    assert "No variants were generated" in (out["guidance_message"] or "")


def test_propose_rejects_too_many_recommendations() -> None:
    from libs.validation_lab.brainstorm import run_propose_variants
    from libs.validation_lab.scenario_patch import MAX_BRAINSTORM_RECOMMENDATIONS

    recs = [
        {
            "recId": f"rec-{i}",
            "verbatim": "Refer people using a suspected cancer pathway referral",
            "ruleId": f"R{i}",
            "ruleStatus": "active",
        }
        for i in range(MAX_BRAINSTORM_RECOMMENDATIONS + 1)
    ]
    with pytest.raises(ValueError, match="Too many recommendations"):
        run_propose_variants(scenario_text="NG12", recommendations=recs)


def test_propose_continues_when_one_recommendation_fails(monkeypatch) -> None:
    from libs.validation_lab import brainstorm as mod
    from libs.validation_lab import brainstorm_propose as propose_mod

    calls = {"n": 0}

    def fake_once(**kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        payload = kwargs["user_payload"]
        rec = (payload.get("recommendations") or [{}])[0]
        rec_id = str(rec.get("recId") or "")
        if rec_id == "rec-a":
            raise RuntimeError("llm down")
        return {
            "assistant_message": "ok",
            "questions": [],
            "proposed": [
                {
                    "variantId": f"{rec_id}-1",
                    "targetRecId": rec_id,
                    "label": "ok",
                    "rationale": "r",
                    "recommended": True,
                    "isControl": False,
                    "triggerConceptIds": [],
                    "pmh": [],
                }
            ],
            "tool_traces": [],
            "seen_concepts": {},
            "seen_observables": set(),
        }

    monkeypatch.setattr(propose_mod, "_propose_once", fake_once)
    monkeypatch.setattr(
        mod,
        "evaluate_variant_against_rule",
        lambda rule_id, variant: (None, "rule not currently compiled"),
    )
    out = mod.run_propose_variants(
        scenario_text="upper GI",
        recommendations=[
            {
                "recId": "rec-a",
                "verbatim": "Refer for oesophageal cancer if dysphagia",
                "ruleId": "R1",
                "ruleStatus": "active",
            },
            {
                "recId": "rec-b",
                "verbatim": "Refer for pancreatic cancer if jaundice",
                "ruleId": "R2",
                "ruleStatus": "active",
            },
        ],
    )
    assert calls["n"] == 2
    assert len(out["variants"]) == 1
    assert out["variants"][0]["targetRecId"] == "rec-b"
    assert "rec-a" in (out["guidance_message"] or "") or "Could not generate" in (
        out["guidance_message"] or ""
    )


def test_propose_with_compiled_rule_stamps_evaluator_value(monkeypatch) -> None:
    from libs.validation_lab import brainstorm as mod

    def fake_loop(**kwargs: Any) -> dict[str, Any]:
        return {
            "assistant_message": "ok",
            "questions": [],
            "proposed": [
                {
                    "variantId": "v1",
                    "targetRecId": "rec-1",
                    "label": "V1",
                    "rationale": "r",
                    "recommended": True,
                    "isControl": False,
                    "triggerConceptIds": ["good"],
                    "pmh": [],
                    "expectedTrigger": False,
                }
            ],
            "tool_traces": [],
            "seen_concepts": {"good": {}},
            "seen_observables": set(),
        }

    monkeypatch.setattr(mod, "_run_tool_loop", fake_loop)
    monkeypatch.setattr(
        mod,
        "evaluate_variant_against_rule",
        lambda rule_id, variant: (True, "verified"),
    )
    out = mod.run_propose_variants(
        scenario_text="x",
        recommendations=[
            {
                "recId": "rec-1",
                "verbatim": "Refer people aged 45 and over with unexplained haematuria",
                "ruleId": "R1",
                "ruleStatus": "active",
            }
        ],
    )
    assert out["variants"][0]["expectedTrigger"] is True
    assert out["variants"][0]["expectedTriggerReason"] == "verified"
