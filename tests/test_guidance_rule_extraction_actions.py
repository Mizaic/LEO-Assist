"""Regression coverage for Phase 6's array-shaped ``actions`` rework.

The critical acceptance criterion for this change is that single-action
recommendations produce byte-identical SNOMED codes/strengths to the
pre-refactor single-``action`` pipeline. These tests exercise the real
node functions (code_snomed, agentic_resolve, verify_codes) with the
Terminology API and LLM consensus calls mocked out, since those require
live infra that is unavailable in this test environment.
"""

from __future__ import annotations

from unittest.mock import patch

from libs.pipeline_graph.subgraphs import guidance_rule_extraction_v2_impl as impl


def _candidate(concept_id: str, term: str, score: float, **extra) -> dict:
    return {
        "concept_id": concept_id,
        "preferred_term": term,
        "semantic_tag": "procedure",
        "score": score,
        "read_code": None,
        "source": "hybrid",
        **extra,
    }


# ---------------------------------------------------------------------------
# Schema-level normalisation
# ---------------------------------------------------------------------------


def test_normalise_actions_accepts_new_array_shape():
    data = {
        "actions": [
            {
                "text": "urgent chest X-ray",
                "search_terms": ["chest X-ray"],
                "strength": "offer",
            },
            {"text": "referral", "strength": "refer"},
        ]
    }
    actions = impl._normalise_actions(data)
    assert [a["text"] for a in actions] == ["urgent chest X-ray", "referral"]
    assert [a["strength"] for a in actions] == ["offer", "refer"]


def test_normalise_actions_degrades_legacy_singular_shape_to_one_item_list():
    data = {"action": {"text": "urgent chest X-ray", "strength": "offer"}}
    actions = impl._normalise_actions(data)
    assert len(actions) == 1
    assert actions[0]["text"] == "urgent chest X-ray"
    assert actions[0]["strength"] == "offer"


def test_normalise_actions_empty_when_no_action_present():
    assert impl._normalise_actions({}) == []


def test_normalise_action_strength_falls_back_to_unspecified_for_unknown_value():
    assert impl._normalise_action_strength("not_a_real_strength") == "unspecified"
    assert impl._normalise_action_strength("Offer") == "offer"


# ---------------------------------------------------------------------------
# code_snomed: single action must resolve identically to the pre-refactor
# single-``action`` code path (same candidates, same payload fields).
# ---------------------------------------------------------------------------


def test_code_snomed_single_action_matches_pre_refactor_payload_shape():
    state = {
        "raw_criteria": None,
        "expanded_criteria": {
            "schema_version": 2,
            "logic_tree": None,
            "actions": [
                {
                    "text": "urgent chest X-ray",
                    "search_terms": ["urgent chest X-ray", "plain X-ray of chest"],
                    "strength": "offer",
                }
            ],
        },
        "recommendation": {"verbatim": "Offer an urgent chest X-ray."},
        "errors": [],
    }
    fake_result = {
        "candidates": [_candidate("399208008", "Plain X-ray of chest", 0.95)],
        "resolver_turns": 1,
        "search_history": [["urgent chest X-ray"]],
        "needs_human_review": False,
    }
    with patch.object(
        impl, "_resolve_term_with_controller", return_value=fake_result
    ) as mocked:
        out = impl.code_snomed(state)

    candidate = out["candidate_criteria"]
    assert candidate["logic_tree"] is None
    assert len(candidate["actions"]) == 1
    action = candidate["actions"][0]
    assert action["term"] == "urgent chest X-ray"
    assert action["strength"] == "offer"
    assert action["candidates"] == fake_result["candidates"]
    assert action["snomed_concept_id"] is None  # not yet verified at this stage
    assert action["verification_status"] == "pending"
    assert action["needs_human_review"] is False
    # Exactly one Terminology API resolution call for the one action.
    assert mocked.call_count == 1
    assert mocked.call_args.kwargs["is_action"] is True


def test_code_snomed_resolves_each_action_independently():
    state = {
        "raw_criteria": None,
        "expanded_criteria": {
            "schema_version": 2,
            "logic_tree": None,
            "actions": [
                {
                    "text": "urgent MRI scan",
                    "search_terms": ["urgent MRI scan"],
                    "strength": "offer",
                },
                {
                    "text": "referral for specialist opinion",
                    "search_terms": ["referral for specialist opinion"],
                    "strength": "refer",
                },
            ],
        },
        "recommendation": {"verbatim": "Request an urgent MRI and refer."},
        "errors": [],
    }
    calls: list[str] = []

    def _fake_resolve(*, term_obj, expected_tag, recommendation_text, is_action):
        calls.append(term_obj["text"])
        return {
            "candidates": [_candidate(f"CID-{len(calls)}", term_obj["text"], 0.9)],
            "resolver_turns": 1,
            "search_history": [[term_obj["text"]]],
            "needs_human_review": False,
        }

    with patch.object(impl, "_resolve_term_with_controller", side_effect=_fake_resolve):
        out = impl.code_snomed(state)

    actions = out["candidate_criteria"]["actions"]
    assert len(actions) == 2
    assert calls == ["urgent MRI scan", "referral for specialist opinion"]
    assert actions[0]["candidates"][0]["concept_id"] == "CID-1"
    assert actions[1]["candidates"][0]["concept_id"] == "CID-2"
    assert actions[0]["strength"] == "offer"
    assert actions[1]["strength"] == "refer"


