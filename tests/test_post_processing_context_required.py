"""Negation detection must never be switched off quietly.

``libs/pipeline/post_processing.py`` used to catch a failed ConText import
and define a local no-op ``apply_context_detection_to_dicts``. Layer 7 then
ran and did nothing, so every fact kept whatever assertion the extractor
guessed -- and the extractor guesses ``present``. "No chest pain" would be
recorded as chest pain present, and nothing in the output said the guard
was missing.

``fail-closed-boundary.mdc`` rule 1 is explicit: a no-op stub that stands
in for a safety layer is prohibited. ConText must import for real, and a
failed import must degrade the run.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B7A69F26  (fail-closed boundary for clinical safety layers)
  DI: DI-02AB393F  (degraded runs routed to human review)
  Risk: R-294446BF
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from libs.pipeline_graph.subgraphs.post_processing import (
    POST_PROCESSING_FAILED_WARNING,
    run_post_process,
)

_MODULE = "libs.pipeline.post_processing"
_CONTEXT_MODULE = "libs.ner.context_engine"

_LETTER = "No chest pain today. Abdomen soft."
_CHEST_PAIN: dict[str, Any] = {
    "text": "chest pain",
    "label": "finding",
    "start": 3,
    "end": 13,
    "assertion": "present",
}


@pytest.fixture
def restored_modules() -> Iterator[None]:
    """Put the real modules back after a test hides ConText."""
    saved = {name: sys.modules.get(name) for name in (_MODULE, _CONTEXT_MODULE)}
    try:
        yield
    finally:
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
            else:
                sys.modules.pop(name, None)


def _import_without_context() -> Any:
    """Import the post-processing module with ConText made unavailable."""
    sys.modules[_CONTEXT_MODULE] = None  # type: ignore[assignment]
    sys.modules.pop(_MODULE, None)
    return importlib.import_module(_MODULE)


def test_the_module_uses_the_real_context_engine() -> None:
    """No stub stands in for the negation guard."""
    context_engine = importlib.import_module(_CONTEXT_MODULE)
    post_processing = importlib.import_module(_MODULE)

    assert (
        post_processing.apply_context_detection_to_dicts
        is context_engine.apply_context_detection_to_dicts
    )


def test_post_processing_will_not_load_without_context(
    restored_modules: None,
) -> None:
    """A missing negation guard stops the module loading, loudly."""
    with pytest.raises(ImportError):
        _import_without_context()


def test_a_run_without_context_degrades_instead_of_coding(
    restored_modules: None,
) -> None:
    """The subgraph is where a missing guard turns into a degraded run."""
    sys.modules[_CONTEXT_MODULE] = None  # type: ignore[assignment]
    sys.modules.pop(_MODULE, None)

    result = run_post_process(  # type: ignore[arg-type]
        {
            "encounter_text": _LETTER,
            "entities": [dict(_CHEST_PAIN)],
            "local_concept_patterns": [],
        }
    )

    assert result.get("degraded") is True, result
    assert POST_PROCESSING_FAILED_WARNING in (result.get("warnings") or [])
    assert not result.get("processed_entities"), result.get("processed_entities")


def test_negation_is_applied_when_context_is_available() -> None:
    """The guard that must never be skipped: "No chest pain" is not present."""
    from libs.pipeline.post_processing import run_post_processing

    processed = run_post_processing(_LETTER, [dict(_CHEST_PAIN)])

    assert [e["assertion"] for e in processed] == ["absent"]
