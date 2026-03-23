from __future__ import annotations

import importlib
import json
import sys
import types


def _load_prompts_router():
    # Test environment may not have full auth/neo4j deps; stub minimal modules
    # required for importing the prompts router.
    if "libs.auth.org_scope" not in sys.modules:
        auth_pkg = types.ModuleType("libs.auth")
        org_scope = types.ModuleType("libs.auth.org_scope")

        class CallerScope:  # noqa: D401 - simple test stub
            """Test stub."""

        def get_caller_scope():
            return None

        org_scope.CallerScope = CallerScope
        org_scope.get_caller_scope = get_caller_scope
        sys.modules["libs.auth"] = auth_pkg
        sys.modules["libs.auth.org_scope"] = org_scope

    if "app.db.neo4j_client" not in sys.modules:
        neo4j_client = types.ModuleType("app.db.neo4j_client")

        class CodingGraphClient:  # noqa: D401 - simple test stub
            """Test stub."""

        neo4j_client.CodingGraphClient = CodingGraphClient
        sys.modules["app.db.neo4j_client"] = neo4j_client

    return importlib.import_module("app.routers.prompts")


class _FakeResult:
    def __init__(self, row=None) -> None:  # noqa: ANN001
        self._row = row

    def single(self):  # noqa: ANN001
        return self._row


class _FakeSession:
    def __init__(self, run_handler) -> None:  # noqa: ANN001
        self._run_handler = run_handler

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    def run(self, query, **params):  # noqa: ANN001
        return self._run_handler(query, params)


class _FakeClient:
    def __init__(self, run_handler) -> None:  # noqa: ANN001
        self._run_handler = run_handler

    def session(self):
        return _FakeSession(self._run_handler)

    def close(self) -> None:
        return None


def test_create_prompt_persists_max_few_shot_and_core(monkeypatch) -> None:
    prompts_router = _load_prompts_router()
    calls: list[tuple[object, dict]] = []

    def _run(query, params):  # noqa: ANN001
        calls.append((query, params))
        return _FakeResult()

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))
    monkeypatch.setattr(prompts_router.uuid, "uuid4", lambda: "prompt-123")

    body = prompts_router.PromptCreateRequest(
        name="extraction",
        description="test",
        systemPrompt="rules",
        outputSchema='{"type":"object"}',
        verification=False,
        maxFewShot=17,
        fewShotExamples=[
            prompts_router.FewShotExample(
                id="ex-1",
                input="[s0] No fever.",
                output='{"terms":[]}',
                deidentified=True,
                category="assertion:absent",
                model_scope="any",
                description="negation",
                core=True,
            )
        ],
    )

    resp = prompts_router.create_prompt(body=body, scope=None)
    assert resp["id"] == "prompt-123"
    assert len(calls) == 1

    _, params = calls[0]
    assert params["max_few_shot"] == 17
    saved_examples = json.loads(params["few_shot_examples"])
    assert saved_examples[0]["core"] is True


def test_update_prompt_persists_max_few_shot_and_core(monkeypatch) -> None:
    prompts_router = _load_prompts_router()
    calls: list[tuple[object, dict]] = []

    def _run(query, params):  # noqa: ANN001
        calls.append((query, params))
        return _FakeResult({"id": params.get("id")})

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))

    body = prompts_router.PromptUpdateRequest(
        name="extraction",
        description="updated",
        systemPrompt="rules v2",
        outputSchema='{"type":"object"}',
        verification=True,
        maxFewShot=9,
        fewShotExamples=[
            prompts_router.FewShotExample(
                id="ex-2",
                input="[s0] eGFR 42",
                output='{"terms":[]}',
                deidentified=True,
                category="observable",
                model_scope="any",
                description="lab",
                core=False,
            )
        ],
    )

    resp = prompts_router.update_prompt(prompt_id="pid-1", body=body, scope=None)
    assert resp["status"] == "updated"
    assert len(calls) == 1

    _, params = calls[0]
    assert params["id"] == "pid-1"
    assert params["max_few_shot"] == 9
    saved_examples = json.loads(params["few_shot_examples"])
    assert saved_examples[0]["core"] is False


def test_get_prompt_returns_default_max_few_shot_when_null(monkeypatch) -> None:
    prompts_router = _load_prompts_router()
    row = {
        "id": "pid-2",
        "name": "extraction",
        "description": "",
        "version": 1,
        "systemPrompt": "rules",
        "outputSchema": "{}",
        "verification": False,
        "fewShotExamples": "[]",
        "maxFewShot": None,
    }

    def _run(query, params):  # noqa: ANN001
        return _FakeResult(row)

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))

    resp = prompts_router.get_prompt(prompt_id="pid-2", scope=None)
    assert resp["id"] == "pid-2"
    assert resp["maxFewShot"] == 20


