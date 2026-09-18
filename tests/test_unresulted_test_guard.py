"""A blank row of a blood panel is not evidence that the test was done.

Measured on five production referrals: eight facts on one patient came from
the empty MANDATORY blood panel on the Sherwood 2WW form. The model quoted
the bare battery labels -- "FBC", "LFT", "UE", "CRP", "Bone", "Lipids",
"Iron", "Random Glucose" -- off rows like::

    | FBC |  | Hb , WCC , Plts , MCV , Neut |  |  |

and each landed as a procedure asserted ``present``. Nothing on that row was
resulted. The form prints the panel on every referral whether or not the
bloods were taken, so the label is evidence of nothing.

The existing result-gated normalisation could not catch this. It only fires
for chunks the taught schema maps to an ``ordered_tests`` section, and this
schema's ``chunk_section_map`` is empty, so the panel chunk passed through
untouched. Forms differ per organisation and service, so a hand-maintained
map is the wrong place to carry a safety property.

Two things this must NOT do:

  - It must not touch a condition. A problem-list row such as
    ``| Diastolic dysfunction (XaYYs) | [DATE] - Ongoing |`` reports no
    number, but the condition is real.
  - It must not touch a requested test. An empty row genuinely supports
    "this test is being asked for", so a ``planned`` assertion stands. It is
    only ``present`` -- "this was done" -- that the blank row contradicts.

Atlas trace:
  DI: DI-5C9CA57B  (form markup must not become present findings)
  DO: DO-E2F2B277  (result-gated ordered-test seeding)
  VT: VT-1B2063CC
  Risk: R-AB80E996
"""

from __future__ import annotations

from libs.pipeline.form_checkbox_seed import TAUGHT_CHECKBOX_SOURCE
from libs.pipeline.unresulted_test_guard import (
    is_unresulted_test_mention,
    line_containing,
    suppress_unresulted_test_mentions,
)

PANEL = """| Date specimen collected | Battery Headers | Result indicator |
| --- | --- | --- |
| FBC |  | Hb , WCC , Plts , MCV , Neut |  |  |
| LFT |  | ALT , Alk Phos , Bili , Alb , GGT |  |  |
| CRP |  |  | ESR |  |
| Diastolic dysfunction (XaYYs) | [DATE] - Ongoing |  |  |
| Hb | 118 g/L | 23.06.26 |
"""


def _ent(text: str, label: str, last: bool = False, **kw) -> dict:
    """Build an entity at an occurrence of *text* in the panel.

    ``last=True`` picks the final occurrence, which is how the tests reach the
    resulted ``| Hb | 118 g/L |`` row rather than the bare "Hb" printed as an
    analyte name inside the blank FBC row.
    """
    start = PANEL.rindex(text) if last else PANEL.index(text)
    ent = {
        "text": text,
        "label": label,
        "start": start,
        "end": start + len(text),
        "assertion": "present",
    }
    ent.update(kw)
    return ent


TICK_ROW = "| B4. Suspicious pelvic mass on pelvic ultrasound | [X] Yes [ ] No |\n"


def _ticked_scan(**kw) -> dict:
    """The scan a ticked B4 box says was carried out.

    Shaped exactly as ``seed_checkbox_entities`` emits it: the taught
    procedure sits on the tick's own span, so its offsets land on the
    checkbox row rather than on the words naming the scan.
    """
    start = TICK_ROW.index("B4.")
    ent = {
        "text": "B4.",
        "entity_text": "Pelvic echography",
        "lookup_term": "Pelvic echography",
        "concept_id": "24848001",
        "label": "procedure",
        "semantic_tag": "procedure",
        "start": start,
        "end": start + len("B4."),
        "assertion": "present",
        "__source": TAUGHT_CHECKBOX_SOURCE,
    }
    ent.update(kw)
    return ent


class TestATickedBoxIsNotABlankRow:
    """A tick is the result. Only a blank printed row says nothing.

    NHS 4568668417 had a pelvic ultrasound, and B4 is taught to record
    the scan as well as the mass it found. The scan was seeded and then
    dropped here, because a tick row is a table row carrying no number.
    An imaging procedure never carries a number, so requiring one asks
    for something that cannot exist and throws away the referrer's own
    statement that the scan was done.
    """

    def test_a_ticked_scan_is_not_treated_as_unresulted(self) -> None:
        assert not is_unresulted_test_mention(_ticked_scan(), TICK_ROW)

    def test_the_ticked_scan_survives_the_guard(self) -> None:
        kept, dropped = suppress_unresulted_test_mentions([_ticked_scan()], TICK_ROW)

        assert dropped == []
        assert [e["concept_id"] for e in kept] == ["24848001"]

    def test_a_blank_panel_row_is_still_dropped(self) -> None:
        """The exemption is the tick, not the table. Guard the original bug."""
        kept, dropped = suppress_unresulted_test_mentions(
            [_ent("FBC", "procedure")], PANEL
        )

        assert kept == []
        assert len(dropped) == 1

    def test_an_untaught_test_on_a_tick_row_is_still_judged(self) -> None:
        """Only a taught tick is exempt. An extractor guess is not."""
        guessed = _ticked_scan()
        guessed.pop("__source")

        assert is_unresulted_test_mention(guessed, TICK_ROW)


