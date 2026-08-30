"""SFH Kings Mill Breast Unit 2WW form -- taught schema must bind and normalise.

The gynae template is already taught. Breast Clinic referrals at RK5 /
service 117038 have no FormSchema, so extract pauses. This VT checks the
Breast Unit referral form:

- Ticked Section A 2WW boxes become findings.
- Several Yes [ ] boxes on one row pair in order (A3-A6).
- Unticked symptomatic boxes and mastalgia guidance do not become facts.
- A blank mandatory blood table is sealed.
- ECOG 0 ticked on one line becomes the performance-status finding.

Atlas trace: DI-5C9CA57B, DI-26546721
"""

from __future__ import annotations

import sys
from pathlib import Path

from libs.completeness.evaluator import evaluate_completeness_groups
from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER
from libs.pipeline.form_checkbox_seed import seed_checkbox_entities
from libs.pipeline.form_schema_normalizer import FormSchema, apply_schema_to_text
from libs.pipeline.form_schema_request import (
    build_sections_from_request,
    normalize_sections_for_request,
)
from libs.pipeline.form_section_hits import collect_section_hits

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from seed_sfh_breast_2ww_template import (  # noqa: E402
    FINGERPRINT,
    build_completeness_groups,
    build_payload,
)

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "form_schema" / "sfh_breast_2ww_template.json"
)

_SECTION_A_PACKED = (
    "A3. Nipple ulceration A4. Unilateral blood stained nipple discharge "
    "A5. Skin nodule A6. Distortion of breast | Yes [ ] Yes [ ] Yes [X] Yes [ ]"
)

_SECTION_A_A1 = (
    "A1. Newly presenting discrete hard lump/localised thickening, "
    "+fixation, + skin tethering | Yes [X]"
)

_ECOG = (
    "ECOG PERFORMANCE STATUS (Please tick one of the following statements "
    "about the patient); [X] 0 - Fully active, able to carry on all "
    "pre-disease and performance without restriction [ ] 1 - Restricted "
    "in physically strenuous activity but ambulatory"
)

_BLANK_FBC = "| FBC |  | Hb , WCC , Plts , MCV , Neut |  |  |  |"

_MASTALGIA = "PATIENTS WITH MASTALGIA TO BE MANAGED BY THE GP. Do not refer in."


def _schema() -> FormSchema:
    payload = build_payload()
    sections = build_sections_from_request(
        normalize_sections_for_request(payload["sections"])
    )
    return FormSchema(
        schema_id="breast-test",
        fingerprint=FINGERPRINT,
        form_name=payload["form_name"],
        sections=sections,
        created_by="test",
        organization_id=payload["organization_id"],
        service_id=payload["service_id"],
    )


def test_seed_payload_binds_kings_mill_breast_clinic() -> None:
    """The taught form is bound to RK5 Breast Clinic service 117038."""
    payload = build_payload()
    assert payload["organization_id"] == "RK5"
    assert payload["service_id"] == "117038"
    assert FINGERPRINT == "sfh-breast-2ww-v1"
    assert "Breast" in payload["form_name"]


def test_ticked_a1_hard_lump_becomes_a_finding() -> None:
    """A1 Yes [X] on its own row must survive as a discrete hard lump."""
    text = (
        "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
        f"| {_SECTION_A_A1} |\n"
    )
    schema = _schema()
    hits = collect_section_hits(schema, [text])
    assert any(h["checked"] and "hard lump" in h["entity_text"].lower() for h in hits)
    seeded = seed_checkbox_entities(text, schema)
    texts = {str(row.get("text") or "").lower() for row in seeded}
    assert any("hard lump" in item for item in texts)
    assert "a1." not in texts
    out = apply_schema_to_text(text, schema)
    assert NON_EXTRACTABLE_MARKER in out


def test_packed_a3_to_a6_pairs_boxes_in_order() -> None:
    """Four Yes boxes on one row: only the ticked A5 skin nodule is a fact."""
    text = (
        "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
        f"| {_SECTION_A_PACKED} |\n"
    )
    schema = _schema()
    checked = {
        h["entity_text"] for h in collect_section_hits(schema, [text]) if h["checked"]
    }
    assert any("Skin nodule" in label for label in checked)
    assert not any("Nipple ulceration" in label for label in checked)
    assert not any("blood stained" in label.lower() for label in checked)
    assert not any("Distortion of breast" in label for label in checked)


def test_blank_mandatory_blood_row_is_sealed() -> None:
    """An empty FBC row must not reach the model as a present test."""
    text = (
        "| Section D: Investigations performed |\n" "| MANDATORY |\n" f"{_BLANK_FBC}\n"
    )
    out = apply_schema_to_text(text, _schema())
    assert NON_EXTRACTABLE_MARKER in out
    assert "Complete blood count" not in out


