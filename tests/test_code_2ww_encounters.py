from __future__ import annotations

from scripts.code_2ww_encounters import _infer_site


def test_2ww_target_site_beats_background_breast_history() -> None:
    text = (
        "Refer re neck - ?2ww neck as has breast cancer ??relevant ?skin based "
        "- hard to be sure"
    )

    assert _infer_site(text) == "head_neck"

