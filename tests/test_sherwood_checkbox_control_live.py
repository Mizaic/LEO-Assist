"""Prove the deterministic checkbox control is live on a taught-form run.

The Sherwood Gynaecology 2WW schema stored ``section_type: "checkbox"`` on
five of its seven sections. That value is outside the vocabulary the
normaliser dispatches on, so every tick box fell through untouched and an
unticked 2WW criterion reached the model as ordinary text. A referral that
says a cancer criterion was NOT met could be coded as a present finding.

These tests run the taught schema over the real (de-identified) referral
text and assert the control now does its job, and that fixing it did not
bring back the Section C false negative it was traded against.

Atlas trace: DI-5C9CA57B, R-687E8027
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.pipeline.form_checkbox_seed import seed_checkbox_entities
from libs.pipeline.form_schema_normalizer import apply_schema_to_text
from libs.pipeline.form_schema_request import dict_to_section
from libs.pipeline.form_schema_section_types import is_valid_section_type

_FIXTURES = Path(__file__).parent / "fixtures" / "form_schema"
_REFERRAL = _FIXTURES / "sherwood_gynae_2ww_chunks_deid.json"
_TEMPLATE = _FIXTURES / "sfh_gynae_2ww_template.json"

_NON_EXTRACTABLE = "[NON_EXTRACTABLE]"


def _schema():
    from libs.pipeline.form_schema_normalizer import FormSchema

    raw = json.loads(_TEMPLATE.read_text(encoding="utf-8"))
    sections = raw if isinstance(raw, list) else raw["sections"]
    return FormSchema(
        schema_id="sfh-gynae-2ww-v1",
        fingerprint="e61c4289e199cfb5",
        form_name="SFH Gynaecology 2WW referral",
        created_by="tests",
        sections=[dict_to_section(s) for s in sections],
    )


def _referral_text() -> str:
    payload = json.loads(_REFERRAL.read_text(encoding="utf-8"))
    return "\n".join(str(c.get("text", "")) for c in payload["chunks"])


def _extractable_lines(text: str) -> list[str]:
    """Lines the model is still allowed to read as clinical content."""
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith(_NON_EXTRACTABLE)
    ]


@pytest.fixture(scope="module")
def normalised() -> str:
    return apply_schema_to_text(_referral_text(), _schema())


def test_every_section_type_is_one_the_normaliser_dispatches_on() -> None:
    """A value outside the vocabulary is what silenced the control."""
    for section in _schema().sections:
        assert is_valid_section_type(section.section_type), (
            f"{section.section_id} holds {section.section_type!r}, which "
            "falls through to a pass-through and does nothing"
        )


def test_control_actually_changed_the_text(normalised: str) -> None:
    """A no-op normaliser is the regression. The output must differ."""
    assert normalised != _referral_text()
    assert _NON_EXTRACTABLE in normalised


def _canonical_texts(section_id: str) -> dict[str, str]:
    """Map each taught option to the finding the control would emit for it.

    The assertions below compare these exact strings rather than bare words
    such as "vulva", which also appear in the form's guidance prose and would
    make the test fail for a reason that has nothing to do with tick boxes.
    """
    raw = json.loads(_TEMPLATE.read_text(encoding="utf-8"))
    sections = raw if isinstance(raw, list) else raw["sections"]
    section = next(s for s in sections if s["section_id"] == section_id)
    return {i["pattern"]: i["entity_text"] for i in section["items"]}


def test_only_the_ticked_cancer_site_survives(normalised: str) -> None:
    """Ovary [ ] Cervix [X] Endometrium [ ] -- only Cervix is real.

    Tick rows are sealed so the model cannot re-quote them. The taught
    fact is seeded from the tick, not written back into the letter.
    """
    emitted = set(_extractable_lines(normalised))
    canonical = _canonical_texts("section_a_cancer_type")
    for text in canonical.values():
        assert text not in emitted

    seeded = {
        str(e.get("entity_text") or e.get("text") or "")
        for e in seed_checkbox_entities(_referral_text(), _schema())
    }
    assert canonical["Cervix"] in seeded
    for unticked in ("Ovary", "Endometrium", "Vagina", "Vulva"):
        assert canonical[unticked] not in seeded, f"unticked site {unticked} leaked"


def test_the_raw_inline_option_row_is_not_extractable(normalised: str) -> None:
    row = [ln for ln in normalised.splitlines() if "Ovary [ ]" in ln]
    assert row, "Section A option row missing from output"
    assert all(ln.strip().startswith(_NON_EXTRACTABLE) for ln in row)


def test_b1_survives_and_b2_to_b9_yield_nothing(normalised: str) -> None:
    """Only B1 was answered Yes. The other eight must not become findings."""
    emitted = set(_extractable_lines(normalised))
    canonical = _canonical_texts("section_b_symptoms")
    assert len(canonical) == 9, "fixture no longer has all nine B criteria"
    for text in canonical.values():
        assert text not in emitted

    seeded = {
        str(e.get("entity_text") or e.get("text") or "")
        for e in seed_checkbox_entities(_referral_text(), _schema())
    }
    found = {p.split(".")[0] for p, text in canonical.items() if text in seeded}
    assert found == {"B1"}, f"Section B emitted {sorted(found)}"


def test_only_the_ticked_frailty_point_survives(normalised: str) -> None:
    """1. Very Fit [X] -- the other eight scale points are not findings."""
    emitted = set(_extractable_lines(normalised))
    canonical = _canonical_texts("section_e_performance")
    for text in canonical.values():
        assert text not in emitted

    seeded = {
        str(e.get("entity_text") or e.get("text") or "")
        for e in seed_checkbox_entities(_referral_text(), _schema())
    }
    found = {p for p, text in canonical.items() if text in seeded}
    assert found == {"1. Very Fit"}, f"Section E emitted {sorted(found)}"


def test_section_c_narrative_survives_intact(normalised: str) -> None:
    """The false negative this control was traded against must not return."""
    source = _referral_text()
    narrative = [ln for ln in source.splitlines() if "vaginal discharge" in ln.lower()]
    assert narrative, "Section C narrative missing from the fixture"

    lowered = normalised.lower()
    for phrase in (
        "vaginal discharge",
        "no vaginal itch",
        "no pelvic pain",
    ):
        assert phrase in lowered, f"Section C lost {phrase!r}"

    for line in narrative:
        assert line in normalised, "Section C narrative line was rewritten"
        kept = [ln for ln in normalised.splitlines() if ln == line]
        assert kept and not kept[0].strip().startswith(_NON_EXTRACTABLE)


def test_section_c_keeps_its_full_length(normalised: str) -> None:
    """Character-level check: no silent truncation of the narrative."""
    payload = json.loads(_REFERRAL.read_text(encoding="utf-8"))
    section_c = [
        str(c["text"]) for c in payload["chunks"] if "Section C" in str(c.get("text"))
    ]
    assert section_c, "Section C chunk missing from the fixture"

    body = max(section_c, key=len)
    narrative_lines = [
        ln
        for ln in body.splitlines()
        if ln.strip() and not ln.strip().startswith("Section C")
    ]
    kept = sum(len(ln) for ln in narrative_lines if ln in normalised)
    total = sum(len(ln) for ln in narrative_lines)

    assert kept == total, f"Section C lost {total - kept} characters"
    assert total > 800, f"fixture narrative unexpectedly short ({total} chars)"
