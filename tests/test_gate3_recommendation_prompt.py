"""Gate 3 B3.1 -- generic Recommendation prompt contract."""

from __future__ import annotations

import re

from libs.prompts.sbar_recommendation_v1 import SBAR_RECOMMENDATION_SYSTEM_V1


def test_recommendation_prompt_has_no_assumed_2ww_role_frame() -> None:
    flat = re.sub(r"\s+", " ", SBAR_RECOMMENDATION_SYSTEM_V1).lower()
    assert "2ww suspected cancer referral" not in flat
    assert "referral described in context" in flat
    assert "notable background findings" in flat
