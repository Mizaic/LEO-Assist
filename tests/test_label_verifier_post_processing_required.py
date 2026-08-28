"""The label verifier must not stand in for the post-processing layers.

``fail-closed-boundary.mdc`` rule 1: a no-op stub that stands in for a safety
layer is prohibited.

``label_verifier`` wrapped its import of ``run_post_processing`` in
``except Exception`` and, on failure, installed a pass-through that returned
the entities untouched plus eight no-op predicates. Its own comment said this
"MUST NOT happen in production". Nothing enforced that. The run did not fail;
it lost the lab-value guard, the scope guard, ConText assertion detection and
the disorder gate, and the only signal was a log line and a RuntimeWarning.

This is the same defect as the ConText stub inside
``libs/pipeline/post_processing.py``, one file over. It matters here because
this path writes gold training labels: a label verified without the negation
guard teaches the model that a denied finding was present.

Atlas trace:
  DI: DI-B7A69F26  (fail-closed boundary)
  DI: DI-F22160C3
  Risk: R-294446BF
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE = "services.api.app.services.label_verifier"
_SOURCE = Path("services/api/app/services/label_verifier.py")


def test_the_verifier_uses_the_real_post_processing_stack() -> None:
    """Identity, not just presence: a stub would satisfy a name check."""
    import libs.pipeline.post_processing as real

    verifier = importlib.import_module(_MODULE)

    assert verifier.run_post_processing is real.run_post_processing


def test_no_pass_through_stub_is_defined_in_the_verifier() -> None:
    """A local definition of the entry point is the stub coming back."""
    source = _SOURCE.read_text()

    assert "def run_post_processing(" not in source, (
        "label_verifier defines its own run_post_processing, which means a "
        "run can lose every safety layer and still look processed"
    )
    assert "layers are DISABLED" not in source


def test_label_verification_does_not_call_an_undefined_aws_toggle() -> None:
    """We run Azure only, and the AWS branch here could never execute.

    ``if aws_llm_enabled():`` referenced a name the module never imports, so
    every call raised NameError before reaching a model. flake8 reported it
    as F821 at HEAD.
    """
    source = _SOURCE.read_text()

    assert "aws_llm_enabled" not in source


def test_the_verifier_will_not_load_without_post_processing() -> None:
    """Hiding the stack must break the import, not silently disable it."""
    for name in [m for m in sys.modules if m.startswith(_MODULE)]:
        del sys.modules[name]

    with patch.dict(sys.modules, {"libs.pipeline.post_processing": None}):
        with pytest.raises(ImportError):
            importlib.import_module(_MODULE)

    # Leave the module importable for whatever runs next.
    for name in [m for m in sys.modules if m.startswith(_MODULE)]:
        del sys.modules[name]
    importlib.import_module(_MODULE)
