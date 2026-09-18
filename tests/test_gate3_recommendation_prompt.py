"""Gate 3 B3.1 -- generic Recommendation prompt contract."""

from __future__ import annotations

import re

from libs.prompts.sbar_recommendation_v1 import SBAR_RECOMMENDATION_SYSTEM_V1


def test_recommendation_prompt_has_no_assumed_2ww_role_frame() -> None:
    flat = re.sub(r"\s+", " ", SBAR_RECOMMENDATION_SYSTEM_V1).lower()
    assert "2ww suspected cancer referral" not in flat
    assert "referral described in context" in flat
    # Bullet 3 was "notable background findings ... noted for clinical
    # consideration", which invited the model to judge significance. It
    # now restates the finding and nothing more.
    assert "extra documented findings" in flat
    assert "is documented" in flat


def test_recommendation_prompt_forbids_clinical_commentary() -> None:
    """The model restates documented facts; the clinician judges meaning."""
    flat = re.sub(r"\s+", " ", SBAR_RECOMMENDATION_SYSTEM_V1).lower()
    assert "no commentary" in flat
    assert "do not add clinical meaning" in flat
    assert "the clinician judges meaning" in flat
    assert "noted for clinical consideration" not in flat


def test_recommendation_prompt_reports_source_disagreement() -> None:
    """Conflicts are surfaced for a person, never resolved by the model."""
    flat = re.sub(r"\s+", " ", SBAR_RECOMMENDATION_SYSTEM_V1).lower()
    assert "source disagreement" in flat
    assert "name both sides" in flat
    assert "do not pick a winner" in flat
    assert "please check" in flat
    assert "do not drop or resolve them" in flat
