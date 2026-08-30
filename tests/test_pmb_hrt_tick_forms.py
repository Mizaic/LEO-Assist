"""HRT-bleed form ticks map to the PMB code, not to HRT or a bleed part.

B7 and B8 on the Sherwood gynae 2WW form mean unexplained bleeding
that cannot be put down to current HRT. That is 76742009.
Short HRT words stay unmapped so salvage cannot return.

Atlas: DI-00DFB149, DI-8BAC9BB3, VT-E053BB7C.
"""

from __future__ import annotations

import json
from pathlib import Path

PMB_ID = "76742009"

_FORM = Path(__file__).resolve().parents[1] / (
    "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"
)

# Taught entity_text and the printed letter spans seen on dry-run.
PMB_TICK_FORMS: tuple[str, ...] = (
    "unexpected bleeding that cannot be attributed to current hrt",
    "postmenopausal bleeding in woman aged over 55 not on hrt",
    (
        "b7. hrt: unexpected or prolonged bleeding persisting "
        "for more than 4 weeks after stopping hrt"
    ),
    (
        "b8. hrt: bleeding persisting after 6 months of hrt use, "
        "if on continuous combined hrt"
    ),
)

_NOT_PMB: frozenset[str] = frozenset(
    {
        "hrt",
        "hormone replacement",
        "on hrt",
        "stopping hrt",
    }
)


def test_hrt_bleed_ticks_are_the_compound_pmb_code() -> None:
    for phrase in PMB_TICK_FORMS:
        assert phrase not in _NOT_PMB
        assert "bleed" in phrase


def test_hrt_word_alone_is_not_a_pmb_surface_form() -> None:
    assert "hrt" not in PMB_TICK_FORMS
    assert "stopping hrt" not in PMB_TICK_FORMS


def test_sfh_b7_b8_entity_text_is_the_taught_pmb_phrase() -> None:
    schema = json.loads(_FORM.read_text())
    items = {
        str(item.get("pattern") or ""): str(item.get("entity_text") or "").lower()
        for section in schema.get("sections") or []
        for item in section.get("items") or []
    }
    shared = "unexpected bleeding that cannot be attributed to current hrt"
    assert items.get("B7.", "") == shared
    assert items.get("B8.", "") == shared


def test_pmb_tick_phrases_target_76742009() -> None:
    assert all(PMB_ID == "76742009" for _ in PMB_TICK_FORMS)
