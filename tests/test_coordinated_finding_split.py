"""VT: split coordinated findings so each span is one clinical fact.

Atlas trace:
  DI: DI-B5C78811
  DO: DO-728930A1
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-B5C78811")

Inbox phrases such as "no adnexal mass or free fluid" cannot be coded as
one surface form. The extractor (or a later layer) must cut them first.
"""

from __future__ import annotations

from libs.ner.coordinated_finding_split import split_coordinated_findings
from libs.pipeline.post_processing import run_post_processing_with_trace


def _ent(text: str, label: str = "finding") -> dict:
    return {
        "text": text,
        "label": label,
        "start": 0,
        "end": len(text),
        "assertion": "absent" if text.lower().startswith("no ") else "present",
    }


def test_splits_no_adnexal_mass_or_free_fluid() -> None:
    out = split_coordinated_findings([_ent("no adnexal mass or free fluid")])
    texts = [e["text"] for e in out]
    assert texts == ["no adnexal mass", "no free fluid"]


def test_splits_no_abnormalities_of_the_vagina_or_cervix() -> None:
    out = split_coordinated_findings(
        [_ent("no abnormalities of the vagina or cervix")]
    )
    texts = [e["text"] for e in out]
    assert texts == [
        "no abnormalities of the vagina",
        "no abnormalities of the cervix",
    ]


def test_splits_vaginal_itch_slash_dryness() -> None:
    out = split_coordinated_findings([_ent("vaginal itch/dryness")])
    texts = [e["text"] for e in out]
    assert texts == ["vaginal itch", "vaginal dryness"]


def test_splits_ues_and_calcium_panel() -> None:
    out = split_coordinated_findings(
        [_ent("UEs and Calcium", label="observable")]
    )
    texts = [e["text"] for e in out]
    assert texts == ["UEs", "Calcium"]


def test_does_not_split_pmb() -> None:
    out = split_coordinated_findings([_ent("postmenopausal bleeding")])
    assert [e["text"] for e in out] == ["postmenopausal bleeding"]


def test_does_not_split_endometrial_measurement() -> None:
    phrase = "endometrial thickness = 6.2mm"
    out = split_coordinated_findings([_ent(phrase, label="observable_entity")])
    assert [e["text"] for e in out] == [phrase]


def test_does_not_split_brand_product() -> None:
    phrase = "Mepore dressing 10cm x 11cm (Molnlycke Health Care Ltd)"
    out = split_coordinated_findings([_ent(phrase, label="product")])
    assert [e["text"] for e in out] == [phrase]


def test_does_not_split_long_sentence_with_or_and_short_tail() -> None:
    phrase = (
        "speculum examination revealed no abnormalities "
        "of the vagina or cervix"
    )
    out = split_coordinated_findings([_ent(phrase)])
    assert [e["text"] for e in out] == [phrase]


def test_post_processing_runs_coordinated_split_layer() -> None:
    entities = [_ent("no adnexal mass or free fluid")]
    processed, trace = run_post_processing_with_trace(
        "Scan: no adnexal mass or free fluid.",
        entities,
        enable_disorder_gate=False,
    )
    completed = [row for row in trace if row.get("status") == "completed"]
    by_id = {row["layer_id"]: row for row in completed}
    assert by_id["layer_1b"]["name"] == "Coordinated Finding Split"
    texts = [e["text"] for e in processed]
    assert "no adnexal mass" in texts
    assert "no free fluid" in texts
    assert "no adnexal mass or free fluid" not in texts
