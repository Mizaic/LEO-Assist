"""Wave 4 tests for the label-smoothing scorer helpers."""

from __future__ import annotations

import pytest

from libs.training_ext.label_smoothing import _blend


def test_blend_identity_at_zero_smoothing():
    assert _blend(0.9, 0.0) == 0.9
    assert _blend(0.3, 0.0) == 0.3


def test_blend_pulls_toward_half():
    assert _blend(0.9, 0.1) == pytest.approx(0.86)
    assert _blend(0.2, 0.1) == pytest.approx(0.23)


def test_blend_zero_passthrough():
    # `_blend` treats exact zero (no positives) as a passthrough so rare
    # labels with no support do not show up as spurious 0.05 after smoothing.
    assert _blend(0.0, 0.5) == 0.0
