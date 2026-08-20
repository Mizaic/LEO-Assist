"""VT for DI-0C766F85 -- seed known form fingerprints from templates."""

from __future__ import annotations

from pathlib import Path

from libs.pipeline.document_quality import score_document_quality
from libs.pipeline.form_fingerprint_registry import (
    known_fingerprints,
    reset_registry,
    seed_fingerprints,
)

FILLED_LOCAL_GYNAE = """
Section A: Gynaecological Cancer type suspected
(Please put a X in appropriate boxes)
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]
Please take a Ca125 by the time of referral for anyone suspected of Ovarian cancer.
Section B: Signs/symptoms for 14-day rule criteria
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
B2. Lesion on clinical examination of the vulva | Yes [ ] No [ ]
"""


def test_seeded_skeleton_matches_filled_copy(tmp_path: Path) -> None:
    reset_registry()
    skeleton = tmp_path / "local-2ww-gynae.fingerprint.txt"
    skeleton.write_text(
        "Section A: Gynaecological Cancer type suspected\n"
        "(Please put a X in appropriate boxes)\n"
        "Ovary [ ] Cervix [ ] Endometrium [ ] Vagina [ ] Vulva [ ]\n"
        "Please take a Ca125 by the time of referral for anyone "
        "suspected of Ovarian cancer.\n"
        "Section B: Signs/symptoms for 14-day rule criteria\n"
        "B1. Lesion suspicious of cancer of cervix | Yes [ ] No [ ]\n"
        "B2. Lesion on clinical examination of the vulva | Yes [ ] No [ ]\n",
        encoding="ascii",
    )
    assert seed_fingerprints(tmp_path) == 1
    scored = score_document_quality(
        FILLED_LOCAL_GYNAE,
        few_shot_max_similarity=0.80,
        known_fingerprints=known_fingerprints(),
    )
    assert scored.form_fingerprint_id == "local-2ww-gynae"
    assert "unknown_form_template" not in scored.quality_reasons


def test_seeded_nss_does_not_match_gynae(tmp_path: Path) -> None:
    reset_registry()
    (tmp_path / "nss-2ww.fingerprint.txt").write_text(
        "Appendix A: Referral criteria\n| Unexplained DVT | [ ] |\n",
        encoding="ascii",
    )
    seed_fingerprints(tmp_path)
    scored = score_document_quality(
        FILLED_LOCAL_GYNAE,
        few_shot_max_similarity=0.80,
        known_fingerprints=known_fingerprints(),
    )
    assert scored.form_fingerprint_id == "unknown"
    assert "unknown_form_template" in scored.quality_reasons


def test_repo_fingerprints_include_local_gynae() -> None:
    reset_registry()
    assert seed_fingerprints() >= 1
    scored = score_document_quality(
        FILLED_LOCAL_GYNAE,
        few_shot_max_similarity=0.80,
        known_fingerprints=known_fingerprints(),
    )
    assert scored.form_fingerprint_id == "local-2ww-gynae"
    assert "unknown_form_template" not in scored.quality_reasons
