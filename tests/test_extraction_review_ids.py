"""VT -- NHS number and UBRN identifiers on paused extraction review.

Atlas trace: DI-4A012A59
"""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.pipeline.extraction_review_ids import (
    extract_review_identifiers,
    format_nhs_number,
    format_ubrn,
)
from libs.pipeline.extraction_review_store import (
    PersistReviewRequest,
    load_extraction_review_detail,
    persist_extraction_review_task,
)
from libs.pipeline.document_quality import score_document_quality


GYNAE_LETTER = """
Sherwood Forest Hospitals NHS Trust
Gynaecological Malignancy
NHS Number: 718 563 0207
Surname: Bennett  Forename: Anzhela
UBRN: 0000 4980 6289
Section A: Gynaecological Cancer type suspected
"""


def test_extracts_labelled_nhs_number_from_letter() -> None:
    ids = extract_review_identifiers(GYNAE_LETTER)
    assert ids.nhs_number == "7185630207"
    assert format_nhs_number(ids.nhs_number) == "718 563 0207"


def test_extracts_labelled_ubrn_from_letter() -> None:
    ids = extract_review_identifiers(GYNAE_LETTER)
    assert ids.ubrn == "000049806289"
    assert format_ubrn(ids.ubrn) == "0000 4980 6289"


def test_graph_values_win_over_letter_parse() -> None:
    ids = extract_review_identifiers(
        GYNAE_LETTER,
        graph_nhs_number="943 476 5919",
        graph_ubrn="111122223333",
    )
    assert ids.nhs_number == "9434765919"
    assert ids.ubrn == "111122223333"


def test_blank_letter_returns_empty_when_graph_missing() -> None:
    ids = extract_review_identifiers("")
    assert ids.nhs_number == ""
    assert ids.ubrn == ""


def test_review_detail_includes_nhs_and_ubrn() -> None:
    quality = score_document_quality(
        GYNAE_LETTER,
        few_shot_max_similarity=0.10,
        known_fingerprints={},
    )
    task = persist_extraction_review_task(
        PersistReviewRequest(
            run_id="run-1",
            patient_id="p1",
            plan_definition_id="pd-referral-assessment",
            step_id="act-ref-extract",
            next_action_id="act-ref-post-process",
            quality=quality,
            draft_entities=[{"text": "Cervix"}],
            source_text=GYNAE_LETTER,
        )
    )
    client = MagicMock()

    # Dispatch on the query rather than on call order. The detail view grew
    # extra lookups (validation case, receiving org and service) and a fixed
    # list of return values breaks on call count alone, which says nothing
    # about whether the identifiers came out right.
    def _run(cypher: str, **_params: object) -> list[dict[str, object]]:
        if "nhs_number" in cypher:
            return [{"nhs_number": "718 563 0207", "ubrn": "000049806289"}]
        if "extraction_review" in cypher.lower() or "task_id" in cypher:
            return [task]
        return []

    client.run.side_effect = _run
    store = MagicMock()
    store.load_accumulated_state.return_value = {"encounter_text": GYNAE_LETTER}
    detail = load_extraction_review_detail(client, task["task_id"], store=store)
    assert detail["nhs_number"] == "718 563 0207"
    assert detail["ubrn"] == "0000 4980 6289"
