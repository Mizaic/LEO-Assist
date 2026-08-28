"""Site 4: a subgraph that fails to import must abort worker startup.

`_register_defaults` used to log and skip a failed registration, so the
worker started with a SHORTER pipeline than the plan asks for. A missing
terminology or post-processing subgraph produces runs that look normal
but skipped a clinical stage.

`.cursor/rules/fail-closed-boundary.mdc` rule 5: "Composition failures
are fatal. A subgraph that fails to register aborts worker startup. It is
never quietly missing from the assembled pipeline at run time."

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26 (fail-closed boundary for clinical safety layers)
  DO: DO-42331CE1
  VT: VT-AA8ED00F
  Risk: R-294446BF
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

import libs.pipeline_graph.registry as registry_module
from libs.pipeline_graph.registry import SubgraphRegistry, _register_defaults

_TERMINOLOGY_MODULE = "libs.pipeline_graph.subgraphs.terminology"

# Clinical stages that must never be quietly missing from a run.
_REQUIRED_SUBGRAPHS = frozenset(
    {
        "encounter_loader",
        "extraction",
        "post_processing",
        "relation_linking",
        "snomed_enrichment",
        "terminology",
        "tier_classify",
        "persist",
        "human_review_gate",
    }
)


# ---------------------------------------------------------------------------
# Happy path -- correct behaviour must not change
# ---------------------------------------------------------------------------


def test_all_default_subgraphs_register_cleanly() -> None:
    registry = SubgraphRegistry()
    _register_defaults(registry)

    registered = {item["id"] for item in registry.list_subgraphs()}
    missing = sorted(_REQUIRED_SUBGRAPHS - registered)
    assert not missing, f"required clinical stages did not register: {missing}"


def test_registered_subgraphs_are_buildable_callables() -> None:
    registry = SubgraphRegistry()
    _register_defaults(registry)

    assert registry.has("terminology")
    assert callable(registry._builders["terminology"])


# ---------------------------------------------------------------------------
# Site 4 -- a registration failure is fatal
# ---------------------------------------------------------------------------


def test_failed_subgraph_import_raises() -> None:
    registry = SubgraphRegistry()
    with patch.dict(sys.modules, {_TERMINOLOGY_MODULE: None}):
        with pytest.raises(Exception):
            _register_defaults(registry)

    assert not registry.has(
        "terminology"
    ), "precondition: the patched terminology import must have failed"


def test_registration_failure_names_the_stage_in_plain_english() -> None:
    registry = SubgraphRegistry()
    with patch.dict(sys.modules, {_TERMINOLOGY_MODULE: None}):
        with pytest.raises(Exception) as excinfo:
            _register_defaults(registry)

    message = str(excinfo.value)
    assert message.isascii()
    assert "terminology" in message
    assert _TERMINOLOGY_MODULE in message
    assert "Cannot start" in message


def test_a_failed_registration_leaves_no_cached_registry() -> None:
    """A short pipeline must never be handed out after a failed build."""
    with patch.object(registry_module, "_default_registry", None):
        with patch.dict(sys.modules, {_TERMINOLOGY_MODULE: None}):
            with pytest.raises(Exception):
                registry_module.get_registry()
        assert registry_module._default_registry is None
