"""PMB phrases must resolve to 76742009, not split codes.

Scan and letter text uses PMB, postmenopausal bleeding, or bleeding
after the menopause. Extraction must keep that as one finding.

Atlas: DI-00DFB149, DO-ABE2AE61, VT-E053BB7C.
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PROMPT = _ROOT / "libs/prompts/extraction_v1.py"
_ESCALATION = _ROOT / "libs/llm_client/escalation.py"
_FORM = _ROOT / "tests/fixtures/form_schema/sfh_gynae_2ww_template.json"


def test_extraction_prompt_keeps_pmb_as_one_finding() -> None:
    text = _PROMPT.read_text()
    assert "postmenopausal bleeding" in text.lower()
    assert "do not split" in text.lower()
    assert "PMB" in text


def test_escalation_prompt_prefers_pmb_single_code() -> None:
    text = _ESCALATION.read_text()
    assert "PMB" in text
    assert "76742009" in text or "postmenopausal bleeding" in text.lower()


def test_sfh_gynae_form_pmb_items_use_postmenopausal_bleeding() -> None:
    schema = json.loads(_FORM.read_text())
    texts = [
        str(item.get("entity_text") or "").lower()
        for section in schema.get("sections") or []
        for item in section.get("items") or []
    ]
    pmb_texts = [t for t in texts if "postmenopausal bleeding" in t or "pmb" in t]
    assert pmb_texts, "SFH gynae 2WW form must emit a PMB finding"
    assert any("postmenopausal bleeding" in t for t in pmb_texts)


def _concept_ids(entities: list[dict]) -> set[str]:
    found: set[str] = set()
    for ent in entities:
        for key in ("snomed_concept_id", "concept_id"):
            raw = ent.get(key)
            if raw:
                found.add(str(raw))
    return found


def _heavy_bleed_entity() -> dict:
    return {
        "text": "heavy vaginal bleeding",
        "label": "finding",
        "assertion": "present",
        "snomed_concept_id": "315224006",
    }


def _postmeno_state_entity() -> dict:
    return {
        "text": "postmenopausal state",
        "label": "finding",
        "assertion": "present",
        "snomed_concept_id": "76498008",
    }


def test_salvage_adds_pmb_when_menopause_and_heavy_pv_bleed() -> None:
    from libs.pipeline.pmb_salvage import salvage_pmb

    letter = "Menopause and amenorrhoea for 3 years. Heavy vaginal bleeding."
    out = salvage_pmb(letter, [_heavy_bleed_entity()])
    assert "76742009" in _concept_ids(out)


def test_salvage_adds_pmb_when_hrt_and_has_been_bleeding() -> None:
    from libs.pipeline.pmb_salvage import salvage_pmb

    letter = (
        "On HRT. Pelvic scan: the patient has been bleeding for the last 24 hours."
    )
    out = salvage_pmb(letter, [_postmeno_state_entity()])
    assert "76742009" in _concept_ids(out)


def test_salvage_adds_pmb_when_hrt_stop_and_worsening_bleed() -> None:
    from libs.pipeline.pmb_salvage import salvage_pmb

    letter = (
        "Bleeding has now settled since stopping HRT. "
        "Scan: worsening bleeding. Fibroid uterus."
    )
    out = salvage_pmb(letter, [{"text": "fibroid", "label": "finding"}])
    assert "76742009" in _concept_ids(out)


def test_salvage_does_not_invent_bleed_from_no_pvb() -> None:
    from libs.pipeline.pmb_salvage import salvage_pmb

    letter = "Postmenopausal. No PVB. No vaginal bleeding."
    out = salvage_pmb(letter, [_postmeno_state_entity()])
    assert "76742009" not in _concept_ids(out)


def test_post_process_wires_pmb_salvage_layer() -> None:
    from libs.pipeline.post_processing import run_post_processing_with_trace

    letter = "Menopause and amenorrhoea for 3 years. Heavy vaginal bleeding."
    entities, trace = run_post_processing_with_trace(
        letter, [_heavy_bleed_entity()], enable_disorder_gate=False
    )
    names = {row.get("name") for row in trace}
    assert "PMB Salvage" in names
    assert "76742009" in _concept_ids(entities)