def test_simulate_prompt_dry_run_assembles_prompt(monkeypatch) -> None:
    """Dry-run simulate returns assembled system prompt, core/dynamic split, user message."""
    prompts_router = _load_prompts_router()

    core_ex = {
        "id": "ex-core", "input": "[s0] No fever.", "output": '{"terms":[]}',
        "deidentified": True, "category": "assertion:absent", "model_scope": "any",
        "description": "negation", "core": True,
    }
    dyn_ex = {
        "id": "ex-dyn", "input": "[s0] eGFR 42.", "output": '{"terms":[]}',
        "deidentified": True, "category": "observable", "model_scope": "any",
        "description": "lab", "core": False,
    }
    row = {
        "id": "pid-sim",
        "name": "extraction",
        "description": "",
        "version": 1,
        "systemPrompt": "Extract clinical entities.",
        "outputSchema": "{}",
        "verification": False,
        "fewShotExamples": json.dumps([core_ex, dyn_ex]),
        "maxFewShot": 20,
    }

    def _run(query, params):  # noqa: ANN001
        return _FakeResult(row)

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))

    body = prompts_router.SimulateRequest(
        encounterText="Patient has no fever and eGFR 42.",
        provider="aws",
        dryRun=True,
    )
    resp = prompts_router.simulate_prompt(prompt_id="pid-sim", body=body, scope=None)

    assert "systemPrompt" in resp
    assert "Extract clinical entities." in resp["systemPrompt"]
    assert len(resp["coreExamples"]) == 1
    assert resp["coreExamples"][0]["category"] == "assertion:absent"
    assert isinstance(resp["selectedDynamicExamples"], list)
    assert "eGFR 42" in resp["userMessage"]
    assert resp["llmResponse"] is None
    assert resp["llmTokenUsage"] is None
    assert isinstance(resp["tokenEstimate"]["approxSystemTokens"], int)
    assert isinstance(resp["tokenEstimate"]["approxUserTokens"], int)
    # New cost structure
    assert "costEstimates" in resp
    assert len(resp["costEstimates"]) == 1
    ce = resp["costEstimates"][0]
    assert ce["role"] == "primary"
    assert "withoutCache" in ce
    assert "withCache" in ce
    assert "cacheSavingPct" in ce


def test_simulate_prompt_returns_model_cost_and_estimate(monkeypatch) -> None:
    prompts_router = _load_prompts_router()

    row = {
        "id": "pid-cost",
        "name": "extraction",
        "description": "",
        "version": 1,
        "systemPrompt": "Extract entities.",
        "outputSchema": "{}",
        "verification": False,
        "fewShotExamples": "[]",
        "maxFewShot": 20,
    }

    def _run(query, params):  # noqa: ANN001
        return _FakeResult(row)

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))
    monkeypatch.setenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_INPUT_TOKEN", "1.00")
    monkeypatch.setenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_CACHED_INPUT_TOKEN", "0.01")
    monkeypatch.setenv("AWS_BEDROCK_MODEL_SMALL_MODEL_COST_PER_1M_OUTPUT_TOKEN", "5.00")

    body = prompts_router.SimulateRequest(
        encounterText="No fever noted.",
        provider="aws",
        tier="small",
        dryRun=True,
    )
    resp = prompts_router.simulate_prompt(prompt_id="pid-cost", body=body, scope=None)

    assert "costEstimates" in resp
    assert len(resp["costEstimates"]) >= 1
    ce = resp["costEstimates"][0]
    assert ce["model"]["provider"] == "aws"
    assert ce["model"]["tier"] == "small"
    assert ce["model"]["costPer1mInput"] == 1.00
    assert ce["model"]["costPer1mCachedInput"] == 0.01
    assert ce["model"]["costPer1mOutput"] == 5.00
    assert ce["withoutCache"]["totalCost"] >= 0
    assert ce["withCache"]["totalCost"] >= 0
    assert ce["withCache"]["totalCost"] <= ce["withoutCache"]["totalCost"]
    assert resp["llmActualCostUsd"] is None  # dry run


def test_get_model_costs_returns_all_combos(monkeypatch) -> None:
    prompts_router = _load_prompts_router()
    resp = prompts_router.get_model_costs(scope=None)

    keys = {c["key"] for c in resp["modelCosts"]}
    assert keys == {"aws:small", "aws:big", "aws:max", "azure:small", "azure:big", "azure:max"}

    for entry in resp["modelCosts"]:
        assert "displayName" in entry
        assert "modelId" in entry
        assert "costPer1mInput" in entry
        assert "costPer1mCachedInput" in entry
        assert "costPer1mOutput" in entry


def test_simulate_prompt_404_for_unknown_id(monkeypatch) -> None:
    prompts_router = _load_prompts_router()

    def _run(query, params):  # noqa: ANN001
        return _FakeResult(None)

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))

    import pytest
    with pytest.raises(Exception):
        prompts_router.simulate_prompt(
            prompt_id="does-not-exist",
            body=prompts_router.SimulateRequest(encounterText="x"),
            scope=None,
        )


def test_get_prompt_parses_core_field_from_examples(monkeypatch) -> None:
    prompts_router = _load_prompts_router()
    row = {
        "id": "pid-3",
        "name": "extraction",
        "description": "",
        "version": 1,
        "systemPrompt": "rules",
        "outputSchema": "{}",
        "verification": False,
        "fewShotExamples": json.dumps(
            [
                {
                    "id": "ex-3",
                    "input": "[s0] No fever.",
                    "output": '{"terms":[]}',
                    "deidentified": True,
                    "category": "assertion:absent",
                    "model_scope": "any",
                    "description": "negation",
                    "core": True,
                }
            ]
        ),
        "maxFewShot": 11,
    }

    def _run(query, params):  # noqa: ANN001
        return _FakeResult(row)

    monkeypatch.setattr(prompts_router, "CodingGraphClient", lambda: _FakeClient(_run))

    resp = prompts_router.get_prompt(prompt_id="pid-3", scope=None)
    assert resp["maxFewShot"] == 11
    assert resp["fewShotExamples"][0]["core"] is True
