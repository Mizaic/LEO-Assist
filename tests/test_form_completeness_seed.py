"""Seed completeness groups from a taught 2WW gynae letter.

Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E
"""

from __future__ import annotations

from libs.pipeline.form_completeness_seed import seed_completeness_groups
from libs.pipeline.form_section_splitter import detect_form_name, split_form_sections

SHERWOOD = """
Sherwood Forest Hospitals NHS Foundation Trust
URGENT SUSPECTED CANCER REFERRAL FOR SUSPECTED GYNAECOLOGICAL MALIGNANCY

Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ] Vagina [ ] Vulva [ ]
IF endometrium MUST TVUS. IF ovary MUST Ca125.

Section B: Signs/symptoms for 14-day rule criteria
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
B9. Suspicion of ovarian cancer | Yes [ ] No [ ]

PMB primary care pathway
Ultrasound arranged [ ] Yes

Patient awareness
Patient informed this is a suspected cancer referral [ ]

Section C: Further Clinical details
BMI: 20.2
Cognitive impairment Yes [ ] No [X]

Section D: Investigations performed
MANDATORY tests: FBC LFTs UEs Calcium
BLOODS DONE TODAY

Section E: PERFORMANCE STATUS
Clinical Frailty Scale 1. Very Fit [X]
Patient Fitness (ECOG STATUS): 0 [ ] 1 [X] 2 [ ]

Minimum Dataset
BP 140/80
HR 70
"""


def test_detect_form_name_from_clinical_title() -> None:
    name = detect_form_name(SHERWOOD)
    assert "gynaecolog" in name.lower() or "urgent suspected cancer" in name.lower()
    assert name != "Referral form"


def test_splitter_keeps_pmb_awareness_ecog_and_min_dataset() -> None:
    sections = split_form_sections(SHERWOOD)
    labels = " ".join(s["label"] for s in sections).lower()
    assert "pmb" in labels
    assert "awareness" in labels
    assert "ecog" in labels
    assert "minimum dataset" in labels
    dataset = next(s for s in sections if "minimum dataset" in s["label"].lower())
    assert dataset["section_type"] == "observable"


def test_splitter_uses_clinical_entity_text_for_cervix() -> None:
    sections = split_form_sections(SHERWOOD)
    section_a = next(s for s in sections if s["section_id"] == "A")
    cervix = next(i for i in section_a["items"] if "cervix" in i["pattern"].lower())
    assert cervix["entity_text"] == "Cervical cancer suspected"


def test_seed_completeness_has_one_of_sites_criteria_if_then_and_bloods() -> None:
    sections = split_form_sections(SHERWOOD)
    groups = seed_completeness_groups(SHERWOOD, sections)
    kinds = {g["name"].lower(): g["kind"] for g in groups}
    assert any(k == "one_of" for k in kinds.values())
    assert any(g["kind"] == "if_then" for g in groups)
    assert any(
        "tvus" in (g.get("then_group") or {}).get("name", "").lower() for g in groups
    )
    assert any(
        "ca125" in (g.get("then_group") or {}).get("name", "").lower() for g in groups
    )
    assert any(
        g["kind"] == "mandatory" and "blood" in g["name"].lower() for g in groups
    )