class TestLineContaining:
    def test_it_returns_the_row_the_span_sits_on(self) -> None:
        start = PANEL.index("FBC")
        line = line_containing(PANEL, start, start + 3)
        assert line.startswith("| FBC |")
        assert "LFT" not in line

    def test_it_handles_a_span_at_the_very_start(self) -> None:
        assert "Date specimen collected" in line_containing(PANEL, 0, 4)

    def test_it_survives_offsets_past_the_end(self) -> None:
        assert line_containing(PANEL, 10**6, 10**6 + 5) == ""


class TestSuppression:
    def test_a_battery_label_on_a_blank_row_is_dropped(self) -> None:
        kept, dropped = suppress_unresulted_test_mentions(
            [_ent("FBC", "procedure")], PANEL
        )

        assert kept == []
        assert len(dropped) == 1
        assert dropped[0]["text"] == "FBC"

    def test_every_blank_battery_row_from_the_real_form_is_dropped(self) -> None:
        ents = [
            _ent("FBC", "procedure"),
            _ent("LFT", "procedure"),
            _ent("CRP", "procedure"),
        ]

        kept, dropped = suppress_unresulted_test_mentions(ents, PANEL)

        assert kept == []
        assert {d["text"] for d in dropped} == {"FBC", "LFT", "CRP"}

    def test_the_reason_says_why_in_plain_english(self) -> None:
        _, dropped = suppress_unresulted_test_mentions(
            [_ent("FBC", "procedure")], PANEL
        )

        reason = dropped[0]["suppressed_reason"]
        assert "does not show a result" in reason.lower()
        assert "row" in reason.lower()


class TestWhatItMustNotTouch:
    def test_a_condition_on_a_blank_row_is_kept(self) -> None:
        """The row has no number, but diastolic dysfunction is real."""
        ent = _ent("Diastolic dysfunction", "clinical_finding")

        kept, dropped = suppress_unresulted_test_mentions([ent], PANEL)

        assert dropped == []
        assert len(kept) == 1

    def test_a_disorder_on_a_blank_row_is_kept(self) -> None:
        ent = _ent("Diastolic dysfunction", "disorder")

        kept, _ = suppress_unresulted_test_mentions([ent], PANEL)

        assert len(kept) == 1

    def test_a_requested_test_is_kept(self) -> None:
        """A blank row does support "we are asking for this"."""
        ent = _ent("FBC", "procedure", assertion="planned")

        kept, dropped = suppress_unresulted_test_mentions([ent], PANEL)

        assert dropped == []
        assert len(kept) == 1

    def test_a_resulted_row_is_kept(self) -> None:
        ent = _ent("Hb", "observable_entity", last=True)

        kept, dropped = suppress_unresulted_test_mentions([ent], PANEL)

        assert dropped == []
        assert len(kept) == 1

    def test_a_test_carrying_its_own_value_is_kept(self) -> None:
        """Blood pressure 140/80 is a measurement, wherever it was quoted."""
        ent = _ent("CRP", "observable_entity", value="12", unit="mg/L")

        kept, dropped = suppress_unresulted_test_mentions([ent], PANEL)

        assert dropped == []
        assert len(kept) == 1

    def test_historical_procedure_in_pmh_table_is_kept(self) -> None:
        """A past hysterectomy in a PMH table is not an unresulted blood test.

        Atlas: DI-0B907354 / VT-24D1E4F6
        """
        text = "| Past medical history | Notes |\n" "| Hysterectomy | performed |\n"
        start = text.index("Hysterectomy")
        ent = {
            "text": "Hysterectomy",
            "label": "procedure",
            "start": start,
            "end": start + len("Hysterectomy"),
            "assertion": "historical",
        }

        kept, dropped = suppress_unresulted_test_mentions([ent], text)

        assert dropped == []
        assert len(kept) == 1
        assert kept[0]["text"] == "Hysterectomy"

    def test_prose_is_never_touched(self) -> None:
        text = "Bloods were taken today and FBC was normal."
        ent = {
            "text": "FBC",
            "label": "procedure",
            "start": text.index("FBC"),
            "end": text.index("FBC") + 3,
            "assertion": "present",
        }

        kept, dropped = suppress_unresulted_test_mentions([ent], text)

        assert dropped == []
        assert len(kept) == 1

    def test_an_entity_with_no_offsets_is_kept(self) -> None:
        """Fail open on suppression: never drop what we cannot locate."""
        ent = {"text": "FBC", "label": "procedure", "assertion": "present"}

        kept, dropped = suppress_unresulted_test_mentions([ent], PANEL)

        assert dropped == []
        assert len(kept) == 1

    def test_order_of_the_survivors_is_preserved(self) -> None:
        ents = [
            _ent("Diastolic dysfunction", "clinical_finding"),
            _ent("FBC", "procedure"),
            _ent("Hb", "observable_entity", last=True),
        ]

        kept, _ = suppress_unresulted_test_mentions(ents, PANEL)

        assert [e["text"] for e in kept] == ["Diastolic dysfunction", "Hb"]

    def test_empty_input_is_fine(self) -> None:
        assert suppress_unresulted_test_mentions([], PANEL) == ([], [])