def test_long_ecog_one_seeds_printed_restricted_phrase() -> None:
    """Box-before-score ECOG 1 must seed from the printed words, not a regex."""
    raw = (
        "ECOG PERFORMANCE STATUS (Please tick one of the following statements "
        "about the patient); [ ] 0 - Fully active, able to carry on all "
        "pre-disease and performance without restriction [X] 1 - Restricted "
        "in physically strenuous activity but ambulatory\n"
    )
    seeded = seed_checkbox_entities(raw, _schema())
    lookups = {str(row.get("lookup_term") or "").lower() for row in seeded}
    assert any("ecog 1" in text and "restricted" in text for text in lookups)
    assert not any("ecog 0" in text for text in lookups)


def test_ecog_zero_ticked_on_shared_line() -> None:
    """ECOG 0 [X] on a shared scale line is Fully active, not ECOG 1."""
    text = f"| Performance status |\n| {_ECOG} |\n"
    checked = [
        h["entity_text"].lower()
        for h in collect_section_hits(_schema(), [text])
        if h["checked"]
    ]
    assert any("ecog 0 fully active" in text for text in checked)
    assert not any("restricted in physically strenuous" in text for text in checked)


_SECTION_A_DOT_TWO = (
    "A.2 30 years and older with a discrete lump that persists "
    "post period/menopause | Yes [X]"
)

_SECTION_A_TWO = (
    "A2. 30 years and older with a discrete lump that persists "
    "post period/menopause | Yes [X]"
)

_INTRACTABLE = (
    "| Asymmetric nodularity persisting after menstruation [ ] | "
    "Intractable breast pain not responding to initial conservative "
    "measures (4-6 weeks regular NSAID or paracetamol as a minimum - "
    "see best practice guidance ) "
    "https://www.breastcancercare.org.uk/publications/benign-breast-"
    "conditions/breast-pain-bcc71 [X] |"
)


def test_a_dot_two_yes_seeds_persisting_lump() -> None:
    """Printed A.2 must seed. A regex pattern is not on the page."""
    raw = (
        "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
        f"| {_SECTION_A_DOT_TWO} |\n"
    )
    seeded = seed_checkbox_entities(raw, _schema())
    texts = {str(row.get("text") or "").lower() for row in seeded}
    assert any("discrete lump" in text and "persists" in text for text in texts)
    assert "a.2" not in texts
    assert r"a\.?2" not in texts


def test_a2_plain_yes_seeds_persisting_lump() -> None:
    """Printed A2. is a second literal, not a regex alternate."""
    raw = (
        "| Section A: Symptoms / Signs suggesting possible breast cancer |\n"
        f"| {_SECTION_A_TWO} |\n"
    )
    seeded = seed_checkbox_entities(raw, _schema())
    texts = {str(row.get("text") or "").lower() for row in seeded}
    assert any("discrete lump" in text and "persists" in text for text in texts)
    assert "a2." not in texts


def test_intractable_pain_tick_seeds_beside_guidance_url() -> None:
    """A ticked symptomatic pain box must seed even when a URL follows."""
    seeded = seed_checkbox_entities(_INTRACTABLE, _schema())
    lookups = {str(row.get("lookup_term") or "").lower() for row in seeded}
    assert "intractable breast pain" in lookups
    assert not any("asymmetric" in text for text in lookups)


def test_narrative_breast_lump_satisfies_two_ww_criterion() -> None:
    """A present breast lump fact meets the 2WW group when Section A is empty.

    Dry-run 000486229679: boxes unticked, exam lumps coded 89164003, NG12
    1.4.1 fired, completeness still asked for a Section A tick.
    """
    result = evaluate_completeness_groups(
        build_completeness_groups(),
        present_concept_ids={89164003},
        present_semantic_tags={"finding"},
        section_hits=[],
    )
    names = {row["name"] for row in result["matched_groups"]}
    assert "two_ww_criterion_required" in names, result
    assert result["complete"] is True


def test_empty_section_a_without_lump_is_still_incomplete() -> None:
    result = evaluate_completeness_groups(
        build_completeness_groups(),
        present_concept_ids=set(),
        present_semantic_tags=set(),
        section_hits=[],
    )
    missing = {row["name"] for row in result["missing_groups"]}
    assert "two_ww_criterion_required" in missing
    assert result["complete"] is False


def test_mastalgia_guidance_is_not_a_patient_fact() -> None:
    """Template advice must be sealed so it cannot become a finding."""
    text = (
        "| Section D: Symptoms/signs for referral by URGENT or Symptomatic "
        "route |\n"
        f"{_MASTALGIA}\n"
    )
    out = apply_schema_to_text(text, _schema())
    sealed = [
        line
        for line in out.splitlines()
        if "MASTALGIA" in line and NON_EXTRACTABLE_MARKER in line
    ]
    assert sealed, out