def test_code_snomed_no_rule_expected_returns_empty_actions_list():
    state = {
        "expanded_criteria": {"no_rule_expected": True, "reason": "service_only"},
        "recommendation": {},
        "errors": [],
    }
    out = impl.code_snomed(state)
    assert out["candidate_criteria"]["actions"] == []
    assert out["candidate_criteria"]["no_rule_expected"] is True


# ---------------------------------------------------------------------------
# agentic_resolve: each action independently escalated when its candidates
# are low-confidence.
# ---------------------------------------------------------------------------


def test_agentic_resolve_refines_each_low_confidence_action_independently():
    candidate_criteria = {
        "logic_tree": None,
        "actions": [
            {
                "term": "urgent MRI scan",
                "candidates": [_candidate("1", "MRI scan", 0.4)],
                "resolver_turns": 0,
            },
            {
                "term": "referral for specialist opinion",
                "candidates": [_candidate("2", "Referral", 0.3)],
                "resolver_turns": 0,
            },
        ],
        "hitl_terms": [],
    }
    state = {
        "candidate_criteria": candidate_criteria,
        "recommendation": {"verbatim": "..."},
        "errors": [],
    }
    calls: list[str] = []

    def _fake_agentic(base_term, expected_tag, recommendation_text):
        calls.append(base_term)
        return {
            "best_candidates": [_candidate("9", f"{base_term} refined", 0.92)],
            "resolver_turns": 2,
            "search_history": [[base_term]],
            "needs_human_review": False,
        }

    with patch.object(impl, "_run_agentic_resolver", side_effect=_fake_agentic):
        out = impl.agentic_resolve(state)

    actions = out["candidate_criteria"]["actions"]
    assert calls == ["urgent MRI scan", "referral for specialist opinion"]
    assert len(actions) == 2
    assert actions[0]["candidates"][0]["concept_id"] == "9"
    assert actions[1]["candidates"][0]["concept_id"] == "9"


def test_agentic_resolve_single_action_unchanged_when_already_confident():
    """A high-confidence single action must not trigger the agentic resolver
    (regression: identical to pre-refactor single-action behaviour)."""
    candidate_criteria = {
        "logic_tree": None,
        "actions": [
            {
                "term": "urgent chest X-ray",
                "candidates": [_candidate("399208008", "Plain X-ray of chest", 0.95)],
                "resolver_turns": 1,
            }
        ],
        "hitl_terms": [],
    }
    state = {
        "candidate_criteria": candidate_criteria,
        "recommendation": {"verbatim": "..."},
        "errors": [],
    }
    with patch.object(impl, "_run_agentic_resolver") as mocked:
        out = impl.agentic_resolve(state)

    mocked.assert_not_called()
    assert out["candidate_criteria"]["actions"][0]["candidates"][0]["concept_id"] == (
        "399208008"
    )


# ---------------------------------------------------------------------------
# verify_codes: single action keeps using the LLM verifier's action_decision
# (byte-identical to pre-refactor); a second action falls back to the
# existing deterministic _select_action_candidate scoring.
# ---------------------------------------------------------------------------


class _FakeVerdict:
    def __init__(self, verdict):
        self.verdict = verdict
        self.input_tokens = 10
        self.output_tokens = 5
        self.cached_input_tokens = 0
        self.llm_calls = 1


_VERIFIED_LEAF_TREE = {
    "kind": "concept",
    "node_id": "n1",
    "criterion": {
        "node_id": "n1",
        "term": "chest X-ray findings",
        "source_text": None,
        "candidates": [_candidate("399208008", "Chest X-ray finding", 0.9)],
        "resolver_turns": 1,
        "search_history": [],
        "needs_human_review": False,
    },
}
_VERIFIED_LEAF_DECISION = {
    "node_id": "n1",
    "status": "verified",
    "selected_concept_id": "399208008",
    "reason": "Broad finding is safe.",
    "confidence": 0.9,
    "retry_search_terms": [],
}


def _base_verify_state(actions, urgency="urgent_2w"):
    return {
        "candidate_criteria": {
            "schema_version": 2,
            "logic_tree": _VERIFIED_LEAF_TREE,
            "actions": actions,
        },
        "raw_criteria": {"logic_tree": _VERIFIED_LEAF_TREE},
        "recommendation": {
            "id": "NG12:v1:CH1:SEC1:R1",
            "verbatim": "Offer an urgent chest X-ray.",
            "urgency": urgency,
            "strength": "offer",
        },
        "errors": [],
        "llm_tokens": {},
    }


def test_verify_codes_single_action_matches_pre_refactor_behaviour():
    actions = [
        {
            "term": "urgent chest X-ray",
            "strength": "offer",
            "candidates": [
                _candidate("399208008", "Plain X-ray of chest (procedure)", 0.95)
            ],
            "original_phrase": None,
            "expansion_source": None,
            "expanded_from": None,
            "resolver_turns": 1,
            "needs_human_review": False,
            "search_history": [],
        }
    ]
    state = _base_verify_state(actions)
    verdict = {
        "overall_status": "verified",
        "leaf_decisions": [_VERIFIED_LEAF_DECISION],
        "action_decision": {
            "status": "verified",
            "selected_concept_id": "399208008",
            "reason": "Correct investigation procedure.",
            "confidence": 0.95,
            "retry_search_terms": [],
        },
    }

    with (
        patch.object(impl, "_load_verifier_prompt", return_value=("system prompt", [])),
        patch(
            "libs.llm_client.consensus.run_consensus",
            return_value=_FakeVerdict(verdict),
        ),
        patch("libs.llm_client.consensus._consensus_verifier_tier", return_value="big"),
    ):
        out = impl.verify_codes(state)

    coded = out["coded_criteria"]
    assert len(coded["actions"]) == 1
    assert coded["actions"][0]["snomed_concept_id"] == "399208008"
    assert coded["actions"][0]["strength"] == "offer"
    assert coded["actions"][0]["verification_status"] == "verified"
    # Back-compat shim consumed by guidance_rule_generator.py::_write_rule.
    assert coded["action"] == coded["actions"][0]
    assert out["errors"] == []


def test_verify_codes_second_action_uses_deterministic_fallback_selection():
    actions = [
        {
            "term": "urgent chest X-ray",
            "strength": "offer",
            "candidates": [
                _candidate("399208008", "Plain X-ray of chest (procedure)", 0.95)
            ],
            "resolver_turns": 1,
            "needs_human_review": False,
            "search_history": [],
        },
        {
            "term": "referral for specialist surgical opinion",
            "strength": "refer",
            "candidates": [
                _candidate(
                    "999999001",
                    "Referral for specialist surgical opinion (procedure)",
                    0.9,
                )
            ],
            "resolver_turns": 1,
            "needs_human_review": False,
            "search_history": [],
        },
    ]
    # Routine urgency so the second action's referral candidate (which has no
    # urgency keyword in its preferred_term) passes the deterministic
    # site/urgency compatibility check in _select_action_candidate.
    state = _base_verify_state(actions, urgency="routine")
    verdict = {
        "overall_status": "verified",
        "leaf_decisions": [_VERIFIED_LEAF_DECISION],
        "action_decision": {
            "status": "verified",
            "selected_concept_id": "399208008",
            "reason": "Correct investigation procedure.",
            "confidence": 0.95,
            "retry_search_terms": [],
        },
    }

    with (
        patch.object(impl, "_load_verifier_prompt", return_value=("system prompt", [])),
        patch(
            "libs.llm_client.consensus.run_consensus",
            return_value=_FakeVerdict(verdict),
        ),
        patch("libs.llm_client.consensus._consensus_verifier_tier", return_value="big"),
    ):
        out = impl.verify_codes(state)

    coded = out["coded_criteria"]
    assert len(coded["actions"]) == 2
    assert coded["actions"][0]["snomed_concept_id"] == "399208008"
    assert (
        coded["actions"][0]["verification_reason"] == "Correct investigation procedure."
    )
    assert coded["actions"][1]["snomed_concept_id"] == "999999001"
    # Second action had no LLM verifier opinion, so it is resolved via the
    # deterministic site/urgency fallback policy (existing behaviour reused).
    assert "fallback policy" in coded["actions"][1]["verification_reason"]
    assert coded["action"] == coded["actions"][0]


def test_verify_codes_no_rule_expected_shape_has_empty_actions_and_none_action():
    state = _base_verify_state([])
    state["candidate_criteria"]["no_rule_expected"] = True
    state["candidate_criteria"]["reason"] = "non_codable_service_recommendation"

    out = impl.verify_codes(state)
    coded = out["coded_criteria"]
    assert coded["actions"] == []
    assert coded["action"] is None
    assert coded["no_rule_expected"] is True
